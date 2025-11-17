"""
Document Processing Tasks
=========================

Bu modul hujjatlar bilan bog'liq asosiy task'larni o'z ichiga oladi:
- Document pipeline processing
- Document image generation
- Document error logging

Bu task'lar hujjatlar yuklab olish, parse qilish, indekslash va Telegram'ga yuborish
jarayonlarini boshqaradi.
"""

import logging
import time
from pathlib import Path
from urllib.parse import urlparse

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from elasticsearch import Elasticsearch
from tika import parser as tika_parser

from ..models import Document, DocumentError
from ..utils import make_retry_session, get_valid_arxiv_session

# Logger
logger = logging.getLogger(__name__)

# Tika setup
import os

os.environ['TIKA_SERVER_ENDPOINT'] = getattr(settings, 'TIKA_URL', 'http://tika:9998')
os.environ['TIKA_CLIENT_ONLY'] = 'True'
os.environ['TIKA_SERVER_JAR'] = '/tmp/tika-server.jar'
os.environ['TIKA_SERVER_HOST'] = 'tika'
os.environ['TIKA_SERVER_PORT'] = '9998'

# Telegram max file size
TELEGRAM_MAX_FILE_SIZE_BYTES = 49 * 1024 * 1024


def log_document_error(document, error_type, error_message, celery_attempt=1):
    """
    Tushunarli va chiroyli shaklda xatolik yozuvini DocumentError modeliga qo'shadi.
    """
    try:
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
        # BU LOG XATOLIKNI DB'GA YOZILGANINI TASDIQLAYDI
        logger.info(
            f"[ERROR LOGGED] DocID: {document.id} | Type: {error_type} | Attempt: {celery_attempt} | Message: {error_text}")
    except Exception as e:
        logger.error(f"[ERROR LOGGING FAILED] DocID: {document.id} | Error: {e}")


def block_product_for_access_denied(document, error_message):
    """
    Xatoliklar uchun product ni block qiladi (Access Denied, Timeout, Tika xatolari).
    
    Args:
        document: Document obyekti
        error_message: Xatolik xabari
    """
    try:
        if hasattr(document, 'product') and document.product:
            product = document.product
            product.blocked = True

            # Xatolik turini aniqlash
            error_str = str(error_message).lower()
            if 'access denied' in error_str or '403' in error_str:
                reason = "Access Denied"
            elif 'readtimeout' in error_str or 'timeout' in error_str:
                reason = "Timeout Error"
            elif 'tika' in error_str or 'localhost:9998' in error_str:
                reason = "Tika Server Error"
            elif 'connection' in error_str:
                reason = "Connection Error"
            else:
                reason = "Processing Error"

            product.blocked_reason = f"{reason}: {str(error_message)[:200]}"
            product.blocked_at = timezone.now()
            product.save(update_fields=['blocked', 'blocked_reason', 'blocked_at'])

            logger.warning(
                f"[PRODUCT BLOCKED] DocID: {document.id} | ProductID: {product.id} | "
                f"Title: {product.title[:50]}... | Reason: {reason}"
            )
        else:
            logger.warning(f"[PRODUCT BLOCK SKIP] DocID: {document.id} | Product topilmadi")
    except Exception as e:
        logger.error(f"[PRODUCT BLOCK FAILED] DocID: {document.id} | Error: {e}")


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=30, max_retries=5,
             name='apps.files.tasks.process_document_pipeline')
