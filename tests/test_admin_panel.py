"""
Admin Panel Tests
=================

Bu modul admin panel funksiyalari uchun testlarni o'z ichiga oladi.
Advanced admin, dashboard API va boshqa admin funksiyalar uchun testlar.
"""

import os
import sys
import django
from django.test import TestCase, RequestFactory
from django.contrib.auth.models import User
from django.contrib.admin.sites import AdminSite
from django.contrib.admin import AdminSite as DjangoAdminSite
from django.core.cache import cache
from django.utils import timezone
from unittest.mock import patch, MagicMock
import json

# Add the project directory to Python path
sys.path.append('/app')

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from apps.files.models import Document, Product, DocumentError
from apps.bot.models import User as BotUser, Broadcast, BroadcastRecipient
from apps.core_api.models import Feedback
from apps.core_api.admin_panel.advanced_admin import (
    AdvancedDocumentAdmin, AdvancedProductAdmin, AdvancedUserAdmin,
    StatusFilter, DateRangeFilter
)
from apps.core_api.admin_panel.dashboard_api import (
    dashboard_stats_api, dashboard_activities_api, dashboard_health_api,
    dashboard_charts_api
)


class AdvancedAdminTests(TestCase):
    """Advanced admin funksiyalari uchun testlar"""
    
    def setUp(self):
        """Test uchun ma'lumotlar yaratish"""
        # Test hujjatlari yaratish
        self.documents = []
        for i in range(5):
            doc = Document.objects.create(
                parse_file_url=f'https://example.com/doc{i}.pdf',
                download_status='completed' if i < 3 else 'pending',
                parse_status='completed' if i < 2 else 'pending',
                index_status='completed' if i < 1 else 'pending',
                telegram_status='completed' if i < 1 else 'pending',
                completed=i < 1,
                pipeline_running=i >= 3
            )
            self.documents.append(doc)
        
        # Test mahsulotlari yaratish
        for i in range(3):
            Product.objects.create(
                document=self.documents[i],
                title=f'Test Product {i}',
                parsed_content=f'Content {i}' if i < 2 else None
            )
        
        # Test foydalanuvchilari yaratish
        for i in range(3):
            BotUser.objects.create(
                telegram_id=1000000 + i,
                username=f'testuser{i}',
                first_name=f'Test{i}',
                last_name='User',
                is_admin=i < 2
            )
        
        # Test feedback yaratish
        for i in range(2):
            Feedback.objects.create(
                full_name=f'Test User {i}',
                contact=f'test{i}@example.com',
                message=f'Test message {i}'
            )
    
    def test_advanced_document_admin(self):
        """Advanced Document Admin testi"""
        admin = AdvancedDocumentAdmin(Document, AdminSite())
        
        # Queryset testi
        queryset = admin.get_queryset(None)
        self.assertIsNotNone(queryset)
        
        # Status badge testi
        doc = self.documents[0]  # completed=True
        badge = admin.status_badge(doc)
        self.assertIn('✅ Tugatilgan', badge)
        
        # Progress bar testi
        progress = admin.progress_bar(doc)
        self.assertIn('4/4', progress)
    
    def test_advanced_product_admin(self):
        """Advanced Product Admin testi"""
        admin = AdvancedProductAdmin(Product, AdminSite())
        
        # Queryset testi
        queryset = admin.get_queryset(None)
        self.assertIsNotNone(queryset)
        
        # Product status testi
        product = Product.objects.first()
        status = admin.product_status(product)
        self.assertIsInstance(status, str)
    
    def test_advanced_user_admin(self):
        """Advanced User Admin testi"""
        admin = AdvancedUserAdmin(BotUser, AdminSite())
        
        # Queryset testi
        queryset = admin.get_queryset(None)
        self.assertIsNotNone(queryset)
        
        # Active badge testi
        user = BotUser.objects.first()
        badge = admin.is_active_badge(user)
        self.assertIn('✅ Active', badge)
    
    def test_status_filter(self):
        """Status filter testi"""
        filter_obj = StatusFilter(None, {}, Document, None)
        
        # Lookups testi
        lookups = filter_obj.lookups(None, None)
        self.assertIsInstance(lookups, tuple)
        self.assertGreater(len(lookups), 0)
        
        # Completed filter testi
        queryset = Document.objects.all()
        filtered = filter_obj.queryset(None, queryset)
        filter_obj.value = lambda: 'completed'
        result = filter_obj.queryset(None, queryset)
        self.assertIsNotNone(result)
    
    def test_date_range_filter(self):
        """Date range filter testi"""
        filter_obj = DateRangeFilter(None, {}, Document, None)
        
        # Lookups testi
        lookups = filter_obj.lookups(None, None)
        self.assertIsInstance(lookups, tuple)
        self.assertGreater(len(lookups), 0)


