"""
System Cleanup Command
======================

Bu komanda tizimni to'liq tozalash va texnik xizmat ko'rsatish uchun yagona komanda.
Celery tasklarini bekor qilish, fayllarni tozalash va tizim holatini tuzatish.

Ishlatish:
    python manage.py cleanup_system --all
    python manage.py cleanup_system --cancel-tasks
    python manage.py cleanup_system --clean-files
"""

import os
import re
import redis
import logging
from urllib.parse import urlparse
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from celery import current_app

from apps.files.models import Document

logger = logging.getLogger(__name__)

# Fayl kengaytmalari ro'yxati
ALL_EXTS = ['pdf', 'docx', 'doc', 'pptx', 'ppt', 'xlsx', 'xls', 'txt', 'rtf', 'odt', 'ods', 'odp']
ALL_EXTS_LOWER = [ext.lower() for ext in ALL_EXTS]


class Command(BaseCommand):
    """
    Tizimni to'liq tozalash va texnik xizmat ko'rsatish komandasi.
    
    Bu komanda quyidagi vazifalarni bajaradi:
    1. Celery tasklarini bekor qilish
    2. Fayllarni tozalash
    3. Database holatini tuzatish
    4. Redis cache'ni tozalash
    5. Temporary fayllarni o'chirish
    """
    
    help = "Tizim holatini to'g'rilash, Celery tasklarini tozalash va fayllarni boshqarish uchun yagona komanda."

    def add_arguments(self, parser):
        parser.add_argument(
            '--all', 
            action='store_true',
            help='Barcha tuzatish va tozalash amallarini tavsiya etilgan tartibda bajaradi.'
        )
        parser.add_argument(
            '--cancel-tasks', 
            action='store_true',
            help='Barcha faol Celery tasklarini bekor qiladi'
        )
        parser.add_argument(
            '--clean-files', 
            action='store_true',
            help='Temporary va keraksiz fayllarni o\'chiradi'
        )
        parser.add_argument(
            '--reset-pipelines', 
            action='store_true',
            help='Stuck pipeline\'larni qayta tiklaydi'
        )
        parser.add_argument(
            '--clean-redis', 
            action='store_true',
            help='Redis cache\'ni tozalaydi'
        )

    def handle(self, *args, **options):
        """Asosiy tozalash jarayoni."""
        self.stdout.write(
            self.style.SUCCESS("=== Tizim Tozalash Jarayoni Boshlandi ===")
        )

        if options['all']:
            self.stdout.write("Barcha tozalash amallari bajarilmoqda...")
            self.cancel_all_tasks()
            self.clean_files()
            self.reset_stuck_pipelines()
            self.clean_redis()
        else:
            if options['cancel_tasks']:
                self.cancel_all_tasks()
            
            if options['clean_files']:
                self.clean_files()
                
            if options['reset_pipelines']:
                self.reset_stuck_pipelines()
                
            if options['clean_redis']:
                self.clean_redis()

        self.stdout.write(
            self.style.SUCCESS("=== Tizim Tozalash Jarayoni Yakunlandi ===")
        )

    def cancel_all_tasks(self):
        """Barcha faol Celery tasklarini bekor qiladi."""
        self.stdout.write("Celery tasklari bekor qilinmoqda...")
        
        try:
            # Celery app'ni olish
            celery_app = current_app
            
            # Barcha faol tasklarni bekor qilish
            celery_app.control.purge()
            
            self.stdout.write(
                self.style.SUCCESS("Barcha Celery tasklari bekor qilindi")
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Celery tasklarini bekor qilishda xatolik: {e}")
            )

    def clean_files(self):
        """Temporary va keraksiz fayllarni o'chiradi."""
        self.stdout.write("Fayllar tozalanmoqda...")
        
        temp_dirs = [
            '/tmp/downloads',
            '/tmp/parsed',
            '/tmp/images',
            settings.MEDIA_ROOT + '/temp/',
        ]
        
        cleaned_count = 0
        
        for temp_dir in temp_dirs:
            if os.path.exists(temp_dir):
                try:
                    for root, dirs, files in os.walk(temp_dir):
                        for file in files:
                            file_path = os.path.join(root, file)
                            try:
                                os.remove(file_path)
                                cleaned_count += 1
                            except OSError:
                                pass
                    
                    self.stdout.write(f"Papka tozalandi: {temp_dir}")
                except Exception as e:
                    self.stdout.write(
                        self.style.WARNING(f"Papka tozalashda xatolik {temp_dir}: {e}")
                    )
        
        self.stdout.write(
            self.style.SUCCESS(f"Jami {cleaned_count} fayl o'chirildi")
        )

    def reset_stuck_pipelines(self):
        """Stuck pipeline'larni qayta tiklaydi."""
        self.stdout.write("Stuck pipeline'lar qayta tiklanmoqda...")
        
        # 1 soatdan eski stuck pipeline'larni topish
        timeout_threshold = timezone.now() - timedelta(hours=1)
        
        stuck_docs = Document.objects.filter(
            pipeline_running=True,
            updated_at__lt=timeout_threshold
        )
        
        count = stuck_docs.count()
        
        if count > 0:
            stuck_docs.update(pipeline_running=False)
            self.stdout.write(
                self.style.SUCCESS(f"{count} ta stuck pipeline qayta tiklandi")
            )
        else:
            self.stdout.write("Stuck pipeline'lar topilmadi")

    def clean_redis(self):
        """Redis cache'ni tozalaydi."""
        self.stdout.write("Redis cache tozalanmoqda...")
        
        try:
            # Redis connection
            r = redis.Redis(
                host=getattr(settings, 'REDIS_HOST', 'localhost'),
                port=getattr(settings, 'REDIS_PORT', 6379),
                db=getattr(settings, 'REDIS_DB', 0)
            )
            
            # Barcha key'larni o'chirish
            r.flushdb()
            
            self.stdout.write(
                self.style.SUCCESS("Redis cache tozalandi")
            )
        except Exception as e:
            self.stdout.write(
                self.style.WARNING(f"Redis tozalashda xatolik: {e}")
            )
