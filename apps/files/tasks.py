# apps/multiparser/tasks.py

import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests
from celery import shared_task
from django.conf import settings
from django.db import transaction, DatabaseError
from elasticsearch import Elasticsearch
from requests.adapters import HTTPAdapter
from tika import parser as tika_parser
from urllib3.util.retry import Retry

try:
    import redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

from .models import Document, DocumentError

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
            doc = Document.objects.select_for_update().get(id=document_id)

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

                # Check if document is now in ideal state and set completed=True
                is_ideal_state = (
                        doc.parse_status == 'completed' and
                        doc.index_status == 'completed' and
                        doc.telegram_file_id is not None and
                        doc.telegram_file_id.strip() != ''
                )

                if is_ideal_state:
                    doc.completed = True
                    doc.download_status = 'completed'
                    doc.delete_status = 'completed'
                    doc.save(update_fields=['telegram_file_id', 'telegram_status', 'completed', 'download_status',
                                            'delete_status'])
                    logger.info(f"[PIPELINE COMPLETED] ✅ Hujjat yakunlandi: {document_id}")
                else:
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


@shared_task(name="apps.files.tasks.cleanup_files_task")
def cleanup_files_task():
    """
    Fayl tizimini skanerlab, qolib ketgan fayllarni va nomuvofiq holatdagi
    hujjatlarni tozalaydi.
    """
    logger.info("========= FAYL TIZIMINI REJALI TOZALASH BOSHLANDI =========")
    
    # Check both 'downloads' and 'download' directories
    downloads_dir = os.path.join(settings.MEDIA_ROOT, 'downloads')
    download_dir = os.path.join(settings.MEDIA_ROOT, 'download')
    
    directories_to_scan = []
    if os.path.exists(downloads_dir):
        directories_to_scan.append(downloads_dir)
        logger.info(f"📁 'downloads' papkasi topildi: {downloads_dir}")
    else:
        logger.warning(f"⚠️  'downloads' papkasi topilmadi: {downloads_dir}")
    
    if os.path.exists(download_dir):
        directories_to_scan.append(download_dir)
        logger.info(f"📁 'download' papkasi topildi: {download_dir}")
    else:
        logger.warning(f"⚠️  'download' papkasi topilmadi: {download_dir}")
    
    if not directories_to_scan:
        logger.warning("❌ Hech qanday tozalash papkasi topilmadi!")
        return

    deleted_files_count = 0
    updated_docs_count = 0
    reset_docs_count = 0

    # Process each directory
    for current_dir in directories_to_scan:
        logger.info(f"🔍 Papka skanerlanyapti: {current_dir}")
        
        for filename in os.listdir(current_dir):
            file_path = os.path.join(current_dir, filename)
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
                    try:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                            logger.info(f"🗑️  FAYL O'CHIRILDI: {filename}")
                            deleted_files_count += 1
                        else:
                            logger.warning(f"⚠️  FAYL MAVJUD EMAS: {filename}")
                    except PermissionError as e:
                        error_msg = f"Fayl o'chirishda ruxsat xatosi: {filename} - {e}"
                        logger.error(f"❌ RUHSAT XATOSI: {error_msg}")
                        log_document_error(doc, 'other', error_msg, 1)
                    except OSError as e:
                        error_msg = f"Fayl o'chirishda tizim xatosi: {filename} - {e}"
                        logger.error(f"❌ FAYL O'CHIRISH XATOSI: {error_msg}")
                        log_document_error(doc, 'other', error_msg, 1)
                    except Exception as e:
                        error_msg = f"Fayl o'chirishda kutilmagan xato: {filename} - {e}"
                        logger.error(f"❌ KUTILMAGAN XATO: {error_msg}")
                        log_document_error(doc, 'other', error_msg, 1)

            except Document.DoesNotExist:
                logger.warning(f"👻 YETIM FAYL (bazada yozuvi yo'q): {filename}. O'chirilmoqda...")
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        logger.info(f"🗑️  YETIM FAYL O'CHIRILDI: {filename}")
                        deleted_files_count += 1
                    else:
                        logger.warning(f"⚠️  YETIM FAYL MAVJUD EMAS: {filename}")
                except PermissionError:
                    logger.error(f"❌ YETIM FAYL RUHSAT XATOSI: {filename} o'chirishga ruxsat yo'q")
                except OSError as e:
                    logger.error(f"❌ YETIM FAYL O'CHIRISH XATOSI: {filename} - {e}")
                except Exception as e:
                    logger.error(f"❌ YETIM FAYL KUTILMAGAN XATO: {filename} - {e}")
            except Exception as e:
                error_msg = f"Tozalashda kutilmagan xato: {filename} - {e}"
                logger.error(f"❌ {error_msg}")
                # Try to log to DocumentError if we can get the document
                try:
                    doc = Document.objects.get(id=doc_id)
                    log_document_error(doc, 'other', error_msg, 1)
                except Document.DoesNotExist:
                    # Document doesn't exist, can't log to DocumentError
                    pass

    logger.info("--- TOZALASH STATISTIKASI ---")
    logger.info(f"O'chirilgan fayllar: {deleted_files_count}")
    logger.info(f"Yakunlangan hujjatlar: {updated_docs_count}")
    logger.info(f"'Pending' qilingan hujjatlar: {reset_docs_count}")
    logger.info("========= FAYL TIZIMINI TOZALASH TUGADI =========")


