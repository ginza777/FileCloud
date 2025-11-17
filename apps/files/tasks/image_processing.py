import os
import tempfile
import requests
import logging
from io import BytesIO

from celery import shared_task
from django.core.files.base import ContentFile
from django.conf import settings
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

# Katta rasmlar uchun maksimal o'lcham
Image.MAX_IMAGE_PIXELS = None


# ----------------------------------------------------
# YORDAMCHI FUNKSIYALAR
# ----------------------------------------------------

def _get_temp_file_path(doc):
    """Vaqtinchalik fayl yo'lini va nomini generatsiya qiladi"""
    file_ext = os.path.splitext(doc.file_name)[1].lower() if doc.file_name else ".dat"
    fd, temp_path = tempfile.mkstemp(suffix=file_ext)
    os.close(fd)
    return temp_path


def parse_file_url(doc: Document, temp_path: str) -> bool:
    """
    Hujjatni URL orqali bardoshli (robust) tarzda yuklab oladi.
    Tarmoq xatolariga qarshi qayta urinish (retry) mexanizmidan foydalanadi.
    """
    if not doc.url:
        logger.warning(f"[DOWNLOAD|SKIP] DocID: {doc.id} | URL mavjud emas.")
        return False

    # Qayta urinish (Retry) strategiyasini sozlash
    retry_strategy = Retry(
        total=3,  # Jami urinishlar soni
        backoff_factor=1,  # Urinishlar orasidagi kutish vaqti (1s, 2s, 4s)
        status_forcelist=[429, 500, 502, 503, 504],  # Qaysi xatolarda qayta urinish kerak
        allowed_methods=["GET"]
    )

    # Sessiya yaratish
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    try:
        # Faylni stream (oqim) rejimida yuklash
        with session.get(doc.url, stream=True, timeout=30) as response:
            # Xato status kodini tekshirish (masalan, 404 Not Found)
            response.raise_for_status()

            # Faylni vaqtinchalik joyga qismlarga bo'lib yozish
            with open(temp_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):  # 8KB
                    if chunk:
                        f.write(chunk)

        logger.info(f"[DOWNLOAD|SUCCESS] DocID: {doc.id} | Fayl URL orqali yuklandi.")
        return True

    except requests.exceptions.HTTPError as e:
        logger.error(f"[DOWNLOAD|HTTP_ERROR] DocID: {doc.id} | URL: {doc.url} | Status: {e.response.status_code}")
        return False
    except requests.exceptions.RequestException as e:
        # Boshqa barcha tarmoq xatolari (Timeout, ConnectionError)
        logger.error(f"[DOWNLOAD|NETWORK_ERROR] DocID: {doc.id} | URL: {doc.url} | Xato: {e}")
        return False
    except Exception as e:
        # Kutilmagan boshqa xatolar
        logger.error(f"[DOWNLOAD|UNEXPECTED_ERROR] DocID: {doc.id} | Xato: {e}", exc_info=True)
        return False


def _save_preview_images(doc, pil_image: Image, page_num: int):
    """
    Bitta PIL Rasm obyektini Katta (1200px) va Kichik (300px)
    formatda WebP qilib saqlaydi va DocumentImage modeliga kiritadi.
    """
    # ... (Bu funksiya o'zgarishsiz qoladi, avvalgi javobdagidek) ...
    img_name_base = f"doc_{doc.id}_page_{page_num}.webp"

    img_large_bytes = BytesIO()
    large_image = pil_image.copy()
    large_image.thumbnail((1200, 1200))
    large_image.save(img_large_bytes, format='WEBP', quality=75)

    img_small_bytes = BytesIO()
    small_image = pil_image.copy()
    small_image.thumbnail((300, 300))
    small_image.save(img_small_bytes, format='WEBP', quality=60)

    doc_image, created = DocumentImage.objects.update_or_create(
        document=doc,
        page_number=page_num,
        defaults={}
    )

    doc_image.image_large.save(img_name_base, ContentFile(img_large_bytes.getvalue()), save=False)
    doc_image.image_small.save(img_name_base, ContentFile(img_small_bytes.getvalue()), save=False)
    doc_image.save()
    logger.info(f"[ImageSave] DocID {doc.id} Page {page_num} rasmlari saqlandi.")


def handle_pdf(doc: Document, file_path: str):
    """PDF fayllarni qayta ishlaydi va sahifalarni rasmga aylantiradi"""
    # ... (Bu funksiya o'zgarishsiz qoladi, avvalgi javobdagidek) ...
    doc.file_size = os.path.getsize(file_path)
    info = pdfinfo_from_path(file_path)
    doc.page_count = info.get("Pages", 0)

    images = convert_from_path(file_path, first_page=1, last_page=5, fmt='jpeg')

    for i, image in enumerate(images):
        _save_preview_images(doc, image, i + 1)

    logger.info(f"[Handler] Success (PDF): {doc.title} | {len(images)} ta rasm generatsiya qilindi.")


def handle_image(doc: Document, file_path: str):
    """Rasm fayllarni qayta ishlaydi (o'zini 'preview' sifatida saqlaydi)"""
    # ... (Bu funksiya o'zgarishsiz qoladi, avvalgi javobdagidek) ...
    doc.file_size = os.path.getsize(file_path)
    doc.page_count = 1

    with Image.open(file_path) as image:
        image = image.convert('RGB')
        _save_preview_images(doc, image, 1)

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
        # 1. Faylni YANGI FUNKSIYA orqali yuklab olish
        if not parse_file_url(doc, temp_file_path):
            raise Exception("Faylni yuklab bo'lmadi (URL xato yoki tarmoq muammosi).")

        file_ext = os.path.splitext(doc.file_name)[1].lower()

        # 2. Fayl turiga qarab rasmlarni generatsiya qilish

        if file_ext == '.pdf' and PDF_SUPPORT:
            handle_pdf(doc, temp_file_path)

        elif file_ext in ['.jpg', '.jpeg', '.png', '.webp']:
            handle_image(doc, temp_file_path)

        else:
            # Rasm generatsiyasi qo'llab-quvvatlanmagan turlar uchun
            doc.file_size = os.path.getsize(temp_file_path)
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