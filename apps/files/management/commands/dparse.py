# apps/multiparser/management/commands/dparse.py
from django.core.management.base import BaseCommand
from django.db import transaction, DatabaseError
from django.db.models import Q
from ...models import Document
from ...tasks import process_document_pipeline


class Command(BaseCommand):
    help = "Hujjatlarni qayta ishlash uchun pipeline'ga yuboradi."

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            nargs='?',  # Argumentni ixtiyoriy qiladi
            default=None,  # Standart qiymat yo'q
            help='Bir martada nechta hujjatni yuborish. Agar berilmasa, barchasi yuboriladi.'
        )

    def handle(self, *args, **options):
        limit = options.get('limit')

        self.stdout.write(self.style.SUCCESS("--- Hujjatlarni navbatga qo'shish boshlandi ---"))
        if limit:
            self.stdout.write(f"Limit: {limit} ta hujjat")
        else:
            self.stdout.write("Limit belgilanmagan, barcha nomzodlar qayta ishlanadi.")

        # 1. "Mukammal tugallangan" holatni aniqlaymiz (bularni o'tkazib yuboramiz)
        perfectly_completed_q = Q(
            download_status='completed',
            parse_status='completed',
            index_status='completed',
            telegram_status='completed',
            telegram_file_id__isnull=False,
            completed=True,
            pipeline_running=False
        ) & ~Q(telegram_file_id='')

        # 2. Qayta ishlash uchun nomzodlarni topamiz:
        # Hozirda ishlamayotgan VA mukammal tugallanmagan barcha hujjatlar
        candidate_docs = Document.objects.filter(
            pipeline_running=False
        ).exclude(
            perfectly_completed_q
        ).order_by('created_at')

        # Agar limit berilgan bo'lsa, queryni cheklaymiz
        if limit:
            candidate_docs = candidate_docs[:limit]

        queued_count = 0

        # Xotirani tejash uchun .iterator() dan foydalanamiz
        for doc in candidate_docs.iterator():
            try:
                with transaction.atomic():
                    # Poyga holatini oldini olish uchun qatorni qulflaymiz (select_for_update)
                    # nowait=True boshqa tranzaksiya tomonidan qulflangan bo'lsa kutmasdan xato beradi
                    locked_doc = Document.objects.select_for_update(nowait=True).get(pk=doc.pk)

                    # Tranzaksiya ichida qayta tekshiramiz, balki boshqa jarayon ishlab yuborgandir
                    if locked_doc.pipeline_running:
                        continue  # O'tkazib yuboramiz

                    # Agar bu hujjat allaqachon mukammal bo'lsa (ehtimoldan yiroq, lekin tekshiramiz)
                    if Document.objects.filter(perfectly_completed_q, pk=locked_doc.pk).exists():
                        continue

                    # 3. Hujjatni tozalab, "pending" holatiga o'tkazamiz
                    locked_doc.download_status = 'pending'
                    locked_doc.parse_status = 'pending'
                    locked_doc.index_status = 'pending'
                    locked_doc.telegram_status = 'pending'
                    locked_doc.delete_status = 'pending'
                    locked_doc.completed = False
                    # pipeline_running ni Celery task o'zi qiladi
                    locked_doc.save()

                    # 4. Tozalangan hujjatni navbatga qo'shamiz
                    process_document_pipeline.apply_async(args=[locked_doc.id])

                    self.stdout.write(self.style.HTTP_INFO(f"Tozalandi va navbatga qo'shildi: {locked_doc.id}"))
                    queued_count += 1

            except DatabaseError:
                # Agar `nowait=True` tufayli qator qulflangan bo'lsa, bu xato keladi.
                # Bu normal holat, shunchaki o'tkazib yuboramiz.
                self.stdout.write(
                    self.style.WARNING(f"Hujjat ({doc.id}) boshqa jarayon tomonidan band, o'tkazib yuborildi."))
                continue
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Hujjatni ({doc.id}) navbatga qo'shishda kutilmagan xato: {e}"))

        self.stdout.write(
            self.style.SUCCESS(f"--- dparse tugadi. Jami {queued_count} ta hujjat navbatga qo'shildi. ---"))