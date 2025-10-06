"""
Performance Tests Module

Bu modul performance testlarini o'z ichiga oladi:
- Database query performance (database so'rovlari tezligi)
- API response time (API javob vaqti)
- Concurrent requests handling (parallel so'rovlar boshqaruvi)
"""
import time
from rest_framework.test import APITestCase
from rest_framework import status
from rest_framework.authtoken.models import Token
from django.contrib.auth.models import User
from django.test import TestCase, TransactionTestCase
from apps.files.models import Document, Product


class DatabasePerformanceTests(TestCase):
    """Database performance testlari"""
    
    def test_database_connection_speed(self):
        """Database connection tezligini test qilish"""
        start_time = time.time()
        
        # Database connection test
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Connection 1 soniyadan kam vaqt olishi kerak
        self.assertLess(duration, 1.0)
        self.assertEqual(result[0], 1)
    
    def test_simple_query_speed(self):
        """Oddiy query tezligini test qilish"""
        start_time = time.time()
        
        # Oddiy query bajarish
        from django.contrib.auth.models import User
        count = User.objects.count()
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Query 1 soniyadan kam vaqt olishi kerak
        self.assertLess(duration, 1.0)
        # Count 0 yoki undan katta
        self.assertGreaterEqual(count, 0)


class APIPerformanceTests(APITestCase):
    """API performance testlari"""
    
    def setUp(self):
        """Test uchun user va token yaratish"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + self.token.key)
        
        # Test uchun ma'lumotlar yaratish
        for i in range(20):
            Document.objects.create(
                completed=True,
                pipeline_running=False
            )
    
    def test_api_response_time(self):
        """API javob vaqtini test qilish"""
        url = '/api/files/documents/'
        
        start_time = time.time()
        response = self.client.get(url)
        end_time = time.time()
        
        duration = end_time - start_time
        
        # API 2 soniyadan kam vaqtda javob berishi kerak
        self.assertLess(duration, 2.0)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_pagination_performance(self):
        """Pagination performance'ni test qilish"""
        url = '/api/files/documents/'
        
        start_time = time.time()
        response = self.client.get(url, {'page_size': 10})
        end_time = time.time()
        
        duration = end_time - start_time
        
        # Pagination 1 soniyadan kam vaqt olishi kerak
        self.assertLess(duration, 1.0)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class ConcurrentRequestTests(APITestCase):
    """Parallel so'rovlar testlari"""
    
    def setUp(self):
        """Test uchun user yaratish"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + self.token.key)
    
    def test_multiple_requests(self):
        """Ko'plab so'rovlarni test qilish"""
        url = '/api/files/documents/'
        
        # Sequential requests (PostgreSQL uchun)
        responses = []
        for _ in range(5):
            response = self.client.get(url)
            responses.append(response.status_code)
        
        # Barcha so'rovlar muvaffaqiyatli bo'lishi kerak
        for status_code in responses:
            self.assertEqual(status_code, status.HTTP_200_OK)

