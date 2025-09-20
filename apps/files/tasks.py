# apps/multiparser/tasks.py

import logging
import os
from pathlib import Path
import requests
from celery import shared_task, chain
from django.conf import settings
from django.db import transaction, DatabaseError
from elasticsearch import Elasticsearch
from tika import parser as tika_parser
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import json
import time

from .models import Document

# --- Logger ---
logger = logging.getLogger(__name__)

# --- Clients Setup ---
tika_parser.TikaClientOnly = True
tika_parser.TikaServerEndpoint = settings.TIKA_URL if hasattr(settings, 'TIKA_URL') else 'http://localhost:9998'

# Telegram maksimal fayl hajmi (49 MB)
TELEGRAM_MAX_FILE_SIZE_BYTES = 49 * 1024 * 1024

# Yangi: Maksimal ruxsat etilgan fayl hajmi (masalan, 500 MB)
MAX_FILE_SIZE_BYTES = 500 * 1024 * 1024


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


def get_es_client():
    es_url = getattr(settings, 'ES_URL', None)
    if not es_url:
        logger.error("Elasticsearch URL (ES_URL) is not set in settings.")
        return None
    try:
        return Elasticsearch(es_url)
    except Exception as e:
        logger.error(f"Elasticsearch client initialization failed: {e}")
        return None


try:
    import redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=60, max_retries=5,
             time_limit=7200)  # 2 soat limit, retry backoff 1 daqiqa
