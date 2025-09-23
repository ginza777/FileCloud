# apps/multiparser/management/commands/dparse.py
from django.core.management.base import BaseCommand
from django.db import transaction, DatabaseError
from ...models import Document
from ...tasks import process_document_pipeline


class Command(BaseCommand):
    help = "Hujjatlarni holatini tekshirib, kerak bo'lsa tozalab, qayta ishlash uchun pipeline'ga yuboradi."

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

        # Qayta ishlash uchun nomzodlarni topamiz: hozirda ishlamayotgan barcha hujjatlar
        candidate_docs = Document.objects.filter(pipeline_running=False).order_by('created_at')

        total_candidates = candidate_docs.count()
        self.stdout.write(f"Jami {total_candidates} ta nomzod topildi.")

        if limit:
            candidate_docs = candidate_docs[:limit]

        # Statistika uchun hisoblagichlar
        updated_as_completed_count = 0
        queued_for_processing_count = 0
        skipped_as_locked_count = 0

        # Xotirani tejash uchun .iterator() dan foydalanamiz
        for doc in candidate_docs.iterator():
            try:
                with transaction.atomic():
                    # Poyga holatini oldini olish uchun qatorni qulflaymiz
                    locked_doc = Document.objects.select_for_update(nowait=True).get(pk=doc.pk)

                    # 1-shart: To'g'ri, yakuniy holat (ideal holat)
                    is_ideal_state = (
                        locked_doc.parse_status == 'completed' and
                        locked_doc.index_status == 'completed' and
                        locked_doc.telegram_file_id is not None and
                        locked_doc.telegram_file_id.strip() != ''
                    )

                    if is_ideal_state:
                        # Hujjat allaqachon yakunlangan, shunchaki holatini to'g'rilab qo'yamiz
                        locked_doc.download_status = 'completed'
                        locked_doc.telegram_status = 'completed'
                        locked_doc.delete_status = 'completed'
                        locked_doc.completed = True
                        locked_doc.save()

                        self.stdout.write(self.style.SUCCESS(f"✅ Holati to'g'rilandi (yakunlangan): {locked_doc.id}"))
                        updated_as_completed_count += 1
                    else:
                        # Hujjat ideal holatda emas, uni tozalab, navbatga qo'shamiz
                        locked_doc.download_status = 'pending'
                        locked_doc.parse_status = 'pending'
                        locked_doc.index_status = 'pending'
                        locked_doc.telegram_status = 'pending'
                        locked_doc.delete_status = 'pending'
                        locked_doc.completed = False
                        # pipeline_running ni Celery task o'zi True qiladi, biz False holatda saqlaymiz
                        locked_doc.save()

                        # Tozalangan hujjatni navbatga qo'shamiz
                        process_document_pipeline.apply_async(args=[locked_doc.id])

                        self.stdout.write(self.style.HTTP_INFO(f"➡️  Navbatga qo'shildi (pending): {locked_doc.id}"))
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
        self.stdout.write(f"✅ Yakunlangan deb topilib, holati yangilanganlar: {updated_as_completed_count} ta")
        self.stdout.write(f"➡️  Qayta ishlash uchun navbatga qo'shilganlar: {queued_for_processing_count} ta")
        self.stdout.write(f"⚠️  Boshqa jarayon band qilgani uchun o'tkazib yuborilganlar: {skipped_as_locked_count} ta")
        self.stdout.write(self.style.SUCCESS("-----------------------------------------"))