"""
Pipeline Reset Command
======================

Bu komanda stuck bo'lib qolgan pipeline'larni qayta tiklaydi.
Pipeline_running=True bo'lib qolgan hujjatlarni tozalaydi.

Ishlatish:
    python manage.py reset_stuck_pipelines
    python manage.py reset_stuck_pipelines --timeout-minutes 30
    python manage.py reset_stuck_pipelines --dry-run
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.files.models import Document
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Stuck pipeline'larni qayta tiklash komandasi.
    
    Bu komanda:
    1. Pipeline_running=True bo'lib qolgan hujjatlarni topadi
    2. Belgilangan vaqtdan eski hujjatlarni qayta tiklaydi
    3. Pipeline holatini False qiladi
    4. Dry-run rejimida faqat ko'rsatadi
    """
    
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
        """Asosiy pipeline qayta tiklash jarayoni."""
        timeout_minutes = options['timeout_minutes']
        dry_run = options['dry_run']
        
        self.stdout.write(
            self.style.SUCCESS("=== Stuck Pipeline'lar Qayta Tiklash ===")
        )
        
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN rejimi - o'zgartirishlar amalga oshirilmaydi"))
        
        self.stdout.write(f"Timeout: {timeout_minutes} daqiqa")
        
        # Vaqt chegarasini hisoblash
        timeout_threshold = timezone.now() - timezone.timedelta(minutes=timeout_minutes)
        
        # Stuck pipeline'larni topish
        stuck_docs = Document.objects.filter(
            pipeline_running=True,
            updated_at__lt=timeout_threshold
        )
        
        total_stuck = stuck_docs.count()
        
        if total_stuck == 0:
            self.stdout.write(
                self.style.SUCCESS("Stuck pipeline'lar topilmadi")
            )
            return
        
        self.stdout.write(f"Topilgan stuck pipeline'lar: {total_stuck}")
        
        # Har bir stuck hujjatni ko'rsatish
        for doc in stuck_docs:
            last_update = doc.updated_at.strftime("%Y-%m-%d %H:%M:%S")
            self.stdout.write(
                f"  Hujjat {doc.id}: oxirgi yangilanish {last_update}"
            )
        
        if not dry_run:
            # Pipeline'larni qayta tiklash
            updated_count = stuck_docs.update(pipeline_running=False)
            
            self.stdout.write(
                self.style.SUCCESS(f"{updated_count} ta pipeline qayta tiklandi")
            )
        else:
            self.stdout.write(
                self.style.WARNING(f"{total_stuck} ta pipeline qayta tiklanadi (dry-run)")
            )
        
        # Yakuniy hisobot
        self.stdout.write(
            self.style.SUCCESS("=== Pipeline Qayta Tiklash Yakunlandi ===")
        )
