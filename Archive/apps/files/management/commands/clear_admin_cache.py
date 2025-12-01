"""
Clear Admin Cache Command
=========================

Bu komanda Django admin panelining cache'ini tozalaydi.
Admin panelida sekinlik bo'lsa yoki ma'lumotlar yangilanmasa ishlatiladi.

Ishlatish:
    python manage.py clear_admin_cache
    python manage.py clear_admin_cache --all
"""

from django.core.management.base import BaseCommand
from django.core.cache import cache
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Django admin panelining cache'ini tozalash komandasi.
    
    Bu komanda:
    1. Admin bilan bog'liq barcha cache'larni tozalaydi
    2. Database connection cache'ini tozalaydi
    3. Session cache'ini tozalaydi (agar kerak bo'lsa)
    4. Cache statistikasini ko'rsatadi
    """
    
    help = "Django admin panelining cache'ini tozalaydi"

    def add_arguments(self, parser):
        parser.add_argument(
            '--all',
            action='store_true',
            help='Barcha cache\'larni tozalash (admin, session, database)'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Batafsil ma\'lumot ko\'rsatish'
        )

    def handle(self, *args, **options):
        """Asosiy cache tozalash jarayoni."""
        all_cache = options['all']
        verbose = options['verbose']
        
        self.stdout.write(
            self.style.SUCCESS("=== Admin Cache Tozalash Jarayoni ===")
        )
        
        if all_cache:
            self.stdout.write("Barcha cache'lar tozalanmoqda...")
        else:
            self.stdout.write("Faqat admin cache'lar tozalanmoqda...")
        
        # Cache statistikasini olish
        if verbose:
            self.show_cache_stats()
        
        # Admin cache'ini tozalash
        admin_cleared = self.clear_admin_cache()
        
        if all_cache:
            # Barcha cache'larni tozalash
            session_cleared = self.clear_session_cache()
            db_cleared = self.clear_database_cache()
            
            self.stdout.write(
                self.style.SUCCESS("=== Barcha Cache'lar Tozalandi ===")
            )
            self.stdout.write(f"Admin cache: {admin_cleared}")
            self.stdout.write(f"Session cache: {session_cleared}")
            self.stdout.write(f"Database cache: {db_cleared}")
        else:
            self.stdout.write(
                self.style.SUCCESS("=== Admin Cache Tozalandi ===")
            )
            self.stdout.write(f"Tozalangan admin cache'lar: {admin_cleared}")
        
        # Yakuniy tavsiyalar
        self.stdout.write("\n" + self.style.WARNING("Tavsiyalar:"))
        self.stdout.write("1. Admin panelini yangilang")
        self.stdout.write("2. Agar sekinlik davom etsa, server restart qiling")
        self.stdout.write("3. Database indekslarini tekshiring")

    def clear_admin_cache(self):
        """Admin cache'ini tozalash"""
        try:
            # Admin bilan bog'liq cache key'larni topish
            admin_keys = []
            
            # Cache backend'ni tekshirish
            if hasattr(cache, '_cache'):
                # LocMemCache uchun
                if hasattr(cache._cache, 'keys'):
                    all_keys = list(cache._cache.keys())
                    admin_keys = [key for key in all_keys if 'admin' in str(key).lower()]
                else:
                    # Boshqa cache backend'lar uchun
                    admin_keys = ['admin_queryset', 'admin_list', 'admin_count']
            
            # Admin cache'larni o'chirish
            if admin_keys:
                cache.delete_many(admin_keys)
                cleared_count = len(admin_keys)
            else:
                # Umumiy admin cache'ni o'chirish
                cache.delete('admin_queryset')
                cache.delete('admin_list')
                cache.delete('admin_count')
                cleared_count = 3
            
            logger.info(f"Admin cache cleared: {cleared_count} items")
            return cleared_count
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Admin cache tozalashda xatolik: {e}")
            )
            logger.error(f"Error clearing admin cache: {e}")
            return 0

    def clear_session_cache(self):
        """Session cache'ini tozalash"""
        try:
            # Session cache'ni tozalash
            cache.delete('session_cache')
            logger.info("Session cache cleared")
            return "Muvaffaqiyatli"
        except Exception as e:
            self.stdout.write(
                self.style.WARNING(f"Session cache tozalashda xatolik: {e}")
            )
            return "Xatolik"

    def clear_database_cache(self):
        """Database connection cache'ini tozalash"""
        try:
            from django.db import connections
            
            # Barcha database connection'larni yopish
            for conn in connections.all():
                conn.close()
            
            logger.info("Database connections cleared")
            return "Muvaffaqiyatli"
        except Exception as e:
            self.stdout.write(
                self.style.WARNING(f"Database cache tozalashda xatolik: {e}")
            )
            return "Xatolik"

    def show_cache_stats(self):
        """Cache statistikasini ko'rsatish"""
        try:
            if hasattr(cache, '_cache'):
                if hasattr(cache._cache, 'keys'):
                    total_keys = len(list(cache._cache.keys()))
                    admin_keys = len([k for k in cache._cache.keys() if 'admin' in str(k).lower()])
                    
                    self.stdout.write(f"Jami cache key'lar: {total_keys}")
                    self.stdout.write(f"Admin cache key'lar: {admin_keys}")
                else:
                    self.stdout.write("Cache statistikasi mavjud emas")
            else:
                self.stdout.write("Cache backend statistikasi mavjud emas")
        except Exception as e:
            self.stdout.write(f"Cache statistikasini olishda xatolik: {e}")
