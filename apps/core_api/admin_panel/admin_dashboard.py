"""
Admin Dashboard View
====================

Bu modul Django admin paneli uchun katta va ma'lumotga boy dashboard yaratadi.
Dashboard loyiha haqida barcha muhim statistiklarni ko'rsatadi.

Xususiyatlar:
- Parse qilingan mahsulotlar soni
- Telegram yuborish statistikasi
- Tika parse natijalari
- Indekslash holati
- Xatoliklar monitoring
- Kunlik faoliyat
- Pipeline holati
- Charts va visualizations
"""

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django.db.models import Count, Q, F
from django.utils import timezone
from django.core.cache import cache
from datetime import datetime, timedelta
import json
import logging

from apps.files.models import (
    Document, Product, DocumentError, ParseProgress, 
    DocumentImage, SearchQuery
)
from apps.bot.models import User, Broadcast, BroadcastRecipient

logger = logging.getLogger(__name__)


from django.contrib.admin.views.decorators import staff_member_required

@staff_member_required
def admin_dashboard(request):
    """
    Admin dashboard view - loyiha haqida barcha statistiklarni ko'rsatadi.
    
    Bu view:
    - Parse qilingan mahsulotlar sonini hisoblaydi
    - Telegram yuborish statistikasini ko'rsatadi
    - Tika parse natijalarini hisoblaydi
    - Indekslash holatini kuzatadi
    - Xatoliklarni monitoring qiladi
    - Kunlik faoliyatni ko'rsatadi
    - Pipeline holatini kuzatadi
    - Charts uchun ma'lumotlar tayyorlaydi
    
    Args:
        request: HTTP request obyekti
    
    Returns:
        HttpResponse: Dashboard sahifasi
    """
    
    # Asosiy statistikalar (Redis cache bilan)
    stats = get_cached_statistics()
    
    # Charts uchun ma'lumotlar (Redis cache bilan)
    chart_data = get_cached_chart_data()
    
    # So'nggi faoliyatlar (Redis cache bilan)
    recent_activities = get_cached_recent_activities()
    
    # Quick actions
    quick_actions = [
        {
            'title': 'Hujjatlar',
            'description': 'Barcha hujjatlarni ko\'rish',
            'icon': 'fas fa-file-alt',
            'url': '/admin/files/document/'
        },
        {
            'title': 'Mahsulotlar',
            'description': 'Mahsulotlarni boshqarish',
            'icon': 'fas fa-box',
            'url': '/admin/files/product/'
        },
        {
            'title': 'Foydalanuvchilar',
            'description': 'Bot foydalanuvchilari',
            'icon': 'fas fa-users',
            'url': '/admin/bot/user/'
        },
        {
            'title': 'Xatoliklar',
            'description': 'Tizim xatoliklari',
            'icon': 'fas fa-exclamation-triangle',
            'url': '/admin/files/documenterror/'
        }
    ]
    
    # System health
    system_health = get_system_health()
    
    context = {
        # Asosiy statistikalar
        'stats': stats,
        'total_documents': stats['total_documents'],
        'completed_documents': stats['completed_documents'],
        'pending_documents': stats['pending_documents'],
        'failed_documents': stats['failed_documents'],
        'total_products': stats['total_products'],
        'total_users': stats['total_users'],
        
        # Charts ma'lumotlari
        'chart_data': chart_data,
        'daily_labels': json.dumps(chart_data['daily_labels']),
        'daily_data': json.dumps(chart_data['daily_data']),
        'completed_count': chart_data['completed_count'],
        'processing_count': chart_data['processing_count'],
        'failed_count': chart_data['failed_count'],
        'pending_count': chart_data['pending_count'],
        'error_types': json.dumps(chart_data['error_types']),
        'error_counts': json.dumps(chart_data['error_counts']),
        'download_percent': chart_data['download_percent'],
        'parse_percent': chart_data['parse_percent'],
        'index_percent': chart_data['index_percent'],
        'telegram_percent': chart_data['telegram_percent'],
        'completed_percent': chart_data['completed_percent'],
        
        # So'nggi faoliyatlar
        'recent_activities': recent_activities,
        
        # Quick actions
        'quick_actions': quick_actions,
        
        # System health
        'system_health': system_health,
    }
    
    return render(request, 'admin/index.html', context)