class DashboardAPITests(TestCase):
    """Dashboard API funksiyalari uchun testlar"""
    
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
                telegram_id=1000000 + i,
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
        
        # Test user yaratish
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.user.is_staff = True
        self.user.save()
        
        # Request factory
        self.factory = RequestFactory()
    
    def test_dashboard_stats_api(self):
        """Dashboard stats API testi"""
        request = self.factory.get('/admin/api/stats/')
        request.user = self.user
        
        response = dashboard_stats_api(request)
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertIn('stats', data)
        
        stats = data['stats']
        self.assertIn('total_documents', stats)
        self.assertIn('completed_documents', stats)
        self.assertIn('total_products', stats)
        self.assertIn('total_users', stats)
    
    def test_dashboard_activities_api(self):
        """Dashboard activities API testi"""
        request = self.factory.get('/admin/api/activities/')
        request.user = self.user
        
        response = dashboard_activities_api(request)
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertIn('activities', data)
        
        activities = data['activities']
        self.assertIsInstance(activities, list)
    
    def test_dashboard_health_api(self):
        """Dashboard health API testi"""
        request = self.factory.get('/admin/api/health/')
        request.user = self.user
        
        with patch('psutil.disk_usage') as mock_disk, \
             patch('psutil.virtual_memory') as mock_memory, \
             patch('psutil.cpu_percent') as mock_cpu:
            
            # Mock ma'lumotlar
            mock_disk.return_value = MagicMock(used=100, total=1000)
            mock_memory.return_value = MagicMock(percent=50.0)
            mock_cpu.return_value = 25.0
            
            response = dashboard_health_api(request)
            self.assertEqual(response.status_code, 200)
            
            data = json.loads(response.content)
            self.assertTrue(data['success'])
            self.assertIn('health', data)
            
            health = data['health']
            self.assertIn('database_status', health)
            self.assertIn('disk_usage', health)
            self.assertIn('memory_usage', health)
            self.assertIn('cpu_usage', health)
    
    def test_dashboard_charts_api(self):
        """Dashboard charts API testi"""
        request = self.factory.get('/admin/api/charts/')
        request.user = self.user
        
        response = dashboard_charts_api(request)
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertIn('charts', data)
        
        charts = data['charts']
        self.assertIsInstance(charts, dict)
    
    def test_dashboard_api_unauthorized(self):
        """Dashboard API unauthorized testi"""
        # Non-staff user
        user = User.objects.create_user(username='regularuser', password='testpass')
        request = self.factory.get('/admin/api/stats/')
        request.user = user
        
        response = dashboard_stats_api(request)
        self.assertEqual(response.status_code, 302)  # Redirect to login
    
    def test_dashboard_api_error_handling(self):
        """Dashboard API error handling testi"""
        request = self.factory.get('/admin/api/stats/')
        request.user = self.user
        
        # Database error simulation
        with patch('apps.files.models.Document.objects.count') as mock_count:
            mock_count.side_effect = Exception('Database error')
            
            response = dashboard_stats_api(request)
            self.assertEqual(response.status_code, 500)
            
            data = json.loads(response.content)
            self.assertFalse(data['success'])
            self.assertIn('error', data)


