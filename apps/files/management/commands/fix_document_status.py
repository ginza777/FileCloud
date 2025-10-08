# fix_document_status.py fayli

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta
from apps.files.models import Document
from django.db import transaction

class Command(BaseCommand):
    help = "Hujjatlar holatini (jumladan, qotib qolgan va xatoliklarni) yakuniy mantiq asosida to'liq tuzatadi"

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='O\'zgarishlarni saqlamasdan, faqat nima qilinishini ko\'rsatish'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        self.stdout.write(self.style.SUCCESS("╔════════════════════════════════════════════════════════════════╗"))
        self.stdout.write(self.style.SUCCESS("║     🔧 HUJJAT STATUSINI KENGAYTIRILGAN TEKSHIRISH VA TUZATISH    ║"))
        self.stdout.write(self.style.SUCCESS("╚════════════════════════════════════════════════════════════════╝\n"))

        if dry_run:
            self.stdout.write(self.style.WARNING("⚠️  DRY RUN REJIMI - Ma'lumotlar bazasiga o'zgarishlar yozilmaydi\n"))

        # --- XATO HOLATLARNI QIDIRISH (KENGAYTIRILGAN) ---

        # 1. Ideal bo'lishi kerak, lekin `completed=False` bo'lganlar
        case_should_be_completed = Q(telegram_file_id__isnull=False) & Q(product__parsed_content__isnull=False) & Q(completed=False)

        # 2. Ideal bo'lmasligi kerak, lekin `completed=True` bo'lganlar
        case_should_be_pending = (Q(telegram_file_id__isnull=True) | Q(product__parsed_content__isnull=True)) & Q(completed=True)

        # 3. 'failed' statusiga ega bo'lganlar (ular reset qilinishi kerak)
        failed_statuses = (
            Q(download_status='failed') | Q(parse_status='failed') |
            Q(index_status='failed') | Q(telegram_status='failed') |
            Q(delete_status='failed')
        )

        # 4. Pipeline'da 2 daqiqadan ko'p qotib qolganlar
        two_minutes_ago = timezone.now() - timedelta(minutes=2)
        stuck_pipeline = Q(pipeline_running=True) & Q(updated_at__lt=two_minutes_ago)

        # Barcha turdagi xato hujjatlarni topish
        docs_to_fix = Document.objects.filter(
            case_should_be_completed | case_should_be_pending | failed_statuses | stuck_pipeline
        ).distinct().select_related('product') # .distinct() bir xil hujjat ikki marta chiqishini oldini oladi

        total_to_fix = docs_to_fix.count()

        if total_to_fix == 0:
            self.stdout.write(self.style.SUCCESS("✅ Barcha hujjatlar to'g'ri holatda. Tuzatishga hojat yo'q!"))
            return

        self.stdout.write(f"📊 Jami {total_to_fix} ta noto'g'ri holatdagi (yoki qotib qolgan/xatolikli) hujjat topildi.\n")

        self.stdout.write("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                          "📋 TUZATILADIGAN HUJJATLARGA NAMUNA:\n"
                          "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

        for doc in docs_to_fix[:10]:
            # ... (Foydalanuvchiga tushunarli ma'lumot chiqarish qismi) ...
            status_line = f"📄 Document ID: {doc.id}"
            if doc.pipeline_running and (timezone.now() - doc.updated_at > timedelta(minutes=2)):
                 status_line += self.style.ERROR(" (QOTIB QOLGAN)")
            elif 'failed' in [doc.download_status, doc.parse_status, doc.index_status, doc.telegram_status, doc.delete_status]:
                 status_line += self.style.ERROR(" (XATOLIK MAVJUD)")
            self.stdout.write(status_line)

        if not dry_run:
            self.stdout.write("\n\n" + self.style.WARNING("🔧 TUZATISH BOSHLANDI... (Har bir hujjat uchun .save() chaqiriladi)"))

            fixed_count = 0
            with transaction.atomic():
                for doc in docs_to_fix.iterator():
                    doc.save() # .save() metodidagi kengaytirilgan mantiq barcha ishni bajaradi
                    fixed_count += 1

            self.stdout.write(self.style.SUCCESS(f"\n✅ {fixed_count} ta hujjat muvaffaqiyatli tuzatildi."))
        else:
            self.stdout.write("\n\n" + self.style.WARNING(
                "DRY RUN tugadi. Haqiqiy o'zgarishlarni amalga oshirish uchun --dry-run bayrog'isiz ishga tushiring."
            ))