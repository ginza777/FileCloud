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
        parser.add_argument(
            '--batch-size',
            type=int,
            default=400,
            help='Batch hajmi (standart 200)'
        )
        parser.add_argument(
            '--parallel',
            action='store_true',
            help='Parallel indekslash (tezroq, lekin ko\'proq resurs talab qiladi)'
        )
        parser.add_argument(
            '--include-partial',
            action='store_true',
            help='To\'liq tugallanmagan hujjatlarni ham indekslash (parse_status=completed)'
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

            # Filter logic based on options
            if options.get('include_partial', False):
                # Include partially completed documents (parse_status=completed)
                documents = Document.objects.filter(
                    product__isnull=False,
                    parse_status='completed'
                ).select_related('product')
                self.stdout.write("⚠️  To'liq tugallanmagan hujjatlarni ham indekslash rejimi faollashtirildi")
            else:
                # Only fully completed documents
                documents = Document.objects.filter(
                    product__isnull=False,
                    completed=True
                ).select_related('product')
                self.stdout.write("✅ Faqat to'liq tugallangan hujjatlarni indekslash rejimi")

            total_docs = documents.count()
            indexed_count = 0

            self.stdout.write(f"Jami {total_docs} ta hujjat topildi")

            # Batch processing bilan tezlashtirish
            batch_size = options.get('batch_size', 200)
            use_parallel = options.get('parallel', False)
            
            self.stdout.write(f"Batch hajmi: {batch_size}")
            if use_parallel:
                self.stdout.write("Parallel indekslash faollashtirildi")
            
            if use_parallel:
                # Parallel processing
                from concurrent.futures import ThreadPoolExecutor, as_completed
                import threading
                
                def process_batch(batch_docs):
                    try:
                        return DocumentIndex.bulk_index_documents(batch_docs)
                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(f"Batch indekslashda xato: {e}")
                        )
                        return 0
                
                # Hujjatlarni batchlarga bo'lish
                batches = []
                batch_docs = []
                for doc in documents:
                    batch_docs.append(doc)
                    if len(batch_docs) >= batch_size:
                        batches.append(batch_docs)
                        batch_docs = []
                
                if batch_docs:
                    batches.append(batch_docs)
                
                # Parallel indekslash
                with ThreadPoolExecutor(max_workers=4) as executor:
                    future_to_batch = {executor.submit(process_batch, batch): batch for batch in batches}
                    
                    for future in as_completed(future_to_batch):
                        batch_result = future.result()
                        indexed_count += batch_result
                        self.stdout.write(f"Indekslandi: {indexed_count}/{total_docs}")
            else:
                # Oddiy batch processing
                batch_docs = []
                
                for doc in documents:
                    batch_docs.append(doc)
                    
                    if len(batch_docs) >= batch_size:
                        try:
                            # Batch indekslash
                            indexed_batch = DocumentIndex.bulk_index_documents(batch_docs)
                            indexed_count += indexed_batch
                            self.stdout.write(f"Indekslandi: {indexed_count}/{total_docs}")
                        except Exception as e:
                            self.stdout.write(
                                self.style.ERROR(f"Batch indekslashda xato: {e}")
                            )
                        batch_docs = []
                
                # Qolgan hujjatlarni indekslash
                if batch_docs:
                    try:
                        indexed_batch = DocumentIndex.bulk_index_documents(batch_docs)
                        indexed_count += indexed_batch
                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(f"Oxirgi batch indekslashda xato: {e}")
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
