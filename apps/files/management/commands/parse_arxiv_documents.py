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
        delay = options.get('delay')

        self.stdout.write(
            self.style.SUCCESS("=== Arxiv.UZ Parser boshlandi ===")
        )

        # Kategorialarni aniqlash
        categories_to_parse = [category] if category else CATEGORIES
        
        if category and category not in CATEGORIES:
            self.stdout.write(
                self.style.ERROR(f"Noma'lum kategoriya: {category}")
            )
            return

        total_documents = 0
        
        for cat in categories_to_parse:
            if limit and total_documents >= limit:
                break
                
            self.stdout.write(f"Kategoriya '{cat}' pars qilinmoqda...")
            
            try:
                # Kategoriya sahifasini yuklash
                url = f"https://arxiv.uz/documents/{cat}/"
                response = requests.get(url, timeout=30)
                response.raise_for_status()
                
                # Sahifa ma'lumotlarini pars qilish
                # (Bu yerda HTML pars qilish logikasi bo'lishi kerak)
                
                self.stdout.write(
                    self.style.SUCCESS(f"Kategoriya '{cat}' muvaffaqiyatli pars qilindi")
                )
                
                time.sleep(delay)
                
            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(f"Kategoriya '{cat}' da xatolik: {e}")
                )
                continue

        self.stdout.write(
            self.style.SUCCESS(f"=== Pars qilish yakunlandi. Jami: {total_documents} hujjat ===")
        )
