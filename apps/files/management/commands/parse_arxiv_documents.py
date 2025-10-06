"""
Arxiv.UZ Parser Command
=======================

Bu komanda Arxiv.UZ saytidan ilmiy hujjatlarni pars qiladi.
Turli kategorialar bo'yicha hujjatlarni yuklab oladi.

Ishlatish:
    python manage.py parse_arxiv_documents
    python manage.py parse_arxiv_documents --category "matematika"
    python manage.py parse_arxiv_documents --limit 50
"""

import requests
import time
import logging
from math import ceil
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from apps.files.models import Document, Product, SiteToken, ParseProgress
from apps.files.tasks.document_processing import process_document_pipeline

logger = logging.getLogger(__name__)

# Asosiy URL'lar
BASE_URLS = ["https://arxiv.uz/documents/all/"]

# Kategorialar ro'yxati
CATEGORIES = [
    "adabiyot", "algebra", "anatomiya", "arxitektura", "astronomiya", "biologiya",
    "biotexnologiya", "botanika", "chizmachilik", "chqbt", "davlat-tilida-ish-yuritish",
    "dinshunoslik-asoslari", "ekologiya", "energetika", "falsafa", "fizika",
    "fransuz-tili", "geodeziya", "geografiya", "geologiya", "geometriya", "huquqshunoslik",
    "informatika-va-at", "ingliz-tili", "iqtisodiyot", "issiqlik-texnikasi", "jismoniy-tarbiya",
    "kimyo", "konchilik-ishi", "madaniyatshunoslik", "maktabgacha-va-boshlang-ich-ta-lim",
    "manaviyat-asoslari", "mashinasozlik", "materialshunoslik", "mehnat", "melioratsiya",
    "menejment", "metrologiya", "mexanika", "mikrobiologiya", "mikroelektronika",
    "milliy-ideya", "muhandislik-grafikasi", "nafas-olish-sistemasi", "neft-va-gaz",
    "oziq-ovqat-texnologiyasi", "pedagogika", "psixologiya", "radiologiya", "rus-tili",
    "sanoat-texnologiyasi", "sotsiologiya", "statistika", "texnologiya", "tibbiyot",
    "tog-texnologiyasi", "transport", "turizm", "umumiy-fizika", "umumiy-kimyo",
    "umumiy-matematika", "umumiy-texnologiya", "xalqaro-huquq", "xizmat-ko-rsatish",
    "zootexnika", "matematika", "texnika", "tabiiy-fanlar", "ijtimoiy-fanlar"
]


