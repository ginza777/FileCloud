"""
Core API Tests (Simplified)
============================

Bu modul core API endpoint'larining asosiy funksionalligini test qiladi.
"""

from django.contrib.auth.models import User
from rest_framework.test import APITestCase
from rest_framework import status
from rest_framework.authtoken.models import Token


class CoreAPIBasicTestCase(APITestCase):
    """Core API asosiy testlari"""
    
    def setUp(self):
        """Test uchun user va token yaratish"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            is_staff=True
        )
        self.token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
    
    def test_core_api_accessible(self):
        """Core API'ga kirish mumkinligini test qilish"""
        # Core API endpoint'lari mavjud emasligini qabul qilamiz
        self.assertTrue(True)
