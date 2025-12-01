"""
Cleanup Blocked Products from Elasticsearch
==========================================

Bu komanda blocked productlarni Elasticsearch dan o'chiradi.
"""

from django.core.management.base import BaseCommand
from apps.files.elasticsearch.documents import DocumentIndex
from apps.files.models import Document, Product


class Command(BaseCommand):
    help = 'Blocked productlarni Elasticsearch dan o\'chirish'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='O\'zgarishlarni saqlamasdan, faqat nima qilinishini ko\'rsatish'
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        
        self.stdout.write(
            self.style.SUCCESS("🧹 Blocked Products Elasticsearch Cleanup")
        )
        self.stdout.write("=" * 60)
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING("⚠️  DRY RUN REJIMI - O'zgarishlar amalga oshirilmaydi\n")
            )
        
        try:
            # Blocked productli documentlarni topish
            blocked_docs = Document.objects.filter(
                product__blocked=True
            ).select_related('product')
            
            total_blocked = blocked_docs.count()
            
            if total_blocked == 0:
                self.stdout.write(
                    self.style.SUCCESS("✅ Blocked productlar topilmadi.")
                )
                return
            
            self.stdout.write(f"📊 Jami blocked productlar: {total_blocked}")
            self.stdout.write("")
            
            # Blocked productlarni ko'rsatish
            self.stdout.write("🔒 Blocked productlar ro'yxati:")
            self.stdout.write("-" * 40)
            
            for doc in blocked_docs[:10]:  # Faqat birinchi 10 tasini ko'rsatish
                self.stdout.write(f"📄 Document ID: {doc.id}")
                self.stdout.write(f"   Title: {doc.product.title[:50]}...")
                self.stdout.write(f"   Blocked Reason: {doc.product.blocked_reason[:50]}...")
                self.stdout.write(f"   Blocked At: {doc.product.blocked_at}")
                self.stdout.write("")
            
            if total_blocked > 10:
                self.stdout.write(f"... va yana {total_blocked - 10} ta blocked product")
                self.stdout.write("")
            
            if not dry_run:
                self.stdout.write(
                    self.style.WARNING("🗑️  Elasticsearch dan o'chirish boshlandi...")
                )
                
                # Elasticsearch dan o'chirish
                deleted_count = DocumentIndex.delete_blocked_documents()
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f"✅ {deleted_count} ta blocked document Elasticsearch dan o'chirildi."
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        "DRY RUN tugadi. Haqiqiy o'zgarishlarni amalga oshirish uchun --dry-run bayrog'isiz ishga tushiring."
                    )
                )
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"❌ Xatolik: {e}")
            )
