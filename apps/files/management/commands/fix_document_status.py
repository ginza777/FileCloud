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
        self.stdout.write("Yangi qoida: Agar telegram_id mavjud va parse_status='completed' bo'lsa -> IDEAL.\n"
                          "Aks holda -> Boshlang'ich holatga qaytariladi.\n")

        if dry_run:
            self.stdout.write(self.style.WARNING("⚠️  DRY RUN REJIMI - Ma'lumotlar bazasiga o'zgarishlar yozilmaydi\n"))

        # --- XATO HOLATLARNI QIDIRISH (SODDALASHTIRILGAN) ---

        # 1-XATO HOLATI: Ideal bo'lishi kerak, lekin `completed=False` bo'lganlar
        case_should_be_completed = Q(telegram_file_id__isnull=False) & Q(parse_status='completed') & Q(completed=False)

        # 2-XATO HOLATI: Ideal bo'lmasligi kerak, lekin `completed=True` bo'lganlar
        case_should_be_pending = (Q(telegram_file_id__isnull=True) | ~Q(parse_status='completed')) & Q(completed=True)

        # Ikkala turdagi xato hujjatlarni topish
        docs_to_fix = Document.objects.filter(
            case_should_be_completed | case_should_be_pending
        ).distinct()

        total_to_fix = docs_to_fix.count()

        if total_to_fix == 0:
            self.stdout.write(self.style.SUCCESS("✅ Barcha hujjatlar yangi qoidaga mos holatda!"))
            return

        self.stdout.write(f"📊 Jami {total_to_fix} ta yangi qoidaga mos kelmaydigan hujjat topildi.\n")

        self.stdout.write("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                          "📋 TUZATILADIGAN HUJJATLARGA NAMUNA:\n"
                          "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

        for doc in docs_to_fix[:10]:
            is_ideal_now = bool(doc.telegram_file_id) and doc.parse_status == 'completed'

            self.stdout.write(f"📄 Document ID: {doc.id}")
            self.stdout.write(
                f"   ├─ Joriy holat: TG ID: {'✅' if bool(doc.telegram_file_id) else '❌'}, Parse Status: '{doc.parse_status}', Completed: {'✅' if doc.completed else '❌'}")

            if is_ideal_now:
                # Bu holat case_should_be_completed ga tushadi
                self.stdout.write(f"   ✨ To'g'ri holat: ✅ completed=True bo'lishi kerak.")
            else:
                # Bu holat case_should_be_pending ga tushadi
                self.stdout.write(f"   ✨ To'g'ri holat: ⚠️  boshlang'ich (pending) holatga qaytarilishi kerak.")

        if not dry_run:
            self.stdout.write("\n\n" + self.style.WARNING("🔧 TUZATISH BOSHLANDI..."))

            fixed_count = 0
            with transaction.atomic():
                # Barcha topilgan hujjatlarni bitta so'rovda boshlang'ich holatga keltiramiz
                # Bu ancha tez ishlaydi

                # Ideal bo'lishi kerak bo'lganlarni to'g'rilaymiz
                docs_to_make_completed = docs_to_fix.filter(case_should_be_completed)

                # Boshqa hamma topilganlarni pending qilamiz
                docs_to_make_pending = docs_to_fix.filter(case_should_be_pending)

                # UPDATE so'rovlari ancha tezroq ishlaydi, lekin .save() signallarini ishga tushirmaydi.
                # Bizning holatda .save() dagi mantiq kerak, shuning uchun loopdan foydalanamiz.
                for doc in docs_to_fix.iterator():
                    doc.save()
                    fixed_count += 1

            self.stdout.write(self.style.SUCCESS(f"\n✅ {fixed_count} ta hujjat muvaffaqiyatli tuzatildi."))
        else:
            self.stdout.write("\n\n" + self.style.WARNING(
                "DRY RUN tugadi. Haqiqiy o'zgarishlarni amalga oshirish uchun --dry-run bayrog'isiz ishga tushiring."
            ))