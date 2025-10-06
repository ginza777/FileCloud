"""
Core Functions Tests
====================

Bu modul loyihaning asosiy funksiyalari uchun testlarni o'z ichiga oladi.
Dashboard, caching, logging va boshqa core funksiyalar uchun testlar.
"""

import os
import sys
import django
from django.test import TestCase, TransactionTestCase
from django.contrib.auth.models import User
from django.core.cache import cache
from django.utils import timezone
from unittest.mock import patch, MagicMock
import logging

# Add the project directory to Python path
sys.path.append('/app')

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from apps.files.models import Document, Product, DocumentError
from apps.bot.models import User as BotUser
from apps.core_api.admin_panel.admin_dashboard import (
    calculate_main_statistics, prepare_chart_data, get_recent_activities,
    get_cached_statistics, get_cached_chart_data, get_cached_recent_activities,
    invalidate_dashboard_cache, get_cached_system_health
)
from utils.logger import get_logger, log_function_call, LoggerMixin


class DashboardStatisticsTests(TestCase):
    """Dashboard statistics funksiyalari uchun testlar"""
    
    def setUp(self):
        """Test uchun ma'lumotlar yaratish"""
        # Test hujjatlari yaratish
        self.documents = []
        for i in range(10):
            doc = Document.objects.create(
                parse_file_url=f'https://example.com/doc{i}.pdf',
                download_status='completed' if i < 8 else 'pending',
                parse_status='completed' if i < 6 else 'pending',
                index_status='completed' if i < 4 else 'pending',
                telegram_status='completed' if i < 2 else 'pending',
                completed=i < 2,
                pipeline_running=i >= 8
            )
            self.documents.append(doc)
        
        # Test mahsulotlari yaratish
        for i in range(5):
            Product.objects.create(
                document=self.documents[i],
                title=f'Test Product {i}',
                parsed_content=f'Content {i}' if i < 3 else None
            )
        
        # Test foydalanuvchilari yaratish
        for i in range(3):
            BotUser.objects.create(
                username=f'testuser{i}',
                first_name=f'Test{i}',
                last_name='User'
            )
        
        # Test xatoliklari yaratish
        for i in range(2):
            DocumentError.objects.create(
                document=self.documents[i],
                error_type='test_error',
                error_message=f'Test error {i}'
            )
    
    def test_calculate_main_statistics(self):
        """Asosiy statistikalarni hisoblash testi"""
        stats = calculate_main_statistics()
        
        # Asosiy tekshirishlar
        self.assertEqual(stats['total_documents'], 10)
        self.assertEqual(stats['completed_documents'], 2)
        self.assertEqual(stats['total_products'], 5)
        self.assertEqual(stats['total_users'], 3)
        self.assertEqual(stats['total_errors'], 2)
        self.assertEqual(stats['pipeline_running'], 2)
        
        # Holatlar tekshirish
        self.assertGreaterEqual(stats['pending_documents'], 0)
        self.assertGreaterEqual(stats['failed_documents'], 0)
        self.assertGreaterEqual(stats['telegram_sent'], 0)
        self.assertGreaterEqual(stats['telegram_failed'], 0)
    
    def test_prepare_chart_data(self):
        """Chart ma'lumotlarini tayyorlash testi"""
        chart_data = prepare_chart_data()
        
        # Kunlik ma'lumotlar tekshirish
        self.assertIn('daily_labels', chart_data)
        self.assertIn('daily_data', chart_data)
        self.assertEqual(len(chart_data['daily_labels']), 7)
        self.assertEqual(len(chart_data['daily_data']), 7)
        
        # Holat taqsimoti tekshirish
        self.assertIn('completed_count', chart_data)
        self.assertIn('processing_count', chart_data)
        self.assertIn('failed_count', chart_data)
        self.assertIn('pending_count', chart_data)
        
        # Foizlar tekshirish
        self.assertIn('download_percent', chart_data)
        self.assertIn('parse_percent', chart_data)
        self.assertIn('index_percent', chart_data)
        self.assertIn('telegram_percent', chart_data)
        self.assertIn('completed_percent', chart_data)
    
    def test_get_recent_activities(self):
        """So'nggi faoliyatlarni olish testi"""
        activities = get_recent_activities()
        
        # Faoliyatlar ro'yxati tekshirish
        self.assertIsInstance(activities, list)
        self.assertLessEqual(len(activities), 10)
        
        # Har bir faoliyat struktura tekshirish
        for activity in activities:
            self.assertIn('title', activity)
            self.assertIn('time', activity)
            self.assertIn('icon', activity)
            self.assertIn('color', activity)
            self.assertIn('status', activity)


