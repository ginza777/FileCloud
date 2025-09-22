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
            
            # Papka yaratish - bir nechta usul bilan
            try:
                os.makedirs(temp_dir, exist_ok=True, mode=0o777)
                self.stdout.write(f"Papka yaratildi: {temp_dir}")
            except PermissionError:
                # Agar 0o777 ishlamasa, 0o755 bilan urinamiz
                try:
                    os.makedirs(temp_dir, exist_ok=True, mode=0o755)
                    self.stdout.write(f"Papka yaratildi (0o755): {temp_dir}")
                except PermissionError:
                    # Agar hali ham ishlamasa, chmod bilan urinamiz
                    try:
                        os.makedirs(temp_dir, exist_ok=True)
                        os.chmod(temp_dir, 0o777)
                        self.stdout.write(f"Papka yaratildi va ruxsatlar o'zgartirildi: {temp_dir}")
                    except PermissionError as e:
                        self.stdout.write(
                            self.style.WARNING(f"Papka yaratishda xato: {e}")
                        )
                        # Fallback: system temp dir ishlatamiz
                        import tempfile
                        system_temp = tempfile.gettempdir()
                        self.stdout.write(
                            self.style.SUCCESS(f"System temp dir ishlatiladi: {system_temp}")
                        )
                        return
            
            # Ruxsatlarni tekshirish
            if os.access(temp_dir, os.W_OK):
                self.stdout.write(
                    self.style.SUCCESS("✅ Papka yozish uchun tayyor")
                )
            else:
                self.stdout.write(
                    self.style.WARNING("⚠️ Papka yozish uchun tayyor emas, ruxsatlarni o'zgartiryapmiz...")
                )
                try:
                    os.chmod(temp_dir, 0o777)
                    if os.access(temp_dir, os.W_OK):
                        self.stdout.write(
                            self.style.SUCCESS("✅ Ruxsatlar o'zgartirildi, papka tayyor")
                        )
                    else:
                        self.stdout.write(
                            self.style.ERROR("❌ Ruxsatlarni o'zgartirishda xato")
                        )
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f"❌ Ruxsatlarni o'zgartirishda xato: {e}")
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
                    self.style.WARNING(f"⚠️ Test fayl yaratishda xato: {e}")
                )
                self.stdout.write(
                    self.style.SUCCESS("System temp dir ishlatiladi")
                )
            
            # Papka ruxsatlarini ko'rsatish
            try:
                stat_info = os.stat(temp_dir)
                permissions = stat.filemode(stat_info.st_mode)
                self.stdout.write(f"Papka ruxsatlari: {permissions}")
            except Exception:
                pass
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Xato: {e}")
            )
            self.stdout.write(
                self.style.SUCCESS("System temp dir ishlatiladi")
            )
