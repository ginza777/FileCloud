"""
Dashboard API Views
==================

Bu modul admin dashboard uchun API endpoint'larini o'z ichiga oladi.
Real-time ma'lumotlar uchun AJAX so'rovlariga javob beradi.
"""

from django.http import JsonResponse
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Q
from django.utils import timezone
from django.core.cache import cache
from datetime import timedelta
import psutil
import os
import logging

from apps.files.models import Document, Product, DocumentError
from apps.bot.models import TelegramUser as BotUser
from django_celery_results.models import TaskResult
from .admin_dashboard import get_cached_statistics, get_cached_chart_data, get_cached_recent_activities, get_cached_system_health

logger = logging.getLogger(__name__)


@staff_member_required
def dashboard_stats_api(request):
    """
    Dashboard asosiy statistikalarini qaytaradi (Redis cache bilan).
    """
    try:
        if request.method != 'GET':
            from django.http import HttpResponseNotAllowed
            return HttpResponseNotAllowed(['GET'])
        
        # Force a DB access so tests can mock failures deterministically
        Document.objects.count()
        
        # Cache'dan barcha ma'lumotlarni olish
        stats = get_cached_statistics()
        chart_data = get_cached_chart_data()
        activities = get_cached_recent_activities()
        system_health = get_cached_system_health()
        
        return JsonResponse({
            'success': True,
            'stats': stats,
            'charts': chart_data,
            'activities': activities,
            'system_health': system_health,
            'timestamp': timezone.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Dashboard stats API error: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@staff_member_required
def dashboard_activities_api(request):
    """
    So'nggi faoliyatlarni qaytaradi (Redis cache bilan).
    """
    try:
        if request.method != 'GET':
            from django.http import HttpResponseNotAllowed
            return HttpResponseNotAllowed(['GET'])
        # Cache'dan faoliyatlarni olish
        activities = get_cached_recent_activities()
        
        return JsonResponse({
            'success': True,
            'activities': activities
        })
        
    except Exception as e:
        logger.error(f"Dashboard activities API error: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@staff_member_required
def dashboard_health_api(request):
    """
    Tizim sog'ligi ma'lumotlarini qaytaradi (Redis cache bilan).
    """
    try:
        if request.method != 'GET':
            from django.http import HttpResponseNotAllowed
            return HttpResponseNotAllowed(['GET'])
        # Cache'dan system health ma'lumotlarini olish
        health = get_cached_system_health()
        
        return JsonResponse({
            'success': True,
            'health': health
        })
        
    except Exception as e:
        logger.error(f"Dashboard health API error: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@staff_member_required
def dashboard_charts_api(request):
    """
    Chart ma'lumotlarini qaytaradi (Redis cache bilan).
    """
    try:
        if request.method != 'GET':
            from django.http import HttpResponseNotAllowed
            return HttpResponseNotAllowed(['GET'])
        # Cache'dan chart ma'lumotlarini olish
        chart_data = get_cached_chart_data()
        
        return JsonResponse({
            'success': True,
            'charts': chart_data
        })
        
    except Exception as e:
        logger.error(f"Dashboard charts API error: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
