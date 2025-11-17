import logging
import os
import shutil
import subprocess
import tempfile
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import requests
from celery import shared_task
from django.conf import settings
from django.core.files.base import ContentFile
from PIL import Image
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Rasm generatsiyasi uchun kerakli kutubxonalar
try:
    from pdf2image import convert_from_path, pdfinfo_from_path
    from pdf2image.exceptions import PDFPageCountError, PDFSyntaxError

    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False

# Logger
logger = logging.getLogger(__name__)

# Modellar
from apps.files.models import Document, DocumentImage
from apps.files.utils import make_retry_session, get_valid_arxiv_session

# Katta rasmlar uchun maksimal o'lcham
Image.MAX_IMAGE_PIXELS = None

MAX_PREVIEW_PAGES = 5


# ----------------------------------------------------
# YORDAMCHI FUNKSIYALAR
# ----------------------------------------------------

def _get_temp_file_path(doc):
    """Vaqtinchalik fayl yo'lini va nomini generatsiya qiladi"""
    file_ext = Path(doc.file_name).suffix or ".dat"
    fd, temp_path = tempfile.mkstemp(suffix=file_ext)
    os.close(fd)
    return temp_path


def _download_document_file(doc: Document, temp_path: str) -> bool:
    """
    Hujjatni parse_file_url orqali yuklab oladi va vaqtinchalik faylga saqlaydi.
    Arxiv.uz uchun PHPSESSID cookie qo'llab-quvvatlanadi.
    """
    if not doc.parse_file_url:
        logger.warning(f"[DOWNLOAD|SKIP] DocID: {doc.id} | URL mavjud emas.")
        return False

    session = make_retry_session()
    parsed_url = doc.parse_file_url.lower()

    if 'arxiv.uz' in parsed_url:
        phpsessid = get_valid_arxiv_session()
        if phpsessid:
            session.cookies.set('PHPSESSID', phpsessid)
            logger.debug(f"[DOWNLOAD|AUTH] DocID: {doc.id} | Arxiv.uz PHPSESSID qo'shildi.")
        else:
            logger.error(f"[DOWNLOAD|AUTH_FAIL] DocID: {doc.id} | Arxiv.uz sessiyasi topilmadi.")
            return False

    try:
        with session.get(doc.parse_file_url, stream=True, timeout=180) as response:
            response.raise_for_status()
            with open(temp_path, 'wb') as temp_file:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        temp_file.write(chunk)

        logger.info(f"[DOWNLOAD|SUCCESS] DocID: {doc.id} | Fayl yuklandi.")
        return True
    except requests.exceptions.HTTPError as e:
        logger.error(f"[DOWNLOAD|HTTP_ERROR] DocID: {doc.id} | Status: {e.response.status_code}")
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"[DOWNLOAD|NETWORK_ERROR] DocID: {doc.id} | Xato: {e}")
        return False
    except Exception as e:
        logger.error(f"[DOWNLOAD|UNEXPECTED_ERROR] DocID: {doc.id} | Xato: {e}", exc_info=True)
        return False


