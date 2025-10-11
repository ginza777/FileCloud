"""
Arxiv.UZ Parser Command
=======================

Bu komanda Arxiv.UZ saytidan ilmiy hujjatlarni pars qiladi.
Turli kategorialar (Hujjat turlari va Fanlar) bo'yicha hujjatlarni yuklab oladi.

MUHIM: 500 Server Error xatosini tuzatish uchun API so'rov mantig'i yangilandi.
Endi ma'lumotlar ikki darajali (BASE_URL + SUB_CATEGORY) asosida olinadi.
"""

import requests
import time
import logging
import re
from math import ceil
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
# apps.files.models o'rniga model yo'lini to'g'irlang, agar kerak bo'lsa
from apps.files.models import Document, Product, SiteToken, ParseProgress
from apps.files.tasks.document_processing import process_document_pipeline

logger = logging.getLogger(__name__)

# Asosiy URL'lar (BASE_URL: Hujjat turi)
BASE_URLS = [
    "https://arxiv.uz/documents/dars-ishlanmalar/",
    "https://arxiv.uz/documents/diplom-ishlar/",
    "https://arxiv.uz/documents/darsliklar/",
    "https://arxiv.uz/documents/slaydlar/",
    "https://arxiv.uz/documents/referatlar/",
    "https://arxiv.uz/documents/kurs-ishlari/",
]

# SUB-Kataloglar (SUB_CATEGORY: Fan nomi)
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
    "zootexnika", "matematika", "texnika", "tabiiy-fanlar", "ijtimoiy-fanlar",
    # Qo'shimcha fanlar ishlaydigan koddan
    "musiqa", "nemis-tili", "o-qish", "odobnoma", "pedagogik-psixologiya", "prezident-asarlari",
    "qishloq-va-o-rmon-xo-jaligi", "radiotexnika", "rus-tili-va-adabiyoti", "san-at",
    "siyosatshunoslik", "suv-xo-jaligi", "tabiatshunoslik", "tarix", "tasviriy-san-at",
    "to-qimachilik", "valeologiya", "xayot-faoliyati-xavfsizligi", "zoologiya"
]


