"""
SOFF.UZ Parser Command
======================

Bu komanda SOFF.UZ saytidan ilmiy hujjatlarni pars qiladi.
Saytning API'sidan foydalanib, barcha mavjud hujjatlarni yuklab oladi.

Ishlatish:
    python manage.py parse_soff_documents
    python manage.py parse_soff_documents --start-page 10 --end-page 20
    python manage.py parse_soff_documents --limit 100

Xususiyatlari:
- Avtomatik token yangilash
- Sahifa bo'yicha pars qilish
- Xatoliklarni boshqarish
- Progress tracking
- Database transaction boshqaruvi

MUHIM: Yangi API tuzilmasiga moslashtirildi.
"""

# apps/files/management/commands/parsing/parse_soff_documents.py

import re
import time
import requests
from django.core.management.base import BaseCommand
from django.db import transaction
# Modellar va utility funksiyalaringizni to'g'ri import qilganingizga ishonch hosil qiling
from apps.files.models import Document, Product, SiteToken, ParseProgress
from apps.files.utils import get_valid_soff_token

# ============================ CONFIGURATION ============================
SOFF_BUILD_ID_HOLDER = "{build_id}"
BASE_API_URL_TEMPLATE = f"https://soff.uz/_next/data/{SOFF_BUILD_ID_HOLDER}/scientific-resources/all.json"

# =======================================================================

def parse_file_size(file_size_str):
    """
    Fayl hajmini string formatdan (masalan, '3.49 MB') baytga o'giradi.

    Args:
        file_size_str (str): Fayl hajmi stringi (masalan, "3.49 MB", "1.2 GB")

    Returns:
        int: Fayl hajmi baytlarda
    """
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
    """
    Poster URL'dan asosiy fayl URL'ini ajratib oladi (yangilangan API talabi).
    """
    if not poster_url:
        return None
    # UUID (file ID) ni ajratib olish
    match = re.search(r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', poster_url)
    if match:
        file_id = match.group(1)
        # Fayl kengaytmasini ajratib olish
        file_ext_match = re.search(
            r'\.(pdf|docx|doc|pptx|ppt|xlsx|xls|txt|rtf|PPT|DOC|DOCX|PPTX|PDF|XLS|XLSX|odt|ods|odp)(?:_page|$)',
            poster_url,
            re.IGNORECASE
        )
        if file_ext_match:
            file_extension = file_ext_match.group(1)
            # Standart media fayl URL'ini shakllantirish
            return f"https://d2co7bxjtnp5o.cloudfront.net/media/documents/{file_id}.{file_extension}"
    return None

def create_slug(title):
    """
    Sarlavhadan slug yaratadi (URL uchun).
    """
    # O'zbek harflarini ingliz harflariga o'giradi
    translit_map = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
        'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
        'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
        'ф': 'f', 'х': 'x', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'shch',
        'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
        'ў': 'o', 'қ': 'q', 'ғ': 'g', 'ҳ': 'h', 'ў': 'o'
    }

    slug = title.lower()
    for cyr, lat in translit_map.items():
        slug = slug.replace(cyr, lat)

    # Faqat harflar, raqamlar va tire qoldiradi
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'\s+', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    return slug.strip('-')


