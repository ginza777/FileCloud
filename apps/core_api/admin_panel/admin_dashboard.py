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
    Document, Product, DocumentError, 
    DocumentImage, SearchQuery
)
from apps.bot.models import TelegramUser, Broadcast, BroadcastRecipient

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
    system_health = get_cached_system_health()
    
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
    
    try:
        # Get total documents and their statuses
        document_stats = Document.objects.aggregate(
            total_documents=Count('id'),
            completed_documents=Count('id', filter=Q(completed=True)),
            pending_documents=Count('id', filter=Q(completed=False, download_status='pending') |
                                              Q(completed=False, parse_status='pending') |
                                              Q(completed=False, index_status='pending') |
                                              Q(completed=False, telegram_status='pending')),
            failed_documents=Count('id', filter=Q(download_status='failed') |
                                            Q(parse_status='failed') |
                                            Q(index_status='failed') |
                                            Q(telegram_status='failed')),
            telegram_sent=Count('id', filter=Q(telegram_status='completed')),
            telegram_failed=Count('id', filter=Q(telegram_status='failed')),
            tika_parsed=Count('id', filter=Q(parse_status='completed')),
            indexed_documents=Count('id', filter=Q(index_status='completed'))
        )

        # Get other counts
        total_products = Product.objects.count()
        total_users = TelegramUser.objects.count()
        total_errors = DocumentError.objects.count()

        # Get today's activity
        today = timezone.now().date()
        today_activity = Document.objects.filter(created_at__date=today).count()

        # Get pipeline running count
        pipeline_running = Document.objects.filter(
            Q(download_status='processing') |
            Q(parse_status='processing') |
            Q(index_status='processing') |
            Q(telegram_status='processing')
        ).count()

        # Combine all statistics
        stats = {
            'total_documents': document_stats['total_documents'] or 0,
            'completed_documents': document_stats['completed_documents'] or 0,
            'pending_documents': document_stats['pending_documents'] or 0,
            'failed_documents': document_stats['failed_documents'] or 0,
            'total_products': total_products or 0,
            'total_users': total_users or 0,
            'telegram_sent': document_stats['telegram_sent'] or 0,
            'telegram_failed': document_stats['telegram_failed'] or 0,
            'tika_parsed': document_stats['tika_parsed'] or 0,
            'indexed_documents': document_stats['indexed_documents'] or 0,
            'total_errors': total_errors or 0,
            'today_activity': today_activity or 0,
            'pipeline_running': pipeline_running or 0
        }

        logger.info(f"Statistics calculated successfully: {stats}")
        return stats

    except Exception as e:
        logger.error(f"Error calculating statistics: {e}")
        # Return default values in case of error
        return {
            'total_documents': 0,
            'completed_documents': 0,
            'pending_documents': 0,
            'failed_documents': 0,
            'total_products': 0,
            'total_users': 0,
            'telegram_sent': 0,
            'telegram_failed': 0,
            'tika_parsed': 0,
            'indexed_documents': 0,
            'total_errors': 0,
            'today_activity': 0,
            'pipeline_running': 0
        }


def prepare_chart_data():
    """
    Charts uchun ma'lumotlarni tayyorlaydi (optimized).
    
    Returns:
        dict: Charts uchun barcha ma'lumotlar
    """
    try:
        # Kunlik faoliyat (oxirgi 7 kun)
        daily_labels = []
        daily_data = []

        # Get documents created in the last 7 days in a single query
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=6)

        daily_counts = Document.objects.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date
        ).values('created_at__date').annotate(
            count=Count('id')
        ).order_by('created_at__date')

        # Create a lookup dict for easy access
        counts_by_date = {
            item['created_at__date']: item['count']
            for item in daily_counts
        }

        # Fill in the data for all days
        current_date = start_date
        while current_date <= end_date:
            daily_labels.append(current_date.strftime('%m/%d'))
            daily_data.append(counts_by_date.get(current_date, 0))
            current_date += timedelta(days=1)

        # Get document status distribution in a single query
        status_stats = Document.objects.aggregate(
            completed_count=Count('id', filter=Q(completed=True)),
            processing_count=Count('id', filter=Q(
                Q(download_status='processing') |
                Q(parse_status='processing') |
                Q(index_status='processing') |
                Q(telegram_status='processing')
            )),
            failed_count=Count('id', filter=Q(
                Q(download_status='failed') |
                Q(parse_status='failed') |
                Q(index_status='failed') |
                Q(telegram_status='failed')
            )),
            pending_count=Count('id', filter=Q(
                Q(download_status='pending') |
                Q(parse_status='pending') |
                Q(index_status='pending') |
                Q(telegram_status='pending')
            ))
        )

        # Get error statistics in a single query
        error_stats = DocumentError.objects.values('error_type').annotate(
            count=Count('id')
        ).order_by('-count')

        error_types = []
        error_counts = []
        for error in error_stats:
            error_types.append(error['error_type'])
            error_counts.append(error['count'])

        # Calculate percentages
        total_documents = Document.objects.count()

        if total_documents > 0:
            # Get all completion percentages in a single query
            completion_stats = Document.objects.aggregate(
                download_completed=Count('id', filter=Q(download_status='completed')),
                parse_completed=Count('id', filter=Q(parse_status='completed')),
                index_completed=Count('id', filter=Q(index_status='completed')),
                telegram_completed=Count('id', filter=Q(telegram_status='completed')),
                fully_completed=Count('id', filter=Q(completed=True))
            )

            download_percent = (completion_stats['download_completed'] / total_documents) * 100
            parse_percent = (completion_stats['parse_completed'] / total_documents) * 100
            index_percent = (completion_stats['index_completed'] / total_documents) * 100
            telegram_percent = (completion_stats['telegram_completed'] / total_documents) * 100
            completed_percent = (completion_stats['fully_completed'] / total_documents) * 100
        else:
            download_percent = parse_percent = index_percent = telegram_percent = completed_percent = 0

        return {
            'daily_labels': daily_labels,
            'daily_data': daily_data,
            'completed_count': status_stats['completed_count'] or 0,
            'processing_count': status_stats['processing_count'] or 0,
            'failed_count': status_stats['failed_count'] or 0,
            'pending_count': status_stats['pending_count'] or 0,
            'error_types': error_types,
            'error_counts': error_counts,
            'download_percent': round(download_percent, 1),
            'parse_percent': round(parse_percent, 1),
            'index_percent': round(index_percent, 1),
            'telegram_percent': round(telegram_percent, 1),
            'completed_percent': round(completed_percent, 1)
        }

    except Exception as e:
        logger.error(f"Error preparing chart data: {e}")
        # Return default values in case of error
        return {
            'daily_labels': [timezone.now().strftime('%m/%d')] * 7,
            'daily_data': [0] * 7,
            'completed_count': 0,
            'processing_count': 0,
            'failed_count': 0,
            'pending_count': 0,
            'error_types': [],
            'error_counts': [],
            'download_percent': 0,
            'parse_percent': 0,
            'index_percent': 0,
            'telegram_percent': 0,
            'completed_percent': 0
        }


