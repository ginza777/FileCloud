from django.core.management.base import BaseCommand
from apps.files.elasticsearch.documents import DocumentIndex
from apps.files.models import Document
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Elasticsearch indeksini yaratadi va barcha hujjatlarni indekslaydi"

    def add_arguments(self, parser):
        parser.add_argument(
            '--rebuild',
            action='store_true',
            help='Indeksni qayta yaratadi va barcha ma\'lumotlarni qayta indekslaydi'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Indeksni majburiy qayta yaratadi'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("=== ELASTICSEARCH INDEKS YARATISH BOSHLANDI ==="))

        try:
            # Indeksni yaratish
            if options['rebuild'] or options['force']:
                self.stdout.write("Indeks qayta yaratilmoqda...")
                DocumentIndex.init_index()
                self.stdout.write(self.style.SUCCESS("✅ Indeks muvaffaqiyatli yaratildi"))
            else:
                self.stdout.write("Indeks yaratilmoqda...")
                DocumentIndex.init_index()
                self.stdout.write(self.style.SUCCESS("✅ Indeks muvaffaqiyatli yaratildi"))

            # Barcha hujjatlarni indekslash
            self.stdout.write("Hujjatlarni indekslash boshlandi...")

            documents = Document.objects.filter(
                product__isnull=False,
                parse_status='completed'
            ).select_related('product')

            total_docs = documents.count()
            indexed_count = 0

            self.stdout.write(f"Jami {total_docs} ta hujjat topildi")

            for doc in documents:
                try:
                    result = DocumentIndex.index_document(doc)
                    if result:
                        indexed_count += 1
                        if indexed_count % 10 == 0:
                            self.stdout.write(f"Indekslandi: {indexed_count}/{total_docs}")
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f"Hujjat {doc.id} indekslashda xato: {e}")
                    )

            self.stdout.write(
                self.style.SUCCESS(
                    f"=== INDEKS YARATISH YAKUNLANDI ===\n"
                    f"Jami indekslangan: {indexed_count}/{total_docs}"
                )
            )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Indeks yaratishda xato: {e}")
            )
            logger.error(f"Elasticsearch index creation failed: {e}")