def _convert_office_to_pdf(source_path: str) -> str | None:
    """
    LibreOffice yordamida ofis fayllarini PDF ga konvertatsiya qiladi.
    """
    output_dir = tempfile.mkdtemp(prefix="doc_pdf_")
    try:
        result = subprocess.run(
            [
                'libreoffice',
                '--headless',
                '--convert-to',
                'pdf',
                '--outdir',
                output_dir,
                source_path
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=180
        )
        if result.returncode != 0:
            logger.error(f"[CONVERT|FAIL] LibreOffice return code {result.returncode}: {result.stderr.decode('utf-8', 'ignore')}")
            return None

        pdf_files = list(Path(output_dir).glob('*.pdf'))
        if not pdf_files:
            logger.error("[CONVERT|FAIL] PDF fayl topilmadi.")
            return None

        pdf_path = str(pdf_files[0])
        logger.info(f"[CONVERT|SUCCESS] {source_path} -> {pdf_path}")
        return pdf_path
    except subprocess.TimeoutExpired:
        logger.error("[CONVERT|TIMEOUT] LibreOffice konvertatsiya vaqtida timeout.")
        return None
    except Exception as e:
        logger.error(f"[CONVERT|ERROR] Faylni PDF ga o'tkazishda xatolik: {e}")
        return None
    finally:
        # Temporary faylni keyinchalik tozalash uchun direktoriyani qaytaramiz.
        # O'chirish generate_document_previews ichida amalga oshiriladi.
        pass


def _save_preview_images(doc, pil_image: Image, page_num: int, *, save_small: bool):
    """
    Bitta PIL Rasm obyektini WebP formatda saqlaydi.

    Args:
        doc (Document): Hujjat
        pil_image (Image): PIL image instance
        page_num (int): Sahifa raqami
        save_small (bool): Kichik rasm ham saqlansinmi
    """
    img_name_base = f"doc_{doc.id}_page_{page_num}.webp"

    img_large_bytes = BytesIO()
    large_image = pil_image.copy()
    large_image.thumbnail((1200, 1200))
    large_image.save(img_large_bytes, format='WEBP', quality=75)

    doc_image, _ = DocumentImage.objects.update_or_create(
        document=doc,
        page_number=page_num,
        defaults={}
    )

    doc_image.image_large.save(
        img_name_base,
        ContentFile(img_large_bytes.getvalue()),
        save=False
    )

    if save_small:
        img_small_bytes = BytesIO()
        small_image = pil_image.copy()
        small_image.thumbnail((300, 300))
        small_image.save(img_small_bytes, format='WEBP', quality=60)
        doc_image.image_small.save(
            img_name_base,
            ContentFile(img_small_bytes.getvalue()),
            save=False
        )
    else:
        if doc_image.image_small:
            doc_image.image_small.delete(save=False)
            doc_image.image_small = None

    doc_image.save()
    logger.info(
        f"[ImageSave] DocID {doc.id} Page {page_num} "
        f"{'large+small' if save_small else 'large only'} rasmlari saqlandi."
    )


def handle_pdf(doc: Document, file_path: str, max_pages: int = MAX_PREVIEW_PAGES, original_file_size: int | None = None):
    """PDF fayllarni qayta ishlaydi va sahifalarni rasmga aylantiradi"""
    doc.file_size = original_file_size or os.path.getsize(file_path)
    info = pdfinfo_from_path(file_path)
    doc.page_count = info.get("Pages", 0)

    images = convert_from_path(
        file_path,
        first_page=1,
        last_page=min(max_pages, doc.page_count or max_pages),
        fmt='jpeg'
    )

    for i, image in enumerate(images):
        _save_preview_images(doc, image, i + 1, save_small=(i == 0))

    logger.info(f"[Handler] Success (PDF): {doc.file_name} | {len(images)} ta rasm generatsiya qilindi.")


def handle_image(doc: Document, file_path: str):
    """Rasm fayllarni qayta ishlaydi (o'zini 'preview' sifatida saqlaydi)"""
    # ... (Bu funksiya o'zgarishsiz qoladi, avvalgi javobdagidek) ...
    doc.file_size = os.path.getsize(file_path)
    doc.page_count = 1

    with Image.open(file_path) as image:
        image = image.convert('RGB')
        _save_preview_images(doc, image, 1, save_small=True)

    logger.info(f"[Handler] Success (Image): {doc.title} | 1 ta rasm saqlandi.")


# ----------------------------------------------------
# ASOSIY TASK
# ----------------------------------------------------

@shared_task(name="generate_document_previews")
def generate_document_previews(document_id):
    """
    Bitta hujjat faylini yuklaydi, o'lchamlarini saqlaydi va
    sahifa rasmlarini (kichik va katta) generatsiya qiladi.
    """
    try:
        doc = Document.objects.get(id=document_id)
    except Document.DoesNotExist:
        logger.warning(f"[ImageTask] DocID {document_id} topilmadi.")
        return

    logger.info(f"--- [ImageTask|START] --- DocID: {document_id} ({doc.file_name})")

    if doc.images.exists() and doc.file_size:
        logger.info(f"[ImageTask] DocID {document_id} uchun rasmlar va o'lcham allaqachon mavjud.")
        return

    temp_file_path = _get_temp_file_path(doc)

    try:
        doc.images.all().delete()

        # 1. Faylni yuklab olish
        if not _download_document_file(doc, temp_file_path):
            raise Exception("Faylni yuklab bo'lmadi (URL xato yoki tarmoq muammosi).")

        file_ext = Path(doc.file_name).suffix.lower()
        converted_pdf_path = None

        # 2. Fayl turiga qarab rasmlarni generatsiya qilish

        original_size = os.path.getsize(temp_file_path)

        if file_ext == '.pdf' and PDF_SUPPORT:
            handle_pdf(doc, temp_file_path, original_file_size=original_size)

        elif file_ext in ['.jpg', '.jpeg', '.png', '.webp']:
            handle_image(doc, temp_file_path)

        else:
            converted_pdf_path = _convert_office_to_pdf(temp_file_path)
            if converted_pdf_path and PDF_SUPPORT:
                handle_pdf(doc, converted_pdf_path, original_file_size=original_size)
            else:
                doc.file_size = original_size
                doc.page_count = 1  # Taxminiy
                logger.info(f"[ImageTask] DocID {doc.id} ({file_ext}) rasm generatsiyasini qo'llab-quvvatlamaydi.")

        # O'lchamlarni saqlash
        doc.save(update_fields=['file_size', 'page_count'])
        logger.info(f"--- [ImageTask|END] --- DocID: {document_id} | Size: {doc.file_size} | Pages: {doc.page_count}")

    except Exception as e:
        logger.error(f"[ImageTask|ERROR] DocID {document_id} da xatolik: {e}", exc_info=True)
        # Xatolik bo'lsa va fayl yuklangan bo'lsa, hech bo'lmaganda o'lchamni saqlashga urinish
        if os.path.exists(temp_file_path) and not doc.file_size:
            try:
                doc.file_size = os.path.getsize(temp_file_path)
                doc.page_count = 1  # Taxminiy
                doc.save(update_fields=['file_size', 'page_count'])
            except Exception as save_e:
                logger.error(
                    f"[ImageTask|SAVE_ERROR] DocID {document_id} xatolik vaqtida o'lchamni saqlashda xato: {save_e}")

    finally:
        # Vaqtinchalik faylni o'chirish
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        if 'converted_pdf_path' in locals() and converted_pdf_path and os.path.exists(converted_pdf_path):
            converted_dir = Path(converted_pdf_path).parent
            try:
                shutil.rmtree(converted_dir, ignore_errors=True)
            except Exception:
                pass