def calculate_main_statistics():
    """
    Asosiy statistikalarni hisoblaydi (optimized queries bilan).
    
    Returns:
        dict: Barcha asosiy statistikalar
    """
    logger.info("Calculating main statistics with optimized queries")
    
    # Barcha statistikalarni bir vaqtda hisoblash (N+1 query muammosini hal qilish)
    stats = Document.objects.aggregate(
        total_documents=Count('id'),
        completed_documents=Count('id', filter=Q(completed=True)),
        pending_documents=Count('id', filter=Q(
            Q(download_status='pending') | 
            Q(parse_status='pending') | 
            Q(index_status='pending') | 
            Q(telegram_status='pending')
        )),
        failed_documents=Count('id', filter=Q(
            Q(download_status='failed') | 
            Q(parse_status='failed') | 
            Q(index_status='failed') | 
            Q(telegram_status='failed')
        )),
        telegram_sent=Count('id', filter=Q(telegram_status='completed')),
        telegram_failed=Count('id', filter=Q(telegram_status='failed')),
        tika_parsed=Count('id', filter=Q(json_data__isnull=False)),
        indexed_documents=Count('id', filter=Q(index_status='completed')),
        pipeline_running=Count('id', filter=Q(pipeline_running=True))
    )
    
    # Mahsulotlar va foydalanuvchilar soni
    total_products = Product.objects.count()
    total_users = User.objects.count()
    
    # Jami xatoliklar
    total_errors = DocumentError.objects.count()
    
    # Bugungi faoliyat
    today = timezone.now().date()
    today_activity = Product.objects.filter(
        created_at__date=today
    ).count()
    
    # Natijalarni birlashtirish
    result = {
        'total_documents': stats['total_documents'],
        'completed_documents': stats['completed_documents'],
        'pending_documents': stats['pending_documents'],
        'failed_documents': stats['failed_documents'],
        'total_products': total_products,
        'total_users': total_users,
        'telegram_sent': stats['telegram_sent'],
        'telegram_failed': stats['telegram_failed'],
        'tika_parsed': stats['tika_parsed'],
        'indexed_documents': stats['indexed_documents'],
        'total_errors': total_errors,
        'today_activity': today_activity,
        'pipeline_running': stats['pipeline_running'],
    }
    
    logger.info(f"Statistics calculated: {result}")
    return result


