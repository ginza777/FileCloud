# fix_document_status.py fayli

from django.core.management.base import BaseCommand
from django.db.models import Q
from apps.files.models import Document
from django.db import transaction


class Command(BaseCommand):
    help = "Hujjatlar holatini yangi, soddalashtirilgan mantiq asosida to'liq tuzatadi"

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='O\'zgarishlarni saqlamasdan, faqat nima qilinishini ko\'rsatish'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        self.stdout.write(self.style.SUCCESS("╔════════════════════════════════════════════════════════════════╗"))
        self.stdout.write(self.style.SUCCESS("║       🔧 HUJJAT STATUSINI SODDALASHTIRILGAN TEKSHIRISH         ║"))
        self.stdout.write(self.style.SUCCESS("╚════════════════════════════════════════════════════════════════╝\n"))
        self.stdout.write("Yangi qoida: Agar telegram_file_id mavjud va parsed_content null emas bo'lsa -> BARCHA STATUSLAR COMPLETED.\n"
                          "Aks holda -> Boshlang'ich holatga qaytariladi.\n")

        if dry_run:
            self.stdout.write(self.style.WARNING("⚠️  DRY RUN REJIMI - Ma'lumotlar bazasiga o'zgarishlar yozilmaydi\n"))

        # --- XATO HOLATLARNI QIDIRISH (YANGI MANTIQ) ---

        # 1-XATO HOLATI: Ideal bo'lishi kerak (telegram_file_id mavjud va parsed_content null emas), lekin barcha statuslar completed emas
        case_should_be_completed = (
            Q(telegram_file_id__isnull=False) & 
            Q(product__parsed_content__isnull=False) & 
            Q(product__parsed_content__gt='') &
            (
                Q(download_status__in=['pending', 'failed']) |
                Q(parse_status__in=['pending', 'failed']) |
                Q(index_status__in=['pending', 'failed']) |
                Q(telegram_status__in=['pending', 'failed']) |
                Q(delete_status__in=['pending', 'failed']) |
                Q(completed=False)
            )
        )

        # 2-XATO HOLATI: Ideal bo'lmasligi kerak (telegram_file_id yoki parsed_content yo'q), lekin `completed=True` bo'lganlar
        case_should_be_pending = (
            (Q(telegram_file_id__isnull=True) | 
             Q(product__parsed_content__isnull=True) | 
             Q(product__parsed_content='')) & 
            Q(completed=True)
        )

        # Ikkala turdagi xato hujjatlarni topish (blocked productlarga teginmaslik)
        docs_to_fix = Document.objects.filter(
            case_should_be_completed | case_should_be_pending
        ).exclude(
            product__blocked=True
        ).select_related('product').distinct()

        total_to_fix = docs_to_fix.count()
        
        # Blocked productlar sonini hisoblash
        blocked_count = Document.objects.filter(
            case_should_be_completed | case_should_be_pending
        ).filter(
            product__blocked=True
        ).count()

        if total_to_fix == 0:
            if blocked_count > 0:
                self.stdout.write(self.style.SUCCESS("✅ Barcha hujjatlar yangi qoidaga mos holatda!"))
                self.stdout.write(self.style.WARNING(f"⚠️  {blocked_count} ta blocked product o'tkazib yuborildi."))
            else:
                self.stdout.write(self.style.SUCCESS("✅ Barcha hujjatlar yangi qoidaga mos holatda!"))
            return

        self.stdout.write(f"📊 Jami {total_to_fix} ta yangi qoidaga mos kelmaydigan hujjat topildi.")
        if blocked_count > 0:
            self.stdout.write(self.style.WARNING(f"⚠️  {blocked_count} ta blocked product o'tkazib yuborildi."))
        self.stdout.write("")

        self.stdout.write("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                          "📋 TUZATILADIGAN HUJJATLARGA NAMUNA:\n"
                          "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

        for doc in docs_to_fix[:10]:
            has_telegram_id = bool(doc.telegram_file_id)
            has_parsed_content = bool(doc.product and doc.product.parsed_content and doc.product.parsed_content.strip())
            is_ideal_now = has_telegram_id and has_parsed_content

            self.stdout.write(f"📄 Document ID: {doc.id}")
            self.stdout.write(
                f"   ├─ Joriy holat: TG ID: {'✅' if has_telegram_id else '❌'}, "
                f"Parsed Content: {'✅' if has_parsed_content else '❌'}, "
                f"Download: {doc.download_status}, Parse: {doc.parse_status}, "
                f"Index: {doc.index_status}, Telegram: {doc.telegram_status}, "
                f"Delete: {doc.delete_status}, Completed: {'✅' if doc.completed else '❌'}")

            if is_ideal_now:
                # Bu holat case_should_be_completed ga tushadi
                self.stdout.write(f"   ✨ To'g'ri holat: ✅ BARCHA STATUSLAR COMPLETED bo'lishi kerak.")
            else:
                # Bu holat case_should_be_pending ga tushadi
                self.stdout.write(f"   ✨ To'g'ri holat: ⚠️  boshlang'ich (pending) holatga qaytarilishi kerak.")

        if not dry_run:
            self.stdout.write("\n\n" + self.style.WARNING("🔧 TUZATISH BOSHLANDI..."))

            fixed_count = 0
            completed_count = 0
            pending_count = 0
            
            with transaction.atomic():
                for doc in docs_to_fix.iterator():
                    doc.download_status = 'pending'
                    doc.parse_status = 'pending'
                    doc.index_status = 'pending'
                    doc.telegram_status = 'pending'
                    doc.delete_status = 'pending'
                    doc.completed = False
                    doc.save()
                    fixed_count += 1
            self.stdout.write(self.style.SUCCESS(f"\n✅ {fixed_count} ta hujjat pending holatga o'tkazildi."))
        else:
            self.stdout.write("\n\n" + self.style.WARNING(
                "DRY RUN tugadi. Haqiqiy o'zgarishlarni amalga oshirish uchun --dry-run bayrog'isiz ishga tushiring."
            ))