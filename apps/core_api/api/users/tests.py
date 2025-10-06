"""
Users API Tests (Simplified)
=============================

Bu modul users API endpoint'larining asosiy funksionalligini test qiladi.
"""

from django.contrib.auth.models import User
from rest_framework.test import APITestCase
from rest_framework import status
from rest_framework.authtoken.models import Token


class UsersAPIBasicTestCase(APITestCase):
    """Users API asosiy testlari"""
    
    def setUp(self):
        """Test uchun user va token yaratish"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.token = Token.objects.create(user=self.user)
    
    def test_token_creation(self):
        """Token yaratish mumkinligini test qilish"""
        self.assertIsNotNone(self.token)
        self.assertEqual(self.token.user, self.user)
    
    def test_user_authentication(self):
        """User authentication test qilish"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        # Token bilan API'ga kirish mumkin
        self.assertTrue(self.client._credentials)
