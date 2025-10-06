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
        
        # Cache key yaratish
        cache_key = f"admin_queryset_{self.model._meta.label}_{hash(str(request.GET))}"
        
        # Cache'dan tekshirish
        cached_queryset = cache.get(cache_key)
        if cached_queryset is not None:
            logger.debug(f"Admin queryset cache hit: {cache_key}")
            return cached_queryset
        
        # Optimizatsiyalar
        if hasattr(self.model_admin, 'list_select_related'):
            queryset = queryset.select_related(*self.model_admin.list_select_related)
        
        if hasattr(self.model_admin, 'list_prefetch_related'):
            queryset = queryset.prefetch_related(*self.model_admin.list_prefetch_related)
        
        # Cache'ga saqlash (5 daqiqa)
        cache.set(cache_key, queryset, 300)
        logger.debug(f"Admin queryset cached: {cache_key}")
        
        return queryset


class OptimizedAdminSite(AdminSite):
    """
    Optimizatsiya qilingan AdminSite klassi.
    Admin panelning umumiy tezligini oshiradi.
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._setup_optimizations()
    
    def _setup_optimizations(self):
        """Admin optimizatsiyalarini sozlash"""
        # ChangeList'ni optimizatsiya qilingan versiya bilan almashtirish
        self.change_list_template = 'admin/optimized_change_list.html'
        
        # Cache sozlamalari
        self.enable_nav_sidebar = True
        self.site_header = "FileFinder Administration (Optimized)"
        self.site_title = "FileFinder Admin"
        self.index_title = "Welcome to FileFinder Administration"


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