class CacheTests(TestCase):
    """Redis cache funksiyalari uchun testlar"""
    
    def setUp(self):
        """Test uchun cache tozalash"""
        cache.clear()
    
    def test_get_cached_statistics(self):
        """Cache'dan statistikalarni olish testi"""
        # Birinchi chaqiruv - cache miss
        stats1 = get_cached_statistics()
        self.assertIsInstance(stats1, dict)
        
        # Ikkinchi chaqiruv - cache hit
        stats2 = get_cached_statistics()
        self.assertEqual(stats1, stats2)
        
        # Cache key tekshirish
        cache_key = 'dashboard_main_statistics'
        self.assertIsNotNone(cache.get(cache_key))
    
    def test_get_cached_chart_data(self):
        """Cache'dan chart ma'lumotlarini olish testi"""
        # Birinchi chaqiruv - cache miss
        chart1 = get_cached_chart_data()
        self.assertIsInstance(chart1, dict)
        
        # Ikkinchi chaqiruv - cache hit
        chart2 = get_cached_chart_data()
        self.assertEqual(chart1, chart2)
    
    def test_get_cached_recent_activities(self):
        """Cache'dan so'nggi faoliyatlarni olish testi"""
        # Birinchi chaqiruv - cache miss
        activities1 = get_cached_recent_activities()
        self.assertIsInstance(activities1, list)
        
        # Ikkinchi chaqiruv - cache hit
        activities2 = get_cached_recent_activities()
        self.assertEqual(activities1, activities2)
    
    def test_invalidate_dashboard_cache(self):
        """Dashboard cache'ni tozalash testi"""
        # Cache'ga ma'lumot qo'shish
        get_cached_statistics()
        get_cached_chart_data()
        get_cached_recent_activities()
        
        # Cache'ni tozalash
        invalidate_dashboard_cache()
        
        # Cache bo'sh ekanligini tekshirish
        cache_keys = [
            'dashboard_main_statistics',
            'dashboard_chart_data',
            'dashboard_recent_activities'
        ]
        
        for key in cache_keys:
            self.assertIsNone(cache.get(key))
    
    def test_get_cached_system_health(self):
        """Cache'dan system health ma'lumotlarini olish testi"""
        with patch('psutil.disk_usage') as mock_disk, \
             patch('psutil.virtual_memory') as mock_memory, \
             patch('psutil.cpu_percent') as mock_cpu:
            
            # Mock ma'lumotlar
            mock_disk.return_value = MagicMock(used=100, total=1000)
            mock_memory.return_value = MagicMock(percent=50.0)
            mock_cpu.return_value = 25.0
            
            # Birinchi chaqiruv - cache miss
            health1 = get_cached_system_health()
            self.assertIsInstance(health1, dict)
            
            # Ikkinchi chaqiruv - cache hit
            health2 = get_cached_system_health()
            self.assertEqual(health1, health2)


class LoggingTests(TestCase):
    """Logging utility funksiyalari uchun testlar"""
    
    def test_get_logger(self):
        """Logger obyektini olish testi"""
        logger = get_logger('test.module')
        self.assertIsInstance(logger, logging.Logger)
        self.assertEqual(logger.name, 'test.module')
    
    def test_log_function_call_decorator(self):
        """Funksiya chaqiruvlarini log qilish decorator testi"""
        logger = get_logger('test.module')
        
        @log_function_call(logger)
        def test_function(x, y=10):
            return x + y
        
        # Funksiyani chaqirish
        result = test_function(5, y=15)
        self.assertEqual(result, 20)
    
    def test_logger_mixin(self):
        """LoggerMixin class testi"""
        class TestClass(LoggerMixin):
            def test_method(self):
                return self.logger.name
        
        obj = TestClass()
        logger_name = obj.test_method()
        self.assertIn('TestClass', logger_name)


