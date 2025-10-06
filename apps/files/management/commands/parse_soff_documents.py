"""
SOFF.UZ Parser Command
======================

Bu komanda SOFF.UZ saytidan ilmiy hujjatlarni pars qiladi.
Yaroqsiz URL'li va bazada mavjud ID'li (Product) elementlarni SKIP qiladi.

MUHIM TUZATISHLAR:
1. Bazada ID bo'yicha mavjud bo'lsa, skip qilish.
2. Har bir item alohida tranzaksiyada, xatoliklar bir-biriga ta'sir qilmaydi.
"""

# apps/files/management/commands/parsing/parse_soff_documents.py

import re
import time
import requests
from django.core.management.base import BaseCommand
from django.db import transaction, IntegrityError
# Modellar va utility funksiyalaringizni to'g'ri import qilganingizga ishonch hosil qiling
from apps.files.models import Document, Product, SiteToken, ParseProgress
from apps.files.utils import get_valid_soff_token

# ============================ CONFIGURATION ============================
SOFF_BUILD_ID_HOLDER = "{build_id}"
BASE_API_URL_TEMPLATE = f"https://soff.uz/_next/data/{SOFF_BUILD_ID_HOLDER}/scientific-resources/all.json"

# ... (parse_file_size, extract_file_url, create_slug funksiyalari o'zgarishsiz qoladi)

def parse_file_size(file_size_str):
    """Fayl hajmini string formatdan (masalan, '3.49 MB') baytga o'giradi."""
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
            re.IGNORECASE
        )
        if file_ext_match:
            file_extension = file_ext_match.group(1)
            return f"https://d2co7bxjtnp5o.cloudfront.net/media/documents/{file_id}.{file_extension}"
    return None

