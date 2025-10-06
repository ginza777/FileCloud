"""
Document Processing Command
===========================

Bu komanda mavjud hujjatlarni qayta ishlash uchun pipeline'ga yuboradi.
Completed=False va pipeline_running=False bo'lgan hujjatlarni topib, ularni qayta ishlash uchun navbatga qo'yadi.
"""

from django.core.management.base import BaseCommand
from django.db import transaction, DatabaseError
from apps.files.models import Document
from apps.files.tasks.document_processing import process_document_pipeline


class Command(BaseCommand):
    """
    Hujjatlarni qayta ishlash uchun pipeline'ga yuborish komandasi.
    """

    help = "Completed=False va pipeline_running=False bo'lgan hujjatlarni pipeline'ga yuboradi"

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            nargs='?',
            default=None,
            help='Bir martada nechta hujjatni tekshirish. Agar berilmasa, barchasi tekshiriladi.'
        )
        parser.add_argument(
            '--document-id',
            type=str,
            help='Muayyan hujjat ID\'sini qayta ishlash'
        )

    def handle(self, *args, **options):
        """Asosiy hujjat qayta ishlash jarayoni."""
        limit = options.get('limit')
        document_id = options.get('document_id')

        self.stdout.write(
            self.style.SUCCESS("--- Hujjatlarni navbatga qo'yish jarayoni boshlandi ---")
        )

        if document_id:
            self.stdout.write(f"Muayyan hujjat qayta ishlanmoqda: {document_id}")
            try:
                document = Document.objects.get(id=document_id)
                self.process_single_document(document)
            except Document.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f"Hujjat topilmadi: {document_id}")
                )
                return
        else:
            if limit:
                self.stdout.write(f"Limit: {limit} ta hujjat tekshiriladi.")
            else:
                self.stdout.write("Limit belgilanmagan, barcha nomzodlar tekshiriladi.")

            # Completed=False va pipeline_running=False bo'lgan hujjatlarni topish
            candidate_docs = Document.objects.filter(
                # 1. Barcha jarayonlar tugatilgan (completed) bo'lmasin.
                completed=False,

                # 2. Pipeline ustida ishlamayotgan bo'lsin.
                pipeline_running=False,

                # 3. Telegram fayl ID'si mavjud bo'lsin (NULL emas).
                telegram_file_id__isnull=False,
            ).exclude(
                # 4. Parse holati 'completed' bo'lmasin.
                parse_status='completed'
            ).exclude(
                # 5. Telegram fayl ID'si bo'sh string ('') bo'lmasin.
                telegram_file_id=''
            ).order_by('created_at') # Eng eski hujjatlardan boshlab


            if limit:
                candidate_docs = candidate_docs[:limit]

            total_candidates = candidate_docs.count()
            self.stdout.write(f"Topilgan nomzod hujjatlar: {total_candidates}")

            if total_candidates == 0:
                self.stdout.write(
                    self.style.WARNING("Qayta ishlash uchun nomzod hujjatlar topilmadi.")
                )
                return

            # Har bir hujjatni qayta ishlash
            processed_count = 0
            for doc in candidate_docs:
                try:
                    self.process_single_document(doc)
                    processed_count += 1
                except Exception as e:
                    self.stdout.write(
                        self.style.WARNING(f"Hujjat {doc.id} da xatolik: {e}. Navbatga qo'yish muvaffaqiyatsiz.")
                    )
                    # Xato bo'lsa ham loopni davom ettirish
                    continue

            self.stdout.write(
                self.style.SUCCESS(f"Jami {processed_count} hujjat navbatga qo'yildi.")
            )

    def process_single_document(self, document):
        """
        Bitta hujjatni qayta ishlash uchun yuborish.
        """
        # Tranzaksiya qismi: Documentni yangilash va Taskni yuborish
        try:
            with transaction.atomic():
                # Pipeline holatini yangilash (faqat bitta field)
                document.pipeline_running = True
                document.save(update_fields=['pipeline_running'])

                # Celery task'ni ishga tushirish
                task = process_document_pipeline.delay(str(document.id))

            self.stdout.write(
                self.style.SUCCESS(
                    f"Hujjat {document.id} navbatga qo'yildi. Task ID: {task.id}"
                )
            )

        except DatabaseError as e:
            # Database xatoligi yuzaga kelsa, uni ushlab, qayta tashlash
            self.stdout.write(
                self.style.ERROR(f"Database xatoligi: {e}. Tranzaksiya bekor qilindi.")
            )
            raise
        except Exception as e:
            # Kutilmagan xatolikni ushlab, qayta tashlash
            self.stdout.write(
                self.style.ERROR(f"Kutilmagan xatolik: {e}. Task yuborilmadi.")
            )
            raise