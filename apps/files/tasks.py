# apps/multiparser/tasks.py

import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytz
import requests
from celery import shared_task
from django.conf import settings
from django.db import transaction
from elasticsearch import Elasticsearch
from requests.adapters import HTTPAdapter
from tika import parser as tika_parser
from urllib3.util.retry import Retry

try:
    import redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

from .models import Document, DocumentError, Product

# --- Logger ---
logger = logging.getLogger(__name__)

# --- Clients Setup ---
tika_parser.TikaClientOnly = True
tika_parser.TikaServerEndpoint = getattr(settings, 'TIKA_URL', 'http://tika:9998')

TELEGRAM_MAX_FILE_SIZE_BYTES = 49 * 1024 * 1024


def log_document_error(document, error_type, error_message, celery_attempt=1):
    """
    Tushunarli va chiroyli shaklda xatolik yozuvini DocumentError modeliga qo'shadi.
    """
    try:
        # Xatolik matnini qisqartirish va formatlash
        if isinstance(error_message, Exception):
            error_text = f"{type(error_message).__name__}: {str(error_message)}"
        else:
            error_text = str(error_message)

        DocumentError.objects.create(
            document=document,
            error_type=error_type,
            error_message=error_text,
            celery_attempt=celery_attempt
        )
        logger.info(
            f"[ERROR LOGGED] DocID {document.id} - Type: {error_type} (Attempt: {celery_attempt}): {error_text}")
    except Exception as e:
        logger.error(f"[ERROR LOGGING FAILED] DocID {document.id} - {e}")


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
    """
    Redis yordamida markazlashtirilgan (distributed) rate limiting uchun kutish funksiyasi.
    Barcha worker'lar uchun umumiy bo'lgan qulf yordamida bir vaqtda faqat bitta
    worker Telegramga so'rov yuborishini ta'minlaydi.
    """
    if not REDIS_AVAILABLE:
        logger.warning("Redis topilmadi, rate limit uchun 5 soniya kutamiz.")
        time.sleep(5)
        return

    try:
        redis_url = getattr(settings, 'CELERY_BROKER_URL', 'redis://redis:6379/0')
        r = redis.from_url(redis_url)

        with r.lock("telegram_api_lock", timeout=60, blocking_timeout=65):
            last_send_time_str = r.get("last_telegram_send_time")
            if last_send_time_str:
                last_send_time = datetime.fromisoformat(last_send_time_str.decode('utf-8'))
                time_since_last = datetime.now() - last_send_time
                min_interval = timedelta(seconds=2)  # Telegram uchun 2 soniya oraliq

                if time_since_last < min_interval:
                    wait_time = (min_interval - time_since_last).total_seconds()
                    if wait_time > 0:
                        logger.info(f"Telegram rate limit uchun {wait_time:.2f} soniya kutamiz...")
                        time.sleep(wait_time)

            r.set("last_telegram_send_time", datetime.now().isoformat())

    except Exception as e:
        logger.error(f"Redis rate limit lock'da xato: {e}. 5 soniya kutamiz.")
        time.sleep(5)


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=20, max_retries=3)
def process_document_pipeline(self, document_id):
    """
    To'liq pipeline. Hujjatni qaysi bosqichda bo'lsa, o'sha yerdan davom ettiradi.
    Yuklaydi, parse qiladi, indekslaydi, yuboradi va oxirida o'chiradi.
    """
    logger.info(f"--- [PIPELINE START] Hujjat ID: {document_id} ---")
    file_path_str = ""

    try:
        with transaction.atomic():
            doc = Document.objects.select_for_update().select_related('product').get(id=document_id)

            if doc.completed:
                logger.info(f"[PIPELINE SKIPPED] Hujjat allaqachon yakunlangan: {document_id}")
                return

            if not doc.pipeline_running:
                doc.pipeline_running = True
                doc.save(update_fields=['pipeline_running'])
                logger.info(f"[PIPELINE LOCK] {document_id} pipeline'ga qulflandi.")

        # Fayl yo'lini aniqlash
        try:
            file_extension = Path(doc.parse_file_url).suffix
            if not file_extension: raise ValueError("Fayl kengaytmasi topilmadi.")
            media_dir = os.path.join(settings.MEDIA_ROOT, 'downloads')
            os.makedirs(media_dir, exist_ok=True)
            file_path_str = os.path.join(media_dir, f"{doc.id}{file_extension}")
        except Exception as path_err:
            log_document_error(doc, 'other', f"Fayl yo'lini aniqlashda xato: {path_err}", self.request.retries + 1)
            doc.pipeline_running = False
            doc.save(update_fields=['pipeline_running'])
            return

        # --- BOSQICHMA-BOSQICH BAJARISH ---

        # 1. DOWNLOAD
        if doc.download_status != 'completed':
            try:
                logger.info(f"[1. Yuklash] Boshlandi: {document_id}")
                doc.download_status = 'processing'
                doc.save(update_fields=['download_status'])
                with make_retry_session().get(doc.parse_file_url, stream=True, timeout=180) as r:
                    r.raise_for_status()
                    with open(file_path_str, "wb") as f:
                        for chunk in r.iter_content(chunk_size=8192): f.write(chunk)
                doc.download_status = 'completed'
                doc.save(update_fields=['download_status'])
                logger.info(f"[1. Yuklash] Muvaffaqiyatli: {document_id}")
            except Exception as e:
                doc.download_status = 'failed'
                doc.save(update_fields=['download_status'])
                log_document_error(doc, 'download', e, self.request.retries + 1)
                raise  # Celery qayta urinishi uchun xatolikni yuqoriga uzatamiz

        # 2. PARSE (TIKA)
        if doc.parse_status != 'completed':
            try:
                logger.info(f"[2. Parse] Boshlandi: {document_id}")
                if not os.path.exists(file_path_str):
                    raise FileNotFoundError(f"Parse qilish uchun fayl topilmadi: {file_path_str}")
                doc.parse_status = 'processing'
                doc.save(update_fields=['parse_status'])
                parsed = tika_parser.from_file(file_path_str)
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
                log_document_error(doc, 'parse', e, self.request.retries + 1)
                raise

        # 3. INDEX (ELASTICSEARCH)
        if doc.index_status != 'completed':
            try:
                logger.info(f"[3. Indekslash] Boshlandi: {document_id}")
                doc.index_status = 'processing'
                doc.save(update_fields=['index_status'])
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
                log_document_error(doc, 'index', e, self.request.retries + 1)
                raise

        # 4. SEND (TELEGRAM)
        if doc.telegram_status != 'completed':
            try:
                logger.info(f"[4. Telegram] Boshlandi: {document_id}")
                if not os.path.exists(file_path_str):
                    raise FileNotFoundError(f"Telegramga yuborish uchun fayl topilmadi: {file_path_str}")

                doc.telegram_status = 'processing'
                doc.save(update_fields=['telegram_status'])

                if os.path.getsize(file_path_str) > TELEGRAM_MAX_FILE_SIZE_BYTES:
                    doc.telegram_status = 'skipped'
                    logger.warning(f"[4. Telegram] Fayl hajmi katta (>49MB), o'tkazib yuborildi: {doc.id}")
                else:
                    wait_for_telegram_rate_limit()
                    caption = f"*{doc.product.title}*\n\nID: `{doc.id}`"
                    url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendDocument"
                    with open(file_path_str, "rb") as f:
                        files = {"document": (Path(file_path_str).name, f)}
                        data = {"chat_id": settings.CHANNEL_ID, "caption": caption, "parse_mode": "Markdown"}
                        response = make_retry_session().post(url, files=files, data=data, timeout=180)
                    resp_data = response.json()

                    if resp_data.get("ok"):
                        doc.telegram_file_id = resp_data["result"]["document"]["file_id"]
                        doc.telegram_status = 'completed'
                        logger.info(f"[4. Telegram] Muvaffaqiyatli: {document_id}")
                    elif resp_data.get("error_code") == 429:
                        retry_after = int(resp_data.get("parameters", {}).get("retry_after", 5))
                        logger.warning(f"[4. Telegram] Rate limit xatosi, {retry_after}s keyin qayta uriniladi.")
                        raise self.retry(countdown=retry_after + 1)
                    else:
                        raise Exception(f"Telegram API xatosi: {resp_data.get('description')}")

                doc.save(update_fields=['telegram_file_id', 'telegram_status'])

            except Exception as e:
                doc.telegram_status = 'failed'
                doc.save(update_fields=['telegram_status'])
                log_document_error(doc, 'telegram_send', e, self.request.retries + 1)
                raise

        # Barcha bosqichlar muvaffaqiyatli o'tdi
        logger.info(f"--- [PIPELINE SUCCESS] ✅ Hujjat ID: {document_id} ---")

    except Exception as pipeline_error:
        # Vazifa qayta urinishga yuborilganda bu yerga keladi
        logger.error(
            f"[PIPELINE RETRYING] {document_id}: {type(pipeline_error).__name__}. Urinish {self.request.retries + 1}/{self.max_retries + 1}")
        # Agar maksimal urinishlar soniga yetsa, pipeline'ni to'xtatamiz
        if self.request.retries >= self.max_retries:
            logger.error(f"[PIPELINE FINAL FAIL] {document_id} barcha urinishlardan so'ng ham muvaffaqiyatsiz bo'ldi.")
            with transaction.atomic():
                doc = Document.objects.select_for_update().get(id=document_id)
                doc.pipeline_running = False
                doc.save(update_fields=['pipeline_running'])
            log_document_error(doc, 'other', f"Pipeline final fail: {pipeline_error}", self.request.retries + 1)
        raise  # Celery'ga xatolikni uzatish shart

    finally:
        # 5. DELETE
        # Bu blok har doim (xatolik bo'lsa ham, bo'lmasa ham) ishlaydi
        try:
            doc = Document.objects.get(id=document_id)

            # Agar hujjat ideal holatga kelgan bo'lsa, faylni o'chiramiz
            is_ideal_state = (
                    doc.parse_status == 'completed' and
                    doc.index_status == 'completed' and
                    doc.telegram_file_id is not None and doc.telegram_file_id.strip() != ''
            )

            # Agar fayl mavjud bo'lsa va...
            if file_path_str and os.path.exists(file_path_str):
                # ...hujjat ideal holatga kelgan bo'lsa YOKI...
                # ...vazifa barcha qayta urinishlardan so'ng ham muvaffaqiyatsiz bo'lsa
                if is_ideal_state or (self.request.retries >= self.max_retries):
                    os.remove(file_path_str)
                    doc.delete_status = 'completed'
                    logger.info(f"[DELETE] Fayl o'chirildi: {file_path_str}")

            # Pipeline'ni yakunlaymiz (qulfni ochamiz)
            doc.pipeline_running = False
            doc.save(update_fields=['delete_status', 'pipeline_running'])
            logger.info(f"[PIPELINE UNLOCK] {document_id} pipeline'dan qulf olindi.")

        except Document.DoesNotExist:
            logger.warning(f"Finally blokida hujjat topilmadi: {document_id}")
        except Exception as final_error:
            logger.error(f"[FINALLY BLOCK ERROR] {document_id}: {final_error}")