def create_slug(title):
    """Sarlavhadan slug yaratadi (URL uchun)."""
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
        start_page = options['start-page']
        end_page = options['end-page']
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
            # Agar start_page berilmasa, oxirgi to'xtagan joydan davom ettiramiz
            if options['start-page'] == 1:
                start_page = progress.last_page + 1
            self.stdout.write(f"Mavjud progress: sahifa {progress.last_page}")

        # 3. Sahifalarni pars qilish
        page = start_page
        total_documents = 0
        total_skipped_url = 0
        total_skipped_exists = 0

        while True:
            if end_page and page > end_page:
                break

            if limit and total_documents >= limit:
                self.stdout.write(f"Limit yetildi: {limit} hujjat")
                break

            self.stdout.write(f"\n{'=' * 10} Sahifa {page} pars qilinmoqda... {'=' * 10}")

            try:
                # API so'rovini yuborish
                api_url = BASE_API_URL_TEMPLATE.format(build_id=token)
                params = {'page': page}

                response = requests.get(api_url, params=params, timeout=30)
                response.raise_for_status()

                data = response.json()

                page_props = data.get('pageProps', {})
                items = page_props.get('productsData', {}).get('results', [])

                if not items:
                    self.stdout.write(self.style.SUCCESS(f"Sahifa {page} da ma'lumot topilmadi. Parsing yakunlandi."))
                    break

                # Hujjatlarni bazaga saqlash
                page_documents = 0

                # Sahifadagi barcha item ID'larini yig'ib olamiz
                item_ids = [item.get('id') for item in items if item.get('id') is not None]
                # Bazada mavjud bo'lgan Product ID'larini bir so'rovda tekshiramiz
                existing_product_ids = set(Product.objects.filter(id__in=item_ids).values_list('id', flat=True))


                # Har bir elementni alohida tranzaksiyada qayta ishlash
                for item in items:
                    if limit and total_documents >= limit:
                        break

                    item_id = item.get('id')

                    # 1. ID mavjudligini tekshirish va skip qilish
                    if item_id is None:
                        continue

                    if item_id in existing_product_ids:
                        self.stdout.write(f"    ℹ️ Hujjat ({item_id}) ID bazada mavjud. Skip qilindi.")
                        total_skipped_exists += 1
                        continue # Keyingi itemga o'tish

                    # 2. Yaroqsiz URL ni tekshirish va skip qilish
                    file_url = extract_file_url(item.get("poster_url"))

                    if not file_url:
                        self.stdout.write(
                            self.style.WARNING(f"    ⚠️ Hujjat ({item_id}) uchun yaroqsiz URL. Skip qilindi.")
                        )
                        total_skipped_url += 1
                        continue

                    try:
                        # 3. Yaratish (Document va Product)
                        with transaction.atomic():

                            # Document yaratish (unique constraint faqat parse_file_url bo'yicha)
                            document, doc_created = Document.objects.get_or_create(
                                parse_file_url=file_url,
                                defaults={
                                    'download_status': 'pending',
                                    'parse_status': 'pending',
                                    'index_status': 'pending',
                                    'telegram_status': 'pending',
                                    'delete_status': 'pending',
                                    'pipeline_running': False,
                                    'completed': False,
                                    # json_data ni ham saqlab qo'yamiz
                                    'json_data': item
                                }
                            )

                            if doc_created:
                                title = item['title']
                                slug = create_slug(title)

                                # Product yaratish (Doc_ID va Slug bo'yicha unique bo'lishi mumkin)
                                Product.objects.create(
                                    id=item_id, # API ID Product ID sifatida
                                    document=document,
                                    title=title,
                                    slug=slug,
                                    parsed_content=item.get('description', ''),
                                    file_size=parse_file_size(item.get('document', {}).get('file_size', '')),
                                    view_count=0,
                                    download_count=0
                                )

                                page_documents += 1
                                total_documents += 1
                                self.stdout.write(f"    ➕ Yangi hujjat qo'shildi: {title} (ID: {item_id})")
                            else:
                                # Document allaqachon parse_file_url bo'yicha mavjud
                                self.stdout.write(f"    ℹ️ Hujjat ({item_id}) Document allaqachon URL bo'yicha mavjud. Skip.")
                                total_skipped_exists += 1


                    except IntegrityError as e:
                        # Bu yerda duplikat slug/ID xatosi ushlanadi
                        self.stdout.write(
                            self.style.WARNING(f"    ❌ Hujjat saqlashda IntegrityError (Duplikat): {e}. ID: {item_id}. Skip qilindi.")
                        )
                        total_skipped_exists += 1
                        continue
                    except Exception as e:
                        # Boshqa kutilmagan xatoliklar
                        self.stdout.write(
                            self.style.ERROR(f"    ❌ Hujjat saqlashda kutilmagan xatolik: {e}. ID: {item_id}")
                        )
                        continue


                # Progress yangilash
                progress.last_page = page
                progress.total_pages_parsed += 1
                progress.save()

                self.stdout.write(
                    self.style.SUCCESS(
                        f"\n--- Sahifa {page} Statistikasi ---"
                    )
                )
                self.stdout.write(f"  - Yangi qo'shilganlar: {page_documents}")
                self.stdout.write(f"  - O'tkazib yuborildi (ID mavjud): {total_skipped_exists}")
                self.stdout.write(f"  - O'tkazib yuborildi (Yaroqsiz URL): {total_skipped_url}")


                # Keyingi sahifaga o'tish
                page += 1

                # Kutish
                if delay > 0:
                    time.sleep(delay)

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 404:
                    self.stdout.write(
                        self.style.ERROR(f"API so'rovida xatolik: 404 Not Found. Token eskirgan bo'lishi mumkin.")
                    )
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
        self.stdout.write(f"Jami yangi hujjatlar: {total_documents}")
        self.stdout.write(f"Jami o'tkazib yuborilganlar (Mavjud/URL): {total_skipped_exists + total_skipped_url}")
        self.stdout.write(f"Oxirgi muvaffaqiyatli sahifa: {page - 1}")