@shared_task(name="apps.files.tasks.soft_uz_process_documents")
def soft_uz_process_documents():
    """
    Hujjatlarni holatini tekshirib, kerak bo'lsa tozalab, qayta ishlash uchun pipeline'ga yuboradi.
    Bu task dparse komandasining funksiyasini bajaradi.
    """
    logger.info("========= SOFT_UZ_PROCESS_DOCUMENTS TASK BOSHLANDI =========")

    # Qayta ishlash uchun nomzodlarni topamiz: hozirda ishlamayotgan barcha hujjatlar
    candidate_docs = Document.objects.filter(pipeline_running=False).order_by('created_at')

    total_candidates = candidate_docs.count()
    logger.info(f"Jami {total_candidates} ta nomzod topildi.")

    # Statistika uchun hisoblagichlar
    updated_as_completed_count = 0
    queued_for_processing_count = 0
    skipped_as_locked_count = 0

    # Xotirani tejash uchun .iterator() dan foydalanamiz
    for doc in candidate_docs.iterator():
        try:
            with transaction.atomic():
                # Poyga holatini oldini olish uchun qatorni qulflaymiz
                locked_doc = Document.objects.select_for_update(nowait=True).get(pk=doc.pk)

                # 1-shart: To'g'ri, yakuniy holat (ideal holat)
                is_ideal_state = (
                        locked_doc.parse_status == 'completed' and
                        locked_doc.index_status == 'completed' and
                        locked_doc.telegram_file_id is not None and
                        locked_doc.telegram_file_id.strip() != ''
                )

                if is_ideal_state:
                    # Hujjat allaqachon yakunlangan, shunchaki holatini to'g'rilab qo'yamiz
                    locked_doc.download_status = 'completed'
                    locked_doc.telegram_status = 'completed'
                    locked_doc.delete_status = 'completed'
                    locked_doc.completed = True
                    locked_doc.save()

                    logger.info(f"✅ Holati to'g'rilandi (yakunlangan): {locked_doc.id}")
                    updated_as_completed_count += 1
                else:
                    # Hujjat ideal holatda emas, uni tozalab, navbatga qo'shamiz
                    locked_doc.download_status = 'pending'
                    locked_doc.parse_status = 'pending'
                    locked_doc.index_status = 'pending'
                    locked_doc.telegram_status = 'pending'
                    locked_doc.delete_status = 'pending'
                    locked_doc.completed = False
                    # pipeline_running ni Celery task o'zi True qiladi, biz False holatda saqlaymiz
                    locked_doc.save()

                    # Tozalangan hujjatni navbatga qo'shamiz
                    process_document_pipeline.apply_async(args=[locked_doc.id])

                    logger.info(f"➡️  Navbatga qo'shildi (pending): {locked_doc.id}")
                    queued_for_processing_count += 1

        except DatabaseError:
            # Agar `nowait=True` tufayli qator qulflangan bo'lsa, bu xato keladi.
            # Bu normal holat, boshqa bir jarayon bu hujjat ustida ishlayotgan bo'lishi mumkin.
            logger.warning(f"⚠️  Hujjat ({doc.id}) boshqa jarayon tomonidan band, o'tkazib yuborildi.")
            skipped_as_locked_count += 1
            continue
        except Exception as e:
            logger.error(f"❌ Hujjatni ({doc.id}) navbatga qo'shishda kutilmagan xato: {e}")

    logger.info("--- SOFT_UZ_PROCESS_DOCUMENTS STATISTIKASI ---")
    logger.info(f"✅ Yakunlangan deb topilib, holati yangilanganlar: {updated_as_completed_count} ta")
    logger.info(f"➡️  Qayta ishlash uchun navbatga qo'shilganlar: {queued_for_processing_count} ta")
    logger.info(f"⚠️  Boshqa jarayon band qilgani uchun o'tkazib yuborilganlar: {skipped_as_locked_count} ta")
    logger.info("========= SOFT_UZ_PROCESS_DOCUMENTS TASK TUGADI =========")


