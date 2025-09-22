# apps/multiparser/tasks.py

import logging
import os
import tempfile
import shutil
from pathlib import Path
import requests
from celery import shared_task
from django.conf import settings
from django.db import transaction, DatabaseError
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
tika_parser.TikaServerEndpoint = settings.TIKA_URL if hasattr(settings, 'TIKA_URL') else 'http://localhost:9998'

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
            # Telegram uchun minimal 1 soniya oraliq
            min_interval = timedelta(seconds=1)
            if time_since_last < min_interval:
                wait_time = (min_interval - time_since_last).total_seconds()
                logger.info(f"Telegram rate limit uchun {wait_time:.2f} soniya kutamiz...")
                time.sleep(wait_time)
        
        last_telegram_send = datetime.now()


def get_temp_file_path(document_id, file_extension):
    """Vaqtincha fayl yo'li yaratadi."""
    temp_dir = getattr(settings, 'TEMP_DIR', None)
    if temp_dir:
        try:
            # Papka yaratish - bir nechta usul bilan
            try:
                os.makedirs(temp_dir, exist_ok=True, mode=0o777)
            except PermissionError:
                try:
                    os.makedirs(temp_dir, exist_ok=True, mode=0o755)
                except PermissionError:
                    try:
                        os.makedirs(temp_dir, exist_ok=True)
                        os.chmod(temp_dir, 0o777)
                    except PermissionError:
                        # Agar hali ham ishlamasa, system temp dir ishlatamiz
                        raise PermissionError("Custom temp dir yaratishda xato")
            
            # Ruxsatlarni tekshirish
            if not os.access(temp_dir, os.W_OK):
                try:
                    os.chmod(temp_dir, 0o777)
                except PermissionError:
                    raise PermissionError("Temp dir ruxsatlarini o'zgartirishda xato")
            
            temp_file_path = os.path.join(temp_dir, f"temp_{document_id}{file_extension}")
            logger.info(f"Vaqtincha fayl yo'li yaratildi: {temp_file_path}")
            return temp_file_path
            
        except PermissionError as e:
            logger.warning(f"TEMP_DIR da ruxsat xatosi: {e}")
            # Fallback: system temp dir ishlatamiz
            temp_file = tempfile.NamedTemporaryFile(
                suffix=file_extension, 
                prefix=f"doc_{document_id}_", 
                delete=False
            )
            temp_file.close()
            logger.info(f"System temp dir ishlatildi: {temp_file.name}")
            return temp_file.name
    else:
        # Agar TEMP_DIR sozlanmagan bo'lsa, system temp dir ishlatamiz
        temp_file = tempfile.NamedTemporaryFile(
            suffix=file_extension, 
            prefix=f"doc_{document_id}_", 
            delete=False
        )
        temp_file.close()
        logger.info(f"System temp dir ishlatildi: {temp_file.name}")
        return temp_file.name


def cleanup_temp_file(file_path):
    """Vaqtincha faylni o'chiradi."""
    try:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Vaqtincha fayl o'chirildi: {file_path}")
    except Exception as e:
        logger.warning(f"Vaqtincha fayl o'chirishda xato: {e}")


def cleanup_old_temp_files():
    """Eski vaqtincha fayllarni tozalaydi."""
    temp_dir = getattr(settings, 'TEMP_DIR', None)
    if not temp_dir or not os.path.exists(temp_dir):
        return
    
    try:
        current_time = time.time()
        max_age = 24 * 60 * 60  # 24 soat
        
        for filename in os.listdir(temp_dir):
            if filename.startswith('temp_') or filename.startswith('doc_'):
                file_path = os.path.join(temp_dir, filename)
                if os.path.isfile(file_path):
                    file_age = current_time - os.path.getmtime(file_path)
                    if file_age > max_age:
                        os.remove(file_path)
                        logger.info(f"Eski vaqtincha fayl o'chirildi: {filename}")
    except Exception as e:
        logger.warning(f"Eski vaqtincha fayllarni tozalashda xato: {e}")


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