def process_document_pipeline(self, document_id):
    """
    Hujjatni to'liq pipeline orqali qayta ishlaydi.
    """
    task_id = self.request.id
    start_time = time.time()

    try:
        doc = Document.objects.select_related('product').get(id=document_id)
    except Document.DoesNotExist:
        logger.error(f"[PIPELINE|NOT_FOUND] DocID: {document_id} | TaskID: {task_id}")
        return

    def get_status_string(d):
        return (f"Download: {d.download_status}, Parse: {d.parse_status}, Index: {d.index_status}, "
                f"Telegram: {d.telegram_status}, Delete: {d.delete_status}, Completed: {d.completed}")

    logger.info(
        f"[PIPELINE|START] DocID: {document_id} | TaskID: {task_id} | Urinish: {self.request.retries + 1}/{self.max_retries + 1} | Joriy status: {get_status_string(doc)}")

    if doc.pipeline_running and (timezone.now() - doc.updated_at).total_seconds() < 3600:
        logger.warning(
            f"[PIPELINE|SKIP] DocID: {document_id} | TaskID: {task_id} | Sabab: Pipeline allaqachon ishlamoqda.")
        return

    doc.pipeline_running = True
    doc.save(update_fields=['pipeline_running'])

    file_path = None
    try:
        file_name = os.path.basename(urlparse(doc.parse_file_url).path)
        downloads_dir = os.path.join(settings.MEDIA_ROOT, 'downloads')
        os.makedirs(downloads_dir, exist_ok=True)
        file_path = os.path.join(downloads_dir, file_name)

        # 1. DOWNLOAD
        if doc.download_status == 'completed':  #
            logger.info(f"[PIPELINE|DOWNLOAD_SKIP] DocID: {document_id} | Status allaqachon 'completed'.")  #
        else:
            logger.info(f"[PIPELINE|DOWNLOAD] DocID: {document_id} | Manzil: {file_path}")  #
            try:
                doc.download_status = 'processing'  #
                doc.save(update_fields=['download_status'])  #

                # --- YECHIM: AVTORIZATSIYA (AUTH) MANTIG'I ---

                # Standart, qayta urinishli session yaratamiz
                session = make_retry_session()  #

                # Agar URL arxiv.uz'ga tegishli bo'lsa, cookie qo'shamiz
                if 'arxiv.uz' in doc.parse_file_url:
                    phpsessid = get_valid_arxiv_session()
                    if phpsessid:
                        session.cookies.set('PHPSESSID', phpsessid)
                        logger.info(
                            f"[PIPELINE|DOWNLOAD_AUTH] DocID: {document_id} | Arxiv.uz uchun PHPSESSID qo'shildi.")
                    else:
                        # Agar token topilmasa yoki eskirgan bo'lsa, xatolik berib, vazifani to'xtatamiz
                        raise Exception("Arxiv.uz PHPSESSID topilmadi yoki eskirgan, yuklab bo'lmaydi.")

                # Tayyorlangan session bilan so'rovni yuborish
                with session.get(doc.parse_file_url, stream=True, timeout=180) as r:  #
                    r.raise_for_status()  # 403 xatosini shu yerda ushlaydi #
                    with open(file_path, "wb") as f:  #
                        for chunk in r.iter_content(chunk_size=8192):  #
                            f.write(chunk)  #

                # --- YECHIM TUGADI ---

                doc.download_status = 'completed'  #
                doc.save(update_fields=['download_status'])  #
                logger.info(f"[PIPELINE|DOWNLOAD_SUCCESS] DocID: {document_id}")  #
            except Exception as e:
                logger.error(f"[PIPELINE|DOWNLOAD_FAIL] DocID: {document_id} | Xato: {e}", exc_info=True)  #
                doc.download_status = 'failed'  #
                doc.save(update_fields=['download_status'])  #
                log_document_error(doc, 'download', e, self.request.retries + 1)  #

                # Access Denied va timeout xatolari uchun product ni block qilish
                error_str = str(e).lower()
                if ('access denied' in error_str or '403' in error_str or
                        'readtimeout' in error_str or 'timeout' in error_str or
                        'connection' in error_str):
                    logger.warning(f"[PIPELINE|BLOCKING_ERROR] DocID: {document_id} | Product ni block qilish...")
                    block_product_for_access_denied(doc, e)

                raise  #

        # 2. PARSE (TIKA)
        if doc.parse_status == 'completed':
            logger.info(f"[PIPELINE|PARSE_SKIP] DocID: {document_id} | Status allaqachon 'completed'.")
        else:
            logger.info(f"[PIPELINE|PARSE] DocID: {document_id}")
            try:
                if not os.path.exists(file_path):
                    raise FileNotFoundError(f"Parse qilish uchun fayl topilmadi: {file_path}")
                doc.parse_status = 'processing'
                doc.save(update_fields=['parse_status'])
                parsed = tika_parser.from_file(file_path)
                content = (parsed.get("content") or "").strip()
                with transaction.atomic():
                    product = doc.product
                    product.parsed_content = content
                    product.save(update_fields=['parsed_content'])
                doc.parse_status = 'completed'
                doc.save(update_fields=['parse_status'])
                logger.info(f"[PIPELINE|PARSE_SUCCESS] DocID: {document_id} | {len(content)} ta belgi ajratib olindi.")
            except Exception as e:
                logger.error(f"[PIPELINE|PARSE_FAIL] DocID: {document_id} | Xato: {e}", exc_info=True)
                doc.parse_status = 'failed'
                doc.save(update_fields=['parse_status'])

                # Tika bilan bog'liq muammolarni aniq DocumentError ga yozish
                error_str = str(e).lower()
                error_type = 'parse'  # Default
                error_message = str(e)

                if ('readtimeout' in error_str or 'timeout' in error_str):
                    error_type = 'tika_timeout'
                    error_message = f"Tika Server Timeout: {e}"
                    logger.warning(f"[PIPELINE|TIKA_TIMEOUT] DocID: {document_id} | Product ni block qilish...")
                    block_product_for_access_denied(doc, f"Tika Parse Timeout: {e}")
                elif ('connection' in error_str or 'connect' in error_str or 'localhost:9998' in error_str):
                    error_type = 'tika_connection'
                    error_message = f"Tika Server Connection Error: {e}"
                elif ('tika' in error_str or 'parse' in error_str):
                    error_type = 'tika_parse'
                    error_message = f"Tika Parse Error: {e}"

                # DocumentError ga yozish
                log_document_error(doc, error_type, error_message, self.request.retries + 1)

                raise

        # 3. INDEX (ELASTICSEARCH)
        if doc.index_status == 'completed':
            logger.info(f"[PIPELINE|INDEX_SKIP] DocID: {document_id} | Status allaqachon 'completed'.")
        else:
            logger.info(f"[PIPELINE|INDEX] DocID: {document_id}")
            try:
                doc.index_status = 'processing'
                doc.save(update_fields=['index_status'])
                es_client = Elasticsearch(settings.ES_URL)
                product = doc.product

                # Blocked productlarni Elasticsearch ga index qilmaslik
                if product.blocked:
                    logger.warning(
                        f"[PIPELINE|INDEX_SKIP] DocID: {document_id} | Product blocked, Elasticsearch ga index qilinmaydi.")
                    doc.index_status = 'skipped'
                    doc.save(update_fields=['index_status'])
                    return

                body = {"title": product.title, "slug": product.slug, "parsed_content": product.parsed_content,
                        "document_id": str(doc.id)}
                es_client.index(index=settings.ES_INDEX, id=str(doc.id), document=body)
                doc.index_status = 'completed'
                doc.save(update_fields=['index_status'])
                logger.info(f"[PIPELINE|INDEX_SUCCESS] DocID: {document_id}")
            except Exception as e:
                logger.error(f"[PIPELINE|INDEX_FAIL] DocID: {document_id} | Xato: {e}", exc_info=True)
                doc.index_status = 'failed'
                doc.save(update_fields=['index_status'])
                log_document_error(doc, 'index', e, self.request.retries + 1)
                raise

        # 4. SEND (TELEGRAM)
        if doc.telegram_status == 'completed' or doc.telegram_status == 'skipped':
            logger.info(f"[PIPELINE|TELEGRAM_SKIP] DocID: {document_id} | Status: '{doc.telegram_status}'.")
        else:
            logger.info(f"[PIPELINE|TELEGRAM] DocID: {document_id}")
            try:
                if not os.path.exists(file_path):
                    logger.warning(
                        f"[PIPELINE|TELEGRAM_RE-DOWNLOAD] DocID: {document_id} | Fayl yo'q, qayta yuklanmoqda.")

                    # Standart, qayta urinishli session yaratamiz
                    session = make_retry_session()

                    # Agar URL arxiv.uz'ga tegishli bo'lsa, cookie qo'shamiz
                    if 'arxiv.uz' in doc.parse_file_url:
                        phpsessid = get_valid_arxiv_session()
                        if phpsessid:
                            session.cookies.set('PHPSESSID', phpsessid)
                            logger.info(
                                f"[PIPELINE|TELEGRAM_RE-DOWNLOAD_AUTH] DocID: {document_id} | Arxiv.uz uchun PHPSESSID qo'shildi.")
                        else:
                            raise Exception("Arxiv.uz PHPSESSID topilmadi yoki eskirgan, yuklab bo'lmaydi.")

                    with session.get(doc.parse_file_url, stream=True, timeout=180) as r:
                        r.raise_for_status()
                        with open(file_path, "wb") as f:
                            for chunk in r.iter_content(chunk_size=8192):
                                f.write(chunk)
                    logger.info(f"[PIPELINE|TELEGRAM_RE-DOWNLOAD_SUCCESS] DocID: {document_id}")

                file_size = os.path.getsize(file_path)
                if file_size > TELEGRAM_MAX_FILE_SIZE_BYTES:
                    doc.telegram_status = 'skipped'
                    doc.save(update_fields=['telegram_status'])
                    logger.warning(
                        f"[PIPELINE|TELEGRAM_SKIPPED] DocID: {doc.id} | Sabab: Fayl hajmi katta ({file_size / 1024 / 1024:.2f} MB).")
                else:
                    from .telegram_tasks import wait_for_telegram_rate_limit
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
                        doc.save(update_fields=['telegram_file_id', 'telegram_status'])
                        logger.info(f"[PIPELINE|TELEGRAM_SUCCESS] DocID: {document_id}")
                    elif resp_data.get("error_code") == 429:
                        retry_after = int(resp_data.get("parameters", {}).get("retry_after", 5))
                        logger.warning(
                            f"[PIPELINE|TELEGRAM_RATE_LIMIT] DocID: {document_id} | {retry_after}s keyin qayta uriniladi.")
                        # Rate limit uchun uzoqroq kutish va exponential backoff
                        wait_time = min(retry_after + (self.request.retries * 2), 30)
                        time.sleep(wait_time)
                        raise self.retry(countdown=wait_time + 5)
                    else:
                        raise Exception(f"Telegram API xatosi: {resp_data.get('description')}")
            except Exception as e:
                logger.error(f"[PIPELINE|TELEGRAM_FAIL] DocID: {document_id} | Xato: {e}", exc_info=True)
                doc.telegram_status = 'failed'
                doc.save(update_fields=['telegram_status'])
                log_document_error(doc, 'telegram_send', e, self.request.retries + 1)
                raise

    except Exception as pipeline_error:
        logger.error(
            f"[PIPELINE|RETRYING] DocID: {document_id} | TaskID: {task_id} | Urinish: {self.request.retries + 1}/{self.max_retries + 1} | Sabab: {type(pipeline_error).__name__}")
        if self.request.retries >= self.max_retries:
            logger.critical(
                f"[PIPELINE|FINAL_FAIL] DocID: {document_id} | TaskID: {task_id} | Barcha urinishlar muvaffaqiyatsiz.")
            with transaction.atomic():
                doc_fail = Document.objects.select_for_update().get(id=document_id)
                doc_fail.pipeline_running = False
                doc_fail.save(update_fields=['pipeline_running'])
            log_document_error(doc, 'pipeline_final_fail', f"Pipeline final fail: {pipeline_error}",
                               self.request.retries + 1)
        raise

    finally:
        logger.info(f"[PIPELINE|FINALLY] DocID: {document_id} | TaskID: {task_id} | Yakuniy ishlarni bajarish.")
        try:
            doc = Document.objects.get(id=document_id)
            if file_path and os.path.exists(file_path):
                # Faylni o'chirish faqat barcha bosqichlar muvaffaqiyatli yakunlanganda yoki barcha urinishlar tugaganda amalga oshiriladi.
                is_fully_completed = doc.download_status == 'completed' and \
                                     doc.parse_status == 'completed' and \
                                     doc.index_status == 'completed' and \
                                     (doc.telegram_status == 'completed' or doc.telegram_status == 'skipped')

                if is_fully_completed or self.request.retries >= self.max_retries:
                    try:
                        os.remove(file_path)
                        doc.delete_status = 'completed'
                        logger.info(f"[PIPELINE|DELETE_SUCCESS] DocID: {document_id} | Fayl o'chirildi: {file_path}")
                    except OSError as e:
                        logger.warning(f"[PIPELINE|DELETE_FAIL] DocID: {document_id} | Faylni o'chirishda xatolik: {e}")
                        doc.delete_status = 'failed'
                else:
                    logger.info(
                        f"[PIPELINE|DELETE_SKIP] DocID: {document_id} | Fayl keyingi urinishlar uchun saqlab qolindi.")

            # Check if all steps are completed and set completed=True
            is_fully_completed = doc.download_status == 'completed' and \
                                 doc.parse_status == 'completed' and \
                                 doc.index_status == 'completed' and \
                                 (doc.telegram_status == 'completed' or doc.telegram_status == 'skipped')

            if is_fully_completed:
                doc.completed = True
                logger.info(
                    f"[PIPELINE|COMPLETED] DocID: {document_id} | Barcha jarayonlar tugatildi, completed=True qo'yildi.")

            doc.pipeline_running = False
            doc.save()  # Bu barcha o'zgarishlarni, jumladan, `completed` holatini saqlaydi.

            end_time = time.time()
            duration = round(end_time - start_time, 2)
            logger.info(
                f"--- [PIPELINE|END] --- DocID: {document_id} | TaskID: {task_id} | Davomiyligi: {duration}s | Yakuniy status: {get_status_string(doc)}")

        except Document.DoesNotExist:
            logger.warning(f"[FINALLY|NOT_FOUND] DocID: {document_id}")
        except Exception as final_error:
            logger.error(f"[FINALLY|FATAL_ERROR] DocID: {document_id} | Xato: {final_error}", exc_info=True)
            try:
                # Agar `finally` blokida xatolik bo'lsa ham, qulfni ochishga harakat qilish
                Document.objects.filter(id=document_id).update(pipeline_running=False)
                logger.warning(f"[PIPELINE|FORCE_UNLOCK] DocID: {document_id} | Pipeline majburan qulfdan ochildi.")
            except Exception as unlock_error:
                logger.critical(
                    f"[PIPELINE|FORCE_UNLOCK_FAIL] DocID: {document_id} | Qulfdan ochish ham muvaffaqiyatsiz bo'ldi: {unlock_error}")
