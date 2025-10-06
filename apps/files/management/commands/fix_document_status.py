"""
Fix Document Completion Status
================================

Bu komanda Document'larning completed statusini to'g'rilaydi.
Agar document'da parsed_content, telegram_file_id mavjud bo'lsa,
lekin completed=False bo'lsa, uni to'g'rilaydi.

Ishlatish:
    python manage.py fix_document_status
    python manage.py fix_document_status --dry-run
"""

from django.core.management.base import BaseCommand
from apps.files.models import Document, Product


class Command(BaseCommand):
    """
    Document completion statusini tuzatish komandasi.
    
    Bu komanda quyidagilarni bajaradi:
    1. telegram_file_id mavjud
    2. product.parsed_content mavjud
    3. Lekin completed=False bo'lgan document'larni topadi va tuzatadi
    """
    
    help = "Document'larning completed statusini to'g'rilaydi"

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Faqat ko\'rish, o\'zgartirmaslik'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        self.stdout.write(self.style.SUCCESS(
            "╔════════════════════════════════════════════════════════════════╗"
        ))
        self.stdout.write(self.style.SUCCESS(
            "║     🔧 DOCUMENT STATUS TUZATISH                                ║"
        ))
        self.stdout.write(self.style.SUCCESS(
            "╚════════════════════════════════════════════════════════════════╝"
        ))
        self.stdout.write("")
        
        if dry_run:
            self.stdout.write(self.style.WARNING("⚠️  DRY RUN MODE - O'zgarishlar saqlanmaydi\n"))
        
        # Tuzatish kerak bo'lgan document'larni topish
        docs_to_fix = Document.objects.filter(
            telegram_file_id__isnull=False,
            product__parsed_content__isnull=False,
            completed=False
        )
        
        total_to_fix = docs_to_fix.count()
        self.stdout.write(f"📊 Tuzatish kerak: {total_to_fix} ta document\n")
        
        if total_to_fix == 0:
            self.stdout.write(self.style.SUCCESS("✅ Barcha document'lar to'g'ri holatda!"))
            return
        
        # Har bir document haqida ma'lumot
        self.stdout.write("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        self.stdout.write("📋 TUZATISH KERAK BO'LGAN DOCUMENT'LAR:")
        self.stdout.write("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
        
        fixed_count = 0
        failed_count = 0
        
        for doc in docs_to_fix[:10]:  # Birinchi 10 tasini ko'rsatish
            try:
                product = doc.product
                self.stdout.write(f"📄 Document ID: {doc.id}")
                self.stdout.write(f"   ├─ Telegram File ID: ✅ Mavjud")
                self.stdout.write(f"   ├─ Parsed Content: ✅ Mavjud ({len(product.parsed_content or '')} bytes)")
                self.stdout.write(f"   └─ Status: ⚠️  completed=False → ✅ completed=True")
            except Exception as e:
                self.stdout.write(f"   └─ ❌ Xatolik: {e}")
        
        if total_to_fix > 10:
            self.stdout.write(f"\n... va yana {total_to_fix - 10} ta document")
        
        # Tuzatish
        if not dry_run:
            self.stdout.write("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            self.stdout.write("🔧 TUZATISH BOSHLANDI...")
            self.stdout.write("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
            
            for doc in docs_to_fix:
                try:
                    # Barcha statuslarni completed ga o'rnatish
                    doc.completed = True
                    doc.pipeline_running = False
                    doc.download_status = 'completed'
                    doc.parse_status = 'completed'
                    doc.telegram_status = 'completed'
                    doc.index_status = 'completed'
                    doc.delete_status = 'completed'
                    doc.save()
                    fixed_count += 1
                    
                    if fixed_count % 10 == 0:
                        self.stdout.write(f"   ✅ {fixed_count}/{total_to_fix} tuzatildi...")
                        
                except Exception as e:
                    failed_count += 1
                    self.stdout.write(
                        self.style.ERROR(f"   ❌ Xatolik: {doc.id}: {e}")
                    )
            
            # Natijalar
            self.stdout.write("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            self.stdout.write("📊 NATIJALAR:")
            self.stdout.write("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
            self.stdout.write(f"   ✅ Muvaffaqiyatli: {fixed_count}")
            if failed_count > 0:
                self.stdout.write(f"   ❌ Xatolik: {failed_count}")
            self.stdout.write(f"   📊 Jami: {total_to_fix}")
            self.stdout.write(f"   📈 Success Rate: {fixed_count * 100 // total_to_fix if total_to_fix > 0 else 0}%")
            
            # Yangi statistika
            self.stdout.write("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            self.stdout.write("📊 YANGI STATISTIKA:")
            self.stdout.write("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
            
            total_docs = Document.objects.count()
            completed_docs = Document.objects.filter(completed=True).count()
            
            self.stdout.write(f"   Jami document'lar: {total_docs}")
            self.stdout.write(f"   Completed: {completed_docs}")
            self.stdout.write(f"   Success Rate: {completed_docs * 100 // total_docs if total_docs > 0 else 0}%")
            
            self.stdout.write("\n" + self.style.SUCCESS("✅ Tuzatish yakunlandi!"))
        else:
            self.stdout.write("\n" + self.style.WARNING(
                "⚠️  DRY RUN tugadi. Haqiqiy o'zgarishlar uchun --dry-run flagini olib tashlang."
            ))

