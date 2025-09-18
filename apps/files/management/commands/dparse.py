# apps/multiparser/management/commands/dparse.py

from django.core.management.base import BaseCommand
from django.db.models import Q
from ...models import Document
from ...tasks import process_document_pipeline

class Command(BaseCommand):
    help = "Qayta ishlanmagan hujjatlar uchun to'liq qayta ishlash zanjirini ishga tushiradi."

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=100, help="Bir martada nechta hujjatni qayta ishlash kerak.")

    def handle(self, *args, **options):
        limit = options['limit']
        self.stdout.write(self.style.SUCCESS("--- Hujjatlarni qayta ishlash zanjirini rejalashtirish boshlandi ---"))

        # To'liq qayta ishlanmagan hujjatlarni topamiz.
        # Ya'ni, o'chirish statusi "completed" bo'lmagan barcha hujjatlar.
        documents_to_process = Document.objects.filter(
            parse_file_url__isnull=False,
            completed = False
        ).order_by('created_at')[:limit]

        count = documents_to_process.count()
        if not count:
            self.stdout.write(self.style.WARNING("Qayta ishlanadigan hujjatlar topilmadi."))
            return

        self.stdout.write(f"{count} ta hujjat qayta ishlash uchun rejalashtirilmoqda...")

        scheduled_count = 0
        for i, document in enumerate(documents_to_process):
            # Telegram'ga bosimni kamaytirish uchun har bir vazifa orasida 15 soniya pauza
            delay_seconds = i * 15
            process_document_pipeline.apply_async(args=[document.id], countdown=delay_seconds)
            scheduled_count += 1

        self.stdout.write(self.style.SUCCESS(f"Muvaffaqiyatli rejalashtirildi: {scheduled_count} ta hujjat."))