class Command(BaseCommand):
    """
    Arxiv.UZ saytidan ilmiy hujjatlarni pars qilish komandasi.
    """

    help = "Arxiv.UZ saytidan ilmiy hujjatlarni pars qiladi"

    def add_arguments(self, parser):
        parser.add_argument(
            '--category',
            type=str,
            help='Muayyan fan nomini pars qilish (masalan: "adabiyot")'
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
        delay = options.get('delay')

        self.stdout.write(self.style.SUCCESS("--- Arxiv.uz parsing jarayoni boshlandi ---"))

        # 1. PHPSESSID ni olish
        try:
            site_token = SiteToken.objects.get(name='arxiv')
            phpsessid = site_token.auth_token
            if not phpsessid:
                self.stdout.write(self.style.ERROR("❌ SiteToken 'arxiv' da auth_token bo'sh!"))
                return
        except SiteToken.DoesNotExist:
            self.stdout.write(self.style.ERROR("❌ SiteToken 'arxiv' topilmadi!"))
            return

        # 2. Headers va cookies sozlash
        headers = {
            'accept': 'application/json, text/plain, */*',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.88 Safari/537.36',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
        }

        cookies = {
            'PHPSESSID': phpsessid,
        }

        # 3. Kategorialarni aniqlash
        urls_to_process = BASE_URLS # Hujjat turlari (darsliklar, referatlar...)

        if category and category not in CATEGORIES:
            self.stdout.write(self.style.ERROR(f"Noma'lum kategoriya: {category}"))
            return

        categories_to_parse = [category] if category else CATEGORIES # Fan nomlari

        # 4. Statistika
        total_documents_processed = 0
        new_documents_created = 0
        documents_queued_for_processing = 0
        page_size = 10 # Har bir sahifadagi elementlar soni

        # 5. Parsing jarayoni (Ikkita loop: Hujjat turi + Fan nomi)
        for base_url in urls_to_process:
            if limit and total_documents_processed >= limit:
                break

            self.stdout.write(f"\n📁 Hujjat Turi: {base_url.split('/')[-2]}")

            for sub_category in categories_to_parse:
                if limit and total_documents_processed >= limit:
                    break

                self.stdout.write(f"  📂 Fan nomi: {sub_category}")

                # Referer API so'rovi uchun shart!
                headers['referer'] = f"https://arxiv.uz/uz/documents/{base_url.split('/')[-2]}/{sub_category}"

                page = 1
                while True:
                    if limit and total_documents_processed >= limit:
                        break

                    # API URL'ini yaratish (Ishlaydigan kod kabi)
                    api_url = f"{base_url}{sub_category}?page={page}&pageSize={page_size}"

                    try:
                        self.stdout.write(f"    📄 Sahifa {page}: {api_url}")

                        time.sleep(delay)

                        response = requests.get(api_url, headers=headers, cookies=cookies, timeout=15)
                        response.raise_for_status() # 500 xatosini shu yerda ushlaydi

                        # JSON ma'lumotlarini olish
                        data = response.json()
                        documents = data.get("documents", [])
                        total_items = data.get("total", 0)

                        if not documents:
                            self.stdout.write(f"    ℹ️  Sahifa {page} da hujjatlar yo'q.")
                            break

                        # Hujjatlarni qayta ishlash va bazaga saqlash
                        with transaction.atomic():
                            for doc_data in documents:
                                if limit and total_documents_processed >= limit:
                                    break

                                doc_id = doc_data.get("id")
                                slug = doc_data.get("slug")
                                title = doc_data.get("title", slug)

                                category_slug = doc_data.get("category", {}).get("slug")
                                subject_slug = doc_data.get("subject", {}).get("slug")

                                # Download URL ni yaratish
                                download_url = None
                                if slug and category_slug and subject_slug:
                                    download_url = f"https://arxiv.uz/uz/download/{category_slug}/{subject_slug}/{slug}"

                                if not download_url:
                                     self.stdout.write(self.style.WARNING(f"    ⚠️ Download URL yaratilmadi: {title}"))
                                     continue

                                # Mavjud hujjatni slug orqali tekshirish
                                try:
                                    existing_doc = Document.objects.get(json_data__slug=slug)

                                    # Blocked productlarga teginmaslik
                                    if hasattr(existing_doc, 'product') and existing_doc.product.blocked:
                                        self.stdout.write(f"    ⚠️ Blocked product o'tkazib yuborildi: {title}")
                                        continue

                                    # Yangilash mantig'i (Productni ham)
                                    existing_doc.json_data = doc_data
                                    existing_doc.parse_file_url = download_url
                                    existing_doc.save()

                                    if hasattr(existing_doc, 'product'):
                                        existing_doc.product.title = title
                                        existing_doc.product.slug = slug
                                        existing_doc.product.save()

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

                                    # Product ID'sini API dan kelgan doc_id ni ishlatish
                                    Product.objects.create(
                                        id=doc_id,
                                        title=title,
                                        slug=slug,
                                        document=new_doc
                                    )

                                    process_document_pipeline.apply_async(args=[new_doc.id])

                                    new_documents_created += 1
                                    documents_queued_for_processing += 1
                                    self.stdout.write(f"    ➕ Yangi: {title}")

                                total_documents_processed += 1

                        # Sahifa ma'lumotlarini tekshirish
                        total_pages = ceil(total_items / page_size)
                        self.stdout.write(f"    📊 Sahifa {page}/{total_pages}, Jami: {total_items}")

                        if page >= total_pages:
                            break

                        page += 1

                    except requests.exceptions.HTTPError as e:
                        self.stdout.write(self.style.ERROR(f"    ❌ HTTP xatosi (Sahifa {page}): {e}"))
                        time.sleep(5)
                        break
                    except requests.exceptions.RequestException as e:
                        self.stdout.write(self.style.ERROR(f"    ❌ Tarmoq xatosi (Sahifa {page}): {e}"))
                        time.sleep(5)
                        break
                    except ValueError as e:
                        self.stdout.write(self.style.ERROR(f"    ❌ JSON Decode xatosi (Sahifa {page}): {e}"))
                        time.sleep(5)
                        break
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f"    ❌ Kutilmagan xato (Sahifa {page}): {e}"))
                        time.sleep(5)
                        break

                self.stdout.write(f"  ✅ Fan nomi tugadi: {sub_category}")
                time.sleep(delay)

        self.stdout.write(self.style.SUCCESS("\n--- JARAYON YAKUNLANDI: STATISTIKA ---"))
        self.stdout.write(f"📊 Jami qayta ishlangan hujjatlar: {total_documents_processed}")
        self.stdout.write(f"➕ Yangi yaratilgan hujjatlar: {new_documents_created}")
        self.stdout.write(f"🔄 Celery navbatiga qo'shilganlar: {documents_queued_for_processing}")
        self.stdout.write(self.style.SUCCESS("-----------------------------------------"))