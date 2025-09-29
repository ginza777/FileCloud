# apps/files/management/commands/parse_arxivuz.py

import requests
import time
import logging
from math import ceil
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from ...models import Document, Product, SiteToken, ParseProgress
from ...tasks import parse_document_pipeline

# Logging sozlamalari
logger = logging.getLogger(__name__)

# Asosiy URL'lar (API uchun /uz/ siz)
BASE_URLS = [
    "https://arxiv.uz/documents/all/"
    
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


class Command(BaseCommand):
    help = 'Arxiv.uz saytidan ma\'lumotlarni oladi, mavjudlarini yangilaydi va yangilarini qo\'shadi.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            nargs='?',
            default=None,
            help='Bir martada nechta sahifani tekshirish. Agar berilmasa, barchasi tekshiriladi.'
        )
        parser.add_argument(
            '--category',
            type=str,
            nargs='?',
            default=None,
            help='Faqat bitta kategoriyani tekshirish (masalan: darsliklar)'
        )

    def handle(self, *args, **options):
        limit = options.get('limit')
        category = options.get('category')

        self.stdout.write(self.style.SUCCESS("--- Arxiv.uz parsing jarayoni boshlandi ---"))
        
        # SiteToken dan PHPSESSID ni olish
        try:
            site_token = SiteToken.objects.get(name='arxiv')
            phpsessid = site_token.auth_token
            if not phpsessid:
                phpsessid="fc33f22ec66a83cbcdc3ba6a8c37e80e"
                return
        except SiteToken.DoesNotExist:
            self.stdout.write(self.style.ERROR("❌ SiteToken 'arxiv' topilmadi!"))
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
        
        # Kategoriyalarni filterlash
        urls_to_process = BASE_URLS
        if category:
            urls_to_process = [url for url in BASE_URLS if category in url]
            if not urls_to_process:
                self.stdout.write(self.style.ERROR(f"❌ '{category}' kategoriyasi topilmadi!"))
                return

        # Statistika uchun hisoblagichlar
        total_documents_processed = 0
        new_documents_created = 0
        existing_documents_updated = 0
        documents_queued_for_processing = 0
        total_urls_processed = 0
        total_pages_processed = 0
        successful_urls = 0
        failed_urls = 0

        for base_url in urls_to_process:
            self.stdout.write(f"\n📁 Kategoriya: {base_url}")
            
            for sub_category in SUB_CATEGORIES:
                self.stdout.write(f"  📂 Sub-kategoriya: {sub_category}")
                
                # Referer'ni dinamik sozlash
                headers['referer'] = f"https://arxiv.uz/uz/documents/{sub_category.split('/')[-1]}/{sub_category.split('/')[-1]}"
                
                page = 1
                page_size = 10
                pages_processed = 0
                url_success = True

                while True:
                    if limit and pages_processed >= limit:
                        self.stdout.write(f"  ⏹️  Limit ({limit}) yetdi, to'xtatildi.")
                        break

                    api_url = f"{base_url}{sub_category}?page={page}&pageSize={page_size}"
                    total_urls_processed += 1
                    
                    # Retry mantiqi
                    max_retries = 3
                    retry_count = 0
                    request_success = False
                    
                    while retry_count < max_retries and not request_success:
                        try:
                            self.stdout.write(f"    📄 Sahifa {page}: {api_url} (urinish {retry_count + 1}/{max_retries})")
                            # Serverga yukni kamaytirish uchun qo'shimcha pauza
                            time.sleep(0.5)  # Sahifalar orasida 0.5 soniya kutish
                            response = requests.get(api_url, headers=headers, cookies=cookies, timeout=15)
                            response.raise_for_status()
                            request_success = True
                            
                        except requests.RequestException as e:
                            retry_count += 1
                            self.stdout.write(self.style.WARNING(f"    ⚠️  So'rov xatosi (urinish {retry_count}/{max_retries}): {e}"))
                            
                            if retry_count < max_retries:
                                self.stdout.write(f"    🔄 5 soniya kutib, qayta uriniladi...")
                                time.sleep(5)  # Xato bo'lsa 5 soniya kutish va qayta urinish
                            else:
                                self.stdout.write(self.style.ERROR(f"    ❌ Barcha urinishlar muvaffaqiyatsiz: {api_url}"))
                                failed_urls += 1
                                url_success = False
                                break
                    
                    if not request_success:
                        continue

                    try:
                        data = response.json()
                    except ValueError as e:
                        self.stdout.write(self.style.ERROR(f"    ❌ JSON xatosi: {e}"))
                        self.stdout.write(f"    📄 Response status: {response.status_code}")
                        self.stdout.write(f"    📄 Content-Type: {response.headers.get('Content-Type', 'N/A')}")
                        self.stdout.write(f"    📄 Response text (first 200 chars): {response.text[:200]}")
                        failed_urls += 1
                        url_success = False
                        break

                    documents = data.get("documents", [])
                    if not documents:
                        self.stdout.write(f"    ℹ️  Hujjatlar yo'q: {api_url}")
                        successful_urls += 1
                        total_pages_processed += 1
                        pages_processed += 1
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
                                            id=hash(slug) % (2**31),  # Integer ID uchun hash
                                            title=title,
                                            slug=slug,
                                            document=existing_doc
                                        )
                                    
                                    existing_documents_updated += 1
                                    self.stdout.write(f"    ✅ Yangilandi: {title}")
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
                                        id=hash(slug) % (2**31),  # Integer ID uchun hash
                                        title=title,
                                        slug=slug,
                                        document=new_doc
                                    )
                                    
                                    # Celery orqali qayta ishlash uchun navbatga qo'shish
                                    parse_document_pipeline.apply_async(args=[new_doc.id])
                                    
                                    new_documents_created += 1
                                    documents_queued_for_processing += 1
                                    self.stdout.write(f"    ➕ Yangi: {title} (ID: {new_doc.id})")

                                total_documents_processed += 1

                        except Exception as e:
                            self.stdout.write(self.style.ERROR(f"    ❌ Hujjatni qayta ishlashda xato: {e}"))
                            continue

                    # Sahifa ma'lumotlarini tekshirish
                    total = data.get("total", 0)
                    total_pages = ceil(total / page_size)
                    self.stdout.write(f"    📊 Sahifa {page}/{total_pages}, Jami hujjatlar: {total}")
                    
                    successful_urls += 1
                    total_pages_processed += 1
                    pages_processed += 1
                    
                    if page >= total_pages:
                        break

                    page += 1
                    # Har bir sahifa orasida qo'shimcha pauza
                    time.sleep(0.5)  # Sahifalar orasida 0.5 soniya kutish

                # Progress ni yangilash
                progress.update_progress(page)
                
                # Sub-kategoriya tugaganidan keyin qo'shimcha pauza
                if url_success:
                    self.stdout.write(f"  ✅ Sub-kategoriya tugadi: {sub_category}")
                else:
                    self.stdout.write(f"  ❌ Sub-kategoriyada xato: {sub_category}")
                time.sleep(0.5)  # Sub-kategoriyalar orasida 0.5 soniya kutish

        self.stdout.write(self.style.SUCCESS("\n--- JARAYON YAKUNLANDI: STATISTIKA ---"))
        self.stdout.write(f"📊 Jami qayta ishlangan hujjatlar: {total_documents_processed}")
        self.stdout.write(f"➕ Yangi yaratilgan hujjatlar: {new_documents_created}")
        self.stdout.write(f"✅ Yangilangan hujjatlar: {existing_documents_updated}")
        self.stdout.write(f"🔄 Celery navbatiga qo'shilgan hujjatlar: {documents_queued_for_processing}")
        self.stdout.write(f"🌐 Jami URL'lar tekshirilgan: {total_urls_processed}")
        self.stdout.write(f"📄 Jami sahifalar qayta ishlangan: {total_pages_processed}")
        self.stdout.write(f"✅ Muvaffaqiyatli URL'lar: {successful_urls}")
        self.stdout.write(f"❌ Xatolik bilan URL'lar: {failed_urls}")
        self.stdout.write(f"📈 Muvaffaqiyat foizi: {(successful_urls/total_urls_processed*100):.1f}%" if total_urls_processed > 0 else "📈 Muvaffaqiyat foizi: 0%")
        self.stdout.write(f"📁 Jami fayllar parse qilish mumkin: {total_documents_processed}")
        self.stdout.write(self.style.SUCCESS("-----------------------------------------"))
