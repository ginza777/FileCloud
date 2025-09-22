from django.core.management.base import BaseCommand
import os
import stat
from django.conf import settings


class Command(BaseCommand):
    help = 'Vaqtincha fayllar papkasini yaratadi va ruxsatlarni to\'g\'rilaydi'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Majburiy qayta yaratish',
        )

    def handle(self, *args, **options):
        self.stdout.write("Vaqtincha fayllar papkasini sozlaymiz...")
        
        temp_dir = getattr(settings, 'TEMP_DIR', None)
        if not temp_dir:
            self.stdout.write(
                self.style.ERROR("TEMP_DIR sozlamasi topilmadi!")
            )
            return
        
        try:
            # Papka yaratish
            if options['force'] and os.path.exists(temp_dir):
                self.stdout.write(f"Eski papka o'chirilmoqda: {temp_dir}")
                import shutil
                shutil.rmtree(temp_dir)
            
            os.makedirs(temp_dir, exist_ok=True, mode=0o755)
            self.stdout.write(f"Papka yaratildi: {temp_dir}")
            
            # Ruxsatlarni tekshirish
            if os.access(temp_dir, os.W_OK):
                self.stdout.write(
                    self.style.SUCCESS("✅ Papka yozish uchun tayyor")
                )
            else:
                self.stdout.write(
                    self.style.ERROR("❌ Papka yozish uchun tayyor emas")
                )
            
            # Test fayl yaratish
            test_file = os.path.join(temp_dir, "test_write.tmp")
            try:
                with open(test_file, "w") as f:
                    f.write("test")
                os.remove(test_file)
                self.stdout.write(
                    self.style.SUCCESS("✅ Test fayl yaratish muvaffaqiyatli")
                )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"❌ Test fayl yaratishda xato: {e}")
                )
            
            # Papka ruxsatlarini ko'rsatish
            stat_info = os.stat(temp_dir)
            permissions = stat.filemode(stat_info.st_mode)
            self.stdout.write(f"Papka ruxsatlari: {permissions}")
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Xato: {e}")
            )
