# apps/multiparser/management/commands/dparse.py
from django.core.management.base import BaseCommand
from django.db import transaction, DatabaseError
from ...models import Document
from ...tasks import process_document_pipeline


class Command(BaseCommand):
    help = "Completed=False va pipeline_running=False bo'lgan barcha hujjatlarni pipeline'ga yuboradi."

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            nargs='?',
            default=None,
            help='Bir martada nechta hujjatni tekshirish. Agar berilmasa, barchasi tekshiriladi.'
        )

    def handle(self, *args, **options):
        limit = options.get('limit')

        self.stdout.write(self.style.SUCCESS("--- Hujjatlarni navbatga qo'yish jarayoni boshlandi ---"))
        if limit:
            self.stdout.write(f"Limit: {limit} ta hujjat tekshiriladi.")
        else:
            self.stdout.write("Limit belgilanmagan, barcha nomzodlar tekshiriladi.")

        # Completed=False va pipeline_running=False bo'lgan barcha hujjatlarni topamiz
        candidate_docs = Document.objects.filter(
            completed=False,
            pipeline_running=False
        ).order_by('created_at')

        total_candidates = candidate_docs.count()
        self.stdout.write(f"Jami {total_candidates} ta nomzod topildi (completed=False, pipeline_running=False).")

        if limit:
            candidate_docs = candidate_docs[:limit]

        # Statistika uchun hisoblagichlar
        queued_for_processing_count = 0
        skipped_as_locked_count = 0

        # Xotirani tejash uchun .iterator() dan foydalanamiz
        for doc in candidate_docs.iterator():
            try:
                with transaction.atomic():
                    # Poyga holatini oldini olish uchun qatorni qulflaymiz
                    locked_doc = Document.objects.select_for_update(nowait=True).get(pk=doc.pk)

                    # Barcha statuslarni pending qilib, navbatga qo'shamiz
                    locked_doc.download_status = 'pending'
                    locked_doc.parse_status = 'pending'
                    locked_doc.index_status = 'pending'
                    locked_doc.telegram_status = 'pending'
                    locked_doc.delete_status = 'pending'
                    locked_doc.completed = False
                    locked_doc.pipeline_running = False
                    locked_doc.save()

                    # Hujjatni navbatga qo'shamiz
                    process_document_pipeline.apply_async(args=[locked_doc.id])

                    self.stdout.write(self.style.HTTP_INFO(f"➡️  Navbatga qo'shildi: {locked_doc.id}"))
                    queued_for_processing_count += 1

            except DatabaseError:
                # Agar `nowait=True` tufayli qator qulflangan bo'lsa, bu xato keladi.
                # Bu normal holat, boshqa bir jarayon bu hujjat ustida ishlayotgan bo'lishi mumkin.
                self.stdout.write(
                    self.style.WARNING(f"⚠️  Hujjat ({doc.id}) boshqa jarayon tomonidan band, o'tkazib yuborildi."))
                skipped_as_locked_count += 1
                continue
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"❌ Hujjatni ({doc.id}) navbatga qo'shishda kutilmagan xato: {e}"))

        self.stdout.write(self.style.SUCCESS("\n--- JARAYON YAKUNLANDI: STATISTIKA ---"))
        self.stdout.write(f"➡️  Navbatga qo'shilganlar: {queued_for_processing_count} ta")
        self.stdout.write(f"⚠️  Boshqa jarayon band qilgani uchun o'tkazib yuborilganlar: {skipped_as_locked_count} ta")
        self.stdout.write(self.style.SUCCESS("-----------------------------------------"))