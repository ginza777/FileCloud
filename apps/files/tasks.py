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
from datetime import datetime, timezone
from django.utils import timezone as django_timezone
import pytz

# YECHIM UCHUN: Redis'ni import qilamiz
try:
    import redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

from .models import Document

# --- Logger ---
logger = logging.getLogger(__name__)

# --- Clients Setup ---
tika_parser.TikaClientOnly = True
tika_parser.TikaServerEndpoint = getattr(settings, 'TIKA_URL', 'http://tika:9998')

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


def wait_for_telegram_rate_limit():
    """
    YANGILANGAN FUNKSIYA: Redis yordamida markazlashtirilgan (distributed)
    rate limiting uchun kutish funksiyasi.
    """
    if not REDIS_AVAILABLE:
        logger.warning("Redis topilmadi, rate limit uchun 5 soniya kutamiz.")
        time.sleep(5)
        return

    try:
        redis_url = getattr(settings, 'CELERY_BROKER_URL', 'redis://redis:6379/0')
        r = redis.from_url(redis_url)

        # Barcha worker'lar uchun umumiy bo'lgan qulf
        with r.lock("telegram_send_lock", timeout=60):
            last_send_time_str = r.get("last_telegram_send_time")

            if last_send_time_str:
                last_send_time = datetime.fromisoformat(last_send_time_str.decode('utf-8'))
                time_since_last = datetime.now() - last_send_time

                # Telegram uchun 2 soniya oraliq yetarli bo'lishi kerak
                min_interval = timedelta(seconds=2)

                if time_since_last < min_interval:
                    wait_time = (min_interval - time_since_last).total_seconds()
                    if wait_time > 0:
                        logger.info(f"Telegram rate limit uchun {wait_time:.2f} soniya kutamiz...")
                        time.sleep(wait_time)

            # Oxirgi yuborilgan vaqtni Redis'ga yozib qo'yamiz
            r.set("last_telegram_send_time", datetime.now().isoformat())

    except Exception as e:
        logger.error(f"Redis rate limit lock'da xato: {e}. 5 soniya kutamiz.")
        time.sleep(5)


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=20, max_retries=3)
def process_document_pipeline(self, document_id):
    """
    To'liq pipeline. Hujjatni yuklaydi, parse qiladi, indekslaydi, yuboradi va oxirida o'chiradi.
    """
    logger.info(f"--- [PIPELINE START] Hujjat ID: {document_id} ---")
    file_path = None  # Fayl yo'lini saqlash uchun

    try:
        doc = Document.objects.select_related('product').get(id=document_id)

        # Pipeline boshida pipeline_running=True qilamiz
        if not doc.pipeline_running:
            doc.pipeline_running = True
            doc.save(update_fields=['pipeline_running'])
            logger.info(f"[PIPELINE LOCK] {document_id} pipeline'ga qulflandi")

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
                    # Telegram API dan kelgan rate limit xatosini alohida ushlaymiz
                    elif resp_data.get("error_code") == 429 and "retry_after" in resp_data:
                        retry_after = int(resp_data["retry_after"])
                        logger.warning(f"[4. Telegram] API dan Rate limit {document_id}, {retry_after}s kutyapmiz...")
                        time.sleep(retry_after)
                        # Qayta urinish uchun xatolik chaqiramiz
                        raise Exception(f"Telegram API rate limit: retry after {retry_after}")
                    else:
                        raise Exception(f"Telegram API xatosi: {resp_data.get('description')}")
                doc.save(update_fields=['telegram_file_id', 'telegram_status'])
                
                # Telegram'ga yuborilgach pipeline_running=False qilamiz
                doc.pipeline_running = False
                doc.save(update_fields=['pipeline_running'])
                logger.info(f"[PIPELINE UNLOCK] {document_id} pipeline'dan qulf olindi")
                
            except Exception as e:
                doc.telegram_status = 'failed'
                doc.save(update_fields=['telegram_status'])
                logger.error(f"[PIPELINE FAIL - Telegram] {document_id}: {e}")
                raise

        # Pipeline muvaffaqiyatli tugadi
        doc.refresh_from_db()
        logger.info(f"--- [PIPELINE SUCCESS] ✅ Hujjat ID: {document_id} ---")

    except Exception as pipeline_error:
        if self.request.retries >= self.max_retries:
            Document.objects.filter(id=document_id).update(pipeline_running=False)
            logger.error(f"[PIPELINE FINAL FAIL] {document_id}: {pipeline_error}")
        raise

    finally:
        try:
            doc.refresh_from_db()
            # Telegram'ga yuborilgan yoki maksimal urinishlar tugagan bo'lsa faylni o'chiramiz
            is_final_state = (
                (doc.telegram_status == 'completed' and doc.telegram_file_id) or 
                (self.request.retries >= self.max_retries)
            )

            if is_final_state and file_path and os.path.exists(file_path):
                os.remove(file_path)
                doc.delete_status = 'completed'
                doc.save(update_fields=['delete_status'])
                logger.info(f"[DELETE] Fayl o'chirildi: {file_path}")
        except Exception as delete_error:
            logger.error(f"[DELETE FAIL] Faylni o'chirishda xato: {document_id} - {delete_error}")


from django.utils import timezone
from datetime import timedelta