def get_recent_activities():
    """
    So'nggi faoliyatlarni olish (optimized).
    
    Returns:
        list: So'nggi faoliyatlar ro'yxati
    """
    
    activities = []
    
    # So'nggi mahsulotlar - select_related bilan optimizatsiya
    recent_products = Product.objects.select_related('document').order_by('-created_at')[:5]
    for product in recent_products:
        activities.append({
            'title': f"Yangi mahsulot: {product.title[:50]}...",
            'time': product.created_at.strftime('%H:%M, %d.%m.%Y'),
            'icon': '📄',
            'status': 'success'
        })
    
    # So'nggi xatoliklar
    recent_errors = DocumentError.objects.select_related('document').order_by('-created_at')[:3]
    for error in recent_errors:
        activities.append({
            'title': f"Xatolik: {error.error_type}",
            'time': error.created_at.strftime('%H:%M, %d.%m.%Y'),
            'icon': '⚠️',
            'status': 'danger'
        })
    
    # ParseProgress model o'chirilgan, shuning uchun bu qism o'chirildi
    
    # So'nggi foydalanuvchilar
    recent_users = TelegramUser.objects.order_by('-created_at')[:2]
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


# Redis Cache Functions with 3-minute refresh
def get_cached_statistics():
    """Redis cache bilan asosiy statistikalarni olish - 3 daqiqa cache"""
    cache_key = 'admin_dashboard_statistics'
    cached_stats = cache.get(cache_key)
    
    if cached_stats is None:
        logger.info("Cache miss for statistics, calculating...")
        cached_stats = calculate_main_statistics()
        # 3 daqiqa cache (180 seconds)
        cache.set(cache_key, cached_stats, 180)
    else:
        logger.debug("Cache hit for statistics")
    
    return cached_stats


def get_cached_chart_data():
    """Redis cache bilan chart ma'lumotlarini olish - 3 daqiqa cache"""
    cache_key = 'admin_dashboard_chart_data'
    cached_data = cache.get(cache_key)
    
    if cached_data is None:
        logger.info("Cache miss for chart data, calculating...")
        cached_data = prepare_chart_data()
        # 3 daqiqa cache (180 seconds)
        cache.set(cache_key, cached_data, 180)
    else:
        logger.debug("Cache hit for chart data")
    
    return cached_data


def get_cached_recent_activities():
    """Redis cache bilan so'nggi faoliyatlarni olish - 3 daqiqa cache"""
    cache_key = 'admin_dashboard_recent_activities'
    cached_activities = cache.get(cache_key)
    
    if cached_activities is None:
        logger.info("Cache miss for recent activities, calculating...")
        cached_activities = get_recent_activities()
        # 3 daqiqa cache (180 seconds)
        cache.set(cache_key, cached_activities, 180)
    else:
        logger.debug("Cache hit for recent activities")
    
    return cached_activities


def invalidate_dashboard_cache():
    """Dashboard cache'ni tozalash"""
    cache_keys = [
        'admin_dashboard_statistics',
        'admin_dashboard_chart_data', 
        'admin_dashboard_recent_activities',
        'dashboard_system_health'
    ]
    
    for key in cache_keys:
        cache.delete(key)
    
    logger.info("Dashboard cache invalidated")


def get_cached_system_health():
    """Redis cache bilan system health ma'lumotlarini olish - 3 daqiqa cache"""
    cache_key = 'dashboard_system_health'
    cached_health = cache.get(cache_key)
    
    if cached_health is None:
        logger.info("Cache miss for system health, calculating...")
        cached_health = get_system_health()
        # 3 daqiqa cache (180 seconds)
        cache.set(cache_key, cached_health, 180)
    else:
        logger.debug("Cache hit for system health")
    
    return cached_health
