"""
Test Admin Actions for Blocked Products
======================================

Bu komanda admin panel actionlarini test qiladi.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.files.models import Document, Product


class Command(BaseCommand):
    help = 'Admin panel actionlarini test qilish'

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
        parser.add_argument(
            '--show-blocked',
            action='store_true',
            help='Blocked productlarni ko\'rsatish'
        )

    def handle(self, *args, **options):
        if options.get('create_test'):
            self.create_test_blocked_products()
        elif options.get('cleanup'):
            self.cleanup_test_products()
        elif options.get('show_blocked'):
            self.show_blocked_products()
        else:
            self.show_admin_actions_info()

    def create_test_blocked_products(self):
        """Test uchun blocked productlar yaratish"""
        self.stdout.write("🧪 Test blocked productlar yaratish...")
        
        try:
            # Test document 1 yaratish
            test_doc1 = Document.objects.create(
                parse_file_url="https://soff.uz/test-blocked-document-1.pdf",
                download_status='failed',
                parse_status='pending',
                index_status='pending',
                telegram_status='pending',
                delete_status='pending',
                completed=False,
                pipeline_running=False
            )
            
            # Test product 1 yaratish
            test_product1 = Product.objects.create(
                title="Test Blocked Product 1",
                slug="test-blocked-product-1",
                document=test_doc1,
                blocked=True,
                blocked_reason="Test: Access Denied error simulation",
                blocked_at=timezone.now()
            )
            
            # Test document 2 yaratish
            test_doc2 = Document.objects.create(
                parse_file_url="https://soff.uz/test-blocked-document-2.pdf",
                download_status='failed',
                parse_status='failed',
                index_status='pending',
                telegram_status='pending',
                delete_status='pending',
                completed=False,
                pipeline_running=False
            )
            
            # Test product 2 yaratish
            test_product2 = Product.objects.create(
                title="Test Blocked Product 2",
                slug="test-blocked-product-2",
                document=test_doc2,
                blocked=True,
                blocked_reason="Test: Tika Server Timeout Error simulation",
                blocked_at=timezone.now()
            )
            
            self.stdout.write(
                self.style.SUCCESS(
                    f"✅ Test blocked productlar yaratildi:\n"
                    f"   Document 1 ID: {test_doc1.id} | Product 1 ID: {test_product1.id}\n"
                    f"   Document 2 ID: {test_doc2.id} | Product 2 ID: {test_product2.id}\n"
                    f"   Title 1: {test_product1.title}\n"
                    f"   Title 2: {test_product2.title}\n"
                    f"   Blocked: {test_product1.blocked} | {test_product2.blocked}"
                )
            )
            
            self.stdout.write(
                self.style.WARNING(
                    f"\n💡 Endi admin panelda test qilish uchun:\n"
                    f"   1. Admin panelga kiring\n"
                    f"   2. Documents bo'limiga o'ting\n"
                    f"   3. Product Status filterida 'Blocked' ni tanlang\n"
                    f"   4. Test documentlarni tanlang\n"
                    f"   5. 'Tanlangan hujjatlarning blocked productlarini unblock qilish' action ni tanlang\n"
                    f"   6. Execute qiling"
                )
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"❌ Test productlar yaratishda xatolik: {e}")
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

    def show_admin_actions_info(self):
        """Admin actionlar haqida ma'lumot"""
        self.stdout.write("📋 Admin Panel Actions Ma'lumoti:")
        self.stdout.write("=" * 60)
        
        self.stdout.write("🔧 Document Admin Actions:")
        self.stdout.write("   1. set_pipeline_running_to_false - Pipeline running ni False qilish")
        self.stdout.write("   2. unblock_products_for_documents - Blocked productlarni unblock qilish")
        self.stdout.write("")
        
        self.stdout.write("🔧 Product Admin Actions:")
        self.stdout.write("   1. unblock_products - Blocked productlarni unblock qilish")
        self.stdout.write("")
        
        self.stdout.write("📊 Document Admin Features:")
        self.stdout.write("   - Product Status column (🔒 Blocked / ✅ Active)")
        self.stdout.write("   - Product blocked filter")
        self.stdout.write("   - Unblock action for selected documents")
        self.stdout.write("")
        
        self.stdout.write("📊 Product Admin Features:")
        self.stdout.write("   - Blocked column")
        self.stdout.write("   - Blocked filter")
        self.stdout.write("   - Unblock action for selected products")
        self.stdout.write("")
        
        self.stdout.write(
            self.style.SUCCESS("✅ Barcha admin actionlar tayyor!")
        )
