# apps/multiparser/management/commands/dparse.py

from django.core.management.base import BaseCommand
from django.db import transaction
from ...models import Document
from ...tasks import process_document_pipeline

class Command(BaseCommand):
    help = "Qayta ishlanmagan hujjatlar uchun to'liq qayta ishlash zanjirini ishga tushiradi."

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=100, help="Bir martada nechta hujjatni qayta ishlash kerak.")
        parser.add_argument('--include-failed', action='store_true', help="failed statusidagi hujjatlarni ham qayta ishga tushirish")

    def handle(self, *args, **options):
        limit = options['limit']
        include_failed = options['include_failed']
        self.stdout.write(self.style.SUCCESS("--- Hujjatlarni qayta ishlash zanjirini rejalashtirish boshlandi ---"))

        base_qs = Document.objects.filter(
            parse_file_url__isnull=False,
            completed=False,
            pipeline_running=False  # hali band qilinmaganlar
        )

        if not include_failed:
            # Faqat pending / processing bo'lmagan (ya'ni yana urinish mumkin) download bosqichidagilar
            base_qs = base_qs.exclude(download_status='failed')

        # Deterministik tartib
        candidates = list(base_qs.order_by('created_at')[:limit])

        if not candidates:
            self.stdout.write(self.style.WARNING("Qayta ishlanadigan hujjatlar topilmadi (yoki barchasi allaqachon band)."))
            return

        locked_ids = []
        with transaction.atomic():
            # Har birini qayta tekshirib, optimistik lock o'rnatamiz
            for doc in candidates:
                updated = Document.objects.filter(id=doc.id, pipeline_running=False).update(pipeline_running=True)
                if updated:
                    locked_ids.append(doc.id)

        if not locked_ids:
            self.stdout.write(self.style.WARNING("Hujjatlar allaqachon boshqa jarayon tomonidan band qilingan."))
            return

        self.stdout.write(f"{len(locked_ids)} ta hujjat band qilindi va pipeline uchun rejalashtiriladi...")

        for i, doc_id in enumerate(locked_ids):
            delay_seconds = i * 10  # biroz tezlashtirdik
            process_document_pipeline.apply_async(args=[doc_id], countdown=delay_seconds)

        self.stdout.write(self.style.SUCCESS(f"Muvaffaqiyatli rejalashtirildi: {len(locked_ids)} ta hujjat."))
