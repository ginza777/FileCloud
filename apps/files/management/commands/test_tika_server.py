"""
Test Tika Server Command
=======================

Bu komanda Tika serverni test qiladi.
Oddiy txt fayl yaratadi, Tika orqali o'qiydi va natijani tekshiradi.

Ishlatish:
    python manage.py test_tika_server
    python manage.py test_tika_server --create-pdf
    python manage.py test_tika_server --cleanup
"""

import os
import tempfile
from django.core.management.base import BaseCommand
from django.conf import settings
from tika import parser as tika_parser
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Tika serverni test qilish'

    def add_arguments(self, parser):
        parser.add_argument(
            '--create-pdf',
            action='store_true',
            help='PDF fayl yaratish va test qilish'
        )
        parser.add_argument(
            '--cleanup',
            action='store_true',
            help='Test fayllarni o\'chirish'
        )
        parser.add_argument(
            '--tika-url',
            type=str,
            default=None,
            help='Tika server URL (default: settings.TIKA_URL)'
        )

    def handle(self, *args, **options):
        create_pdf = options.get('create_pdf', False)
        cleanup = options.get('cleanup', False)
        tika_url = options.get('tika_url')
        
        if cleanup:
            self.cleanup_test_files()
            return
        
        if create_pdf:
            self.test_tika_with_pdf(tika_url)
        else:
            self.test_tika_with_txt(tika_url)

    def test_tika_with_txt(self, tika_url=None):
        """TXT fayl bilan Tika serverni test qilish"""
        self.stdout.write("🧪 Tika Server Test (TXT fayl)")
        self.stdout.write("=" * 50)
        
        # Tika URL ni o'rnatish
        if tika_url:
            tika_parser.TikaServerEndpoint = tika_url
            self.stdout.write(f"🔗 Tika URL: {tika_url}")
        else:
            tika_url = getattr(settings, 'TIKA_URL', 'http://tika:9998')
            tika_parser.TikaServerEndpoint = tika_url
            self.stdout.write(f"🔗 Tika URL: {tika_url} (settings dan)")
        
        # Test fayl yaratish
        test_content = """
        Bu Tika server test fayli.
        
        Test ma'lumotlari:
        - Fayl turi: TXT
        - Kodirovka: UTF-8
        - Tika server: {tika_url}
        
        Bu matn Tika orqali o'qilishi va parse qilinishi kerak.
        Agar siz bu matnni ko'ryapsiz, Tika server ishlayapti!
        
        Test tugash: ✅
        """.format(tika_url=tika_url)
        
        # Vaqtinchalik fayl yaratish
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as temp_file:
            temp_file.write(test_content)
            temp_file_path = temp_file.name
        
        self.stdout.write(f"📄 Test fayl yaratildi: {temp_file_path}")
        
        try:
            # Tika orqali faylni o'qish
            self.stdout.write("🔍 Tika orqali faylni o'qish...")
            
            parsed = tika_parser.from_file(temp_file_path)
            
            if parsed:
                content = parsed.get("content", "").strip()
                metadata = parsed.get("metadata", {})
                
                self.stdout.write("✅ Tika server muvaffaqiyatli ishladi!")
                self.stdout.write("")
                
                # Content natijalarini ko'rsatish
                self.stdout.write("📋 Parse natijalari:")
                self.stdout.write("-" * 30)
                self.stdout.write(f"Content uzunligi: {len(content)} belgi")
                self.stdout.write(f"Content (birinchi 200 belgi):")
                self.stdout.write(f"'{content[:200]}...'")
                self.stdout.write("")
                
                # Metadata natijalarini ko'rsatish
                if metadata:
                    self.stdout.write("📊 Metadata:")
                    self.stdout.write("-" * 30)
                    for key, value in metadata.items():
                        if key in ['Content-Type', 'Content-Encoding', 'X-Parsed-By']:
                            self.stdout.write(f"  {key}: {value}")
                    self.stdout.write("")
                
                # Test muvaffaqiyatini tekshirish
                if "Tika server ishlayapti" in content:
                    self.stdout.write(
                        self.style.SUCCESS("🎉 Test muvaffaqiyatli! Tika server to'g'ri ishlayapti.")
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING("⚠️ Test natijasi kutilganidek emas.")
                    )
                
            else:
                self.stdout.write(
                    self.style.ERROR("❌ Tika server javob bermadi yoki xatolik yuz berdi.")
                )
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"❌ Tika server testida xatolik: {e}")
            )
            logger.error(f"Tika server test xatolik: {e}", exc_info=True)
            
        finally:
            # Vaqtinchalik faylni o'chirish
            try:
                os.unlink(temp_file_path)
                self.stdout.write(f"🗑️ Test fayl o'chirildi: {temp_file_path}")
            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(f"⚠️ Test faylni o'chirishda xatolik: {e}")
                )

    def test_tika_with_pdf(self, tika_url=None):
        """PDF fayl bilan Tika serverni test qilish"""
        self.stdout.write("🧪 Tika Server Test (PDF fayl)")
        self.stdout.write("=" * 50)
        
        # Tika URL ni o'rnatish
        if tika_url:
            tika_parser.TikaServerEndpoint = tika_url
            self.stdout.write(f"🔗 Tika URL: {tika_url}")
        else:
            tika_url = getattr(settings, 'TIKA_URL', 'http://tika:9998')
            tika_parser.TikaServerEndpoint = tika_url
            self.stdout.write(f"🔗 Tika URL: {tika_url} (settings dan)")
        
        # Oddiy PDF fayl yaratish (ReportLab ishlatib)
        try:
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import letter
        except ImportError:
            self.stdout.write(
                self.style.ERROR("❌ ReportLab topilmadi! 'pip install reportlab' komandasini ishga tushiring.")
            )
            return
        
        # Vaqtinchalik PDF fayl yaratish
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
            temp_file_path = temp_file.name
        
        self.stdout.write(f"📄 PDF fayl yaratish: {temp_file_path}")
        
        try:
            # PDF fayl yaratish
            c = canvas.Canvas(temp_file_path, pagesize=letter)
            c.drawString(100, 750, "Tika Server Test PDF")
            c.drawString(100, 730, f"Tika URL: {tika_url}")
            c.drawString(100, 710, "Bu PDF fayl Tika orqali test qilinmoqda.")
            c.drawString(100, 690, "Agar siz bu matnni ko'ryapsiz, Tika server ishlayapti!")
            c.drawString(100, 670, "Test tugash: ✅")
            c.save()
            
            self.stdout.write("✅ PDF fayl yaratildi")
            
            # Tika orqali PDF faylni o'qish
            self.stdout.write("🔍 Tika orqali PDF faylni o'qish...")
            
            parsed = tika_parser.from_file(temp_file_path)
            
            if parsed:
                content = parsed.get("content", "").strip()
                metadata = parsed.get("metadata", {})
                
                self.stdout.write("✅ Tika server muvaffaqiyatli ishladi!")
                self.stdout.write("")
                
                # Content natijalarini ko'rsatish
                self.stdout.write("📋 Parse natijalari:")
                self.stdout.write("-" * 30)
                self.stdout.write(f"Content uzunligi: {len(content)} belgi")
                self.stdout.write(f"Content (birinchi 200 belgi):")
                self.stdout.write(f"'{content[:200]}...'")
                self.stdout.write("")
                
                # Metadata natijalarini ko'rsatish
                if metadata:
                    self.stdout.write("📊 Metadata:")
                    self.stdout.write("-" * 30)
                    for key, value in metadata.items():
                        if key in ['Content-Type', 'Content-Encoding', 'X-Parsed-By', 'xmp:CreatorTool']:
                            self.stdout.write(f"  {key}: {value}")
                    self.stdout.write("")
                
                # Test muvaffaqiyatini tekshirish
                if "Tika server ishlayapti" in content:
                    self.stdout.write(
                        self.style.SUCCESS("🎉 Test muvaffaqiyatli! Tika server PDF fayllarni to'g'ri o'qiyapti.")
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING("⚠️ Test natijasi kutilganidek emas.")
                    )
                
            else:
                self.stdout.write(
                    self.style.ERROR("❌ Tika server javob bermadi yoki xatolik yuz berdi.")
                )
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"❌ Tika server testida xatolik: {e}")
            )
            logger.error(f"Tika server test xatolik: {e}", exc_info=True)
            
        finally:
            # Vaqtinchalik faylni o'chirish
            try:
                os.unlink(temp_file_path)
                self.stdout.write(f"🗑️ Test fayl o'chirildi: {temp_file_path}")
            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(f"⚠️ Test faylni o'chirishda xatolik: {e}")
                )

    def cleanup_test_files(self):
        """Test fayllarni tozalash"""
        self.stdout.write("🧹 Test fayllarni tozalash...")
        
        # Vaqtinchalik fayllarni topish va o'chirish
        temp_dir = tempfile.gettempdir()
        test_files = []
        
        for filename in os.listdir(temp_dir):
            if filename.startswith('tmp') and (filename.endswith('.txt') or filename.endswith('.pdf')):
                file_path = os.path.join(temp_dir, filename)
                try:
                    # Fayl ichida test matn borligini tekshirish
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        if 'Tika server test' in content or 'Tika Server Test' in content:
                            test_files.append(file_path)
                except:
                    pass
        
        if test_files:
            for file_path in test_files:
                try:
                    os.unlink(file_path)
                    self.stdout.write(f"🗑️ O'chirildi: {file_path}")
                except Exception as e:
                    self.stdout.write(
                        self.style.WARNING(f"⚠️ O'chirishda xatolik: {file_path} - {e}")
                    )
            
            self.stdout.write(
                self.style.SUCCESS(f"✅ {len(test_files)} ta test fayl o'chirildi.")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS("✅ Test fayllar topilmadi.")
            )
