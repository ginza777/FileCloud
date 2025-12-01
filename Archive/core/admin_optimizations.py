"""
Django Admin Performance Optimizations
=====================================

Bu fayl Django admin panelini optimizatsiya qilish uchun sozlamalarni o'z ichiga oladi.
Admin panelning tez ishlashi uchun cache, database optimizatsiyalari va boshqa sozlamalar.

Ishlatish:
    Bu fayl settings.py da import qilinadi va admin optimizatsiyalari qo'shiladi.
"""

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.contrib.admin.views.main import ChangeList
from django.contrib.admin import AdminSite
from redis.exceptions import RedisError
import logging

logger = logging.getLogger(__name__)


class OptimizedChangeList(ChangeList):
    """
    Optimizatsiya qilingan ChangeList klassi.
    Admin list view'larida tezroq ishlash uchun optimizatsiyalar qo'shadi.
    """
    
    def get_queryset(self, request):
        """Optimizatsiya qilingan queryset olish"""
        queryset = super().get_queryset(request)
        
        try:
            # Cache key yaratish
            cache_key = f"admin_queryset_{self.model._meta.label}_{hash(str(request.GET))}"

            # Cache'dan tekshirish
            try:
                cached_queryset = cache.get(cache_key)
                if cached_queryset is not None:
                    logger.debug(f"Admin queryset cache hit: {cache_key}")
                    return cached_queryset
            except (RedisError, ConnectionError) as e:
                logger.warning(f"Redis cache get error in admin: {str(e)}")
                cached_queryset = None

            # Optimizatsiyalar
            if hasattr(self.model_admin, 'list_select_related'):
                queryset = queryset.select_related(*self.model_admin.list_select_related)

            if hasattr(self.model_admin, 'list_prefetch_related'):
                queryset = queryset.prefetch_related(*self.model_admin.list_prefetch_related)

            # Cache'ga saqlash (5 daqiqa)
            try:
                cache.set(cache_key, queryset, 300)
                logger.debug(f"Admin queryset cached: {cache_key}")
            except (RedisError, ConnectionError) as e:
                logger.warning(f"Redis cache set error in admin: {str(e)}")

        except Exception as e:
            logger.error(f"Unexpected error in admin queryset optimization: {str(e)}")

        return queryset


class OptimizedAdminSite(AdminSite):
    """
    Optimizatsiya qilingan AdminSite klassi.
    Admin saytining ishlashini tezlashtirish uchun qo'shimcha optimizatsiyalar.
    """
    
    def get_app_list(self, request, app_label=None):
        """
        Admin app list'ni olish - cache bilan optimizatsiyalangan
        """
        try:
            cache_key = f"admin_app_list_{request.user.id}_{app_label or 'all'}"

            # Cache'dan tekshirish
            try:
                cached_app_list = cache.get(cache_key)
                if cached_app_list is not None:
                    return cached_app_list
            except (RedisError, ConnectionError) as e:
                logger.warning(f"Redis cache get error in admin app list: {str(e)}")
                cached_app_list = None

            # App list'ni olish
            app_list = super().get_app_list(request, app_label)

            # Cache'ga saqlash (30 daqiqa)
            try:
                cache.set(cache_key, app_list, 1800)
            except (RedisError, ConnectionError) as e:
                logger.warning(f"Redis cache set error in admin app list: {str(e)}")

            return app_list

        except Exception as e:
            logger.error(f"Unexpected error in admin app list: {str(e)}")
            return super().get_app_list(request, app_label)


def optimize_admin_performance():
    """
    Django admin panelini optimizatsiya qilish uchun asosiy funksiya.
    Bu funksiya settings.py da chaqiriladi.
    """
    
    # Database optimizatsiyalari
    if hasattr(settings, 'DATABASES'):
        for db_name, db_config in settings.DATABASES.items():
            if 'OPTIONS' not in db_config:
                db_config['OPTIONS'] = {}
            
            # PostgreSQL optimizatsiyalari
            if 'postgresql' in db_config.get('ENGINE', ''):
                db_config['OPTIONS'].update({
                    'MAX_CONNS': 20,
                    'MIN_CONNS': 5,
                    'CONN_MAX_AGE': 600,  # 10 daqiqa
                })
            
            # MySQL optimizatsiyalari
            elif 'mysql' in db_config.get('ENGINE', ''):
                db_config['OPTIONS'].update({
                    'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
                    'charset': 'utf8mb4',
                })
    
    # Cache sozlamalari
    if not hasattr(settings, 'CACHES'):
        settings.CACHES = {
            'default': {
                'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
                'LOCATION': 'unique-snowflake',
                'TIMEOUT': 300,  # 5 daqiqa
                'OPTIONS': {
                    'MAX_ENTRIES': 1000,
                }
            }
        }
    
    # Admin optimizatsiyalari
    settings.ADMIN_OPTIMIZATIONS = {
        'ENABLE_CACHE': True,
        'CACHE_TIMEOUT': 300,  # 5 daqiqa
        'PAGINATION_SIZE': 25,
        'ENABLE_SELECT_RELATED': True,
        'ENABLE_PREFETCH_RELATED': True,
    }
    
    logger.info("Django admin performance optimizations applied")


def get_admin_cache_key(model, request_params):
    """
    Admin cache key yaratish uchun yordamchi funksiya.
    
    Args:
        model: Django model klassi
        request_params: Request parametrlari
    
    Returns:
        str: Cache key
    """
    import hashlib
    
    # Request parametrlarini hash qilish
    params_str = str(sorted(request_params.items()))
    params_hash = hashlib.md5(params_str.encode()).hexdigest()[:8]
    
    return f"admin_{model._meta.label}_{params_hash}"


def clear_admin_cache():
    """Admin cache'ini tozalash"""
    try:
        # Admin bilan bog'liq barcha cache'larni tozalash
        cache.delete_many([
            key for key in cache._cache.keys() 
            if key.startswith('admin_')
        ])
        logger.info("Admin cache cleared successfully")
    except Exception as e:
        logger.error(f"Error clearing admin cache: {e}")


# Admin optimizatsiyalarini avtomatik qo'llash
if hasattr(settings, 'ADMIN_OPTIMIZATIONS'):
    optimize_admin_performance()