def download_task(self, document_id):
    """Alohida yuklab olish taski."""
    start_time = time.time()
    logger.info(f"[DOWNLOAD START] Hujjat ID: {document_id}")
    try:
        doc = Document.objects.select_related('product').get(id=document_id)
        if doc.download_status == 'completed':
            logger.info(f"[DOWNLOAD ALREADY COMPLETED] {document_id}")
            return document_id  # Keyingi task uchun ID qaytar

        doc.download_status = 'processing'
        doc.save(update_fields=['download_status'])

        # Yangi: Fayl hajmini oldindan tekshirish (HEAD request)
        session = make_retry_session()
        head_response = session.head(doc.parse_file_url, timeout=60)
        if 'Content-Length' in head_response.headers:
            file_size = int(head_response.headers['Content-Length'])
            if file_size > MAX_FILE_SIZE_BYTES:
                doc.download_status = 'skipped_too_large'
                doc.save(update_fields=['download_status'])
                logger.warning(f"[DOWNLOAD SKIPPED] Fayl juda katta: {file_size} bytes, ID: {document_id}")
                return document_id  # Keyingi bosqichlarga o'tkazib yuborish uchun

        file_full_path_str = str(Path(settings.MEDIA_ROOT) / f"downloads/{doc.id}{Path(doc.parse_file_url).suffix}")
        Path(file_full_path_str).parent.mkdir(parents=True, exist_ok=True)

        with session.get(doc.parse_file_url, stream=True, timeout=1800) as r:  # 30 daqiqa timeout
            r.raise_for_status()
            downloaded_size = 0
            with open(file_full_path_str, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        if downloaded_size % (10 * 1024 * 1024) == 0:  # Har 10 MB da log
                            logger.info(
                                f"[DOWNLOAD PROGRESS] {document_id}: {downloaded_size / 1024 / 1024:.2f} MB yuklandi")

        doc.file_path = file_full_path_str
        doc.download_status = 'completed'
        doc.save()
        logger.info(f"[DOWNLOAD SUCCESS] {document_id} | Vaqt: {time.time() - start_time:.2f}s")
        return document_id
    except Exception as e:
        doc.download_status = 'failed'
        doc.save(update_fields=['download_status'])
        logger.error(f"[DOWNLOAD FAIL] {document_id}: {e}")
        raise


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=60, max_retries=5, time_limit=7200)
def parse_task(self, document_id):
    """Alohida parse taski."""
    start_time = time.time()
    logger.info(f"[PARSE START] Hujjat ID: {document_id}")
    try:
        doc = Document.objects.select_related('product').get(id=document_id)
        if doc.parse_status == 'completed' or doc.download_status != 'completed':
            logger.info(f"[PARSE SKIP] {document_id} (allaqachon yoki yuklanmagan)")
            return document_id

        doc.parse_status = 'processing'
        doc.save(update_fields=['parse_status'])

        if not os.path.exists(doc.file_path):
            raise FileNotFoundError(f"Fayl topilmadi: {doc.file_path}")

        # Yangi: Tika uchun timeout oshirish
        parsed = tika_parser.from_file(doc.file_path, requestOptions={'timeout': 1800})
        content = parsed.get("content", "").strip() if parsed else ""

        with transaction.atomic():
            product = doc.product
            product.parsed_content = content
            product.save(update_fields=['parsed_content'])
            doc.parse_status = 'completed'
            doc.save()

        logger.info(f"[PARSE SUCCESS] {document_id} | Vaqt: {time.time() - start_time:.2f}s")
        return document_id
    except Exception as e:
        doc.parse_status = 'failed'
        doc.save(update_fields=['parse_status'])
        logger.error(f"[PARSE FAIL] {document_id}: {e}")
        raise


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=60, max_retries=5, time_limit=7200)
def index_task(self, document_id):
    """Alohida indekslash taski."""
    start_time = time.time()
    logger.info(f"[INDEX START] Hujjat ID: {document_id}")
    try:
        doc = Document.objects.select_related('product').get(id=document_id)
        if doc.index_status == 'completed' or doc.parse_status != 'completed':
            logger.info(f"[INDEX SKIP] {document_id}")
            return document_id

        doc.index_status = 'processing'
        doc.save(update_fields=['index_status'])

        es_client = get_es_client()
        es_index = getattr(settings, 'ES_INDEX', None)
        if es_client is None or not es_index:
            raise Exception("Elasticsearch sozlanmagan (ES_URL / ES_INDEX).")

        product = doc.product
        body = {
            "title": product.title,
            "slug": product.slug,
            "parsed_content": product.parsed_content,
            "document_id": str(doc.id),
        }
        es_client.index(index=es_index, id=str(doc.id), document=body)
        doc.index_status = 'completed'
        doc.save()

        logger.info(f"[INDEX SUCCESS] {document_id} | Vaqt: {time.time() - start_time:.2f}s")
        return document_id
    except Exception as e:
        doc.index_status = 'failed'
        doc.save(update_fields=['index_status'])
        logger.error(f"[INDEX FAIL] {document_id}: {e}")
        raise


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=60, max_retries=5, time_limit=7200)
def telegram_task(self, document_id):
    """Alohida Telegram yuborish taski."""
    start_time = time.time()
    logger.info(f"[TELEGRAM START] Hujjat ID: {document_id}")
    try:
        doc = Document.objects.select_related('product').get(id=document_id)
        if doc.telegram_status in ['completed', 'skipped'] or doc.index_status != 'completed':
            logger.info(f"[TELEGRAM SKIP] {document_id}")
            return document_id

        doc.telegram_status = 'processing'
        doc.save(update_fields=['telegram_status'])

        if not doc.file_path or not os.path.exists(doc.file_path):
            doc.telegram_status = 'skipped'
            doc.save(update_fields=['telegram_status'])
            logger.warning(f"[TELEGRAM SKIPPED] Fayl yo'q: {doc.file_path}")
            return document_id

        file_size = os.path.getsize(doc.file_path)
        if file_size > TELEGRAM_MAX_FILE_SIZE_BYTES:
            doc.telegram_status = 'skipped'
            doc.save(update_fields=['telegram_status'])
            logger.warning(f"[TELEGRAM SKIPPED] Fayl katta: {file_size} bytes, ID: {document_id}")
            return document_id

        json_data_str = json.dumps(doc.json_data, ensure_ascii=False, indent=2) if doc.json_data else '{}'
        json_data_str = json_data_str.replace('`', '\u200b`')
        static_caption = (
            f"*{doc.product.title}*\n"
            f"ID: `{doc.id}`\n"
            f"URL: {doc.parse_file_url}\n"
            f"Slug: `{doc.product.slug}`\n"
            f"\n*JSON:*\n```"
        )
        closing = "\n```"
        max_caption_len = 1024
        available_json_len = max_caption_len - len(static_caption) - len(closing)
        if len(json_data_str) > available_json_len:
            json_data_str = json_data_str[:available_json_len - 10] + '\n...'
        caption = static_caption + json_data_str + closing
        if len(caption) > 1024:
            truncated = caption[:1000].rstrip()
            if not truncated.endswith('```'):
                truncated += '\n...\n```'
            caption = truncated

        url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendDocument"
        max_telegram_retries = 5
        session = make_retry_session()
        for attempt in range(max_telegram_retries):
            with open(doc.file_path, "rb") as f:
                files = {"document": (Path(doc.file_path).name, f)}
                data = {"chat_id": settings.CHANNEL_ID, "caption": caption, "parse_mode": "Markdown"}
                response = session.post(url, files=files, data=data, timeout=1800)  # 30 daqiqa timeout
            resp_data = response.json()
            if resp_data.get("ok"):
                doc.telegram_file_id = resp_data["result"]["document"]["file_id"]
                doc.telegram_status = 'completed'
                doc.save()
                logger.info(f"[TELEGRAM SUCCESS] {document_id} | Vaqt: {time.time() - start_time:.2f}s")
                return document_id
            elif resp_data.get("error_code") == 429 and "retry_after" in resp_data.get("parameters", {}):
                retry_after = int(resp_data["parameters"]["retry_after"])
                logger.warning(f"[TELEGRAM RATE LIMIT] {document_id}, {retry_after}s kutamiz...")
                time.sleep(retry_after)
                continue
            else:
                raise Exception(f"Telegram API xatosi: {resp_data.get('description')}")

        doc.telegram_status = 'failed'
        doc.save(update_fields=['telegram_status'])
        logger.error(f"[TELEGRAM FAIL] 5 urinish muvaffaqiyatsiz: {document_id}")
        raise Exception("Telegram yuborish muvaffaqiyatsiz (5 urinish)")
    except Exception as e:
        doc.telegram_status = 'failed'
        doc.save(update_fields=['telegram_status'])
        logger.error(f"[TELEGRAM FAIL] {document_id}: {e}")
        raise


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=60, max_retries=5, time_limit=7200)
def delete_task(self, document_id):
    """Alohida o'chirish taski."""
    start_time = time.time()
    logger.info(f"[DELETE START] Hujjat ID: {document_id}")
    try:
        doc = Document.objects.get(id=document_id)
        if doc.delete_status == 'completed' or doc.telegram_status not in ['completed', 'skipped']:
            logger.info(f"[DELETE SKIP] {document_id}")
            return

        doc.delete_status = 'processing'
        doc.save(update_fields=['delete_status'])

        if doc.file_path and os.path.exists(doc.file_path):
            os.remove(doc.file_path)
            doc.file_path = None

        doc.delete_status = 'completed'
        doc.pipeline_running = False  # Pipeline tugadi
        doc.save()
        logger.info(f"[DELETE SUCCESS] {document_id} | Vaqt: {time.time() - start_time:.2f}s")
    except Exception as e:
        doc.delete_status = 'failed'
        doc.pipeline_running = False  # Pipeline xatoligi, qayta urinish uchun ochiq qoldirish
        doc.save(update_fields=['delete_status', 'pipeline_running'])
        logger.error(f"[DELETE FAIL] {document_id}: {e}")
        raise