class SystemHealthTests(TestCase):
    """System health funksiyalari uchun testlar"""
    
    def test_system_health_with_psutil(self):
        """psutil bilan system health testi"""
        with patch('psutil.disk_usage') as mock_disk, \
             patch('psutil.virtual_memory') as mock_memory, \
             patch('psutil.cpu_percent') as mock_cpu:
            
            # Mock ma'lumotlar
            mock_disk.return_value = MagicMock(used=500, total=1000)
            mock_memory.return_value = MagicMock(percent=75.0)
            mock_cpu.return_value = 30.0
            
            from apps.core_api.admin_panel.admin_dashboard import get_system_health
            health = get_system_health()
            
            # Natijalar tekshirish
            self.assertEqual(health['disk_usage'], '50.0%')
            self.assertEqual(health['memory_usage'], '75.0%')
            self.assertEqual(health['cpu_usage'], '30.0%')
            self.assertEqual(health['database_status'], 'OK')
    
    def test_system_health_without_psutil(self):
        """psutil bo'lmasa system health testi"""
        with patch.dict('sys.modules', {'psutil': None}):
            from apps.core_api.admin_panel.admin_dashboard import get_system_health
            health = get_system_health()
            
            # N/A qiymatlar tekshirish
            self.assertEqual(health['disk_usage'], 'N/A')
            self.assertEqual(health['memory_usage'], 'N/A')
            self.assertEqual(health['cpu_usage'], 'N/A')
            self.assertEqual(health['database_status'], 'OK')


class PerformanceTests(TransactionTestCase):
    """Performance testlari"""
    
    def test_statistics_calculation_performance(self):
        """Statistika hisoblash performance testi"""
        import time
        
        # Ko'p ma'lumot yaratish
        documents = []
        for i in range(100):
            doc = Document.objects.create(
                parse_file_url=f'https://example.com/doc{i}.pdf',
                download_status='completed' if i % 2 == 0 else 'pending',
                parse_status='completed' if i % 3 == 0 else 'pending',
                index_status='completed' if i % 4 == 0 else 'pending',
                telegram_status='completed' if i % 5 == 0 else 'pending',
                completed=i % 10 == 0
            )
            documents.append(doc)
        
        # Performance test
        start_time = time.time()
        stats = calculate_main_statistics()
        end_time = time.time()
        
        # Vaqt tekshirish (1 soniyadan kam bo'lishi kerak)
        execution_time = end_time - start_time
        self.assertLess(execution_time, 1.0)
        
        # Natija tekshirish
        self.assertEqual(stats['total_documents'], 100)
    
    def test_cache_performance(self):
        """Cache performance testi"""
        import time
        
        # Cache miss performance
        start_time = time.time()
        stats1 = get_cached_statistics()
        cache_miss_time = time.time() - start_time
        
        # Cache hit performance
        start_time = time.time()
        stats2 = get_cached_statistics()
        cache_hit_time = time.time() - start_time
        
        # Cache hit tezroq bo'lishi kerak
        self.assertLess(cache_hit_time, cache_miss_time)
        self.assertEqual(stats1, stats2)


class IntegrationTests(TestCase):
    """Integration testlari"""
    
    def test_dashboard_integration(self):
        """Dashboard integration testi"""
        from apps.core_api.admin_panel.admin_dashboard import admin_dashboard
        from django.test import RequestFactory
        
        # Test request yaratish
        factory = RequestFactory()
        request = factory.get('/admin/')
        
        # Mock user
        user = User.objects.create_user(username='testuser', password='testpass')
        request.user = user
        
        # Dashboard view testi
        with patch('apps.core_api.admin_panel.admin_dashboard.staff_member_required') as mock_decorator:
            mock_decorator.return_value = lambda func: func
            
            response = admin_dashboard(request)
            self.assertEqual(response.status_code, 200)
    
    def test_cache_invalidation_integration(self):
        """Cache invalidation integration testi"""
        # Cache'ga ma'lumot qo'shish
        stats1 = get_cached_statistics()
        chart1 = get_cached_chart_data()
        activities1 = get_cached_recent_activities()
        
        # Cache'ni tozalash
        invalidate_dashboard_cache()
        
        # Yangi ma'lumotlar olish
        stats2 = get_cached_statistics()
        chart2 = get_cached_chart_data()
        activities2 = get_cached_recent_activities()
        
        # Ma'lumotlar yangilanganligini tekshirish
        self.assertIsNotNone(stats2)
        self.assertIsNotNone(chart2)
        self.assertIsNotNone(activities2)


if __name__ == '__main__':
    import unittest
    unittest.main()
