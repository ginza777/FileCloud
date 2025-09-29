# apps/files/management/commands/reset_stuck_pipelines.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.files.models import Document
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Pipeline_running=True bo'lib qolib ketgan hujjatlarni tozalaydi"

    def add_arguments(self, parser):
        parser.add_argument(
            '--timeout-minutes',
            type=int,
            default=60,
            help='Necha daqiqadan keyin pipeline stuck deb hisoblash (default: 60)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Faqat ko\'rsatish, o\'zgartirish qilmaslik'
        )

    def handle(self, *args, **options):
        timeout_minutes = options['timeout_minutes']
        dry_run = options['dry_run']
        
        # Vaqt chegarasini hisoblash
        timeout_threshold = timezone.now() - timezone.timedelta(minutes=timeout_minutes)
        
        # Stuck bo'lgan hujjatlarni topish
        stuck_docs = Document.objects.filter(
            pipeline_running=True,
            updated_at__lt=timeout_threshold
        )
        
        count = stuck_docs.count()
        
        if count == 0:
            self.stdout.write(self.style.SUCCESS("Stuck bo'lgan pipeline'lar topilmadi."))
            return
            
        self.stdout.write(f"Topildi: {count} ta stuck pipeline")
        
        if dry_run:
            self.stdout.write("DRY RUN - Quyidagi hujjatlar qayta ishga tushiriladi:")
            for doc in stuck_docs[:10]:  # Faqat birinchi 10 tasini ko'rsatish
                time_diff = (timezone.now() - doc.updated_at).total_seconds() / 60
                self.stdout.write(f"  - ID: {doc.id}, Oxirgi yangilanish: {time_diff:.1f} daqiqa oldin")
        else:
            # Pipeline_running ni False qilish
            updated_count = stuck_docs.update(pipeline_running=False)
            self.stdout.write(self.style.SUCCESS(f"✅ {updated_count} ta hujjat qayta ishga tushirildi"))
            
            # Statistika
            self.stdout.write(f"Jami hujjatlar: {Document.objects.count()}")
            self.stdout.write(f"Completed: {Document.objects.filter(completed=True).count()}")
            self.stdout.write(f"Pipeline running: {Document.objects.filter(pipeline_running=True).count()}")
