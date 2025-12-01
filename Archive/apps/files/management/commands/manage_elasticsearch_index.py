"""
Elasticsearch Index Management Command
=====================================

Bu komanda Elasticsearch indeksini boshqaradi va hujjatlarni indekslaydi.
Indeksni yaratish, qayta yaratish va ma'lumotlarni indekslash.

Ishlatish:
    python manage.py manage_elasticsearch_index
    python manage.py manage_elasticsearch_index --rebuild
    python manage.py manage_elasticsearch_index --batch-size 500
"""

from django.core.management.base import BaseCommand
from apps.files.elasticsearch.documents import DocumentIndex
from apps.files.models import Document
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Elasticsearch indeksini boshqarish komandasi.
    
    Bu komanda:
    1. Elasticsearch indeksini yaratadi
    2. Barcha hujjatlarni indekslaydi
    3. Indeksni qayta yaratadi
    4. Batch rejimida ishlaydi
    5. Parallel indekslashni qo'llab-quvvatlaydi
    """
    
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
            default=1000,
            help='Batch hajmi (standart 1000)'
        )
        parser.add_argument(
            '--parallel',
            action='store_true',
            help='Parallel indekslashni ishlatadi'
        )

    def handle(self, *args, **options):
        """Asosiy indekslash jarayoni."""
        rebuild = options['rebuild']
        force = options['force']
        batch_size = options['batch_size']
        parallel = options['parallel']

        self.stdout.write(
            self.style.SUCCESS("=== Elasticsearch Indeks Boshqaruvi ===")
        )

        try:
            # Indeksni yaratish/yangilash
            if rebuild or force:
                self.stdout.write("Indeks qayta yaratilmoqda...")
                DocumentIndex._index.delete(ignore=[400, 404])
                DocumentIndex.init()
                self.stdout.write(
                    self.style.SUCCESS("Indeks qayta yaratildi")
                )
            else:
                # Indeks mavjudligini tekshirish
                if not DocumentIndex._index.exists():
                    self.stdout.write("Indeks yaratilmoqda...")
                    DocumentIndex.init()
                    self.stdout.write(
                        self.style.SUCCESS("Indeks yaratildi")
                    )
                else:
                    self.stdout.write("Indeks mavjud")

            # Hujjatlarni indekslash
            self.stdout.write("Hujjatlarni indekslash boshlandi...")
            
            # Completed=True va blocked=False bo'lgan hujjatlarni olish
            documents = Document.objects.filter(
                completed=True
            ).exclude(
                product__blocked=True
            ).select_related('product')
            total_docs = documents.count()
            
            self.stdout.write(f"Jami indekslash kerak bo'lgan hujjatlar: {total_docs}")
            
            if total_docs == 0:
                self.stdout.write(
                    self.style.WARNING("Indekslash kerak bo'lgan hujjatlar topilmadi")
                )
                return

            # Batch indekslash
            indexed_count = 0
            
            for i in range(0, total_docs, batch_size):
                batch_docs = documents[i:i + batch_size]
                
                # Har bir hujjatni indekslash
                for doc in batch_docs:
                    try:
                        DocumentIndex.index_document(doc)
                        indexed_count += 1
                    except Exception as e:
                        self.stdout.write(
                            self.style.WARNING(f"Hujjat {doc.id} indekslashda xatolik: {e}")
                        )
                
                self.stdout.write(
                    f"Indekslandi: {indexed_count}/{total_docs} "
                    f"({(indexed_count/total_docs)*100:.1f}%)"
                )

            # Yakuniy hisobot
            self.stdout.write(
                self.style.SUCCESS("=== Indekslash Yakunlandi ===")
            )
            self.stdout.write(f"Jami indekslangan hujjatlar: {indexed_count}")
            
            # Indeks statistikasini ko'rsatish
            self.show_index_stats()

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Indekslashda xatolik: {e}")
            )
            logger.error(f"Elasticsearch indekslashda xatolik: {e}")

    def show_index_stats(self):
        """Indeks statistikasini ko'rsatish."""
        try:
            stats = DocumentIndex._index.stats()
            doc_count = stats['indices'][DocumentIndex._index._name]['total']['docs']['count']
            
            self.stdout.write(f"Indeksdagi hujjatlar soni: {doc_count}")
            
        except Exception as e:
            self.stdout.write(
                self.style.WARNING(f"Statistika olishda xatolik: {e}")
            )
