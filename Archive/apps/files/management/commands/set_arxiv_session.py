"""
Management command to set arxiv.uz PHPSESSID for authentication
==============================================================

Bu command arxiv.uz saytidan fayllarni yuklab olish uchun kerakli PHPSESSID ni 
ma'lumotlar bazasiga saqlaydi.

Ishlatish:
    python manage.py set_arxiv_session --phpsessid "your_phpsessid_value"
    
Yoki interaktiv rejimda:
    python manage.py set_arxiv_session
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.files.models import SiteToken
from apps.files.utils import validate_arxiv_session, login_to_arxiv


class Command(BaseCommand):
    help = 'Arxiv.uz uchun PHPSESSID ni o\'rnatadi va tekshiradi'

    def add_arguments(self, parser):
        parser.add_argument(
            '--phpsessid',
            type=str,
            help='Arxiv.uz PHPSESSID qiymati'
        )
        parser.add_argument(
            '--validate',
            action='store_true',
            help='Mavjud PHPSESSID ni tekshirish'
        )
        parser.add_argument(
            '--auto-login',
            action='store_true',
            help='Avtomatik login qilib PHPSESSID olish'
        )

    def handle(self, *args, **options):
        phpsessid = options.get('phpsessid')
        validate_only = options.get('validate', False)
        auto_login = options.get('auto_login', False)
        
        if validate_only:
            self.validate_existing_session()
            return
            
        if auto_login:
            self.stdout.write("🔐 Avtomatik login qilish...")
            phpsessid = login_to_arxiv()
            if not phpsessid:
                raise CommandError("❌ Avtomatik login muvaffaqiyatsiz!")
            
            self.stdout.write(
                self.style.SUCCESS(
                    f"✅ Avtomatik login muvaffaqiyatli! PHPSESSID: {phpsessid[:20]}..."
                )
            )
            
            # Sessiya ma'lumotlarini ko'rsatish
            self.show_session_info(phpsessid)
            return
            
        if not phpsessid:
            phpsessid = self.get_phpsessid_interactively()
            
        if not phpsessid:
            raise CommandError("PHPSESSID kiritilmadi!")
            
        # PHPSESSID ni tekshirish
        self.stdout.write("PHPSESSID ni tekshirish...")
        if not validate_arxiv_session(phpsessid):
            raise CommandError("❌ PHPSESSID noto'g'ri yoki eskirgan! To'g'ri PHPSESSID kiriting.")
            
        # Ma'lumotlar bazasiga saqlash
        try:
            with transaction.atomic():
                site_token, created = SiteToken.objects.update_or_create(
                    name='arxiv',
                    defaults={'auth_token': phpsessid}
                )
                
                action = "yaratildi" if created else "yangilandi"
                self.stdout.write(
                    self.style.SUCCESS(
                        f"✅ Arxiv.uz PHPSESSID muvaffaqiyatli {action}: {phpsessid[:20]}..."
                    )
                )
                
                # Sessiya ma'lumotlarini ko'rsatish
                self.show_session_info(phpsessid)
                
        except Exception as e:
            raise CommandError(f"❌ PHPSESSID saqlashda xatolik: {e}")

    def get_phpsessid_interactively(self):
        """Interaktiv rejimda PHPSESSID ni olish"""
        self.stdout.write("\n🔐 Arxiv.uz PHPSESSID ni kiriting:")
        self.stdout.write("   (Browser Developer Tools > Application > Cookies > arxiv.uz > PHPSESSID)")
        self.stdout.write("   Yoki curl command dan -b parametridagi PHPSESSID qiymatini oling\n")
        
        phpsessid = input("PHPSESSID: ").strip()
        
        if not phpsessid:
            self.stdout.write(self.style.WARNING("⚠️  PHPSESSID kiritilmadi!"))
            return None
            
        return phpsessid

    def validate_existing_session(self):
        """Mavjud sessiyani tekshirish"""
        try:
            site_token = SiteToken.objects.get(name='arxiv')
            phpsessid = site_token.auth_token
            
            if not phpsessid:
                self.stdout.write(self.style.WARNING("⚠️  PHPSESSID mavjud emas!"))
                return
                
            self.stdout.write(f"🔍 Mavjud PHPSESSID ni tekshirish: {phpsessid[:20]}...")
            
            if validate_arxiv_session(phpsessid):
                self.stdout.write(self.style.SUCCESS("✅ PHPSESSID haqiqiy va ishlaydi!"))
                self.show_session_info(phpsessid)
            else:
                self.stdout.write(self.style.ERROR("❌ PHPSESSID eskirgan yoki noto'g'ri!"))
                
        except SiteToken.DoesNotExist:
            self.stdout.write(self.style.WARNING("⚠️  Arxiv.uz token topilmadi! Avval PHPSESSID ni o'rnating."))

    def show_session_info(self, phpsessid):
        """Sessiya ma'lumotlarini ko'rsatish"""
        try:
            import requests
            
            session = requests.Session()
            session.cookies.set('PHPSESSID', phpsessid)
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36',
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Referer': 'https://arxiv.uz/uz'
            })
            
            response = session.get('https://arxiv.uz/user/info', timeout=10)
            
            if response.status_code == 200:
                user_data = response.json()
                self.stdout.write(f"\n👤 User ma'lumotlari:")
                self.stdout.write(f"   ID: {user_data.get('id')}")
                self.stdout.write(f"   Name: {user_data.get('name')}")
                self.stdout.write(f"   Role: {user_data.get('role')}")
                
                subscription = user_data.get('subscription')
                if subscription:
                    plan = subscription.get('plan', {})
                    expires_at = subscription.get('expiresAt')
                    self.stdout.write(f"   Subscription: {plan.get('name', 'N/A')}")
                    if expires_at:
                        self.stdout.write(f"   Expires: {expires_at}")
                        
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"⚠️  User ma'lumotlarini olishda xatolik: {e}"))