@shared_task(bind=True)
def process_document_pipeline(self, document_id):
    """
    To'liq pipeline ni chain orqali chaqirish.
    Har bir bosqich alohida task bo'lib, o'z retry va timeoutlari bor.
    Lockdan foydalanmaymiz, chunki alohida tasklar avtomatik boshqariladi.
    """
    logger.info(f"--- [PIPELINE START] Hujjat ID: {document_id} ---")
    try:
        doc = Document.objects.get(id=document_id)
        # Pipeline_running=True bo'lsa ham davom etamiz, chunki dparse command tomonidan 
        # qasddan ishga tushirilgan
        logger.info(f"[PIPELINE CONTINUE] {document_id} pipeline davom etmoqda")

        # Chain yaratish
        pipeline_chain = chain(
            download_task.s(document_id),
            parse_task.s(),
            index_task.s(),
            telegram_task.s(),
            delete_task.s()
        )
        pipeline_chain.apply_async()

        logger.info(f"--- [PIPELINE INITIATED] Hujjat ID: {document_id} ---")
    except Exception as e:
        doc.pipeline_running = False
        doc.save(update_fields=['pipeline_running'])
        logger.error(f"[PIPELINE INIT FAIL] {document_id}: {e}")
    # Muvaffaqiyatli tugash delete_task da yoki xatolarda avtomatik retry bo'ladi