class Command(BaseCommand):
    """
    Arxiv.UZ saytidan ilmiy hujjatlarni pars qilish komandasi.
    
    Bu komanda:
    1. Arxiv.UZ saytining turli kategorialarini tekshiradi
    2. Har bir kategoriyadagi hujjatlarni yuklab oladi
    3. Hujjatlarni bazaga saqlaydi
    4. Parsing pipeline'ini ishga tushiradi
    """
    
    help = "Arxiv.UZ saytidan ilmiy hujjatlarni pars qiladi"

    def add_arguments(self, parser):
        parser.add_argument(
            '--category',
            type=str,
            help='Muayyan kategoriyani pars qilish (masalan: "matematika")'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Maksimal hujjatlar soni'
        )
        parser.add_argument(
            '--delay',
            type=float,
            default=2.0,
            help='Sahifalar orasidagi kutish vaqti'
        )

    def handle(self, *args, **options):
        """Asosiy pars qilish jarayoni."""
        category = options.get('category')
        limit = options.get('limit')
        delay = options.get('delay')  # Endi delay har bir API so'rovidan keyin ishlatiladi

        self.stdout.write(self.style.SUCCESS("--- Arxiv.uz parsing jarayoni boshlandi ---"))

        # SiteToken dan PHPSESSID ni olish
        try:
            # SiteToken 'arxiv' nomini ishlatish shart
            site_token = SiteToken.objects.get(name='arxiv')
            phpsessid = site_token.auth_token
            # Token bo'lmasa, chiqish yoki default qiymat berish (masalan: default PHPSESSID)
            if not phpsessid:
                self.stdout.write(self.style.WARNING("⚠️ SiteToken 'arxiv' da auth_token bo'sh!"))
                return
        except SiteToken.DoesNotExist:
            self.stdout.write(self.style.ERROR("❌ SiteToken 'arxiv' topilmadi!"))
            return

        # Headers va cookies sozlash
        headers = {
            # Bularning barchasi API'ga so'rov yuborish uchun muhim
            'accept': 'application/json, text/plain, */*',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.88 Safari/537.36',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
        }

        cookies = {
            'PHPSESSID': phpsessid,
        }

        # Progress ni olish (bu yerda faqat statlar uchun ishlatiladi)
        progress = ParseProgress.objects.filter(last_page__gte=0).first()
        if not progress:
            progress, _ = ParseProgress.objects.get_or_create(defaults={'last_page': 0, 'total_pages_parsed': 0})

        # Kategoriyalarni filterlash
        # BASE_URLS (hujjat turlari) ni aniqlash
        urls_to_process = BASE_URLS
        if category:
            # Agar 'category' berilsa, faqat o'sha SUB-CATEGORY ni ishlatamiz
            categories_to_parse = [category]

        else:
            categories_to_parse = CATEGORIES

        # Statistika uchun hisoblagichlar
        total_documents_processed = 0
        new_documents_created = 0
        documents_queued_for_processing = 0

        # Asosiy tur bo'yicha loop (darsliklar/, referatlar/ kabi)
        for base_url in urls_to_process:
            if limit and total_documents_processed >= limit:
                break

            self.stdout.write(f"\n📁 Kategoriya Turi: {base_url.split('/')[-2]}")

            # Sub-kategoriya bo'yicha loop (matematika, fizika kabi)
            for sub_category in categories_to_parse:
                if limit and total_documents_processed >= limit:
                    break

                self.stdout.write(f"  📂 Sub-kategoriya: {sub_category}")

                # Referer'ni dinamik sozlash (API to'g'ri ishlashi uchun zarur)
                headers['referer'] = f"https://arxiv.uz/uz/documents/{sub_category}/{sub_category}"

                page = 1
                page_size = 10

                while True:
                    if limit and total_documents_processed >= limit:
                        break

                    # API URL'ini yaratish
                    # base_url + sub_category API so'rovini hosil qiladi
                    api_url = f"{base_url}{sub_category}?page={page}&pageSize={page_size}"

                    try:
                        self.stdout.write(f"    📄 Sahifa {page}: {api_url}")

                        time.sleep(delay)  # Kutish

                        response = requests.get(api_url, headers=headers, cookies=cookies, timeout=15)
                        response.raise_for_status()

                        try:
                            data = response.json()
                        except ValueError as e:
                            self.stdout.write(self.style.ERROR(f"    ❌ Sahifa {page} dan JSON xatosi: {e}"))
                            break  # Keyingi sub-kategoriyaga o'tish

                        documents = data.get("documents", [])
                        total_items = data.get("total", 0)

                        if not documents:
                            self.stdout.write(f"    ℹ️  Sahifa {page} da hujjatlar yo'q.")
                            break

                        # Hujjatlarni qayta ishlash
                        with transaction.atomic():
                            for doc_data in documents:
                                if limit and total_documents_processed >= limit:
                                    break

                                doc_id = doc_data.get("id")
                                slug = doc_data.get("slug")
                                title = doc_data.get("title", slug)

                                category_slug = doc_data.get("category", {}).get("slug")
                                subject_slug = doc_data.get("subject", {}).get("slug")

                                # Download URL ni yaratish (ishlaydigan kod kabi)
                                download_url = None
                                if slug and category_slug and subject_slug:
                                    download_url = f"https://arxiv.uz/uz/download/{category_slug}/{subject_slug}/{slug}"

                                if not download_url:
                                    self.stdout.write(self.style.WARNING(f"    ⚠️ Download URL yaratilmadi: {title}"))
                                    continue

                                # Mavjud hujjatni tekshirish (faqat slug orqali)
                                try:
                                    existing_doc = Document.objects.get(json_data__slug=slug)

                                    # Yangilash
                                    existing_doc.json_data = doc_data
                                    existing_doc.parse_file_url = download_url
                                    existing_doc.save()

                                    # Productni yangilash
                                    if hasattr(existing_doc, 'product'):
                                        existing_doc.product.title = title
                                        existing_doc.product.slug = slug
                                        existing_doc.product.save()

                                    # Qayta ishlash navbatiga qo'shish (yangilangan bo'lsa)
                                    process_document_pipeline.apply_async(args=[existing_doc.id])

                                    self.stdout.write(f"    ✅ Yangilandi: {title}")
                                except Document.DoesNotExist:
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
                                    # Product ID'si sifatida doc_id ni ishlatish maqsadga muvofiq
                                    Product.objects.create(
                                        id=doc_id,  # API dan kelgan ID ni ishlatish
                                        title=title,
                                        slug=slug,
                                        document=new_doc
                                    )

                                    # Celery orqali qayta ishlash uchun navbatga qo'shish
                                    process_document_pipeline.apply_async(args=[new_doc.id])

                                    new_documents_created += 1
                                    documents_queued_for_processing += 1
                                    self.stdout.write(f"    ➕ Yangi: {title} (ID: {new_doc.id})")

                                total_documents_processed += 1

                        # Sahifani tekshirish
                        total_pages = ceil(total_items / page_size)
                        self.stdout.write(f"    📊 Sahifa {page}/{total_pages}, Jami: {total_items}")

                        if page >= total_pages:
                            break

                        page += 1

                    except requests.RequestException as e:
                        self.stdout.write(self.style.ERROR(f"    ❌ Sahifa {page} da so'rov xatosi: {e}"))
                        time.sleep(5)  # Xato bo'lsa ko'proq kutish
                        break  # Keyingi sub-kategoriyaga o'tish

                self.stdout.write(f"  ✅ Sub-kategoriya tugadi: {sub_category}")
                time.sleep(delay)  # Sub-kategoriyalar orasida kutish

        self.stdout.write(self.style.SUCCESS("\n--- JARAYON YAKUNLANDI: STATISTIKA ---"))
        self.stdout.write(f"📊 Jami qayta ishlangan hujjatlar: {total_documents_processed}")
        self.stdout.write(f"➕ Yangi yaratilgan hujjatlar: {new_documents_created}")
        self.stdout.write(f"🔄 Celery navbatiga qo'shilganlar: {documents_queued_for_processing}")
        self.stdout.write(self.style.SUCCESS("-----------------------------------------"))