@shared_task(name="apps.files.tasks.soft_uz_parse")
def soft_uz_parse():
    """
    Soff.uz saytidan ma'lumotlarni oladi, mavjudlarini yangilaydi va yangilarini qo'shadi.
    Bu task parse komandasining funksiyasini bajaradi va haftada 1 marta ishlaydi.
    """
    import re
    import time
    import requests
    from django.db import transaction
    from .models import Document, Product, SiteToken, ParseProgress
    from .utils import get_valid_soff_token

    logger.info("========= SOFT_UZ_PARSE TASK BOSHLANDI =========")

    # Configuration
    SOFF_BUILD_ID_HOLDER = "{build_id}"
    BASE_API_URL_TEMPLATE = f"https://soff.uz/_next/data/{SOFF_BUILD_ID_HOLDER}/scientific-resources/all.json"

    def parse_file_size(file_size_str):
        """Convert file size string (e.g., '3.49 MB') to bytes"""
        if not file_size_str:
            return 0
        match = re.match(r'(\d+\.?\d*)\s*(MB|GB|KB)', file_size_str, re.IGNORECASE)
        if not match:
            return 0
        size, unit = float(match.group(1)), match.group(2).upper()
        if unit == 'GB':
            return size * 1024 * 1024 * 1024
        elif unit == 'MB':
            return size * 1024 * 1024
        elif unit == 'KB':
            return size * 1024
        return 0

    def extract_file_url(poster_url):
        """Poster URL'dan asosiy fayl URL'ini ajratib oladi."""
        if not poster_url:
            return None
        match = re.search(r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', poster_url)
        if match:
            file_id = match.group(1)
            file_ext_match = re.search(
                r'\.(pdf|docx|doc|pptx|ppt|xlsx|xls|txt|rtf|PPT|DOC|DOCX|PPTX|PDF|XLS|XLSX|odt|ods|odp)(?:_page|$)',
                poster_url,
                re.IGNORECASE)
            if file_ext_match:
                file_extension = file_ext_match.group(1)  # Preserve original case
                return f"https://d2co7bxjtnp5o.cloudfront.net/media/documents/{file_id}.{file_extension}"
        return None

    try:
        # Reset progress to start from page 1
        progress = ParseProgress.get_current_progress()
        progress.last_page = 0
        progress.save()
        logger.info("Parsing jarayoni 1-sahifaga qaytarildi.")

        page = 1
        total_created = 0
        total_updated = 0
        total_skipped = 0

        while True:
            logger.info(f"{'=' * 20} Sahifa: {page} {'=' * 20}")

            token = get_valid_soff_token()
            if not token:
                logger.error("Yaroqli token olinmadi. 5 soniyadan so'ng qayta uriniladi...")
                time.sleep(5)
                continue

            base_api_url = BASE_API_URL_TEMPLATE.replace(SOFF_BUILD_ID_HOLDER, token)
            site_token = SiteToken.objects.filter(name='soff').first()

            headers = {"accept": "*/*", "user-agent": "Mozilla/5.0"}
            cookies = {"token": site_token.auth_token if site_token else None}

            try:
                response = requests.get(f"{base_api_url}?page={page}", headers=headers, cookies=cookies, timeout=30)
                response.raise_for_status()
                data = response.json()
                items = data.get("pageProps", {}).get("productsData", {}).get("results", [])
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 404:
                    logger.warning(f"Sahifa {page} (404). Token eskirgan bo'lishi mumkin. Yangilanmoqda...")
                    time.sleep(2)
                    continue
                logger.error(f"Sahifa {page} da HTTP xatoligi: {e}")
                time.sleep(10)
                continue
            except requests.exceptions.RequestException as e:
                logger.error(f"Sahifa {page} da tarmoq xatoligi: {e}.")
                time.sleep(10)
                continue
            except ValueError:
                logger.warning(f"Sahifa {page} dan JSON javob o'qilmadi. Qayta urinilmoqda...")
                time.sleep(2)
                continue

            if not items:
                logger.info(f"Sahifa {page} da ma'lumot topilmadi. Parsing yakunlandi.")
                break

            # --- Sahifadagi ma'lumotlarni qayta ishlash ---
            created_count = 0
            updated_count = 0
            invalid_url_count = 0
            skipped_large_file_count = 0

            # Yangilash va yaratish uchun listlar
            docs_to_create, products_to_create = [], []
            docs_to_update, products_to_update = [], []

            # Sahifadagi mavjud mahsulotlarni bir so'rovda olish
            item_ids = [item['id'] for item in items if 'id' in item]
            existing_products = Product.objects.filter(id__in=item_ids).select_related('document')
            existing_products_map = {p.id: p for p in existing_products}

            for item in items:
                item_id = item.get("id")
                file_url = extract_file_url(item.get("poster_url"))
                file_size_str = item.get("document", {}).get("file_size")

                # Skip if file size > 50MB or no file URL
                if not file_url:
                    invalid_url_count += 1
                    continue
                if file_size_str:
                    file_size_bytes = parse_file_size(file_size_str)
                    if file_size_bytes > 50 * 1024 * 1024:  # 50MB in bytes
                        skipped_large_file_count += 1
                        logger.warning(f"Skipped item {item_id}: File size {file_size_str} exceeds 50MB")
                        continue

                # Agar mahsulot mavjud bo'lsa -> YANGILASH
                if item_id in existing_products_map:
                    product = existing_products_map[item_id]
                    doc = product.document

                    # Ma'lumotlarni yangilash
                    product.title = item.get("title", "")
                    product.slug = item.get("slug", "")
                    doc.json_data = item
                    doc.parse_file_url = file_url  # URL ham yangilanishi mumkin

                    products_to_update.append(product)
                    docs_to_update.append(doc)

                # Agar mahsulot mavjud bo'lmasa -> YARATISH
                else:
                    doc = Document(parse_file_url=file_url, json_data=item)
                    prod = Product(id=item_id, title=item.get("title", ""), slug=item.get("slug", ""), document=doc)

                    docs_to_create.append(doc)
                    products_to_create.append(prod)

            # --- Ma'lumotlar bazasi amaliyotlari ---
            with transaction.atomic():
                # Yaratish
                if docs_to_create:
                    Document.objects.bulk_create(docs_to_create, batch_size=100)
                    Product.objects.bulk_create(products_to_create, batch_size=100)
                    created_count = len(products_to_create)
                    total_created += created_count

                # Yangilash
                if products_to_update:
                    Product.objects.bulk_update(products_to_update, ['title', 'slug'], batch_size=100)
                    Document.objects.bulk_update(docs_to_update, ['json_data', 'parse_file_url'], batch_size=100)
                    updated_count = len(products_to_update)
                    total_updated += updated_count

            # --- Sahifa Statistikasi ---
            logger.info(f"--- Sahifa {page} Statistikasi ---")
            logger.info(f"  - Jami elementlar: {len(items)}")
            logger.info(f"  - Yangi qo'shilganlar: {created_count}")
            logger.info(f"  - Yangilanganlar: {updated_count}")
            logger.info(f"  - O'tkazib yuborildi (yaroqsiz URL): {invalid_url_count}")
            logger.info(f"  - O'tkazib yuborildi (fayl hajmi > 50MB): {skipped_large_file_count}")

            progress.update_progress(page)
            page += 1
            time.sleep(0.02)

    except Exception as e:
        logger.error(f"Parsing jarayonida xato: {e}")
        raise
    finally:
        logger.info(f"{'=' * 20} PARSING YAKUNLANDI {'=' * 20}")
        logger.info(f"Jami qo'shildi: {total_created}")
        logger.info(f"Jami yangilandi: {total_updated}")
        logger.info(
            f"Jami o'tkazib yuborildi (fayl hajmi > 50MB yoki yaroqsiz URL): {invalid_url_count + skipped_large_file_count}")
        logger.info(f"Oxirgi muvaffaqiyatli sahifa: {progress.last_page}")
        logger.info("========= SOFT_UZ_PARSE TASK TUGADI =========")