@shared_task
def cleanup_old_temp_files_task():
    """Eski vaqtincha fayllarni tozalash uchun periodic task."""
    logger.info("Eski vaqtincha fayllarni tozalash boshlandi...")
    cleanup_old_temp_files()
    logger.info("Eski vaqtincha fayllarni tozalash tugadi.")


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=20, max_retries=3)
def process_document_pipeline(self, document_id):
    """
    To'liq pipeline. pipeline_running lock ishlatiladi:
    - dparse band qilgan bo'lishi mumkin
    - Agar band emas bo'lsa bu yerda optimistik lock qo'lga olinadi
    - Retry jarayonida lock yechilmaydi
    - Faqat muvaffaqiyatli tugaganda yoki final (oxirgi) muvaffaqiyatsiz holatda yechiladi
    Idempotent Telegram yuborish: telegram_status completed bo'lsa qayta yuborilmaydi.
    """
    logger.info(f"--- [PIPELINE START] Hujjat ID: {document_id} ---")

    try:
        try:
            doc = Document.objects.select_related('product').get(id=document_id)
        except Document.DoesNotExist:
            logger.error(f"[PIPELINE FAIL] Hujjat {document_id} topilmadi")
            return

        # Agar document pipeline_running=False bo'lsa demak boshqa task oldinroq tugatgan yoki lock yo'q
        if not doc.pipeline_running:
            logger.warning(f"[PIPELINE SKIP] {document_id} lock yo'q (allaqachon qayta ishlangan yoki rejalashtirilmagan).")
            return

        # Allaqachon tugagan bo'lsa chiqib ketamiz
        if doc.completed:
            logger.info(f"[PIPELINE ALREADY COMPLETED] {document_id}")
            # Pipeline running holatini yechamiz
            Document.objects.filter(id=document_id).update(pipeline_running=False)
            return

        # Vaqtincha fayl yo'li yaratamiz
        file_extension = Path(doc.parse_file_url).suffix
        temp_file_path = get_temp_file_path(doc.id, file_extension)
        
        # Eski vaqtincha fayllarni tozalaymiz
        cleanup_old_temp_files()

        # 1. DOWNLOAD
        if doc.download_status != 'completed':
            logger.info(f"[1. Yuklash] Boshlandi: {document_id}")
            if doc.download_status != 'processing':
                doc.download_status = 'processing'
                doc.save(update_fields=['download_status'])
            try:
                # Fayl yozish uchun ruxsatni tekshiramiz
                temp_dir = os.path.dirname(temp_file_path)
                if not os.access(temp_dir, os.W_OK):
                    raise PermissionError(f"Fayl yozish uchun ruxsat yo'q: {temp_dir}")
                
                with make_retry_session().get(doc.parse_file_url, stream=True, timeout=180) as r:
                    r.raise_for_status()
                    with open(temp_file_path, "wb") as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                doc.file_path = temp_file_path
                doc.download_status = 'completed'
                doc.save()
                logger.info(f"[1. Yuklash] Muvaffaqiyatli: {document_id}")
            except PermissionError as e:
                doc.download_status = 'failed'
                doc.save(update_fields=['download_status'])
                cleanup_temp_file(temp_file_path)  # Xato bo'lsa vaqtincha faylni o'chiramiz
                logger.error(f"[PIPELINE FAIL - Yuklash] Permission denied: {document_id}: {e}")
                raise
            except Exception as e:
                doc.download_status = 'failed'
                doc.save(update_fields=['download_status'])
                cleanup_temp_file(temp_file_path)  # Xato bo'lsa vaqtincha faylni o'chiramiz
                logger.error(f"[PIPELINE FAIL - Yuklash] {document_id}: {e}")
                raise

        doc.refresh_from_db()
        # 2. PARSE
        if doc.download_status == 'completed' and doc.parse_status != 'completed':
            logger.info(f"[2. Parse] Boshlandi: {document_id}")
            if doc.parse_status != 'processing':
                doc.parse_status = 'processing'
                doc.save(update_fields=['parse_status'])
            try:
                if not doc.file_path or not os.path.exists(doc.file_path):
                    doc.parse_status = 'failed'
                    doc.save(update_fields=['parse_status'])
                    logger.error(f"[PIPELINE FAIL - Parse] {document_id}: File not found or path is None: {doc.file_path}")
                    return  # Exit gracefully, do not raise
                parsed = tika_parser.from_file(doc.file_path)
                # Safely extract content with proper None handling
                content = ""
                if parsed:
                    raw_content = parsed.get("content", "")
                    if raw_content is not None:
                        content = raw_content.strip()
                    else:
                        content = ""
                with transaction.atomic():
                    product = doc.product
                    product.parsed_content = content
                    product.save(update_fields=['parsed_content'])
                    doc.parse_status = 'completed'
                    doc.save()
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
            if doc.index_status != 'processing':
                doc.index_status = 'processing'
                doc.save(update_fields=['index_status'])
            try:
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
                logger.info(f"[3. Indekslash] Muvaffaqiyatli: {document_id}")
            except Exception as e:
                doc.index_status = 'failed'
                doc.save(update_fields=['index_status'])
                logger.error(f"[PIPELINE FAIL - Indekslash] {document_id}: {e}")
                raise

        doc.refresh_from_db()
        # 4. TELEGRAM (idempotent)
        if doc.index_status == 'completed' and doc.telegram_status not in ['completed', 'skipped']:
            logger.info(f"[4. Telegram] Boshlandi: {document_id}")
            if doc.telegram_file_id and doc.telegram_status == 'completed':
                logger.info(f"[4. Telegram] Allaqachon yuborilgan: {document_id}")
            else:
                if doc.telegram_status != 'processing':
                    doc.telegram_status = 'processing'
                    doc.save(update_fields=['telegram_status'])
                try:
                    if not doc.file_path or not os.path.exists(doc.file_path):
                        doc.telegram_status = 'skipped'
                        doc.save(update_fields=['telegram_status'])
                        logger.warning(f"[4. Telegram] Fayl yo'q, o'tkazildi: {doc.file_path}")
                    else:
                        file_size = os.path.getsize(doc.file_path)
                        if file_size > TELEGRAM_MAX_FILE_SIZE_BYTES:
                            doc.telegram_status = 'skipped'
                            doc.save(update_fields=['telegram_status'])
                            logger.warning(f"[4. Telegram] Fayl katta, o'tkazildi: {file_size}")
                        else:
                            # Rate limiting uchun kutamiz
                            wait_for_telegram_rate_limit()
                            
                            json_data_str = json.dumps(doc.json_data, ensure_ascii=False, indent=2) if doc.json_data else '{}'
                            json_data_str = json_data_str.replace('`', '\u200b`')
                            static_caption = (
                                f"*{doc.product.title}*\n"
                                f"ID: `{doc.id}`\n"
                                f"URL: {doc.parse_file_url}\n"
                                f"Slug: `{doc.product.slug}`\n"
                                f"\n*JSON:*\n```")
                            closing = "\n```"
                            max_caption_len = 1024
                            available_json_len = max_caption_len - len(static_caption) - len(closing)
                            if len(json_data_str) > available_json_len:
                                json_data_str = json_data_str[:available_json_len-10] + '\n...'
                            caption = static_caption + json_data_str + closing
                            if len(caption) > 1024:
                                truncated = caption[:1000].rstrip()
                                if not truncated.endswith('```'):
                                    truncated += '\n...\n```'
                                caption = truncated
                            url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendDocument"
                            max_telegram_retries = 5
                            for attempt in range(max_telegram_retries):
                                with open(doc.file_path, "rb") as f:
                                    files = {"document": (Path(doc.file_path).name, f)}
                                    data = {"chat_id": settings.CHANNEL_ID, "caption": caption, "parse_mode": "Markdown"}
                                    response = make_retry_session().post(url, files=files, data=data, timeout=180)
                                resp_data = response.json()
                                if resp_data.get("ok"):
                                    doc.telegram_file_id = resp_data["result"]["document"]["file_id"]
                                    doc.telegram_status = 'completed'
                                    doc.save()
                                    logger.info(f"[4. Telegram] Muvaffaqiyatli: {document_id}")
                                    break
                                elif resp_data.get("error_code") == 429 and "retry_after" in resp_data:
                                    retry_after = int(resp_data["retry_after"])
                                    logger.warning(f"[4. Telegram] Rate limit {document_id}, {retry_after}s kutyapmiz...")
                                    time.sleep(retry_after)
                                    continue
                                else:
                                    raise Exception(f"Telegram API xatosi: {resp_data.get('description')}")
                            else:
                                doc.telegram_status = 'failed'
                                doc.save(update_fields=['telegram_status'])
                                logger.error(f"[4. Telegram] 5 urinish muvaffaqiyatsiz: {document_id}")
                                raise Exception("Telegram yuborish muvaffaqiyatsiz (5 urinish)")
                except Exception as e:
                    doc.telegram_status = 'failed'
                    doc.save(update_fields=['telegram_status'])
                    logger.error(f"[PIPELINE FAIL - Telegram] {document_id}: {e}")
                    raise

        doc.refresh_from_db()
        # 5. DELETE LOCAL
        if doc.telegram_status in ['completed', 'skipped'] and doc.delete_status != 'completed':
            logger.info(f"[5. O'chirish] Boshlandi: {document_id}")
            if doc.delete_status != 'processing':
                doc.delete_status = 'processing'
                doc.save(update_fields=['delete_status'])
            try:
                # Vaqtincha faylni o'chiramiz
                if doc.file_path and os.path.exists(doc.file_path):
                    cleanup_temp_file(doc.file_path)
                    logger.info(f"[5. O'chirish] Vaqtincha fayl o'chirildi: {doc.file_path}")
                else:
                    logger.warning(f"[5. O'chirish] Vaqtincha fayl topilmadi: {doc.file_path}")
                
                # Eski downloads papkasidagi faylni ham o'chirishga harakat qilamiz (agar mavjud bo'lsa)
                old_file_name = f"{doc.id}{Path(doc.parse_file_url).suffix}"
                old_file_path = os.path.join(settings.MEDIA_ROOT, 'downloads', old_file_name)
                if os.path.exists(old_file_path):
                    os.remove(old_file_path)
                    logger.info(f"[5. O'chirish] Eski fayl o'chirildi: {old_file_path}")
                
                doc.delete_status = 'completed'
                doc.save(update_fields=['delete_status'])
                logger.info(f"[5. O'chirish] Tugadi: {document_id}")
            except Exception as e:
                doc.delete_status = 'failed'
                doc.save(update_fields=['delete_status'])
                logger.error(f"[PIPELINE FAIL - O'chirish] {document_id}: {e}")
                raise

        # Pipeline muvaffaqiyatli tugadi - completed holatini yangilaymiz
        doc.refresh_from_db()
        doc.save()  # Bu completed holatini avtomatik yangilaydi
        logger.info(f"--- [PIPELINE SUCCESS] ✅ Hujjat ID: {document_id} ---")
    except Exception as pipeline_error:
        # Agar yana retry bo'ladigan bo'lsa lockni yechmaymiz (Celery autoretry keyingi chaqiriqda davom etadi)
        if self.request.retries >= self.max_retries:
            Document.objects.filter(id=document_id).update(pipeline_running=False)
            logger.error(f"[PIPELINE FINAL FAIL] {document_id}: {pipeline_error}")
        raise
    else:
        # Muvaffaqiyatli tugadi -> lockni yechamiz
        Document.objects.filter(id=document_id).update(pipeline_running=False)
    finally:
        # Har doim vaqtincha faylni o'chirishga harakat qilamiz
        try:
            if 'temp_file_path' in locals() and temp_file_path:
                cleanup_temp_file(temp_file_path)
        except Exception as cleanup_error:
            logger.warning(f"Cleanup xatosi {document_id}: {cleanup_error}")
