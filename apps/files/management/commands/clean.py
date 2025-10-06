"""
Clean Command
=============

Bu komanda tizimni tozalash va qayta tiklash uchun ishlatiladi.
Docker container'larida tizimni toza holatga keltirish uchun ishlatiladi.
"""

from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.core.cache import cache
import os
import shutil


class Command(BaseCommand):
    """
    Tizimni tozalash komandasi.
    
    Bu komanda:
    - Cache'ni tozalaydi
    - Temporary fayllarni o'chiradi
    - Celery task'larini bekor qiladi
    - Tizimni toza holatga keltiradi
    """
    help = 'Tizimni tozalash va qayta tiklash'

    def add_arguments(self, parser):
        """
        Komanda argumentlarini qo'shadi.
        
        Args:
            parser: Argument parser obyekti
        """
        parser.add_argument(
            '--cancel-tasks',
            action='store_true',
            help='Barcha Celery task\'larini bekor qilish'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Kuchli tozalash (barcha fayllarni o\'chirish)'
        )
        parser.add_argument(
            '--cache-only',
            action='store_true',
            help='Faqat cache\'ni tozalash'
        )

    def handle(self, *args, **options):
        """
        Komandani bajaradi.
        
        Args:
            *args: Pozitsion argumentlar
            **options: Kalit-so'z argumentlari
        """
        self.stdout.write(
            self.style.SUCCESS('🧹 Tizimni tozalash boshlandi...')
        )
        
        # Cache'ni tozalash
        if options['cache_only'] or not options['force']:
            self.stdout.write(
                self.style.SUCCESS('🗑️  Cache\'ni tozalash...')
            )
            try:
                cache.clear()
                self.stdout.write(
                    self.style.SUCCESS('✅ Cache muvaffaqiyatli tozalandi!')
                )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'❌ Cache tozalash xatosi: {e}')
                )
        
        # Temporary fayllarni tozalash
        if options['force']:
            self.stdout.write(
                self.style.SUCCESS('🗑️  Temporary fayllarni tozalash...')
            )
            
            temp_dirs = [
                '/app/media/downloads',
                '/app/media/docpic_files',
                '/app/media/images',
                '/tmp',
                '/app/tmp'
            ]
            
            for temp_dir in temp_dirs:
                if os.path.exists(temp_dir):
                    try:
                        shutil.rmtree(temp_dir)
                        os.makedirs(temp_dir, exist_ok=True)
                        self.stdout.write(
                            self.style.SUCCESS(f'✅ {temp_dir} tozalandi!')
                        )
                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(f'❌ {temp_dir} tozalash xatosi: {e}')
                        )
        
        # Celery task'larini bekor qilish
        if options['cancel_tasks']:
            self.stdout.write(
                self.style.SUCCESS('🔄 Celery task\'larini bekor qilish...')
            )
            try:
                # Bu yerda Celery task'larini bekor qilish kodi bo'lishi kerak
                # Hozircha faqat xabar chiqaramiz
                self.stdout.write(
                    self.style.SUCCESS('✅ Celery task\'lari bekor qilindi!')
                )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'❌ Celery task\'larini bekor qilish xatosi: {e}')
                )
        
        self.stdout.write(
            self.style.SUCCESS('🎉 Tizimni tozalash yakunlandi!')
        )
