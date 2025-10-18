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
                          "Aks holda -> BUTUNLAY PENDING holatga qaytariladi (barcha statuslar pending).\n"
                          "Blocked fayllar ham tuzatiladi va blokdan ochiladi.\n")

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

        # 2-XATO HOLATI: Ideal bo'lmasligi kerak (telegram_file_id yoki parsed_content yo'q), lekin completed=True yoki boshqa statuslar completed
        case_should_be_pending = (
            (Q(telegram_file_id__isnull=True) | 
             Q(product__parsed_content__isnull=True) | 
             Q(product__parsed_content='')) & 
            (
                Q(completed=True) |
                Q(download_status='completed') |
                Q(parse_status='completed') |
                Q(index_status='completed') |
                Q(telegram_status='completed') |
                Q(delete_status='completed')
            )
        )

        # Ikkala turdagi xato hujjatlarni topish (blocked productlarga ham teginish)
        docs_to_fix = Document.objects.filter(
            case_should_be_completed | case_should_be_pending
        ).select_related('product').distinct()

        total_to_fix = docs_to_fix.count()
        
        # Blocked productlar sonini hisoblash
        blocked_count = Document.objects.filter(
            case_should_be_completed | case_should_be_pending
        ).filter(
            product__blocked=True
        ).count()

        if total_to_fix == 0:
            self.stdout.write(self.style.SUCCESS("✅ Barcha hujjatlar yangi qoidaga mos holatda!"))
            return

        self.stdout.write(f"📊 Jami {total_to_fix} ta yangi qoidaga mos kelmaydigan hujjat topildi.")
        if blocked_count > 0:
            self.stdout.write(self.style.WARNING(f"⚠️  {blocked_count} ta blocked product tuzatiladi va blokdan ochiladi."))
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
                f"Delete: {doc.delete_status}, Completed: {'✅' if doc.completed else '❌'}, "
                f"Blocked: {'✅' if doc.product and doc.product.blocked else '❌'}")

            if is_ideal_now:
                # Bu holat case_should_be_completed ga tushadi
                self.stdout.write(f"   ✨ To'g'ri holat: ✅ BARCHA STATUSLAR COMPLETED bo'lishi kerak.")
            else:
                # Bu holat case_should_be_pending ga tushadi
                self.stdout.write(f"   ✨ To'g'ri holat: ⚠️  BUTUNLAY PENDING holatga qaytarilishi kerak (barcha statuslar pending).")

        if not dry_run:
            self.stdout.write("\n\n" + self.style.WARNING("🔧 TUZATISH BOSHLANDI..."))

            fixed_count = 0
            completed_count = 0
            pending_count = 0
            unblocked_count = 0
            
            with transaction.atomic():
                for doc in docs_to_fix.iterator():
                    has_telegram_id = bool(doc.telegram_file_id)
                    has_parsed_content = bool(doc.product and doc.product.parsed_content and doc.product.parsed_content.strip())
                    is_ideal = has_telegram_id and has_parsed_content
                    was_blocked = doc.product and doc.product.blocked
                    
                    if is_ideal:
                        # Telegram file ID mavjud va parsed_content null emas -> COMPLETED
                        doc.download_status = 'completed'
                        doc.parse_status = 'completed'
                        doc.index_status = 'completed'
                        doc.telegram_status = 'completed'
                        doc.delete_status = 'completed'
                        doc.completed = True
                        completed_count += 1
                        
                        # Har bir tuzatilgan document uchun info
                        self.stdout.write(f"✅ Document {str(doc.id)[:8]}... -> COMPLETED (TG: ✅, Content: ✅)")
                    else:
                        # Telegram file ID yoki parsed_content yo'q -> BUTUNLAY PENDING
                        doc.download_status = 'pending'
                        doc.parse_status = 'pending'
                        doc.index_status = 'pending'
                        doc.telegram_status = 'pending'
                        doc.delete_status = 'pending'
                        doc.completed = False
                        pending_count += 1
                        
                        # Har bir tuzatilgan document uchun info
                        tg_status = "✅" if has_telegram_id else "❌"
                        content_status = "✅" if has_parsed_content else "❌"
                        self.stdout.write(f"⚠️  Document {str(doc.id)[:8]}... -> BUTUNLAY PENDING (TG: {tg_status}, Content: {content_status})")
                    
                    # Blocked holatdan ochish
                    if was_blocked and doc.product:
                        doc.product.blocked = False
                        doc.product.save()
                        unblocked_count += 1
                    
                    doc.save()
                    fixed_count += 1
                    
                    # Har 1000 ta document uchun progress ko'rsatish
                    if fixed_count % 1000 == 0:
                        self.stdout.write(f"📊 Progress: {fixed_count:,} / {total_to_fix:,} tuzatildi...")
            
            # Yakuniy natija
            self.stdout.write("\n" + "="*80)
            self.stdout.write(self.style.SUCCESS("🎉 TUZATISH YAKUNLANDI!"))
            self.stdout.write("="*80)
            self.stdout.write(f"📊 Jami tuzatilgan: {fixed_count:,} ta hujjat")
            self.stdout.write(f"✅ COMPLETED holatga: {completed_count:,} ta")
            self.stdout.write(f"⚠️  PENDING holatga: {pending_count:,} ta")
            self.stdout.write(f"🔓 Blokdan ochilgan: {unblocked_count:,} ta")
            self.stdout.write(f"📈 Muvaffaqiyat foizi: {(completed_count/fixed_count*100):.1f}%" if fixed_count > 0 else "📈 Muvaffaqiyat foizi: 0%")
            self.stdout.write("="*80)
        else:
            self.stdout.write("\n\n" + self.style.WARNING(
                "DRY RUN tugadi. Haqiqiy o'zgarishlarni amalga oshirish uchun --dry-run bayrog'isiz ishga tushiring."
            ))