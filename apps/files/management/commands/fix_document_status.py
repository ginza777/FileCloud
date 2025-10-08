"""
Fix Document Completion Status
================================

Bu komanda Document'larning completed statusini to'g'rilaydi.
U shunchaki ideal holatda bo'lishi kerak bo'lgan, lekin completed=False
bo'lgan hujjatlarni topadi va ularni qayta saqlaydi (.save()).
Document.save() metodi esa barcha kerakli statuslarni avtomatik to'g'rilaydi.

Ishlatish:
    python manage.py fix_document_status
    python manage.py fix_document_status --dry-run
"""

from django.core.management.base import BaseCommand
from apps.files.models import Document, Product
from django.db import transaction

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
            "║     🔧 DOCUMENT STATUS TUZATISH (YANGI MANTIQ)                 ║"
        ))
        self.stdout.write(self.style.SUCCESS(
            "╚════════════════════════════════════════════════════════════════╝"
        ))
        self.stdout.write("")

        if dry_run:
            self.stdout.write(self.style.WARNING("⚠️  DRY RUN MODE - O'zgarishlar saqlanmaydi\n"))

        # Tuzatish kerak bo'lgan document'larni topish
        # Bular ideal holatda bo'lishi kerak, lekin completed=False bo'lganlar
        docs_to_fix = Document.objects.filter(
            telegram_file_id__isnull=False,
            product__parsed_content__isnull=False,
            completed=False
        ).select_related('product') # product'ni oldindan yuklab olamiz

        total_to_fix = docs_to_fix.count()
        self.stdout.write(f"📊 Tuzatish kerak: {total_to_fix} ta document\n")

        if total_to_fix == 0:
            self.stdout.write(self.style.SUCCESS("✅ Barcha document'lar to'g'ri holatda!"))
            return

        self.stdout.write("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        self.stdout.write("📋 TUZATILADIGAN DOCUMENT'LAR (NAMUNA):")
        self.stdout.write("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

        for doc in docs_to_fix[:10]:
            self.stdout.write(f"📄 Document ID: {doc.id}")
            self.stdout.write(f"   ├─ Telegram File ID: ✅ Mavjud")
            self.stdout.write(f"   ├─ Parsed Content: ✅ Mavjud ({len(doc.product.parsed_content or '')} belgi)")
            self.stdout.write(f"   └─ Joriy Status: ⚠️  completed=False")
            self.stdout.write(f"   ✨ Yangi Status: ✅ completed=True va barcha statuslar 'completed' bo'ladi.")

        if total_to_fix > 10:
            self.stdout.write(f"\n... va yana {total_to_fix - 10} ta document")

        if not dry_run:
            self.stdout.write("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            self.stdout.write("🔧 TUZATISH BOSHLANDI... (Har bir hujjat .save() qilinadi)")
            self.stdout.write("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

            fixed_count = 0
            failed_count = 0

            # O'zgarishlarni bitta tranzaksiyada bajarish tezroq va xavfsizroq
            with transaction.atomic():
                for doc in docs_to_fix:
                    try:
                        # Shunchaki .save() ni chaqirish kifoya.
                        # Barcha mantiq modelning o'zida.
                        doc.save()
                        fixed_count += 1

                        if fixed_count % 10 == 0:
                            self.stdout.write(f"   ✅ {fixed_count}/{total_to_fix} tuzatildi...")

                    except Exception as e:
                        failed_count += 1
                        self.stdout.write(
                            self.style.ERROR(f"   ❌ Xatolik: {doc.id}: {e}")
                        )

            self.stdout.write("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            self.stdout.write("📊 NATIJALAR:")
            self.stdout.write("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
            self.stdout.write(f"   ✅ Muvaffaqiyatli: {fixed_count}")
            if failed_count > 0:
                self.stdout.write(self.style.ERROR(f"   ❌ Xatolik: {failed_count}"))

            self.stdout.write("\n" + self.style.SUCCESS("✅ Tuzatish yakunlandi!"))
        else:
            self.stdout.write("\n" + self.style.WARNING(
                "⚠️  DRY RUN tugadi. Haqiqiy o'zgarishlar uchun --dry-run flagini olib tashlang."
            ))