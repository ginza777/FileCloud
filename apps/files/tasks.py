# apps/multiparser/tasks.py

import logging
import os
import tempfile
from pathlib import Path
import requests
from celery import shared_task
from django.conf import settings
from django.db import transaction
from elasticsearch import Elasticsearch
from tika import parser as tika_parser
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import json
import time
import threading
from datetime import datetime, timedelta

from .models import Document

# --- Logger ---
logger = logging.getLogger(__name__)

# --- Clients Setup ---
tika_parser.TikaClientOnly = True
tika_parser.TikaServerEndpoint = getattr(settings, 'TIKA_URL', 'http://tika:9998')
tika_parser.TikaServerClasspath = None

# Telegramning maksimal fayl hajmi (49 MB)
TELEGRAM_MAX_FILE_SIZE_BYTES = 49 * 1024 * 1024

# Telegram rate limiting uchun global lock
telegram_lock = threading.Lock()
last_telegram_send = None


def make_retry_session():
    """Qayta urinishlar bilan mustahkam HTTP session yaratadi."""
    session = requests.Session()
    retry = Retry(
        total=5, read=5, connect=5, backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def wait_for_telegram_rate_limit():
    """Telegram rate limiting uchun kutish funksiyasi."""
    global last_telegram_send
    with telegram_lock:
        if last_telegram_send is not None:
            time_since_last = datetime.now() - last_telegram_send
            min_interval = timedelta(seconds=10)
            if time_since_last < min_interval:
                wait_time = (min_interval - time_since_last).total_seconds()
                logger.info(f"Telegram rate limit uchun {wait_time:.2f} soniya kutamiz...")
                time.sleep(wait_time)
        last_telegram_send = datetime.now()


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=20, max_retries=3)
def process_document_pipeline(self, document_id):
    """
    To'liq pipeline. Hujjatni yuklaydi, parse qiladi, indekslaydi, yuboradi va oxirida o'chiradi.
    """
    logger.info(f"--- [PIPELINE START] Hujjat ID: {document_id} ---")
    file_path = None  # Fayl yo'lini saqlash uchun

    try:
        doc = Document.objects.select_related('product').get(id=document_id)

        if not doc.pipeline_running:
            logger.warning(f"[PIPELINE SKIP] {document_id} lock yo'q.")
            return

        if doc.completed:
            logger.info(f"[PIPELINE ALREADY COMPLETED] {document_id}")
            Document.objects.filter(id=document_id).update(pipeline_running=False)
            return

        # Fayl yo'lini yaratish
        file_extension = Path(doc.parse_file_url).suffix
        media_dir = os.path.join(settings.MEDIA_ROOT, 'downloads')
        os.makedirs(media_dir, exist_ok=True)
        file_path = os.path.join(media_dir, f"{doc.id}{file_extension}")

        # 1. DOWNLOAD
        if doc.download_status != 'completed':
            logger.info(f"[1. Yuklash] Boshlandi: {document_id}")
            doc.download_status = 'processing'
            doc.save(update_fields=['download_status'])
            try:
                with make_retry_session().get(doc.parse_file_url, stream=True, timeout=180) as r:
                    r.raise_for_status()
                    with open(file_path, "wb") as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            f.write(chunk)
                doc.download_status = 'completed'
                doc.save(update_fields=['download_status'])
                logger.info(f"[1. Yuklash] Muvaffaqiyatli: {document_id}")
            except Exception as e:
                doc.download_status = 'failed'
                doc.save(update_fields=['download_status'])
                logger.error(f"[PIPELINE FAIL - Yuklash] {document_id}: {e}")
                raise

        doc.refresh_from_db()
        # 2. PARSE
        if doc.download_status == 'completed' and doc.parse_status != 'completed':
            logger.info(f"[2. Parse] Boshlandi: {document_id}")
            doc.parse_status = 'processing'
            doc.save(update_fields=['parse_status'])

            if not os.path.exists(file_path):
                # Agar fayl topilmasa, bu jiddiy xato. Vazifani qayta urinish uchun exception chaqiramiz.
                logger.error(f"[PIPELINE FAIL - Parse] Fayl topilmadi (qayta uriniladi): {file_path}")
                raise FileNotFoundError(f"Fayl topilmadi: {file_path}")

            try:
                parsed = tika_parser.from_file(file_path)
                content = (parsed.get("content") or "").strip()
                with transaction.atomic():
                    product = doc.product
                    product.parsed_content = content
                    product.save(update_fields=['parsed_content'])
                    doc.parse_status = 'completed'
                    doc.save(update_fields=['parse_status'])
                logger.info(f"[2. Parse] Muvaffaqiyatli: {document_id}")
            except Exception as e:
                doc.parse_status = 'failed'
                doc.save(update_fields=['parse_status'])
                logger.error(f"[PIPELINE FAIL - Parse] {document_id}: {e}")
                raise

        doc.refresh_from_db()
        # 3. INDEX
        if doc.parse_status == 'completed' and doc.index_status != 'completed':
            logger.info(f"[3. Indekslash] Boshlandi: {document_id}")
            doc.index_status = 'processing'
            doc.save(update_fields=['index_status'])
            try:
                es_client = Elasticsearch(settings.ES_URL)
                product = doc.product
                body = {"title": product.title, "slug": product.slug, "parsed_content": product.parsed_content,
                        "document_id": str(doc.id)}
                es_client.index(index=settings.ES_INDEX, id=str(doc.id), document=body)
                doc.index_status = 'completed'
                doc.save(update_fields=['index_status'])
                logger.info(f"[3. Indekslash] Muvaffaqiyatli: {document_id}")
            except Exception as e:
                doc.index_status = 'failed'
                doc.save(update_fields=['index_status'])
                logger.error(f"[PIPELINE FAIL - Indekslash] {document_id}: {e}")
                raise

        doc.refresh_from_db()
        # 4. TELEGRAM
        if doc.index_status == 'completed' and doc.telegram_status != 'completed':
            logger.info(f"[4. Telegram] Boshlandi: {document_id}")
            doc.telegram_status = 'processing'
            doc.save(update_fields=['telegram_status'])
            try:
                if not os.path.exists(file_path):
                    raise FileNotFoundError(f"Telegramga yuborish uchun fayl topilmadi: {file_path}")

                if os.path.getsize(file_path) > TELEGRAM_MAX_FILE_SIZE_BYTES:
                    doc.telegram_status = 'skipped'
                    logger.warning(f"[4. Telegram] Fayl hajmi katta, o'tkazib yuborildi: {doc.id}")
                else:
                    wait_for_telegram_rate_limit()
                    caption = f"*{doc.product.title}*\n\nID: `{doc.id}`"
                    url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendDocument"
                    with open(file_path, "rb") as f:
                        files = {"document": (Path(file_path).name, f)}
                        data = {"chat_id": settings.CHANNEL_ID, "caption": caption, "parse_mode": "Markdown"}
                        response = make_retry_session().post(url, files=files, data=data, timeout=180)
                    resp_data = response.json()
                    if resp_data.get("ok"):
                        doc.telegram_file_id = resp_data["result"]["document"]["file_id"]
                        doc.telegram_status = 'completed'
                        logger.info(f"[4. Telegram] Muvaffaqiyatli: {document_id}")
                    else:
                        raise Exception(f"Telegram API xatosi: {resp_data.get('description')}")
                doc.save(update_fields=['telegram_file_id', 'telegram_status'])
            except Exception as e:
                doc.telegram_status = 'failed'
                doc.save(update_fields=['telegram_status'])
                logger.error(f"[PIPELINE FAIL - Telegram] {document_id}: {e}")
                raise

        # Pipeline muvaffaqiyatli tugadi
        doc.refresh_from_db()
        doc.pipeline_running = False
        doc.save()  # Bu `completed` statusini avtomatik yangilaydi
        logger.info(f"--- [PIPELINE SUCCESS] ✅ Hujjat ID: {document_id} ---")

    except Exception as pipeline_error:
        # Agar yana retry bo'lsa, lockni yechmaymiz
        if self.request.retries >= self.max_retries:
            Document.objects.filter(id=document_id).update(pipeline_running=False)
            logger.error(f"[PIPELINE FINAL FAIL] {document_id}: {pipeline_error}")
        raise  # Celery'ning qayta urinish mexanizmini ishga tushirish uchun

    finally:
        # 5. FAYLNI O'CHIRISH
        # Bu blok vazifa muvaffaqiyatli tugasa ham, xatolik bilan tugasa ham (qayta urinishlardan so'ng) ishlaydi.
        # Faqatgina pipeline tugagan (completed=True) yoki oxirgi urinishda xatolikka uchragan (final fail) hujjatlarning fayllarini o'chiramiz.
        try:
            doc.refresh_from_db()
            is_final_state = doc.completed or (self.request.retries >= self.max_retries)

            if is_final_state and file_path and os.path.exists(file_path):
                os.remove(file_path)
                doc.delete_status = 'completed'
                doc.save(update_fields=['delete_status'])
                logger.info(f"[DELETE] Fayl o'chirildi: {file_path}")
        except Exception as delete_error:
            logger.error(f"[DELETE FAIL] Faylni o'chirishda xato: {document_id} - {delete_error}")

# Kerak bo'lmagan vazifalar olib tashlandi. Misol uchun:
# delete_file_after_delay
# cleanup_old_files_task
# cleanup_old_temp_files_task