class AdminPanelIntegrationTests(TestCase):
    """Admin panel integration testlari"""
    
    def setUp(self):
        """Test uchun ma'lumotlar yaratish"""
        # Test hujjatlari yaratish
        self.documents = []
        for i in range(5):
            doc = Document.objects.create(
                parse_file_url=f'https://example.com/doc{i}.pdf',
                download_status='completed' if i < 3 else 'pending',
                parse_status='completed' if i < 2 else 'pending',
                index_status='completed' if i < 1 else 'pending',
                telegram_status='completed' if i < 1 else 'pending',
                completed=i < 1
            )
            self.documents.append(doc)
        
        # Test mahsulotlari yaratish
        for i in range(3):
            Product.objects.create(
                document=self.documents[i],
                title=f'Test Product {i}',
                parsed_content=f'Content {i}' if i < 2 else None
            )
        
        # Test foydalanuvchilari yaratish
        for i in range(3):
            BotUser.objects.create(
                telegram_id=1000000 + i,
                username=f'testuser{i}',
                first_name=f'Test{i}',
                last_name='User',
                is_admin=i < 2
            )
        
        # Test user yaratish
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.user.is_staff = True
        self.user.save()
        
        # Request factory
        self.factory = RequestFactory()
    
    def test_admin_panel_full_workflow(self):
        """Admin panel to'liq workflow testi"""
        # 1. Dashboard stats API
        request = self.factory.get('/admin/api/stats/')
        request.user = self.user
        
        response = dashboard_stats_api(request)
        self.assertEqual(response.status_code, 200)
        
        # 2. Dashboard activities API
        request = self.factory.get('/admin/api/activities/')
        request.user = self.user
        
        response = dashboard_activities_api(request)
        self.assertEqual(response.status_code, 200)
        
        # 3. Dashboard health API
        request = self.factory.get('/admin/api/health/')
        request.user = self.user
        
        with patch('psutil.disk_usage') as mock_disk, \
             patch('psutil.virtual_memory') as mock_memory, \
             patch('psutil.cpu_percent') as mock_cpu:
            
            mock_disk.return_value = MagicMock(used=100, total=1000)
            mock_memory.return_value = MagicMock(percent=50.0)
            mock_cpu.return_value = 25.0
            
            response = dashboard_health_api(request)
            self.assertEqual(response.status_code, 200)
        
        # 4. Dashboard charts API
        request = self.factory.get('/admin/api/charts/')
        request.user = self.user
        
        response = dashboard_charts_api(request)
        self.assertEqual(response.status_code, 200)
    
    def test_admin_panel_performance(self):
        """Admin panel performance testi"""
        import time
        
        request = self.factory.get('/admin/api/stats/')
        request.user = self.user
        
        # Performance test
        start_time = time.time()
        response = dashboard_stats_api(request)
        end_time = time.time()
        
        # Vaqt tekshirish (1 soniyadan kam bo'lishi kerak)
        execution_time = end_time - start_time
        self.assertLess(execution_time, 1.0)
        
        # Response tekshirish
        self.assertEqual(response.status_code, 200)
    
    def test_admin_panel_cache_integration(self):
        """Admin panel cache integration testi"""
        # Cache'ni tozalash
        cache.clear()
        
        request = self.factory.get('/admin/api/stats/')
        request.user = self.user
        
        # Birinchi chaqiruv - cache miss
        response1 = dashboard_stats_api(request)
        self.assertEqual(response1.status_code, 200)
        
        # Ikkinchi chaqiruv - cache hit
        response2 = dashboard_stats_api(request)
        self.assertEqual(response2.status_code, 200)
        
        # Response'lar bir xil bo'lishi kerak
        data1 = json.loads(response1.content)
        data2 = json.loads(response2.content)
        self.assertEqual(data1, data2)


class AdminPanelSecurityTests(TestCase):
    """Admin panel security testlari"""
    
    def setUp(self):
        """Test uchun ma'lumotlar yaratish"""
        # Test user yaratish
        self.staff_user = User.objects.create_user(username='staff', password='testpass')
        self.staff_user.is_staff = True
        self.staff_user.save()
        
        self.regular_user = User.objects.create_user(username='regular', password='testpass')
        
        # Request factory
        self.factory = RequestFactory()
    
    def test_staff_required_decorator(self):
        """Staff required decorator testi"""
        # Staff user testi
        request = self.factory.get('/admin/api/stats/')
        request.user = self.staff_user
        
        response = dashboard_stats_api(request)
        self.assertEqual(response.status_code, 200)
        
        # Regular user testi
        request = self.factory.get('/admin/api/stats/')
        request.user = self.regular_user
        
        response = dashboard_stats_api(request)
        self.assertEqual(response.status_code, 302)  # Redirect to login
    
    def test_http_method_restriction(self):
        """HTTP method restriction testi"""
        request = self.factory.post('/admin/api/stats/')
        request.user = self.staff_user
        
        response = dashboard_stats_api(request)
        self.assertEqual(response.status_code, 405)  # Method not allowed
    
    def test_csrf_protection(self):
        """CSRF protection testi"""
        # CSRF token bo'lmasa
        request = self.factory.post('/admin/api/stats/')
        request.user = self.staff_user
        
        response = dashboard_stats_api(request)
        self.assertEqual(response.status_code, 405)  # Method not allowed


if __name__ == '__main__':
    import unittest
    unittest.main()
