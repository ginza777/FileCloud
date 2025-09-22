from django.core.management.base import BaseCommand
from apps.files.models import Document


class Command(BaseCommand):
    help = 'Telegram file ID yo\'q bo\'lgan hujjatlarni completed=False qiladi'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Faqat ko\'rsatadi, o\'zgartirmaydi',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        # Telegram file ID yo'q bo'lgan completed=True hujjatlarni topish
        docs_to_fix = Document.objects.filter(
            completed=True,
            telegram_file_id__isnull=True
        )
        
        count = docs_to_fix.count()
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING(f'DRY RUN: {count} ta hujjat topildi (o\'zgartirilmaydi)')
            )
            
            # Bir nechta misol ko'rsatish
            for doc in docs_to_fix[:5]:
                self.stdout.write(f'  ID: {doc.id}')
                self.stdout.write(f'  Telegram status: {doc.telegram_status}')
                self.stdout.write(f'  Completed: {doc.completed}')
                self.stdout.write('  ---')
        else:
            # Hujjatlarni completed=False qilish
            updated_count = docs_to_fix.update(completed=False)
            
            self.stdout.write(
                self.style.SUCCESS(f'✅ {updated_count} ta hujjat completed=False qilindi')
            )
            
            # Yangi holatni ko'rsatish
            remaining_completed = Document.objects.filter(completed=True).count()
            self.stdout.write(f'Jami completed=True hujjatlar: {remaining_completed} ta')
