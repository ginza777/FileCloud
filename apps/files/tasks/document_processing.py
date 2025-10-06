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
import os
import time
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import requests
from celery import shared_task
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction, DatabaseError
from django.utils import timezone
from elasticsearch import Elasticsearch
from requests.adapters import HTTPAdapter
from tika import parser as tika_parser
from urllib3.util.retry import Retry

from ..models import Document, DocumentImage, DocumentError
from ..utils import make_retry_session

# PIL, pdf2image va requests kutubxonalarini import qilish
try:
    from PIL import Image, ImageDraw, ImageFont
    from pdf2image import convert_from_path, convert_from_bytes
    from pdf2image.exceptions import PDFPageCountError, PDFSyntaxError
except ImportError as e:
    import logging
    logger = logging.getLogger(__name__)
    logger.error(f"Kerakli kutubxona topilmadi: {e}. 'pip install Pillow pdf2image' komandasini ishga tushiring.")
    raise e

# Logger
logger = logging.getLogger(__name__)

# Tika setup
tika_parser.TikaClientOnly = True
tika_parser.TikaServerEndpoint = getattr(settings, 'TIKA_URL', 'http://tika:9998')

# Telegram max file size
TELEGRAM_MAX_FILE_SIZE_BYTES = 49 * 1024 * 1024


