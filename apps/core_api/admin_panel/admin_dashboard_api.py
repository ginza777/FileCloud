"""
Admin Dashboard API Views
=========================

Bu modul admin dashboard uchun AJAX API endpoint'larini o'z ichiga oladi.
Real-time ma'lumotlar uchun ishlatiladi.
"""

from django.http import JsonResponse
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.http import require_http_methods
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta

from apps.files.models import Document, Product, DocumentError, ParseProgress
from apps.bot.models import User


@staff_member_required
@require_http_methods(["GET"])
def dashboard_stats_api(request):
    """
    Dashboard statistikalarini JSON formatida qaytaradi.
    
    Bu API endpoint:
    - Real-time statistikalar
    - Charts uchun ma'lumotlar
    - So'nggi faoliyatlar
    - Pipeline holati
    
    Returns:
        JsonResponse: Dashboard ma'lumotlari
    """
    
    try:
        # Asosiy statistikalar
        stats = calculate_main_statistics()
        
        # Charts ma'lumotlari
        chart_data = prepare_chart_data()
        
        # So'nggi faoliyatlar
        recent_activities = get_recent_activities()
        
        # Pipeline holati
        pipeline_status = get_pipeline_status()
        
        response_data = {
            'success': True,
            'timestamp': timezone.now().isoformat(),
            'stats': stats,
            'charts': chart_data,
            'activities': recent_activities,
            'pipeline': pipeline_status,
        }
        
        return JsonResponse(response_data)
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e),
            'timestamp': timezone.now().isoformat(),
        }, status=500)


@staff_member_required
@require_http_methods(["GET"])
def dashboard_charts_api(request):
    """
    Dashboard charts uchun ma'lumotlarni qaytaradi.
    
    Returns:
        JsonResponse: Charts ma'lumotlari
    """
    
    try:
        chart_data = prepare_chart_data()
        
        return JsonResponse({
            'success': True,
            'data': chart_data,
            'timestamp': timezone.now().isoformat(),
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=500)


@staff_member_required
@require_http_methods(["GET"])
def dashboard_activities_api(request):
    """
    So'nggi faoliyatlarni qaytaradi.
    
    Returns:
        JsonResponse: So'nggi faoliyatlar
    """
    
    try:
        activities = get_recent_activities()
        
        return JsonResponse({
            'success': True,
            'activities': activities,
            'timestamp': timezone.now().isoformat(),
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=500)


def calculate_main_statistics():
    """
    Asosiy statistikalarni hisoblaydi.
    
    Returns:
        dict: Barcha asosiy statistikalar
    """
    
    # Parse qilingan mahsulotlar soni
    parsed_products = Product.objects.filter(
        parsed_content__isnull=False
    ).exclude(
        parsed_content=''
    ).count()
    
    # Telegram yuborish statistikasi
    telegram_sent = Document.objects.filter(
        telegram_status='completed'
    ).count()
    
    telegram_failed = Document.objects.filter(
        telegram_status='failed'
    ).count()
    
    # Tika orqali parse qilingan (json_data mavjud bo'lsa)
    tika_parsed = Document.objects.filter(
        json_data__isnull=False
    ).count()
    
    # Indekslangan hujjatlar
    indexed_documents = Document.objects.filter(
        index_status='completed'
    ).count()
    
    # Jami xatoliklar
    total_errors = DocumentError.objects.count()
    
    # Bugungi faoliyat
    today = timezone.now().date()
    today_activity = Product.objects.filter(
        created_at__date=today
    ).count()
    
    # Pipeline ishlayotgan hujjatlar
    pipeline_running = Document.objects.filter(
        pipeline_running=True
    ).count()
    
    return {
        'parsed_products': parsed_products,
        'telegram_sent': telegram_sent,
        'telegram_failed': telegram_failed,
        'tika_parsed': tika_parsed,
        'indexed_documents': indexed_documents,
        'total_errors': total_errors,
        'today_activity': today_activity,
        'pipeline_running': pipeline_running,
    }


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
            'color': '#28a745',
            'status': 'success'
        })
    
    # So'nggi xatoliklar
    recent_errors = DocumentError.objects.order_by('-created_at')[:3]
    for error in recent_errors:
        activities.append({
            'title': f"Xatolik: {error.error_type}",
            'time': error.created_at.strftime('%H:%M, %d.%m.%Y'),
            'icon': '⚠️',
            'color': '#dc3545',
            'status': 'danger'
        })
    
    # So'nggi parse progress
    try:
        progress = ParseProgress.objects.latest('last_run_at')
        activities.append({
            'title': f"Parse jarayoni: {progress.last_page} sahifa",
            'time': progress.last_run_at.strftime('%H:%M, %d.%m.%Y'),
            'icon': '⚙️',
            'color': '#17a2b8',
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
            'color': '#6c757d',
            'status': 'secondary'
        })
    
    # Vaqt bo'yicha tartiblash
    activities.sort(key=lambda x: x['time'], reverse=True)
    
    return activities[:10]  # Eng so'nggi 10 ta faoliyat


def get_pipeline_status():
    """
    Pipeline holatini olish.
    
    Returns:
        dict: Pipeline holati ma'lumotlari
    """
    
    # Pipeline holatlarini hisoblash
    pipeline_stats = {
        'total_pipelines': Document.objects.count(),
        'running_pipelines': Document.objects.filter(pipeline_running=True).count(),
        'completed_pipelines': Document.objects.filter(completed=True).count(),
        'failed_pipelines': Document.objects.filter(
            Q(download_status='failed') |
            Q(parse_status='failed') |
            Q(index_status='failed') |
            Q(telegram_status='failed')
        ).count(),
    }
    
    # Pipeline jarayonlari
    pipeline_processes = {
        'download': {
            'total': Document.objects.count(),
            'completed': Document.objects.filter(download_status='completed').count(),
            'processing': Document.objects.filter(download_status='processing').count(),
            'failed': Document.objects.filter(download_status='failed').count(),
            'pending': Document.objects.filter(download_status='pending').count(),
        },
        'parse': {
            'total': Document.objects.count(),
            'completed': Document.objects.filter(parse_status='completed').count(),
            'processing': Document.objects.filter(parse_status='processing').count(),
            'failed': Document.objects.filter(parse_status='failed').count(),
            'pending': Document.objects.filter(parse_status='pending').count(),
        },
        'index': {
            'total': Document.objects.count(),
            'completed': Document.objects.filter(index_status='completed').count(),
            'processing': Document.objects.filter(index_status='processing').count(),
            'failed': Document.objects.filter(index_status='failed').count(),
            'pending': Document.objects.filter(index_status='pending').count(),
        },
        'telegram': {
            'total': Document.objects.count(),
            'completed': Document.objects.filter(telegram_status='completed').count(),
            'processing': Document.objects.filter(telegram_status='processing').count(),
            'failed': Document.objects.filter(telegram_status='failed').count(),
            'pending': Document.objects.filter(telegram_status='pending').count(),
        },
    }
    
    return {
        'stats': pipeline_stats,
        'processes': pipeline_processes,
    }