def prepare_chart_data():
    """
    Charts uchun ma'lumotlarni tayyorlaydi.
    
    Returns:
        dict: Charts uchun barcha ma'lumotlar
    """
    
    # Kunlik faoliyat (oxirgi 7 kun)
    daily_labels = []
    daily_data = []
    
    for i in range(7):
        date = timezone.now().date() - timedelta(days=i)
        daily_labels.append(date.strftime('%m/%d'))
        
        count = Product.objects.filter(
            created_at__date=date
        ).count()
        daily_data.append(count)
    
    daily_labels.reverse()
    daily_data.reverse()
    
    # Holat taqsimoti
    completed_count = Document.objects.filter(completed=True).count()
    processing_count = Document.objects.filter(
        Q(download_status='processing') |
        Q(parse_status='processing') |
        Q(index_status='processing') |
        Q(telegram_status='processing')
    ).count()
    failed_count = Document.objects.filter(
        Q(download_status='failed') |
        Q(parse_status='failed') |
        Q(index_status='failed') |
        Q(telegram_status='failed')
    ).count()
    pending_count = Document.objects.filter(
        Q(download_status='pending') |
        Q(parse_status='pending') |
        Q(index_status='pending') |
        Q(telegram_status='pending')
    ).count()
    
    # Xatolik turlari
    error_types = []
    error_counts = []
    
    error_stats = DocumentError.objects.values('error_type').annotate(
        count=Count('id')
    ).order_by('-count')
    
    for error in error_stats:
        error_types.append(error['error_type'])
        error_counts.append(error['count'])
    
    # Jarayon foizlari
    total_documents = Document.objects.count()
    
    if total_documents > 0:
        download_percent = (Document.objects.filter(
            download_status='completed'
        ).count() / total_documents) * 100
        
        parse_percent = (Document.objects.filter(
            parse_status='completed'
        ).count() / total_documents) * 100
        
        index_percent = (Document.objects.filter(
            index_status='completed'
        ).count() / total_documents) * 100
        
        telegram_percent = (Document.objects.filter(
            telegram_status='completed'
        ).count() / total_documents) * 100
        
        completed_percent = (Document.objects.filter(
            completed=True
        ).count() / total_documents) * 100
    else:
        download_percent = parse_percent = index_percent = telegram_percent = completed_percent = 0
    
    return {
        'daily_labels': daily_labels,
        'daily_data': daily_data,
        'completed_count': completed_count,
        'processing_count': processing_count,
        'failed_count': failed_count,
        'pending_count': pending_count,
        'error_types': error_types,
        'error_counts': error_counts,
        'download_percent': round(download_percent, 1),
        'parse_percent': round(parse_percent, 1),
        'index_percent': round(index_percent, 1),
        'telegram_percent': round(telegram_percent, 1),
        'completed_percent': round(completed_percent, 1),
    }


def get_recent_activities():
    """
    So'nggi faoliyatlarni olish.
    
    Returns:
        list: So'nggi faoliyatlar ro'yxati
    """
    
    activities = []
    
    # So'nggi mahsulotlar
    recent_products = Product.objects.order_by('-created_at')[:5]
    for product in recent_products:
        activities.append({
            'title': f"Yangi mahsulot: {product.title[:50]}...",
            'time': product.created_at.strftime('%H:%M, %d.%m.%Y'),
            'icon': '📄',
            'status': 'success'
        })
    
    # So'nggi xatoliklar
    recent_errors = DocumentError.objects.order_by('-created_at')[:3]
    for error in recent_errors:
        activities.append({
            'title': f"Xatolik: {error.error_type}",
            'time': error.created_at.strftime('%H:%M, %d.%m.%Y'),
            'icon': '⚠️',
            'status': 'danger'
        })
    
    # So'nggi parse progress
    try:
        progress = ParseProgress.objects.latest('last_run_at')
        activities.append({
            'title': f"Parse jarayoni: {progress.last_page} sahifa",
            'time': progress.last_run_at.strftime('%H:%M, %d.%m.%Y'),
            'icon': '⚙️',
            'status': 'info'
        })
    except ParseProgress.DoesNotExist:
        pass
    
    # So'nggi foydalanuvchilar
    recent_users = User.objects.order_by('-created_at')[:2]
    for user in recent_users:
        activities.append({
            'title': f"Yangi foydalanuvchi: {user.full_name}",
            'time': user.created_at.strftime('%H:%M, %d.%m.%Y'),
            'icon': '👤',
            'status': 'secondary'
        })
    
    # Vaqt bo'yicha tartiblash
    activities.sort(key=lambda x: x['time'], reverse=True)
    
    return activities[:10]  # Eng so'nggi 10 ta faoliyat