def log_document_error(document, error_type, error_message, celery_attempt=1):
    """
    Tushunarli va chiroyli shaklda xatolik yozuvini DocumentError modeliga qo'shadi.
    
    Args:
        document: Document obyekti
        error_type: Xatolik turi (str)
        error_message: Xatolik xabari (str yoki Exception)
        celery_attempt: Celery urinish raqami (int)
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


def add_watermark_to_image(pil_image, text="fayltop.cloud"):
    """
    Rasmga takrorlanuvchi, xira suv belgisini qo'shadi.
    
    Args:
        pil_image: PIL Image obyekti
        text: Suv belgisi matni (str)
    
    Returns:
        PIL.Image: Suv belgisi qo'shilgan rasm
    """
    image = pil_image.convert('RGBA')
    overlay = Image.new('RGBA', image.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)
    width, height = image.size

    # Shriftni loyihadagi 'static/fonts' papkasidan ishonchli tarzda topish
    try:
        font_path = os.path.join(settings.BASE_DIR, 'static', 'fonts', 'DejaVuSans.ttf')
        if not os.path.exists(font_path):
            font = ImageFont.load_default()
        else:
            font = ImageFont.truetype(font_path, max(14, width // 40))
    except Exception:
        font = ImageFont.load_default()

    step = max(120, width // 6)
    alpha = 28  # Xira effekt uchun

    # Matnni diagonal qilib joylashtirish
    for y in range(-height, height, step):
        draw.text((0, y), text, font=font, fill=(255, 255, 255, alpha))

    overlay = overlay.rotate(30, expand=1)
    overlay = overlay.crop((
        (overlay.width - width) // 2,
        (overlay.height - height) // 2,
        (overlay.width + width) // 2,
        (overlay.height + height) // 2
    ))

    combined = Image.alpha_composite(image, overlay)
    return combined.convert('RGB')


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=10, max_retries=3)
def generate_document_images_task(self, document_id: str, max_pages: int = 5):
    """
    Hujjatni yuklaydi, 5 tagacha sahifasini suv belgisi bilan rasmga aylantiradi,
    rasmlarni DocumentImage modeliga saqlaydi va vaqtinchalik faylni o'chiradi.
    
    Args:
        document_id: Hujjat ID'si (str)
        max_pages: Maksimal sahifalar soni (int)
    
    Returns:
        str: Muvaffaqiyat xabari
    """
    doc = Document.objects.get(id=document_id)
    if not doc.parse_file_url:
        return f"Document {document_id} has no file URL. Skipping."

    # Vaqtinchalik faylni to'g'ridan-to'g'ri 'docpic_files' papkasiga yuklaymiz
    ext = Path(doc.parse_file_url).suffix or '.bin'
    work_path = os.path.join(settings.DOCPIC_FILES_DIR, f"{doc.id}{ext}")

    images: list[Image.Image] = []

    try:
        # 1. Faylni yuklab olish
        with make_retry_session().get(doc.parse_file_url, stream=True, timeout=180) as r:
            r.raise_for_status()
            with open(work_path, 'wb') as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)

        # 2. Faylni rasmga aylantirish
        if ext.lower() == '.pdf':
            try:
                images = convert_from_path(work_path, dpi=150, first_page=1, last_page=max_pages)
            except (PDFPageCountError, PDFSyntaxError) as e:
                logger.warning(f"PDF konvertatsiya xatosi (DocID: {doc.id}): {e}")
                pass

        # Agar PDF bo'lmasa yoki PDF xato bo'lsa, boshqa usullarni sinab ko'rish
        if not images:
            try:
                with open(work_path, 'rb') as fb:
                    data = fb.read()
                images = convert_from_bytes(data, dpi=150, first_page=1, last_page=max_pages)
            except Exception as e:
                # Barcha usullar ish bermasa, matnli rasm yaratish
                img = Image.new('RGB', (1024, 1448), color=(245, 247, 250))
                draw = ImageDraw.Draw(img)
                preview_text = (getattr(doc, 'product', None) and doc.product.title or 'Hujjat')[:120]
                draw.text((40, 60), f"{preview_text}\n\n(Rasmli ko'rinish mavjud emas)", fill=(30, 41, 59))
                images = [img]
                logger.warning(f"Bytes konvertatsiya xatosi (DocID: {doc.id}): {e}")

        # 3. Rasmlarni qayta ishlash va saqlash
        for idx, pil_img in enumerate(images[:max_pages], start=1):
            # O'lchamini o'zgartirish (web uchun optimizatsiya)
            w = 1280
            ratio = w / pil_img.width
            h = int(pil_img.height * ratio)
            pil_img = pil_img.resize((w, h), Image.Resampling.LANCZOS)

            # Suv belgisini qo'shish
            wm = add_watermark_to_image(pil_img, text="fayltop.cloud")

            # Xotirada JPEG formatiga o'tkazish
            buf = BytesIO()
            wm.save(buf, format='JPEG', quality=82, progressive=True, optimize=True)
            buf.seek(0)

            filename = f"page_{idx}.jpg"

            # Shu sahifa uchun eski rasmni o'chirish (qayta ishlash holatlari uchun)
            DocumentImage.objects.filter(document=doc, page_number=idx).delete()

            # Yangi rasmni model orqali saqlash
            di = DocumentImage(document=doc, page_number=idx)
            di.image.save(filename, ContentFile(buf.read()), save=True)

    finally:
        # 4. Vaqtinchalik faylni o'chirish
        try:
            if os.path.exists(work_path):
                os.remove(work_path)
        except Exception:
            # Agar o'chirishda xato bo'lsa ham, vazifani to'xtatmaslik
            pass

    return f"Successfully generated {len(images)} images for document {document_id}."


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=20, max_retries=3,
             name='apps.files.tasks.process_document_pipeline')
def process_document_pipeline(self, document_id):
    """
    Hujjatni to'liq pipeline orqali qayta ishlaydi:
    1. Download - Faylni yuklab olish
    2. Parse - Tika orqali parse qilish
    3. Index - Elasticsearch'ga indekslash
    4. Telegram - Telegram'ga yuborish
    5. Delete - Vaqtinchalik faylni o'chirish

    Args:
        document_id: Hujjat ID'si (str)
    """
    try:
        doc = Document.objects.select_related('product').get(id=document_id)
    except Document.DoesNotExist:
        logger.error(f"Document {document_id} not found in pipeline.")
        return

    if doc.pipeline_running and (timezone.now() - doc.updated_at).total_seconds() < 3600:
        logger.warning(f"Pipeline for document {document_id} is already running. Skipping new task.")
        return

    doc.pipeline_running = True
    doc.save(update_fields=['pipeline_running'])

    file_path = None

    try:
        # --- FAYL YO'LINI ANIQLASH ---
        file_name = os.path.basename(urlparse(doc.parse_file_url).path)
        downloads_dir = os.path.join(settings.MEDIA_ROOT, 'downloads')
        os.makedirs(downloads_dir, exist_ok=True)
        file_path = os.path.join(downloads_dir, file_name)

        # --- BOSQICHMA-BOSQICH BAJARISH ---

        # 1. DOWNLOAD
        if doc.download_status != 'completed':
            try:
                logger.info(f"[1. Yuklash] Boshlandi: {document_id} -> {file_path}")
                doc.download_status = 'processing'
                doc.save(update_fields=['download_status'])

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
                log_document_error(doc, 'download', e, self.request.retries + 1)
                raise

        # 2. PARSE (TIKA)
        if doc.parse_status != 'completed':
            try:
                logger.info(f"[2. Parse] Boshlandi: {document_id}")
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
                if not os.path.exists(file_path):
                    logger.warning(f"[4. Telegram] Fayl yo'q, qayta yuklashga harakat qilamiz: {file_path}")
                    try:
                        with make_retry_session().get(doc.parse_file_url, stream=True, timeout=180) as r:
                            r.raise_for_status()
                            with open(file_path, "wb") as f:
                                for chunk in r.iter_content(chunk_size=8192):
                                    f.write(chunk)
                        logger.info(f"[4. Telegram] Fayl qayta yuklandi: {file_path}")
                    except Exception as download_error:
                        raise FileNotFoundError(
                            f"Telegramga yuborish uchun fayl topilmadi va qayta yuklash muvaffaqiyatsiz: {file_path} - {download_error}")

                file_size = os.path.getsize(file_path)
                if file_size > TELEGRAM_MAX_FILE_SIZE_BYTES:
                    doc.telegram_status = 'skipped'
                    doc.save(update_fields=['telegram_status'])
                    logger.warning(f"[4. Telegram] Fayl hajmi katta (>49MB), o'tkazib yuborildi: {doc.id}")
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
                        logger.info(f"[4. Telegram] Muvaffaqiyatli: {document_id}")
                    elif resp_data.get("error_code") == 429:
                        retry_after = int(resp_data.get("parameters", {}).get("retry_after", 5))
                        logger.warning(f"[4. Telegram] Rate limit xatosi, {retry_after}s keyin qayta uriniladi.")
                        raise self.retry(countdown=retry_after + 1)
                    else:
                        raise Exception(f"Telegram API xatosi: {resp_data.get('description')}")

                # # O'CHIRILDI: Keraksiz va takrorlanuvchi "Ideal Holat" tekshiruvi.
                # # Bu mantiq endi faqat modelning save() metodida bo'ladi.
                doc.save(update_fields=['telegram_file_id', 'telegram_status'])

            except Exception as e:
                doc.telegram_status = 'failed'
                doc.save(update_fields=['telegram_status'])
                log_document_error(doc, 'telegram_send', e, self.request.retries + 1)
                raise

        logger.info(f"--- [PIPELINE SUCCESS] ✅ Hujjat ID: {document_id} ---")

    except Exception as pipeline_error:
        logger.error(
            f"[PIPELINE RETRYING] {document_id}: {type(pipeline_error).__name__}. Urinish {self.request.retries + 1}/{self.max_retries + 1}")
        if self.request.retries >= self.max_retries:
            logger.error(f"[PIPELINE FINAL FAIL] {document_id} barcha urinishlardan so'ng ham muvaffaqiyatsiz bo'ldi.")
            with transaction.atomic():
                doc = Document.objects.select_for_update().get(id=document_id)
                doc.pipeline_running = False
                doc.save(update_fields=['pipeline_running'])
            log_document_error(doc, 'other', f"Pipeline final fail: {pipeline_error}", self.request.retries + 1)
        raise

    finally:
        # 5. DELETE va YAKUNIY SAQLASH
        try:
            doc = Document.objects.get(id=document_id)

            has_parsed_content = (
                    hasattr(doc,
                            'product') and doc.product and doc.product.parsed_content and doc.product.parsed_content.strip() != ''
            )
            is_ideal_state = (
                    doc.telegram_file_id and doc.telegram_file_id.strip() != '' and has_parsed_content
            )

            if file_path and os.path.exists(file_path):
                should_delete = (
                        is_ideal_state or (self.request.retries >= self.max_retries)
                )
                if should_delete:
                    try:
                        os.remove(file_path)
                        doc.delete_status = 'completed'
                        logger.info(f"[DELETE] Fayl o'chirildi: {file_path}")
                    except OSError as e:
                        logger.warning(f"[DELETE FAILED] Faylni o'chirishda xatolik: {file_path}, {e}")
                        doc.delete_status = 'failed'

            # Pipeline'ni yakunlaymiz (qulfni ochamiz) va oxirgi holatni saqlaymiz.
            doc.pipeline_running = False

            # O'ZGARTIRILDI: update_fields olib tashlandi.
            # Bu chaqiruv Document.save() metodidagi "Ideal Holat" mantiqini ishga tushiradi
            # va `completed=True` holatini to'g'ri saqlaydi.
            doc.save()

            logger.info(f"[PIPELINE UNLOCK] {document_id} pipeline'dan qulf olindi.")

        except Document.DoesNotExist:
            logger.warning(f"Finally blokida hujjat topilmadi: {document_id}")
        except Exception as final_error:
            logger.error(f"[FINALLY BLOCK ERROR] {document_id}: {final_error}")
            try:
                Document.objects.filter(id=document_id).update(pipeline_running=False)
                logger.info(f"[PIPELINE FORCE UNLOCK] {document_id} pipeline'dan majburiy qulf olindi.")
            except Exception as unlock_error:
                logger.error(f"[PIPELINE FORCE UNLOCK FAILED] {document_id}: {unlock_error}")
