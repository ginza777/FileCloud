from django.core.management.base import BaseCommand
from ...models import Document
from urllib.parse import urlparse
import os
import re

ALL_EXTS = [
    'pdf', 'docx', 'doc', 'pptx', 'ppt', 'xlsx', 'xls', 'txt', 'rtf', 'PDF', 'DOCX', 'DOC', 'PPTX', 'PPT', 'XLSX',
    'XLS', 'TXT', 'RTF',
    'PPT', 'DOC', 'DOCX', 'PPTX', 'PDF', 'XLS', 'XLSX', 'odt', 'ods', 'odp'
]


class Command(BaseCommand):
    help = 'Fix parse_file_url extension to match poster_url extension case for all supported extensions and skip files larger than 50MB. Also reset failed documents.'

    def get_poster_extension(self, poster_url):
        """Extract the document extension from poster_url before any suffixes like _page-1_generate.webp"""
        parsed_url = urlparse(poster_url).path
        filename = os.path.basename(parsed_url)
        # Remove known suffix like _page-1_generate.webp
        if '_page-1_generate.webp' in filename:
            filename = filename.split('_page-1_generate.webp')[0]
        return os.path.splitext(filename)[1]

    def parse_file_size(self, file_size_str):
        """Convert file size string (e.g., '3.49 MB') to bytes"""
        if not file_size_str:
            return 0
        match = re.match(r'(\d+\.?\d*)\s*(MB|GB|KB)', file_size_str, re.IGNORECASE)
        if not match:
            return 0
        size, unit = float(match.group(1)), match.group(2).upper()
        if unit == 'GB':
            return size * 1024 * 1024 * 1024
        elif unit == 'MB':
            return size * 1024 * 1024
        elif unit == 'KB':
            return size * 1024
        return 0

    def has_failed_status(self, doc):
        """Check if document has any failed status"""
        return (
            doc.download_status == 'failed' or
            doc.parse_status == 'failed' or
            doc.index_status == 'failed' or
            doc.telegram_status == 'failed' or
            doc.delete_status == 'failed'
        )

    def reset_document_statuses(self, doc):
        """Reset all document statuses to pending"""
        doc.download_status = 'pending'
        doc.parse_status = 'pending'
        doc.index_status = 'pending'
        doc.telegram_status = 'pending'
        doc.delete_status = 'pending'
        doc.completed = False
        doc.pipeline_running = False
        doc.file_path = None
        doc.save()

    def handle(self, *args, **options):
        updated = 0
        skipped = 0
        reset_count = 0
        
        for doc in Document.objects.all():
            data = doc.json_data or {}
            poster_url = data.get('poster_url')
            file_size_str = data.get('document', {}).get('file_size')

            # Skip if file size > 50MB
            if file_size_str:
                file_size_bytes = self.parse_file_size(file_size_str)
                if file_size_bytes > 50 * 1024 * 1024:  # 50MB in bytes
                    doc.delete()
                    skipped += 1
                    self.stdout.write(self.style.WARNING(
                        f"Skipped and deleted Document {doc.id}: File size {file_size_str} exceeds 50MB"))
                    continue

            # Check if document has any failed status and reset if needed
            if self.has_failed_status(doc):
                self.reset_document_statuses(doc)
                reset_count += 1
                self.stdout.write(self.style.HTTP_INFO(f"Reset failed document {doc.id}"))
                continue

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

        self.stdout.write(self.style.SUCCESS(f"Done. Total updated: {updated}, Total skipped and deleted: {skipped}, Total reset: {reset_count}"))