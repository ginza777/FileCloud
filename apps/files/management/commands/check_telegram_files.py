from django.core.management.base import BaseCommand
from apps.files.models import Document, Product
from django.db.models import Q


class Command(BaseCommand):
    help = 'Check documents without telegram_file_id'

    def handle(self, *args, **options):
        # Telegram file_id bo'sh bo'lgan hujjatlarni topish
        docs_without_file_id = Document.objects.filter(
            Q(telegram_file_id__isnull=True) | Q(telegram_file_id='')
        ).select_related('product')
        
        self.stdout.write(f'Telegram file_id bo\'sh bo\'lgan hujjatlar soni: {docs_without_file_id.count()}')
        
        if docs_without_file_id.exists():
            self.stdout.write('\nBirinchi 10 ta hujjat:')
            for doc in docs_without_file_id[:10]:
                product_title = doc.product.title if doc.product else "No product"
                self.stdout.write(f'ID: {doc.id}, Status: {doc.telegram_status}, Product: {product_title}')
        
        # Telegram status bo'yicha statistikalar
        self.stdout.write('\nTelegram status bo\'yicha statistikalar:')
        for status in ['pending', 'processing', 'completed', 'failed', 'skipped']:
            count = Document.objects.filter(telegram_status=status).count()
            self.stdout.write(f'{status}: {count}')
