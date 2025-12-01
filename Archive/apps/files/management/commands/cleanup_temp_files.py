"""
Temporary Files Cleanup Command
===============================

Bu komanda temporary fayllarni tozalaydi va disk to'lib qolishini oldini oladi.
Eski fayllarni o'chiradi va disk joyini bo'shatadi.

Ishlatish:
    python manage.py cleanup_temp_files
    python manage.py cleanup_temp_files --dry-run
    python manage.py cleanup_temp_files --max-age-hours 48
"""

from django.core.management.base import BaseCommand
import os
import shutil
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Temporary fayllarni tozalash komandasi.
    
    Bu komanda:
    1. Temporary papkalardagi eski fayllarni topadi
    2. Belgilangan vaqtdan eski fayllarni o'chiradi
    3. Disk joyini bo'shatadi
    4. Dry-run rejimida faqat ko'rsatadi
    """
    
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
        """Asosiy tozalash jarayoni."""
        dry_run = options['dry_run']
        max_age_hours = options['max_age_hours']
        
        self.stdout.write(
            self.style.SUCCESS("=== Temporary Fayllar Tozalash Jarayoni ===")
        )
        
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN rejimi - fayllar o'chirilmaydi"))
        
        self.stdout.write(f"Eski fayllar: {max_age_hours} soatdan eski")
        
        # Temporary papkalar ro'yxati
        temp_dirs = [
            '/tmp/downloads',
            '/tmp/parsed',
            '/tmp/images',
            '/tmp/uploads',
            '/var/tmp',
        ]
        
        total_files = 0
        total_size = 0
        
        for temp_dir in temp_dirs:
            if os.path.exists(temp_dir):
                self.stdout.write(f"Papka tekshirilmoqda: {temp_dir}")
                
                files_count, size_freed = self.clean_directory(
                    temp_dir, max_age_hours, dry_run
                )
                
                total_files += files_count
                total_size += size_freed
                
                if files_count > 0:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  {files_count} fayl, {self.format_size(size_freed)} bo'shatildi"
                        )
                    )
                else:
                    self.stdout.write("  Hech qanday fayl topilmadi")
        
        # Yakuniy hisobot
        self.stdout.write(
            self.style.SUCCESS("=== Tozalash Yakunlandi ===")
        )
        self.stdout.write(f"Jami fayllar: {total_files}")
        self.stdout.write(f"Bo'shatilgan joy: {self.format_size(total_size)}")

    def clean_directory(self, directory, max_age_hours, dry_run):
        """
        Muayyan papkadagi eski fayllarni tozalash.
        
        Args:
            directory (str): Tozalash kerak bo'lgan papka
            max_age_hours (int): Maksimal yosh (soat)
            dry_run (bool): Faqat ko'rsatish rejimi
        
        Returns:
            tuple: (fayllar soni, bo'shatilgan joy)
        """
        files_count = 0
        size_freed = 0
        
        # Vaqt chegarasi
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        
        try:
            for root, dirs, files in os.walk(directory):
                for file in files:
                    file_path = os.path.join(root, file)
                    
                    try:
                        # Fayl statistikasini olish
                        stat = os.stat(file_path)
                        file_time = datetime.fromtimestamp(stat.st_mtime)
                        file_size = stat.st_size
                        
                        # Fayl eski bo'lsa
                        if file_time < cutoff_time:
                            files_count += 1
                            size_freed += file_size
                            
                            if not dry_run:
                                os.remove(file_path)
                                self.stdout.write(f"  O'chirildi: {file_path}")
                            else:
                                self.stdout.write(f"  O'chiriladi: {file_path}")
                                
                    except (OSError, IOError) as e:
                        self.stdout.write(
                            self.style.WARNING(f"  Fayl bilan ishlashda xatolik {file_path}: {e}")
                        )
                        continue
                        
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Papka tekshirishda xatolik {directory}: {e}")
            )
        
        return files_count, size_freed

    def format_size(self, size_bytes):
        """
        Bayt sonini o'qiladigan formatga o'giradi.
        
        Args:
            size_bytes (int): Bayt soni
        
        Returns:
            str: Formatlangan hajm
        """
        if size_bytes == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB", "TB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1
        
        return f"{size_bytes:.1f} {size_names[i]}"