class Command(BaseCommand):
    """
    SOFF.UZ saytidan ilmiy hujjatlarni pars qilish komandasi.
    """

    help = "SOFF.UZ saytidan ilmiy hujjatlarni pars qiladi"

    def add_arguments(self, parser):
        parser.add_argument(
            '--start-page',
            type=int,
            default=1,
            help='Boshlanish sahifasi (default: 1)'
        )
        parser.add_argument(
            '--end-page',
            type=int,
            default=None,
            help='Tugash sahifasi (agar berilmasa, barcha sahifalar)'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Maksimal hujjatlar soni (test uchun)'
        )
        parser.add_argument(
            '--delay',
            type=float,
            default=1.0,
            help='Sahifalar orasidagi kutish vaqti sekundlarda (default: 1.0)'
        )

    def handle(self, *args, **options):
        """
        Asosiy pars qilish jarayoni.
        """
        start_page = options['start_page']
        end_page = options['end_page']
        limit = options['limit']
        delay = options['delay']

        self.stdout.write(
            self.style.SUCCESS("=== SOFF.UZ Parser boshlandi ===")
        )

        # 1. Token olish/yangilash
        token = get_valid_soff_token()
        if not token:
            self.stdout.write(
                self.style.ERROR("SOFF token olishda xatolik!")
            )
            return

        self.stdout.write(f"Token: {token}")

        # 2. Progress obyektini yaratish/yangilash
        progress, created = ParseProgress.objects.get_or_create(
            defaults={'last_page': 0, 'total_pages_parsed': 0}
        )

        if created:
            self.stdout.write("Yangi progress obyekti yaratildi")
        else:
            self.stdout.write(f"Mavjud progress: sahifa {progress.last_page}")

        # 3. Sahifalarni pars qilish
        page = start_page
        total_documents = 0

        while True:
            if end_page and page > end_page:
                break

            if limit and total_documents >= limit:
                self.stdout.write(f"Limit yetildi: {limit} hujjat")
                break

            self.stdout.write(f"Sahifa {page} pars qilinmoqda...")

            try:
                # API so'rovini yuborish
                api_url = BASE_API_URL_TEMPLATE.format(build_id=token)
                # 'slug' va 'search' kerak emas. Faqat 'page' yetarli.
                params = {'page': page}

                response = requests.get(api_url, params=params, timeout=30)
                response.raise_for_status()

                data = response.json()

                # Yangi API strukturasi bo'yicha ma'lumotlarni olish
                # pageProps -> productsData -> results
                page_props = data.get('pageProps', {})
                items = page_props.get('productsData', {}).get('results', []) # <--- BU YER YANGILANDI

                if not items:
                    self.stdout.write(f"Sahifa {page} bo'sh - pars qilish tugadi")
                    break

                # Hujjatlarni bazaga saqlash
                page_documents = 0
                with transaction.atomic():
                    for item in items:
                        if limit and total_documents >= limit:
                            break

                        # Fayl URL'ini yangi usul bilan ajratib olish
                        file_url = extract_file_url(item.get("poster_url"))

                        if not file_url:
                            self.stdout.write(
                                self.style.WARNING(f"Hujjat ({item.get('id', 'N/A')}) uchun yaroqsiz URL - o'tkazib yuborildi.")
                            )
                            continue

                        try:
                            # Document obyektini yaratish/olish
                            document, doc_created = Document.objects.get_or_create(
                                parse_file_url=file_url, # <-- extract_file_url() dan keladi
                                defaults={
                                    'download_status': 'pending',
                                    'parse_status': 'pending',
                                    'index_status': 'pending',
                                    'telegram_status': 'pending',
                                    'delete_status': 'pending',
                                    'pipeline_running': False,
                                    'completed': False
                                }
                            )

                            if doc_created:
                                # Product obyektini yaratish
                                Product.objects.create(
                                    document=document,
                                    # Product ID'sini API'dan olish
                                    id=item.get('id'),
                                    title=item['title'],
                                    slug=create_slug(item['title']),
                                    parsed_content=item.get('description', ''),
                                    # Fayl hajmini document ichidan olish
                                    file_size=parse_file_size(item.get('document', {}).get('file_size', '')),
                                    view_count=0,
                                    download_count=0
                                )
                                page_documents += 1
                                total_documents += 1

                        except Exception as e:
                            self.stdout.write(
                                self.style.WARNING(f"Hujjat saqlashda xatolik: {e}. ID: {item.get('id', 'N/A')}")
                            )
                            continue

                # Progress yangilash
                # parse.py dan farqli o'laroq, bu yerda update_progress() funksiyasi yo'q, shuning uchun last_page ni to'g'ridan-to'g'ri yangilaymiz.
                progress.last_page = page
                progress.total_pages_parsed += 1
                progress.save()

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Sahifa {page} muvaffaqiyatli: {page_documents} hujjat qo'shildi"
                    )
                )

                # Keyingi sahifaga o'tish
                page += 1

                # Kutish
                if delay > 0:
                    time.sleep(delay)

            except requests.exceptions.HTTPError as e:
                # 404 xatosi token eskirganligini anglatishi mumkin, shu sababli to'xtatish
                if e.response.status_code == 404:
                    self.stdout.write(
                        self.style.ERROR(f"API so'rovida xatolik: 404 Not Found. Token eskirgan bo'lishi mumkin.")
                    )
                    # Loop ni qayta boshlash uchun token yangilanishini kutish mumkin, lekin hozircha to'xtatamiz
                    break
                self.stdout.write(
                    self.style.ERROR(f"API so'rovida HTTP xatoligi: {e}")
                )
                break
            except requests.RequestException as e:
                self.stdout.write(
                    self.style.ERROR(f"API so'rovida tarmoq xatoligi: {e}")
                )
                break
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"Kutilmagan xatolik: {e}")
                )
                break

        # Yakuniy hisobot
        self.stdout.write(
            self.style.SUCCESS(
                f"\n=== Pars qilish yakunlandi ==="
            )
        )
        self.stdout.write(f"Jami hujjatlar: {total_documents}")
        self.stdout.write(f"Oxirgi muvaffaqiyatli sahifa: {page - 1}")