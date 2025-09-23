# apps/multiparser/management/commands/parse.py

import re
import time
import requests
from django.core.management.base import BaseCommand
from django.db import transaction
from ...models import Document, Product, SiteToken, ParseProgress
from ...utils import get_valid_soff_token

# ============================ CONFIGURATION ============================
SOFF_BUILD_ID_HOLDER = "{build_id}"
BASE_API_URL_TEMPLATE = f"https://soff.uz/_next/data/{SOFF_BUILD_ID_HOLDER}/scientific-resources/all.json"

# =======================================================================

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
        file_ext_match = re.search(r'\.(pdf|docx|doc|pptx|ppt|xlsx|xls|txt|rtf|PPT|DOC|DOCX|PPTX|PDF|XLS|XLSX|odt|ods|odp)(?:_page|$)', poster_url,
                                   re.IGNORECASE)
        if file_ext_match:
            file_extension = file_ext_match.group(1)  # Preserve original case
            return f"https://d2co7bxjtnp5o.cloudfront.net/media/documents/{file_id}.{file_extension}"
    return None

class Command(BaseCommand):
    help = 'Soff.uz saytidan ma\'lumotlarni oladi, mavjudlarini yangilaydi va yangilarini qo\'shadi.'

    def add_arguments(self, parser):
        parser.add_argument('--start-page', type=int, default=1,
                            help='Boshlanadigan sahifa (standart: oxirgi to`xtagan joydan)')
        parser.add_argument('--end-page', type=int, default=10000, help='Tugaydigan sahifa (standart: cheksiz)')
        parser.add_argument('--reset-progress', action='store_true', help='Parsing jarayonini 1-sahifadan boshlash')

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("=== MA'LUMOTLARNI PARSE QILISH BOSHLANDI (YANGILASH REJIMI) ==="))

        progress = ParseProgress.get_current_progress()

        if options['reset_progress']:
            progress.last_page = 0
            progress.save()
            self.stdout.write(self.style.SUCCESS('Parsing jarayoni 1-sahifaga qaytarildi.'))

        start_page = options['start_page'] if options['start_page'] is not None else progress.last_page + 1
        end_page = options['end_page']

        page = start_page
        total_created = 0
        total_updated = 0
        total_skipped = 0

        try:
            while True:
                if end_page and page > end_page:
                    self.stdout.write(self.style.WARNING(f"Belgilangan oxirgi sahifaga ({end_page}) yetildi."))
                    break

                self.stdout.write(self.style.HTTP_INFO(f"\n{'=' * 20} Sahifa: {page} {'=' * 20}"))

                token = get_valid_soff_token()
                if not token:
                    self.stdout.write(self.style.ERROR("Yaroqli token olinmadi. 5 soniyadan so'ng qayta uriniladi..."))
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
                        self.stdout.write(self.style.WARNING(
                            f"Sahifa {page} (404). Token eskirgan bo'lishi mumkin. Yangilanmoqda..."))
                        time.sleep(2)
                        continue
                    self.stdout.write(self.style.ERROR(f"Sahifa {page} da HTTP xatoligi: {e}"))
                    time.sleep(10)
                    continue
                except requests.exceptions.RequestException as e:
                    self.stdout.write(self.style.ERROR(f"Sahifa {page} da tarmoq xatoligi: {e}."))
                    time.sleep(10)
                    continue
                except ValueError:
                    self.stdout.write(
                        self.style.WARNING(f"Sahifa {page} dan JSON javob o'qilmadi. Qayta urinilmoqda..."))
                    time.sleep(2)
                    continue

                if not items:
                    self.stdout.write(self.style.SUCCESS(f"Sahifa {page} da ma'lumot topilmadi. Parsing yakunlandi."))
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
                            self.stdout.write(self.style.WARNING(f"Skipped item {item_id}: File size {file_size_str} exceeds 50MB"))
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
                self.stdout.write(self.style.SUCCESS(f"--- Sahifa {page} Statistikasi ---"))
                self.stdout.write(f"  - Jami elementlar: {len(items)}")
                self.stdout.write(self.style.SUCCESS(f"  - Yangi qo'shilganlar: {created_count}"))
                self.stdout.write(self.style.HTTP_INFO(f"  - Yangilanganlar: {updated_count}"))
                self.stdout.write(self.style.ERROR(f"  - O'tkazib yuborildi (yaroqsiz URL): {invalid_url_count}"))
                self.stdout.write(self.style.WARNING(f"  - O'tkazib yuborildi (fayl hajmi > 50MB): {skipped_large_file_count}"))

                progress.update_progress(page)
                page += 1
                time.sleep(0.02)

        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\n\nParsing foydalanuvchi tomonidan to'xtatildi."))
        finally:
            self.stdout.write(self.style.SUCCESS(
                f"\n{'=' * 20} PARSING YAKUNLANDI {'=' * 20}\n"
                f"Jami qo'shildi: {total_created}\n"
                f"Jami yangilandi: {total_updated}\n"
                f"Jami o'tkazib yuborildi (fayl hajmi > 50MB yoki yaroqsiz URL): {invalid_url_count + skipped_large_file_count}\n"
                f"Oxirgi muvaffaqiyatli sahifa: {progress.last_page}\n"
            ))