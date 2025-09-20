from django.core.management.base import BaseCommand
from ...models import Document
from urllib.parse import urlparse
import os

ALL_EXTS = [
    'pdf', 'docx', 'doc', 'pptx', 'ppt', 'xlsx', 'xls', 'txt', 'rtf','PDF', 'DOCX', 'DOC', 'PPTX', 'PPT', 'XLSX', 'XLS', 'TXT', 'RTF',
    'PPT', 'DOC', 'DOCX', 'PPTX', 'PDF', 'XLS', 'XLSX', 'odt', 'ods', 'odp'
]

class Command(BaseCommand):
    help = 'Fix parse_file_url extension to match poster_url extension case for all supported extensions.'

    def get_poster_extension(self, poster_url):
        """Extract the document extension from poster_url before any suffixes like _page-1_generate.webp"""
        parsed_url = urlparse(poster_url).path
        filename = os.path.basename(parsed_url)
        # Remove known suffix like _page-1_generate.webp
        if '_page-1_generate.webp' in filename:
            filename = filename.split('_page-1_generate.webp')[0]
        return os.path.splitext(filename)[1]

    def handle(self, *args, **options):
        updated = 0
        for doc in Document.objects.all():
            data = doc.json_data or {}
            poster_url = data.get('poster_url')
            if not poster_url or not doc.parse_file_url:
                continue
            # Get extensions
            poster_ext = self.get_poster_extension(poster_url)
            file_ext = os.path.splitext(urlparse(doc.parse_file_url).path)[1]
            # Remove leading dot for comparison
            poster_ext_nodot = poster_ext[1:] if poster_ext.startswith('.') else poster_ext
            file_ext_nodot = file_ext[1:] if file_ext.startswith('.') else file_ext
            # Check if both are in ALL_EXTS and only case differs
            if (
                poster_ext_nodot.lower() in [e.lower() for e in ALL_EXTS]
                and file_ext_nodot.lower() == poster_ext_nodot.lower()
                and file_ext_nodot != poster_ext_nodot
            ):
                # Replace extension in parse_file_url
                new_url = doc.parse_file_url[:-len(file_ext)] + poster_ext
                doc.parse_file_url = new_url
                doc.save(update_fields=['parse_file_url'])
                updated += 1
                self.stdout.write(self.style.SUCCESS(f"Updated Document {doc.id}: {file_ext} -> {poster_ext}"))
        self.stdout.write(self.style.SUCCESS(f"Done. Total updated: {updated}"))