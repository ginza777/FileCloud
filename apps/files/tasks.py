# apps/multiparser/tasks.py

import logging
import os
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

from .models import Document

# --- Logger ---
logger = logging.getLogger(__name__)

# --- Clients Setup ---
tika_parser.TikaClientOnly = True
tika_parser.TikaServerEndpoint = settings.TIKA_URL if hasattr(settings, 'TIKA_URL') else 'http://localhost:9998'

# Telegramning maksimal fayl hajmi (49 MB)
TELEGRAM_MAX_FILE_SIZE_BYTES = 49 * 1024 * 1024


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


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=10, max_retries=3)
def process_document_pipeline(self, document_id):
    """
    Hujjatni qayta ishlashning to'liq va xatolarga bardoshli zanjiri.
    Har bir qadam o'zidan oldingisi muvaffaqiyatli bo'lsa ishlaydi.
    1. Yuklash -> 2. Parse -> 3. Indekslash -> 4. Telegram -> 5. O'chirish
    """
    logger.info(f"--- [PIPELINE START] Hujjat ID: {document_id} ---")

    try:
        doc = Document.objects.select_related('product').get(id=document_id)
    except Document.DoesNotExist:
        logger.error(f"[PIPELINE FAIL] Hujjat {document_id} bazada topilmadi.")
        return

    file_full_path_str = str(Path(settings.MEDIA_ROOT) / f"downloads/{doc.id}{Path(doc.parse_file_url).suffix}")

    # ================= 1. FAYLNI YUKLASH =================
    if doc.download_status != 'completed':
        logger.info(f"[1. Yuklash] Boshlandi: {document_id}")
        doc.download_status = 'processing'
        doc.save(update_fields=['download_status'])
        try:
            Path(file_full_path_str).parent.mkdir(parents=True, exist_ok=True)
            with make_retry_session().get(doc.parse_file_url, stream=True, timeout=180) as r:
                r.raise_for_status()
                with open(file_full_path_str, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192): f.write(chunk)

            doc.file_path = file_full_path_str
            doc.download_status = 'completed'
            doc.save(update_fields=['file_path', 'download_status'])
            logger.info(f"[1. Yuklash] Muvaffaqiyatli: {document_id}")
        except Exception as e:
            doc.download_status = 'failed'
            doc.save(update_fields=['download_status'])
            logger.error(f"[PIPELINE FAIL - Yuklash] {document_id}: {e}")
            raise self.retry(exc=e)

    # ================= 2. TIKA ORQALI PARSE QILISH =================
    doc.refresh_from_db()
    if doc.download_status == 'completed' and doc.parse_status != 'completed':
        logger.info(f"[2. Parse] Boshlandi: {document_id}")
        doc.parse_status = 'processing'
        doc.save(update_fields=['parse_status'])
        try:
            parsed = tika_parser.from_file(doc.file_path)
            content = parsed.get("content", "").strip() if parsed else ""

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
            raise self.retry(exc=e)

    # ================= 3. ELASTICSEARCH'GA INDEKSLASH =================
    doc.refresh_from_db()
    if doc.parse_status == 'completed' and doc.index_status != 'completed':
        logger.info(f"[3. Indekslash] Boshlandi: {document_id}")
        doc.index_status = 'processing'
        doc.save(update_fields=['index_status'])
        try:
            es_client = get_es_client()
            es_index = getattr(settings, 'ES_INDEX', None)
            if es_client is None or not es_index:
                raise Exception("Elasticsearch client or index is not configured. Please set ES_URL and ES_INDEX in your Django settings.")
            product = doc.product
            body = {
                "title": product.title,
                "slug": product.slug,
                "parsed_content": product.parsed_content,
                "document_id": str(doc.id),
            }
            es_client.index(index=es_index, id=str(doc.id), document=body)
            doc.index_status = 'completed'
            doc.save(update_fields=['index_status'])
            logger.info(f"[3. Indekslash] Muvaffaqiyatli: {document_id}")
        except Exception as e:
            doc.index_status = 'failed'
            doc.save(update_fields=['index_status'])
            logger.error(f"[PIPELINE FAIL - Indekslash] {document_id}: {e}")
            raise self.retry(exc=e)

    # ================= 4. TELEGRAM'GA YUBORISH =================
    doc.refresh_from_db()
    if doc.index_status == 'completed' and doc.telegram_status not in ['completed', 'skipped']:
        logger.info(f"[4. Telegram] Boshlandi: {document_id}")
        doc.telegram_status = 'processing'
        doc.save(update_fields=['telegram_status'])
        try:
            file_size = os.path.getsize(doc.file_path)
            if file_size > TELEGRAM_MAX_FILE_SIZE_BYTES:
                doc.telegram_status = "skipped"
                doc.save(update_fields=['telegram_status'])
                logger.warning(f"[4. Telegram] Fayl hajmi katta bo'lgani uchun o'tkazib yuborildi: {file_size} bytes")
            else:
                # Build caption with document info
                json_data_str = json.dumps(doc.json_data, ensure_ascii=False, indent=2) if doc.json_data else '{}'
                # Escape backticks in JSON to avoid breaking Markdown
                json_data_str = json_data_str.replace('`', '\u200b`')
                # Compose the static part of the caption
                static_caption = (
                    f"*{doc.product.title}*\n"
                    f"ID: `{doc.id}`\n"
                    f"URL: {doc.parse_file_url}\n"
                    f"Slug: `{doc.product.slug}`\n"
                    f"\n*JSON:*\n```")
                closing = "\n```"
                # Telegram caption limit is 1024 chars
                max_caption_len = 1024
                # Calculate how much space is left for JSON
                available_json_len = max_caption_len - len(static_caption) - len(closing)
                if len(json_data_str) > available_json_len:
                    json_data_str = json_data_str[:available_json_len-10] + '\n...'
                caption = static_caption + json_data_str + closing

                # Telegram caption limit is 1024 chars
                if len(caption) > 1024:
                    # Truncate and close code block if needed
                    truncated = caption[:1000].rstrip()
                    # Ensure we don't break Markdown formatting
                    if not truncated.endswith('```'):
                        truncated += '\n...\n```'
                    caption = truncated

                url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendDocument"
                max_telegram_retries = 5
                telegram_attempt = 0
                while telegram_attempt < max_telegram_retries:
                    with open(doc.file_path, "rb") as f:
                        files = {"document": (Path(doc.file_path).name, f)}
                        data = {"chat_id": settings.CHANNEL_ID, "caption": caption, "parse_mode": "Markdown"}
                        response = make_retry_session().post(url, files=files, data=data, timeout=180)
                    resp_data = response.json()
                    if resp_data.get("ok"):
                        doc.telegram_file_id = resp_data["result"]["document"]["file_id"]
                        doc.telegram_status = 'completed'
                        doc.save(update_fields=['telegram_file_id', 'telegram_status'])
                        logger.info(f"[4. Telegram] Muvaffaqiyatli yuborildi: {document_id}")
                        break
                    elif resp_data.get("error_code") == 429 and "retry_after" in resp_data:
                        retry_after = int(resp_data["retry_after"])
                        logger.warning(f"[4. Telegram] Too Many Requests: {document_id}, retrying after {retry_after} seconds...")
                        time.sleep(retry_after)
                        telegram_attempt += 1
                        continue
                    else:
                        raise Exception(f"Telegram API xatosi: {resp_data.get('description')}")
                else:
                    # Agar 5 marta ham muvaffaqiyatli bo'lmasa, failed deb belgilash
                    doc.telegram_status = 'failed'
                    doc.save(update_fields=['telegram_status'])
                    logger.error(f"[PIPELINE FAIL - Telegram] {document_id}: Too Many Requests or other error after {max_telegram_retries} attempts.")
                    raise Exception(f"Telegram API xatosi: Too Many Requests or other error after {max_telegram_retries} attempts.")
        except Exception as e:
            doc.telegram_status = 'failed'
            doc.save(update_fields=['telegram_status'])
            logger.error(f"[PIPELINE FAIL - Telegram] {document_id}: {e}")
            raise self.retry(exc=e)

    # ================= 5. LOKAL FAYLNI O'CHIRISH =================
    doc.refresh_from_db()
    if doc.telegram_status in ['completed', 'skipped'] and doc.delete_status != 'completed':
        logger.info(f"[5. O'chirish] Boshlandi: {document_id}")
        doc.delete_status = 'processing'
        doc.save(update_fields=['delete_status'])
        try:
            if doc.file_path and os.path.exists(doc.file_path):
                os.remove(doc.file_path)
                doc.file_path = None
                doc.delete_status = 'completed'
                doc.save(update_fields=['file_path', 'delete_status'])
                logger.info(f"[5. O'chirish] Fayl muvaffaqiyatli o'chirildi: {document_id}")
            else:
                doc.delete_status = 'completed'  # Fayl yo'q bo'lsa ham tugatildi deb hisoblaymiz
                doc.save(update_fields=['delete_status'])
        except Exception as e:
            doc.delete_status = 'failed'
            doc.save(update_fields=['delete_status'])
            logger.error(f"[PIPELINE FAIL - O'chirish] {document_id}: {e}")
            raise self.retry(exc=e)

    logger.info(f"--- [PIPELINE SUCCESS] ✅ Hujjat ID: {document_id} ---")