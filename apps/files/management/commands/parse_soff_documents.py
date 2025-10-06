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
"""

# apps/files/management/commands/parsing/parse_soff_documents.py

import re
import time
import requests
from django.core.management.base import BaseCommand
from django.db import transaction
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


def create_slug(title):
    """
    Sarlavhadan slug yaratadi (URL uchun).
    
    Args:
        title (str): Hujjat sarlavhasi
    
    Returns:
        str: Slug string
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
    
    Bu komanda:
    1. SOFF.UZ saytining API'sidan foydalanadi
    2. Barcha mavjud hujjatlarni yuklab oladi
    3. Har bir hujjat uchun Document va Product obyektlarini yaratadi
    4. Parsing progressini kuzatadi
    5. Xatoliklarni boshqaradi
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
        
        Jarayon:
        1. Token olish/yangilash
        2. Sahifalarni ketma-ket pars qilish
        3. Har bir sahifadagi hujjatlarni bazaga saqlash
        4. Progress hisobotini ko'rsatish
        """
        start_page = options['start_page']
        end_page = options['end_page']
        limit = options['limit']
        delay = options['delay']

        self.stdout.write(
            self.style.SUCCESS("=== SOFF.UZ Parser boshlandi ===")
        )
        
        # Token olish
        token = get_valid_soff_token()
        if not token:
            self.stdout.write(
                self.style.ERROR("SOFF token olishda xatolik!")
            )
            return

        self.stdout.write(f"Token: {token}")
        
        # Progress obyektini yaratish/yangilash
        progress, created = ParseProgress.objects.get_or_create(
            defaults={'last_page': 0, 'total_pages_parsed': 0}
        )
        
        if created:
            self.stdout.write("Yangi progress obyekti yaratildi")
        else:
            self.stdout.write(f"Mavjud progress: sahifa {progress.last_page}")

        # Sahifalarni pars qilish
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
                params = {
                    'slug': 'all',
                    'search': '',
                    'page': page
                }
                
                response = requests.get(api_url, params=params, timeout=30)
                response.raise_for_status()
                
                data = response.json()
                
                # Sahifa ma'lumotlarini tekshirish
                page_props = data.get('pageProps', {})
                posts = page_props.get('posts', [])
                
                if not posts:
                    self.stdout.write(f"Sahifa {page} bo'sh - pars qilish tugadi")
                    break
                
                # Hujjatlarni bazaga saqlash
                page_documents = 0
                with transaction.atomic():
                    for post in posts:
                        if limit and total_documents >= limit:
                            break
                            
                        try:
                            # Document obyektini yaratish
                            document, doc_created = Document.objects.get_or_create(
                                parse_file_url=post['file_url'],
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
                                    title=post['title'],
                                    slug=create_slug(post['title']),
                                    parsed_content=post.get('description', ''),
                                    file_size=parse_file_size(post.get('file_size', '')),
                                    view_count=0,
                                    download_count=0
                                )
                                page_documents += 1
                                total_documents += 1
                                
                        except Exception as e:
                            self.stdout.write(
                                self.style.WARNING(f"Hujjat saqlashda xatolik: {e}")
                            )
                            continue
                
                # Progress yangilash
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
                    
            except requests.RequestException as e:
                self.stdout.write(
                    self.style.ERROR(f"API so'rovida xatolik: {e}")
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
                f"=== Pars qilish yakunlandi ==="
            )
        )
        self.stdout.write(f"Jami hujjatlar: {total_documents}")
        self.stdout.write(f"Oxirgi sahifa: {page - 1}")
