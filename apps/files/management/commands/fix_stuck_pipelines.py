from django.core.management.base import BaseCommand
from django.db import transaction
from ...models import Document


class Command(BaseCommand):
    help = "Qotib qolgan pipeline holatlarini tuzatadi"

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Faqat ko\'rish, o\'zgartirish emas'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        self.stdout.write(self.style.SUCCESS("=== QOTIB QOLGAN PIPELINE HOLATLARINI TUZATISH ==="))

        # 1. Completed=True lekin pipeline_running=True bo'lgan hujjatlar
        stuck_completed = Document.objects.filter(
            completed=True,
            pipeline_running=True
        )
        
        count_completed = stuck_completed.count()
        self.stdout.write(f"Topildi: {count_completed} ta completed=True, pipeline_running=True hujjat")
        
        if count_completed > 0:
            if not dry_run:
                with transaction.atomic():
                    stuck_completed.update(pipeline_running=False)
                self.stdout.write(self.style.SUCCESS(f"✅ {count_completed} ta hujjat tuzatildi (pipeline_running=False)"))
            else:
                self.stdout.write(f"DRY RUN: {count_completed} ta hujjat tuzatiladi (pipeline_running=False)")

        # 2. Barcha statuslar completed/skipped lekin completed=False bo'lgan hujjatlar  
        done_states = ['completed', 'skipped']
        incomplete_docs = Document.objects.filter(
            download_status__in=done_states,
            parse_status__in=done_states,
            index_status__in=done_states,
            telegram_status__in=done_states,
            delete_status__in=done_states,
            completed=False
        )
        
        count_incomplete = incomplete_docs.count()
        self.stdout.write(f"Topildi: {count_incomplete} ta barcha statuslar tugagan, lekin completed=False hujjat")
        
        if count_incomplete > 0:
            if not dry_run:
                for doc in incomplete_docs:
                    doc.save()  # Bu completed=True qiladi
                self.stdout.write(self.style.SUCCESS(f"✅ {count_incomplete} ta hujjat tuzatildi (completed=True)"))
            else:
                self.stdout.write(f"DRY RUN: {count_incomplete} ta hujjat tuzatiladi (completed=True)")

        # 3. Uzoq vaqt pipeline_running=True holatida qolgan hujjatlar (1 soatdan ortiq)
        from django.utils import timezone
        from datetime import timedelta
        
        one_hour_ago = timezone.now() - timedelta(hours=1)
        long_running = Document.objects.filter(
            pipeline_running=True,
            updated_at__lt=one_hour_ago
        ).exclude(completed=True)
        
        count_long_running = long_running.count()
        self.stdout.write(f"Topildi: {count_long_running} ta 1 soatdan ortiq pipeline_running=True hujjat")
        
        if count_long_running > 0:
            if not dry_run:
                with transaction.atomic():
                    long_running.update(pipeline_running=False)
                self.stdout.write(self.style.WARNING(f"⚠️  {count_long_running} ta uzoq vaqt ishlaydigan hujjat to'xtatildi"))
            else:
                self.stdout.write(f"DRY RUN: {count_long_running} ta uzoq vaqt ishlaydigan hujjat to'xtatiladi")

        # Statistika
        self.stdout.write("\n=== HOZIRGI HOLAT ===")
        total_docs = Document.objects.count()
        completed_docs = Document.objects.filter(completed=True).count()
        running_docs = Document.objects.filter(pipeline_running=True).count()
        pending_docs = Document.objects.filter(completed=False, pipeline_running=False).count()
        
        self.stdout.write(f"Jami hujjatlar: {total_docs}")
        self.stdout.write(f"Tugagan: {completed_docs}")
        self.stdout.write(f"Ishlamoqda: {running_docs}")
        self.stdout.write(f"Kutilmoqda: {pending_docs}")
        
        if dry_run:
            self.stdout.write(self.style.WARNING("\n⚠️  DRY RUN rejimi - hech narsa o'zgartirilmadi"))
            self.stdout.write("Asl o'zgarishlar uchun --dry-run flagini olib tashlang")
        else:
            self.stdout.write(self.style.SUCCESS("\n✅ Barcha muammolar tuzatildi!"))
