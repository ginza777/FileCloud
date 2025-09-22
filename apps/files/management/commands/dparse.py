# apps/multiparser/management/commands/dparse.py
from django.core.management.base import BaseCommand
from django.db import transaction
from ...models import Document
from ...tasks import process_document_pipeline
import re

class Command(BaseCommand):
    help = "Hujjatlarni pipeline'ga yuborish. Chala qolgan hujjatlarni qayta ishlash imkoniyati bilan."

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=1000, help='Bir martada nechta hujjatni yuborish (standart 1000)')
        parser.add_argument('--max-size', type=float, default=50.0, help='Maksimal fayl hajmi MB da (standart 50 MB)')
        parser.add_argument('--include-incomplete', action='store_true', help='Chala qolgan (incomplete) hujjatlarni ham qo\'shish')

    def parse_file_size(self, file_size_str):
        """Parse file size string like '3.49 MB' to float value in MB"""
        if not file_size_str:
            return 0.0
        
        # Extract number and unit from string like "3.49 MB"
        match = re.match(r'([\d.]+)\s*([A-Za-z]+)', file_size_str.strip())
        if not match:
            return 0.0
        
        size_value = float(match.group(1))
        unit = match.group(2).upper()
        
        # Convert to MB
        if unit == 'KB':
            return size_value / 1024
        elif unit == 'MB':
            return size_value
        elif unit == 'GB':
            return size_value * 1024
        else:
            return 0.0

    def is_file_too_large(self, document, max_size_mb):
        """Check if document file size exceeds the maximum allowed size"""
        if not document.json_data:
            return False
        
        try:
            file_size_str = document.json_data.get('document', {}).get('file_size')
            if not file_size_str:
                return False
            
            file_size_mb = self.parse_file_size(file_size_str)
            return file_size_mb > max_size_mb
        except (AttributeError, KeyError, ValueError):
            return False

    def reset_document_statuses(self, document):
        """Hujjat statuslarini reset qilish"""
        document.download_status = 'pending'
        document.parse_status = 'pending'
        document.index_status = 'pending'
        document.telegram_status = 'pending'
        document.delete_status = 'pending'
        document.completed = False
        document.file_path = None
        document.save()

    def is_incomplete_document(self, document):
        """Hujjat chala qolgan yoki xatolik bilan tugagan mi?"""
        failed_or_incomplete_states = ['failed', 'pending', 'processing']
        
        return (
            document.download_status in failed_or_incomplete_states or
            document.parse_status in failed_or_incomplete_states or
            document.index_status in failed_or_incomplete_states or
            document.telegram_status in failed_or_incomplete_states or
            document.delete_status in failed_or_incomplete_states
        )

    def handle(self, *args, **options):
        limit = options['limit']
        max_size_mb = options['max_size']
        include_incomplete = options['include_incomplete']
        
        self.stdout.write(self.style.SUCCESS("--- Oddiy dparse boshlandi ---"))
        self.stdout.write(self.style.SUCCESS(f"Maksimal fayl hajmi: {max_size_mb} MB"))
        
        if include_incomplete:
            self.stdout.write(self.style.SUCCESS("Chala qolgan hujjatlar ham qo'shiladi"))

        # Asosiy query - completed=False va pipeline_running=False
        base_qs = Document.objects.filter(
            parse_file_url__isnull=False,
            completed=False,
            pipeline_running=False
        )
        
        # Agar include_incomplete flag berilgan bo'lsa, chala qolgan hujjatlarni ham qo'shamiz
        if include_incomplete:
            # Chala qolgan hujjatlarni topish
            incomplete_qs = Document.objects.filter(
                parse_file_url__isnull=False,
                pipeline_running=False
            ).exclude(completed=True)
            
            # Ikki query'ni birlashtirish
            combined_ids = set(base_qs.values_list('id', flat=True)) | set(incomplete_qs.values_list('id', flat=True))
            qs = Document.objects.filter(id__in=combined_ids).order_by('created_at')[:limit]
        else:
            qs = base_qs.order_by('created_at')[:limit]

        docs = list(qs)
        
        # Filter out large files va chala qolgan hujjatlarni reset qilish
        filtered_docs = []
        skipped_count = 0
        reset_count = 0
        
        for doc in docs:
            if self.is_file_too_large(doc, max_size_mb):
                skipped_count += 1
                self.stdout.write(
                    self.style.WARNING(f"Fayl o'tkazib yuborildi (hajmi katta): {doc.id}")
                )
            else:
                # Agar chala qolgan hujjat bo'lsa, statuslarini reset qilamiz
                if include_incomplete and self.is_incomplete_document(doc):
                    self.reset_document_statuses(doc)
                    reset_count += 1
                    self.stdout.write(
                        self.style.HTTP_INFO(f"Hujjat statuslari reset qilindi: {doc.id}")
                    )
                
                filtered_docs.append(doc)
        
        if skipped_count > 0:
            self.stdout.write(
                self.style.WARNING(f"Jami {skipped_count} ta fayl hajmi katta bo'lgani uchun o'tkazib yuborildi")
            )
            
        if reset_count > 0:
            self.stdout.write(
                self.style.HTTP_INFO(f"Jami {reset_count} ta chala qolgan hujjat statuslari reset qilindi")
            )
        
        docs = filtered_docs
        
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