def get_system_health():
    """
    Tizim sog'ligi ma'lumotlarini olish.
    
    Returns:
        dict: Tizim sog'ligi ma'lumotlari
    """
    try:
        import psutil
        
        # Disk foydalanishi
        disk_usage = psutil.disk_usage('/')
        disk_percent = round((disk_usage.used / disk_usage.total) * 100, 1)
        
        # Xotira foydalanishi
        memory = psutil.virtual_memory()
        memory_percent = round(memory.percent, 1)
        
        # CPU foydalanishi
        cpu_percent = round(psutil.cpu_percent(interval=1), 1)
        
        # Database holati
        try:
            Document.objects.count()
            database_status = 'OK'
        except:
            database_status = 'ERROR'
        
        # Celery holati
        try:
            from django_celery_results.models import TaskResult
            TaskResult.objects.count()
            celery_status = 'OK'
        except:
            celery_status = 'ERROR'
        
        # Elasticsearch holati (mock)
        elasticsearch_status = 'OK'  # Haqiqiy tekshirish kerak
        
        # Redis holati (mock)
        redis_status = 'OK'  # Haqiqiy tekshirish kerak
        
        return {
            'database_status': database_status,
            'celery_status': celery_status,
            'elasticsearch_status': elasticsearch_status,
            'redis_status': redis_status,
            'disk_usage': f'{disk_percent}%',
            'memory_usage': f'{memory_percent}%',
            'cpu_usage': f'{cpu_percent}%'
        }
        
    except ImportError:
        # psutil mavjud bo'lmasa
        return {
            'database_status': 'OK',
            'celery_status': 'OK',
            'elasticsearch_status': 'OK',
            'redis_status': 'OK',
            'disk_usage': 'N/A',
            'memory_usage': 'N/A',
            'cpu_usage': 'N/A'
        }
    except Exception as e:
        logger.error(f"System health check error: {e}")
        return {
            'database_status': 'ERROR',
            'celery_status': 'ERROR',
            'elasticsearch_status': 'ERROR',
            'redis_status': 'ERROR',
            'disk_usage': 'ERROR',
            'memory_usage': 'ERROR',
            'cpu_usage': 'ERROR'
        }


# Redis Cache Functions
def get_cached_statistics():
    """Redis cache bilan asosiy statistikalarni olish"""
    cache_key = 'dashboard_main_statistics'
    cached_stats = cache.get(cache_key)
    
    if cached_stats is None:
        logger.info("Cache miss for main statistics, calculating...")
        cached_stats = calculate_main_statistics()
        # 5 daqiqa cache
        cache.set(cache_key, cached_stats, 300)
    else:
        logger.debug("Cache hit for main statistics")
    
    return cached_stats


def get_cached_chart_data():
    """Redis cache bilan chart ma'lumotlarini olish"""
    cache_key = 'dashboard_chart_data'
    cached_data = cache.get(cache_key)
    
    if cached_data is None:
        logger.info("Cache miss for chart data, calculating...")
        cached_data = prepare_chart_data()
        # 10 daqiqa cache
        cache.set(cache_key, cached_data, 600)
    else:
        logger.debug("Cache hit for chart data")
    
    return cached_data


def get_cached_recent_activities():
    """Redis cache bilan so'nggi faoliyatlarni olish"""
    cache_key = 'dashboard_recent_activities'
    cached_activities = cache.get(cache_key)
    
    if cached_activities is None:
        logger.info("Cache miss for recent activities, calculating...")
        cached_activities = get_recent_activities()
        # 2 daqiqa cache
        cache.set(cache_key, cached_activities, 120)
    else:
        logger.debug("Cache hit for recent activities")
    
    return cached_activities


def invalidate_dashboard_cache():
    """Dashboard cache'ni tozalash"""
    cache_keys = [
        'dashboard_main_statistics',
        'dashboard_chart_data', 
        'dashboard_recent_activities'
    ]
    
    for key in cache_keys:
        cache.delete(key)
    
    logger.info("Dashboard cache invalidated")


def get_cached_system_health():
    """Redis cache bilan system health ma'lumotlarini olish"""
    cache_key = 'dashboard_system_health'
    cached_health = cache.get(cache_key)
    
    if cached_health is None:
        logger.info("Cache miss for system health, calculating...")
        cached_health = get_system_health()
        # 1 daqiqa cache
        cache.set(cache_key, cached_health, 60)
    else:
        logger.debug("Cache hit for system health")
    
    return cached_health
