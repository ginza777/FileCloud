# apps/files/management/commands/cleanup_temp_files.py
from django.core.management.base import BaseCommand
import os
import shutil
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Temporary fayllarni tozalaydi va disk to'lib qolishini oldini oladi"

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Faqat ko\'rsatish, o\'chirish qilmaslik'
        )
        parser.add_argument(
            '--max-age-hours',
            type=int,
            default=24,
            help='Necha soatdan eski fayllarni o\'chirish (default: 24)'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        max_age_hours = options['max_age_hours']
        
        temp_dirs = [
            '/tmp/downloads',
            '/tmp',
        ]
        
        total_freed = 0
        total_files = 0
        
        for temp_dir in temp_dirs:
            if not os.path.exists(temp_dir):
                continue
                
            self.stdout.write(f"Tozalash: {temp_dir}")
            
            # Fayllarni yoshi bo'yicha tekshirish
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    try:
                        # Fayl yoshini tekshirish
                        file_age_hours = (os.path.getctime(file_path) - os.path.getctime('/')) / 3600
                        
                        if file_age_hours > max_age_hours:
                            file_size = os.path.getsize(file_path)
                            total_freed += file_size
                            total_files += 1
                            
                            if dry_run:
                                self.stdout.write(f"  [DRY RUN] O'chiriladi: {file_path} ({file_size} bytes)")
                            else:
                                os.remove(file_path)
                                self.stdout.write(f"  ✅ O'chirildi: {file_path} ({file_size} bytes)")
                                
                    except Exception as e:
                        self.stdout.write(f"  ❌ Xatolik: {file_path} - {e}")
        
        # Disk hajmini ko'rsatish
        try:
            disk_usage = shutil.disk_usage('/tmp')
            free_gb = disk_usage.free / (1024**3)
            used_gb = (disk_usage.total - disk_usage.free) / (1024**3)
            total_gb = disk_usage.total / (1024**3)
            
            self.stdout.write(f"\n📊 Disk holati:")
            self.stdout.write(f"  Jami: {total_gb:.1f} GB")
            self.stdout.write(f"  Ishlatilgan: {used_gb:.1f} GB")
            self.stdout.write(f"  Bo'sh: {free_gb:.1f} GB")
            
            if free_gb < 1.0:  # 1 GB dan kam bo'sh joy
                self.stdout.write(self.style.WARNING("⚠️  DIQQAT: Disk to'lib qolmoqda!"))
            elif free_gb < 2.0:  # 2 GB dan kam bo'sh joy
                self.stdout.write(self.style.WARNING("⚠️  Ogoh: Disk to'lib qolish arafasida"))
            else:
                self.stdout.write(self.style.SUCCESS("✅ Disk holati yaxshi"))
                
        except Exception as e:
            self.stdout.write(f"❌ Disk hajmini o'qishda xatolik: {e}")
        
        # Natijalar
        if dry_run:
            self.stdout.write(f"\n📋 DRY RUN natijalari:")
            self.stdout.write(f"  O'chiriladigan fayllar: {total_files} ta")
            self.stdout.write(f"  Bo'shatiladigan joy: {total_freed / (1024**2):.1f} MB")
        else:
            self.stdout.write(f"\n✅ Tozalash yakunlandi:")
            self.stdout.write(f"  O'chirilgan fayllar: {total_files} ta")
            self.stdout.write(f"  Bo'shatilgan joy: {total_freed / (1024**2):.1f} MB")
