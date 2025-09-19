# apps/multiparser/management/commands/dparse.py
from django.core.management.base import BaseCommand
from django.db import transaction
from ...models import Document
from ...tasks import process_document_pipeline

class Command(BaseCommand):
    help = "Oddiy: hujjatlarni pipeline'ga yuborish. Faqat --limit mavjud."

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=1000, help='Bir martada nechta hujjatni yuborish (standart 1000)')

    def handle(self, *args, **options):
        limit = options['limit']
        self.stdout.write(self.style.SUCCESS("--- Oddiy dparse boshlandi ---"))

        qs = Document.objects.filter(
            parse_file_url__isnull=False,
            completed=False,
            pipeline_running=False
        ).order_by('created_at')[:limit]

        docs = list(qs)
        if not docs:
            self.stdout.write(self.style.WARNING('Yuboriladigan hujjat topilmadi.'))
            return

        locked_ids = []
        with transaction.atomic():
            for d in docs:
                updated = Document.objects.filter(id=d.id, pipeline_running=False).update(pipeline_running=True)
                if updated:
                    locked_ids.append(d.id)
        if not locked_ids:
            self.stdout.write(self.style.WARNING('Hech qaysi hujjat band qilinmadi (boshqa jarayon band qilgan bo\'lishi mumkin).'))
            return

        for doc_id in locked_ids:
            process_document_pipeline.apply_async(args=[doc_id])

        self.stdout.write(self.style.SUCCESS(f"{len(locked_ids)} ta hujjat pipeline'ga yuborildi."))
        self.stdout.write(self.style.SUCCESS('--- dparse tugadi ---'))
