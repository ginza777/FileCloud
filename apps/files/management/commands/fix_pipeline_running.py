from django.core.management.base import BaseCommand
from apps.files.models import Document


class Command(BaseCommand):
    help = 'Pipeline ishlayotgan hujjatlarni pending holatiga qaytarish'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Faqat ko\'rsatish, o\'zgartirmaslik',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        # Pipeline ishlayotgan hujjatlarni topish
        pipeline_running_docs = Document.objects.filter(pipeline_running=True)
        count = pipeline_running_docs.count()
        
        self.stdout.write(f"Pipeline ishlayotgan hujjatlar: {count} ta")
        
        if count == 0:
            self.stdout.write(self.style.SUCCESS("Barcha hujjatlar to'g'ri holatda"))
            return
        
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - Hech narsa o'zgartirilmaydi"))
            for doc in pipeline_running_docs[:10]:  # Faqat birinchi 10 tasini ko'rsatish
                self.stdout.write(f"  - {doc.id}: {doc.download_status}/{doc.parse_status}/{doc.index_status}/{doc.telegram_status}")
            if count > 10:
                self.stdout.write(f"  ... va yana {count - 10} ta")
        else:
            # Hujjatlarni pending holatiga qaytarish
            updated = pipeline_running_docs.update(
                pipeline_running=False,
                download_status='pending',
                parse_status='pending',
                index_status='pending',
                telegram_status='pending',
                delete_status='pending',
                completed=False
            )
            
            self.stdout.write(
                self.style.SUCCESS(f"✅ {updated} ta hujjat pending holatiga qaytarildi")
            )
