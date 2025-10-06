"""
Parsing Tasks
=============

Bu modul parsing bilan bog'liq task'larni o'z ichiga oladi:
- Soft.uz parsing
- Arxiv.uz parsing
- Document processing

Bu task'lar turli saytlardan ma'lumotlarni parse qilish va hujjatlarni qayta ishlash uchun ishlatiladi.
"""

import logging
import re
import time
import requests
from math import ceil
from celery import shared_task
from django.db import transaction
from django.utils import timezone

from ..models import Document, Product, SiteToken, ParseProgress
from ..utils import get_valid_soff_token
from .document_processing import process_document_pipeline

# Logger
logger = logging.getLogger(__name__)


@shared_task(name="apps.files.tasks.soft_uz_process_documents")
def soft_uz_process_documents():
    """
    Hujjatlarni holatini tekshirib, kerak bo'lsa tozalab, qayta ishlash uchun pipeline'ga yuboradi.
    Bu task dparse komandasining funksiyasini bajaradi.
    
    Bu task:
    - Pipeline ishlamayotgan hujjatlarni topadi
    - Ideal holatdagi hujjatlarni yakunlaydi
    - Pending holatdagi hujjatlarni qayta tiklaydi
    - Celery pipeline'ga yuboradi
    
    Returns:
        str: Processing natijasi xabari
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

                # IDEAL HOLAT QOIDASI (4 shart):
                # 1. parsed_content mavjud va bo'sh emas
                # 2. telegram_file_id mavjud va bo'sh emas
                # 3. pipeline_running = False
                # 4. index_status = 'completed'

                has_parsed_content = (
                        hasattr(locked_doc, 'product') and
                        locked_doc.product is not None and
                        locked_doc.product.parsed_content is not None and
                        locked_doc.product.parsed_content.strip() != ''
                )

                has_telegram_file = (
                        locked_doc.telegram_file_id is not None and
                        locked_doc.telegram_file_id.strip() != ''
                )

                is_indexed = (locked_doc.index_status == 'completed')
                pipeline_not_running = (not locked_doc.pipeline_running)

                is_ideal_state = (
                        has_parsed_content and has_telegram_file and
                        is_indexed and pipeline_not_running
                )

                if is_ideal_state:
                    # IDEAL HOLAT: Barcha statuslarni completed qilamiz
                    locked_doc.completed = True
                    locked_doc.pipeline_running = False
                    locked_doc.download_status = 'completed'
                    locked_doc.parse_status = 'completed'
                    locked_doc.index_status = 'completed'
                    locked_doc.telegram_status = 'completed'
                    locked_doc.delete_status = 'completed'
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
    
    Bu task:
    - Soff.uz saytidan ma'lumotlarni oladi
    - Mavjud mahsulotlarni yangilaydi
    - Yangi mahsulotlarni qo'shadi
    - Parse progress'ni kuzatadi
    
    Returns:
        str: Parsing natijasi xabari
    """
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


