"""
Document Image Generation Command
=================================

Bu komanda completed hujjatlar uchun preview rasmlarini yaratadi.
Watermark bilan 5 tagacha sahifa rasmini generatsiya qiladi.

Ishlatish:
    python manage.py generate_document_images
    python manage.py generate_document_images --document "uuid-here"
    python manage.py generate_document_images --limit 50
"""

from django.core.management.base import BaseCommand
from apps.files.models import Document
from apps.files.tasks import generate_document_images_task
from time import perf_counter


class Command(BaseCommand):
    """
    Hujjatlar uchun preview rasmlarini generatsiya qilish komandasi.
    
    Bu komanda:
    1. Completed hujjatlarni topadi
    2. Har bir hujjat uchun preview rasmlarini yaratadi
    3. Watermark qo'shadi
    4. Celery task orqali parallel ishlaydi
    5. Progress hisobotini ko'rsatadi
    """
    
    help = "Completed hujjatlar uchun watermark bilan preview rasmlarini generatsiya qiladi"

    def add_arguments(self, parser):
        parser.add_argument(
            '--document', 
            type=str, 
            help='Muayyan hujjat UUID\'sini ishlash'
        )
        parser.add_argument(
            '--limit', 
            type=int, 
            default=100, 
            help='Indekslash kerak bo\'lgan hujjatlar soni'
        )
        parser.add_argument(
            '--max-pages',
            type=int,
            default=5,
            help='Har bir hujjat uchun maksimal sahifa soni'
        )

    def handle(self, *args, **options):
        """Asosiy rasm generatsiya jarayoni."""
        start_time = perf_counter()
        doc_id = options.get('document')
        limit = options.get('limit')
        max_pages = options.get('max_pages')

        self.stdout.write(
            self.style.SUCCESS("=== Hujjat Rasmlari Generatsiya Jarayoni ===")
        )

        # Hujjatlarni aniqlash
        if doc_id:
            docs = Document.objects.filter(id=doc_id, completed=True)
            header = f"Muayyan hujjat ishlanmoqda: {doc_id}"
        else:
            docs = Document.objects.filter(completed=True).order_by('-created_at')[:limit]
            header = f"Oxirgi {limit} ta completed hujjat ishlanmoqda"

        self.stdout.write(header)

        total = docs.count()
        if total == 0:
            self.stdout.write(
                self.style.WARNING("Mos completed hujjatlar topilmadi.")
            )
            return

        self.stdout.write(f"Jami hujjatlar: {total}")
        self.stdout.write(f"Maksimal sahifalar: {max_pages}")

        # Har bir hujjat uchun task yaratish
        tasks_created = 0
        
        for doc in docs:
            try:
                # Celery task'ni ishga tushirish
                task = generate_document_images_task.delay(
                    str(doc.id), 
                    max_pages=max_pages
                )
                
                tasks_created += 1
                self.stdout.write(
                    f"Hujjat {doc.id} navbatga qo'yildi. Task ID: {task.id}"
                )
                
            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(f"Hujjat {doc.id} da xatolik: {e}")
                )
                continue

        # Yakuniy hisobot
        end_time = perf_counter()
        elapsed_time = end_time - start_time
        
        self.stdout.write(
            self.style.SUCCESS("=== Generatsiya Jarayoni Yakunlandi ===")
        )
        self.stdout.write(f"Navbatga qo'yilgan tasklar: {tasks_created}")
        self.stdout.write(f"Jarayon vaqti: {elapsed_time:.2f} soniya")
        
        if tasks_created > 0:
            self.stdout.write(
                "Rasmlar Celery worker'lar tomonidan generatsiya qilinadi."
            )