@shared_task(name="apps.files.tasks.cleanup_completed_files_task")
def cleanup_completed_files_task():
    """
    Fayl tizimini skanerlab, qolib ketgan fayllarni va nomuvofiq holatdagi
    hujjatlarni tozalaydi. Bu vazifa barcha tozalash mantig'ini o'z ichiga oladi.
    """
    logger.info("========= FAYL TIZIMI TOZALASH BOSHLANDI =========")
    logger.info("Fayl tizimi bo'yicha rejali tozalash boshlandi...")
    downloads_dir = os.path.join(settings.MEDIA_ROOT, 'downloads')
    logger.info(f"Tozalash joyi: {downloads_dir}")

    if not os.path.exists(downloads_dir):
        logger.warning(f"Tozalash uchun 'downloads' papkasi topilmadi: {downloads_dir}")
        return

    # Tashkent vaqt mintaqasi
    tashkent_tz = pytz.timezone('Asia/Tashkent')

    # Tozalash statistikasi
    found_files = 0
    deleted_files = 0
    reset_docs = 0
    protected_files = 0

    # Avval papkadagi barcha fayllarni sanab chiqamiz
    try:
        all_files = os.listdir(downloads_dir)
        logger.info(f"Jami {len(all_files)} ta fayl topildi")
    except Exception as e:
        logger.error(f"Papkani o'qishda xato: {e}")
        return

    for filename in all_files:
        file_path = os.path.join(downloads_dir, filename)
        if not os.path.isfile(file_path):
            continue

        found_files += 1
        doc_id = os.path.splitext(filename)[0]
        file_size = os.path.getsize(file_path) / (1024 * 1024)  # MB da
        logger.info(f"FAYL: {filename} | {file_size:.2f} MB")

        try:
            doc = Document.objects.get(id=doc_id)

            # Hujjat holatini log qilamiz
            logger.info(f"HUJJAT #{doc_id}: download={doc.download_status}, parse={doc.parse_status}, "
                       f"index={doc.index_status}, telegram={doc.telegram_status}, "
                       f"telegram_file_id={doc.telegram_file_id is not None}, "
                       f"completed={doc.completed}, pipeline_running={doc.pipeline_running}")

            # 1-Qoida: Hujjat hozirda pipeline'da ishlayaptimi?
            if doc.pipeline_running:
                logger.info(f"🔄 PIPELINE ISHLAYAPTI: Hujjat hozirda ishlov berilmoqda, himoyalanadi: {doc_id}")
                protected_files += 1
                continue

            # 2-Qoida: Hujjat mukammal tugallanganmi? (completed=True va telegram_file_id bor)
            is_perfectly_completed = (
                    doc.completed and
                    doc.telegram_file_id is not None and
                    doc.telegram_file_id.strip() != ''
            )

            if is_perfectly_completed:
                # Ha, mukammal tugallangan. Demak fayl ortiqcha.
                logger.info(f"✅ HIMOYALANGAN: Muvaffaqiyatli hujjatning ortiqcha fayli o'chirilmoqda: {filename}")
                try:
                    os.remove(file_path)
                    logger.info(f"✅ FAYL O'CHIRILDI: {filename}")
                    deleted_files += 1
                except Exception as e:
                    logger.error(f"❌ XATO: Faylni o'chirishda xatolik: {e}")
                # Hujjatning o'ziga tegmaymiz, u to'g'ri holatda.
                continue

            # 3-Qoida: Hujjat mukammal EMAS. Faylni o'chiramiz va hujjatni pending qilamiz
            logger.info(f"🔶 TUGALLANMAGAN: Hujjat mukammal tugallanmagan, fayl o'chirilmoqda: {doc_id}")
            
            # Faylni o'chiramiz
            try:
                os.remove(file_path)
                logger.info(f"🗑️ FAYL O'CHIRILDI: {filename}")
                deleted_files += 1
            except Exception as e:
                logger.error(f"❌ XATO: Faylni o'chirishda xatolik: {e}")

            # Hujjatni "pending" holatiga qaytaramiz
            old_status = f"download={doc.download_status}, parse={doc.parse_status}, index={doc.index_status}, telegram={doc.telegram_status}"
            doc.download_status = 'pending'
            doc.parse_status = 'pending'
            doc.index_status = 'pending'
            doc.telegram_status = 'pending'
            doc.delete_status = 'pending'
            doc.completed = False
            doc.pipeline_running = False
            doc.save()
            logger.info(f"🔄 HUJJAT QAYTA TIKLANDI: ID {doc_id}, eski holat: {old_status}")
            reset_docs += 1

        except Document.DoesNotExist:
            # Fayl bor, lekin bazada unga mos yozuv yo'q ("yetim" fayl)
            logger.warning(f"👻 YETIM FAYL: Bazada yozuvi yo'q fayl topildi: {filename}")
            logger.warning(f"🗑️ O'CHIRILMOQDA: Yetim fayl o'chirilmoqda: {filename}")
            try:
                os.remove(file_path)
                logger.info(f"✅ YETIM FAYL O'CHIRILDI: {filename}")
                deleted_files += 1
            except Exception as e:
                logger.error(f"❌ XATO: Yetim faylni o'chirishda xatolik: {e}")
        except Exception as e:
            logger.error(f"❌ XATO: Faylni ({filename}) tozalashda kutilmagan xato: {e}")

    logger.info(f"========= TOZALASH STATISTIKASI =========")
    logger.info(f"Jami ko'rib chiqilgan fayllar: {found_files}")
    logger.info(f"O'chirilgan fayllar: {deleted_files}")
    logger.info(f"Tozalangan hujjatlar: {reset_docs}")
    logger.info(f"Himoyalangan fayllar: {protected_files}")
    logger.info(f"========= FAYL TIZIMI TOZALASH TUGADI =========")
