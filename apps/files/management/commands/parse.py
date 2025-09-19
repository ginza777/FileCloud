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


def extract_file_url(poster_url):
    """Poster URL'dan asosiy fayl URL'ini ajratib oladi."""
    if not poster_url:
        return None

    # Handle direct document URLs
    if 'documents' in poster_url and any(ext in poster_url.lower() for ext in ['.pdf', '.docx', '.doc', '.pptx', '.ppt', '.xlsx', '.xls', '.txt', '.rtf', '.odt', '.ods', '.odp']):
        return poster_url

    # Extract document ID from the poster URL
    uuid_match = re.search(r'file-(\d+)', poster_url)
    if not uuid_match:
        return None

    file_id = uuid_match.group(1)
    return f"https://soff.uz/api/v1/document/download/{file_id}"


class Command(BaseCommand):
    help = 'Soff.uz saytidan faqat yangi mahsulotlarni olib bazaga qo`shadi (Tuzatilgan versiya)'

    def add_arguments(self, parser):
        parser.add_argument('--start-page', type=int, default=1000,
                            help='Boshlanadigan sahifa (standart: oxirgi to`xtagan joydan)')
        parser.add_argument('--end-page', type=int, default=100000, help='Tugaydigan sahifa (standart: cheksiz)')
        parser.add_argument('--reset-progress', action='store_true', help='Parsing jarayonini 1-sahifadan boshlash')

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("=== MA'LUMOTLARNI PARSE QILISH BOSHLANDI (SODDA REJIM) ==="))

        progress = ParseProgress.get_current_progress()

        if options['reset_progress']:
            progress.last_page = 0
            progress.save()
            self.stdout.write(self.style.SUCCESS('Parsing jarayoni 1-sahifaga qaytarildi.'))

        start_page = options['start_page'] if options['start_page'] is not None else progress.last_page + 1
        end_page = options['end_page']

        page = start_page
        total_created = 0

        try:
            while True:
                if end_page and page > end_page:
                    self.stdout.write(self.style.WARNING(f"Belgilangan oxirgi sahifaga ({end_page}) yetildi."))
                    break

                self.stdout.write(f"\nSahifa {page} qayta ishlanmoqda...")

                # Get valid token before making request
                token = get_valid_soff_token()
                if not token:
                    self.stdout.write(self.style.ERROR("Token olinmadi. Parsing to'xtatildi."))
                    break

                base_api_url = BASE_API_URL_TEMPLATE.replace(SOFF_BUILD_ID_HOLDER, token)
                site_token = SiteToken.objects.filter(name='soff').first()

                headers = {
                    "accept": "*/*",
                    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                    "referer": "https://soff.uz/scientific-resources/all"
                }
                cookies = {"token": site_token.auth_token if site_token else None}

                try:
                    response = requests.get(f"{base_api_url}?page={page}", headers=headers, cookies=cookies, timeout=30)
                    response.raise_for_status()
                    data = response.json()
                    items = data.get("pageProps", {}).get("productsData", {}).get("results", [])

                except requests.exceptions.RequestException as e:
                    if response.status_code == 404:
                        self.stdout.write(self.style.WARNING("Token eskirgan, yangilanmoqda..."))
                        # Token will be refreshed in the next iteration
                        time.sleep(2)
                        continue
                    else:
                        self.stdout.write(self.style.ERROR(f"Sahifa {page} da tarmoq xatoligi: {e}"))
                        time.sleep(10)
                        continue
                except ValueError:
                    self.stdout.write(self.style.WARNING("JSON xatolik, token yangilanmoqda..."))
                    time.sleep(2)
                    continue

                if not items:
                    self.stdout.write(self.style.SUCCESS(f"Sahifa {page} da ma'lumot topilmadi. Parsing yakunlandi."))
                    break

                product_ids_on_page = {item.get("id") for item in items if item.get("id")}
                existing_ids = set(Product.objects.filter(id__in=product_ids_on_page).values_list('id', flat=True))
                new_items = [item for item in items if item.get("id") and item.get("id") not in existing_ids]

                if not new_items:
                    self.stdout.write(f"Sahifa {page} da yangi ma'lumotlar yo'q. O'tkazib yuborildi.")
                    progress.update_progress(page)
                    page += 1
                    continue

                docs_to_create = []
                doc_product_data_map = {}

                for item in new_items:
                    file_url = extract_file_url(item.get("poster_url"))
                    # ===== ✅ TALABINGIZGA BINOAN QO'SHILDI =====
                    # Agar fayl URL'i topilmasa, keyingisiga o'tamiz
                    if not file_url:
                        self.stdout.write(
                            self.style.WARNING(f"ID {item.get('id')} uchun fayl URL topilmadi, o'tkazib yuborildi."))
                        continue

                    doc = Document(
                        parse_file_url=file_url,
                        json_data=item
                    )
                    docs_to_create.append(doc)
                    doc_product_data_map[doc] = item

                if docs_to_create:
                    with transaction.atomic():
                        Document.objects.bulk_create(docs_to_create, batch_size=100)

                        products_to_create = []
                        for doc in docs_to_create:
                            item_data = doc_product_data_map[doc]
                            prod = Product(
                                id=item_data.get("id"),
                                title=item_data.get("title", ""),
                                slug=item_data.get("slug", ""),
                                document=doc
                            )
                            products_to_create.append(prod)

                        Product.objects.bulk_create(products_to_create, batch_size=100)

                    created_count = len(products_to_create)
                    total_created += created_count
                    self.stdout.write(
                        self.style.SUCCESS(f"Sahifa {page} dan {created_count} ta yangi ma'lumot qo'shildi."))

                progress.update_progress(page)
                page += 1
                time.sleep(0.5)

        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\n\nParsing foydalanuvchi tomonidan to'xtatildi."))
        finally:
            self.stdout.write(self.style.SUCCESS(
                f"\n=== PARSING YAKUNLANDI ===\n"
                f"Jami qo'shildi: {total_created}\n"
                f"Oxirgi muvaffaqiyatli sahifa: {progress.last_page}\n"
            ))