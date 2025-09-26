from django.core.management.base import BaseCommand
from apps.files.models import Document
from apps.files.tasks import generate_document_images_task
from time import perf_counter


class Command(BaseCommand):
    help = "Generate up to 5 watermarked preview images for completed documents"

    def add_arguments(self, parser):
        parser.add_argument('--document', type=str, help='Specific document UUID to process')
        parser.add_argument('--limit', type=int, default=100, help='Limit number of documents to enqueue')

    def handle(self, *args, **options):
        start = perf_counter()
        doc_id = options.get('document')
        limit = options.get('limit')

        if doc_id:
            docs = Document.objects.filter(id=doc_id, completed=True)
            header = f"1. Processing specific document: {doc_id}"
        else:
            docs = Document.objects.filter(completed=True).order_by('-created_at')[:limit]
            header = f"Processing last {limit} completed documents"

        total = docs.count()
        if total == 0:
            self.stdout.write(self.style.WARNING("No matching completed documents found."))
            return

        self.stdout.write(self.style.NOTICE("=" * 60))
        self.stdout.write(self.style.NOTICE(header))
        self.stdout.write(self.style.NOTICE(f"Total: {total}"))
        self.stdout.write(self.style.NOTICE("=" * 60))

        enqueued = 0
        for idx, doc in enumerate(docs, start=1):
            line = f"{idx:03d}. Enqueue → {doc.id} | title: {getattr(doc.product, 'title', '')[:60]}"
            self.stdout.write(line)
            generate_document_images_task.delay(str(doc.id))
            enqueued += 1

        dur = perf_counter() - start
        self.stdout.write(self.style.SUCCESS("-" * 60))
        self.stdout.write(self.style.SUCCESS(f"Done. Enqueued: {enqueued}/{total} | Time: {dur:.2f}s"))
        self.stdout.write(self.style.SUCCESS("Use Flower or logs to monitor Celery workers."))


