"""
Backfill Document Images Command
================================

Bu komanda `completed=True` bo'lgan, lekin sahifa rasmlari
generatsiya qilinmagan hujjatlarni topadi va ular uchun
`generate_document_previews` task'ini chaqiradi.

Ishlatish:
    python manage.py backfill_images
    python manage.py backfill_images --limit 100
    python manage.py backfill_images --document-id "uuid-here"
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from apps.files.models import Document
from apps.files.tasks.image_processing import generate_document_previews
import uuid


class Command(BaseCommand):
    help = "Mavjud 'completed=True' hujjatlar uchun sahifa rasmlarini generatsiya qiladi"

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            nargs='?',
            default=None,
            help="Bir martada nechta hujjatni navbatga qo'yish."
        )
        parser.add_argument(
            '--document-id',
            type=str,
            nargs='?',
            default=None,
            help='Faqat bitta aniq hujjatni qayta ishlash.'
        )

    @transaction.atomic
    def handle(self, *args, **options):
        limit = options.get('limit')
        document_id = options.get('document_id')

        if document_id:
            # Aniq bitta hujjatni qayta ishlash
            try:
                doc_id_uuid = uuid.UUID(document_id)
                candidate_docs = Document.objects.filter(id=doc_id_uuid)
                self.stdout.write(self.style.NOTICE(f"Faqat {document_id} ID li hujjat qidirilmoqda..."))
            except ValueError:
                self.stdout.write(self.style.ERROR("Noto'g'ri UUID format."))
                return
        else:
            # Rasmlari yo'q va 'completed=True' bo'lgan hujjatlarni qidirish
            candidate_docs = Document.objects.filter(
                completed=True,
                images__isnull=True  # Bog'liq 'DocumentImage' obyektlari yo'q
            ).order_by('-created_at')  # Eng yangilaridan boshlash

            if limit:
                candidate_docs = candidate_docs[:limit]

        if not candidate_docs.exists():
            self.stdout.write(
                self.style.SUCCESS("Rasmlarni generatsiya qilish uchun hujjatlar topilmadi. Barchasi joyida!"))
            return

        self.stdout.write(f"Jami {candidate_docs.count()} ta hujjat rasm generatsiyasi uchun navbatga qo'yiladi...")

        processed_count = 0
        for doc in candidate_docs:
            try:
                # Taskni chaqirish
                generate_document_previews.delay(str(doc.id))
                processed_count += 1
                self.stdout.write(f"  -> Navbatga qo'yildi: {doc.id} ({doc.file_name})")
            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(f"Hujjat {doc.id} ni navbatga qo'yishda xatolik: {e}")
                )
                continue

        self.stdout.write(
            self.style.SUCCESS(
                f"\nJami {processed_count} ta hujjat rasmlarni generatsiya qilish uchun muvaffaqiyatli navbatga qo'yildi.")
        )