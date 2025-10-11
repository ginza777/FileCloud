"""
Test Blocked Products Functionality
==================================

Bu komanda blocked product funksiyasini test qiladi.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.files.models import Document, Product


class Command(BaseCommand):
    help = 'Blocked product funksiyasini test qilish'

    def add_arguments(self, parser):
        parser.add_argument(
            '--create-test',
            action='store_true',
            help='Test uchun blocked product yaratish'
        )
        parser.add_argument(
            '--cleanup',
            action='store_true',
            help='Test blocked productlarni o\'chirish'
        )

    def handle(self, *args, **options):
        if options.get('create_test'):
            self.create_test_blocked_product()
        elif options.get('cleanup'):
            self.cleanup_test_products()
        else:
            self.show_blocked_products()

    def create_test_blocked_product(self):
        """Test uchun blocked product yaratish"""
        self.stdout.write("🧪 Test blocked product yaratish...")
        
        try:
            # Test document yaratish
            test_doc = Document.objects.create(
                parse_file_url="https://soff.uz/test-blocked-document.pdf",
                download_status='failed',
                parse_status='pending',
                index_status='pending',
                telegram_status='pending',
                delete_status='pending',
                completed=False,
                pipeline_running=False
            )
            
            # Test product yaratish
            test_product = Product.objects.create(
                title="Test Blocked Product",
                slug="test-blocked-product",
                document=test_doc,
                blocked=True,
                blocked_reason="Test: Tika Server Timeout Error simulation",
                blocked_at=timezone.now()
            )
            
            self.stdout.write(
                self.style.SUCCESS(
                    f"✅ Test blocked product yaratildi:\n"
                    f"   Document ID: {test_doc.id}\n"
                    f"   Product ID: {test_product.id}\n"
                    f"   Title: {test_product.title}\n"
                    f"   Blocked: {test_product.blocked}\n"
                    f"   Reason: {test_product.blocked_reason}"
                )
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"❌ Test product yaratishda xatolik: {e}")
            )

    def cleanup_test_products(self):
        """Test blocked productlarni o'chirish"""
        self.stdout.write("🧹 Test blocked productlarni o'chirish...")
        
        try:
            # Test productlarni topish va o'chirish
            test_products = Product.objects.filter(
                title__icontains="Test Blocked Product"
            )
            
            count = test_products.count()
            if count > 0:
                # Documentlarni ham o'chirish
                for product in test_products:
                    if product.document:
                        product.document.delete()
                    else:
                        product.delete()
                
                self.stdout.write(
                    self.style.SUCCESS(f"✅ {count} ta test product o'chirildi.")
                )
            else:
                self.stdout.write(
                    self.style.WARNING("⚠️ Test productlar topilmadi.")
                )
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"❌ Test productlarni o'chirishda xatolik: {e}")
            )

    def show_blocked_products(self):
        """Blocked productlarni ko'rsatish"""
        self.stdout.write("📋 Blocked productlar ro'yxati:")
        self.stdout.write("=" * 60)
        
        try:
            blocked_products = Product.objects.filter(blocked=True).select_related('document')
            
            if not blocked_products.exists():
                self.stdout.write(
                    self.style.SUCCESS("✅ Blocked productlar topilmadi.")
                )
                return
            
            for product in blocked_products:
                self.stdout.write(f"🔒 Product ID: {product.id}")
                self.stdout.write(f"   Title: {product.title}")
                self.stdout.write(f"   Slug: {product.slug}")
                self.stdout.write(f"   Document ID: {product.document.id if product.document else 'N/A'}")
                self.stdout.write(f"   Blocked At: {product.blocked_at}")
                self.stdout.write(f"   Reason: {product.blocked_reason}")
                self.stdout.write("-" * 40)
            
            self.stdout.write(
                self.style.WARNING(f"📊 Jami blocked productlar: {blocked_products.count()}")
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"❌ Blocked productlarni ko'rsatishda xatolik: {e}")
            )
