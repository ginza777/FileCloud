from elasticsearch.helpers import bulk
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
            help="Indeksni qayta yaratadi va barcha ma'lumotlarni qayta indekslaydi"
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Indeksni majburiy qayta yaratadi'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("=== ELASTICSEARCH INDEKS YARATISH BOSHLANDI ==="))

        try:
            # Initialize index
            if options['rebuild'] or options['force']:
                self.stdout.write("Indeks qayta yaratilmoqda...")
                DocumentIndex.init_index()
                self.stdout.write(self.style.SUCCESS("✅ Indeks muvaffaqiyatli yaratildi"))
            else:
                self.stdout.write("Indeks yaratilmoqda...")
                DocumentIndex.init_index()
                self.stdout.write(self.style.SUCCESS("✅ Indeks muvaffaqiyatli yaratildi"))

            # Fetch documents
            self.stdout.write("Hujjatlarni indekslash boshlandi...")
            documents = Document.objects.filter(
                product__isnull=False,
                parse_status='completed'
            ).select_related('product')

            total_docs = documents.count()
            indexed_count = 0
            bulk_actions = []

            self.stdout.write(f"Jami {total_docs} ta hujjat topildi")

            for doc in documents.iterator(chunk_size=1000):  # Use iterator with chunk_size
                try:
                    # Prepare document for bulk indexing
                    action = DocumentIndex.prepare_bulk_action(doc)  # Hypothetical method
                    bulk_actions.append(action)

                    if len(bulk_actions) >= 1000:  # Adjust batch size as needed
                        success, failed = bulk(DocumentIndex.get_es_client(), bulk_actions)
                        indexed_count += success
                        self.stdout.write(f"Indekslandi: {indexed_count}/{total_docs}")
                        bulk_actions = []  # Reset for next batch

                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f"Hujjat {doc.id} indekslashda xato: {e}")
                    )
                    logger.error(f"Document {doc.id} indexing failed: {e}")

            # Index remaining documents
            if bulk_actions:
                success, failed = bulk(DocumentIndex.get_es_client(), bulk_actions)
                indexed_count += success

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