@shared_task(name="apps.multiparser.tasks.cleanup_files_task")
def cleanup_files_task():
    """
    Fayl tizimini skanerlab, qolib ketgan fayllarni va nomuvofiq holatdagi
    hujjatlarni tozalaydi.
    """
    logger.info("========= FAYL TIZIMINI REJALI TOZALASH BOSHLANDI =========")
    downloads_dir = os.path.join(settings.MEDIA_ROOT, 'downloads')

    if not os.path.exists(downloads_dir):
        logger.warning(f"Tozalash uchun 'downloads' papkasi topilmadi: {downloads_dir}")
        return

    deleted_files_count = 0
    updated_docs_count = 0
    reset_docs_count = 0

    for filename in os.listdir(downloads_dir):
        file_path = os.path.join(downloads_dir, filename)
        if not os.path.isfile(file_path): continue

        doc_id = os.path.splitext(filename)[0]

        try:
            with transaction.atomic():
                doc = Document.objects.select_for_update().get(id=doc_id)

                # Agar pipeline ishlayotgan bo'lsa, bu faylga tegmaymiz
                if doc.pipeline_running:
                    logger.info(f"🔄 FAYL HIMOYALANGAN (pipeline ishlayapti): {filename}")
                    continue

                # Ideal holatni tekshirish
                is_ideal_state = (
                        doc.parse_status == 'completed' and
                        doc.index_status == 'completed' and
                        doc.telegram_file_id is not None and doc.telegram_file_id.strip() != ''
                )

                if is_ideal_state:
                    # Hujjat ideal holatda, statuslarni to'liq 'completed' qilamiz
                    doc.download_status = 'completed'
                    doc.telegram_status = 'completed'
                    doc.delete_status = 'completed'
                    doc.completed = True
                    doc.save()
                    logger.info(f"✅ HUJJAT YAKUNLANDI: {doc.id} holati 'completed' ga o'rnatildi.")
                    updated_docs_count += 1
                else:
                    # Hujjat ideal holatda emas, statuslarni 'pending' qilamiz
                    doc.download_status = 'pending'
                    doc.parse_status = 'pending'
                    doc.index_status = 'pending'
                    doc.telegram_status = 'pending'
                    doc.delete_status = 'pending'
                    doc.completed = False
                    doc.save()
                    logger.warning(f"⚠️  HUJJAT QAYTA TIKLANDI: {doc.id} holati 'pending' ga o'rnatildi.")
                    reset_docs_count += 1

                # Ikkala holatda ham faylni o'chiramiz
                os.remove(file_path)
                logger.info(f"🗑️  FAYL O'CHIRILDI: {filename}")
                deleted_files_count += 1

        except Document.DoesNotExist:
            logger.warning(f"👻 YETIM FAYL (bazada yozuvi yo'q): {filename}. O'chirilmoqda...")
            os.remove(file_path)
            deleted_files_count += 1
        except Exception as e:
            logger.error(f"❌ Tozalashda kutilmagan xato ({filename}): {e}")

    logger.info("--- TOZALASH STATISTIKASI ---")
    logger.info(f"O'chirilgan fayllar: {deleted_files_count}")
    logger.info(f"Yakunlangan hujjatlar: {updated_docs_count}")
    logger.info(f"'Pending' qilingan hujjatlar: {reset_docs_count}")
    logger.info("========= FAYL TIZIMINI TOZALASH TUGADI =========")