@shared_task(name="apps.files.tasks.arxiv_uz_parse")
def arxiv_uz_parse():
    """
    Arxiv.uz saytidan ma'lumotlarni oladi, mavjudlarini yangilaydi va yangilarini qo'shadi.
    Bu task parse_arxivuz komandasining funksiyasini bajaradi.
    
    Bu task:
    - Arxiv.uz saytidan ma'lumotlarni oladi
    - Turli kategoriyalarni skanerlaydi
    - Mavjud hujjatlarni yangilaydi
    - Yangi hujjatlarni qo'shadi
    - Celery pipeline'ga yuboradi
    
    Returns:
        str: Parsing natijasi xabari
    """
    logger.info("========= ARXIV_UZ_PARSE TASK BOSHLANDI =========")

    # Asosiy URL'lar
    BASE_URLS = [
        "https://arxiv.uz/documents/dars-ishlanmalar/",
        "https://arxiv.uz/documents/diplom-ishlar/",
        "https://arxiv.uz/documents/darsliklar/",
        "https://arxiv.uz/documents/slaydlar/",
        "https://arxiv.uz/documents/referatlar/",
        "https://arxiv.uz/documents/kurs-ishlari/",
    ]

    # Sub-kataloglar
    SUB_CATEGORIES = [
        "adabiyot", "algebra", "anatomiya", "arxitektura", "astronomiya", "biologiya",
        "biotexnologiya", "botanika", "chizmachilik", "chqbt", "davlat-tilida-ish-yuritish",
        "dinshunoslik-asoslari", "ekologiya", "energetika", "falsafa", "fizika",
        "fransuz-tili", "geodeziya", "geografiya", "geologiya", "geometriya", "huquqshunoslik",
        "informatika-va-at", "ingliz-tili", "iqtisodiyot", "issiqlik-texnikasi", "jismoniy-tarbiya",
        "kimyo", "konchilik-ishi", "madaniyatshunoslik", "maktabgacha-va-boshlang-ich-ta-lim",
        "manaviyat-asoslari", "mashinasozlik", "materialshunoslik", "mehnat", "melioratsiya",
        "metrologiya", "mexanika", "milliy-istiqlol-g-oyasi", "musiqa", "nemis-tili",
        "o-qish", "odam-va-uning-salomatligi", "odobnoma", "oziq-ovqat-texnologiyasi",
        "pedagogik-psixologiya", "prezident-asarlari", "psixologiya", "psixologiya-1",
        "qishloq-va-o-rmon-xo-jaligi", "radiotexnika", "rus-tili-va-adabiyoti", "san-at",
        "siyosatshunoslik", "sotsiologiya", "suv-xo-jaligi", "tabiatshunoslik", "tarix",
        "tasviriy-san-at", "texnika-va-texnologiya", "tibbiyot", "tilshunoslik",
        "to-qimachilik", "transport", "valeologiya", "xayot-faoliyati-xavfsizligi", "zoologiya"
    ]

    try:
        # SiteToken dan PHPSESSID ni olish
        site_token = SiteToken.objects.get(name='arxiv')
        phpsessid = site_token.auth_token
        if not phpsessid:
            logger.error("SiteToken.auth_token bo'sh!")
            return
    except SiteToken.DoesNotExist:
        logger.error("SiteToken 'arxiv' topilmadi!")
        return

    # Headers va cookies sozlash
    headers = {
        'accept': 'application/json, text/plain, */*',
        'accept-language': 'en-US,en;q=0.9',
        'priority': 'u=1, i',
        'sec-ch-ua': '"Chromium";v="140", "Not=A?Brand";v="24", "Google Chrome";v="140"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"macOS"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
    }

    cookies = {
        'PHPSESSID': phpsessid,
    }

    # Parse progress ni olish
    progress = ParseProgress.get_current_progress()

    # Statistika uchun hisoblagichlar
    total_documents_processed = 0
    new_documents_created = 0
    existing_documents_updated = 0
    documents_queued_for_processing = 0
    total_urls_processed = 0
    total_pages_processed = 0
    successful_urls = 0
    failed_urls = 0

    for base_url in BASE_URLS:
        logger.info(f"Kategoriya: {base_url}")

        for sub_category in SUB_CATEGORIES:
            logger.info(f"Sub-kategoriya: {sub_category}")

            # Referer'ni dinamik sozlash
            headers[
                'referer'] = f"https://arxiv.uz/uz/documents/{sub_category.split('/')[-1]}/{sub_category.split('/')[-1]}"

            page = 1
            page_size = 10
            url_success = True

            while True:
                api_url = f"{base_url}{sub_category}?page={page}&pageSize={page_size}"
                total_urls_processed += 1

                try:
                    logger.info(f"Sahifa {page}: {api_url}")
                    # Serverga yukni kamaytirish uchun qo'shimcha pauza
                    time.sleep(2)  # Sahifalar orasida 2 soniya kutish
                    response = requests.get(api_url, headers=headers, cookies=cookies, timeout=15)
                    response.raise_for_status()

                    try:
                        data = response.json()
                    except ValueError as e:
                        logger.error(f"JSON xatosi: {e}")
                        failed_urls += 1
                        url_success = False
                        break

                    documents = data.get("documents", [])
                    if not documents:
                        logger.info(f"Hujjatlar yo'q: {api_url}")
                        successful_urls += 1
                        total_pages_processed += 1
                        break

                    # Har bir hujjatni qayta ishlash
                    for doc_data in documents:
                        try:
                            with transaction.atomic():
                                # Hujjat ma'lumotlarini olish
                                doc_id = doc_data.get("id")
                                slug = doc_data.get("slug")
                                title = doc_data.get("title", slug)
                                uploaded_at = doc_data.get("uploadedAt")

                                # Metadata
                                metadata = doc_data.get("metadata", {})
                                file_info = metadata.get("file", {})
                                file_size = file_info.get("size", 0)
                                file_extension = file_info.get("extension", "")

                                # Category va Subject
                                category_info = doc_data.get("category", {})
                                subject_info = doc_data.get("subject", {})

                                # Download URL ni yaratish
                                category_slug = category_info.get("slug")
                                subject_slug = subject_info.get("slug")

                                if slug and category_slug and subject_slug:
                                    download_url = f"https://arxiv.uz/uz/download/{category_slug}/{subject_slug}/{slug}"
                                else:
                                    download_url = None

                                # Mavjud hujjatni tekshirish
                                existing_doc = None
                                try:
                                    # Slug orqali qidirish
                                    existing_doc = Document.objects.get(json_data__slug=slug)
                                except Document.DoesNotExist:
                                    pass

                                if existing_doc:
                                    # Mavjud hujjatni yangilash
                                    existing_doc.json_data = doc_data
                                    existing_doc.parse_file_url = download_url
                                    existing_doc.save()

                                    # Product ni ham yangilash
                                    try:
                                        product = existing_doc.product
                                        product.title = title
                                        product.slug = slug
                                        product.save()
                                    except Product.DoesNotExist:
                                        # Agar Product yo'q bo'lsa, yaratamiz
                                        Product.objects.create(
                                            id=hash(slug) % (2 ** 31),  # Integer ID uchun hash
                                            title=title,
                                            slug=slug,
                                            document=existing_doc
                                        )

                                    existing_documents_updated += 1
                                    logger.info(f"Yangilandi: {title}")
                                else:
                                    # Yangi hujjat yaratish
                                    new_doc = Document.objects.create(
                                        parse_file_url=download_url,
                                        json_data=doc_data,
                                        download_status='pending',
                                        parse_status='pending',
                                        index_status='pending',
                                        telegram_status='pending',
                                        delete_status='pending'
                                    )

                                    # Yangi Product yaratish
                                    Product.objects.create(
                                        id=hash(slug) % (2 ** 31),  # Integer ID uchun hash
                                        title=title,
                                        slug=slug,
                                        document=new_doc
                                    )

                                    # Celery orqali qayta ishlash uchun navbatga qo'shish
                                    process_document_pipeline.apply_async(args=[new_doc.id])

                                    new_documents_created += 1
                                    documents_queued_for_processing += 1
                                    logger.info(f"Yangi: {title} (ID: {new_doc.id})")

                                total_documents_processed += 1

                        except Exception as e:
                            logger.error(f"Hujjatni qayta ishlashda xato: {e}")
                            continue

                    # Sahifa ma'lumotlarini tekshirish
                    total = data.get("total", 0)
                    total_pages = ceil(total / page_size)
                    logger.info(f"Sahifa {page}/{total_pages}, Jami hujjatlar: {total}")

                    successful_urls += 1
                    total_pages_processed += 1

                    if page >= total_pages:
                        break

                    page += 1
                    # Har bir sahifa orasida qo'shimcha pauza
                    time.sleep(3)  # Sahifalar orasida 3 soniya kutish

                except requests.RequestException as e:
                    logger.error(f"So'rov xatosi: {e}")
                    failed_urls += 1
                    url_success = False
                    # Xato bo'lsa ham qo'shimcha pauza
                    time.sleep(5)  # Xato bo'lsa 5 soniya kutish
                    break

            # Progress ni yangilash
            progress.update_progress(page)

            # Sub-kategoriya tugaganidan keyin qo'shimcha pauza
            if url_success:
                logger.info(f"Sub-kategoriya tugadi: {sub_category}")
            else:
                logger.info(f"Sub-kategoriyada xato: {sub_category}")
            time.sleep(2)  # Sub-kategoriyalar orasida 2 soniya kutish

    logger.info("========= ARXIV_UZ_PARSE TASK TUGADI =========")
    logger.info(f"Jami qayta ishlangan hujjatlar: {total_documents_processed}")
    logger.info(f"Yangi yaratilgan hujjatlar: {new_documents_created}")
    logger.info(f"Yangilangan hujjatlar: {existing_documents_updated}")
    logger.info(f"Celery navbatiga qo'shilgan hujjatlar: {documents_queued_for_processing}")
    logger.info(f"Jami URL'lar tekshirilgan: {total_urls_processed}")
    logger.info(f"Jami sahifalar qayta ishlangan: {total_pages_processed}")
    logger.info(f"Muvaffaqiyatli URL'lar: {successful_urls}")
    logger.info(f"Xatolik bilan URL'lar: {failed_urls}")
    logger.info(
        f"Muvaffaqiyat foizi: {(successful_urls / total_urls_processed * 100):.1f}%" if total_urls_processed > 0 else "Muvaffaqiyat foizi: 0%")
