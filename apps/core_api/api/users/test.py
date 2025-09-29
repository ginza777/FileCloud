"""
User API Tests
"""
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model

User = get_user_model()

__all__ = [
    'UserAPITestCase',
    'UserStatsTestCase'
]


class UserAPITestCase(APITestCase):
    """Test cases for User API endpoints"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            first_name='Test',
            last_name='User'
        )
    
    def test_user_list(self):
        """Test user list endpoint"""
        url = reverse('user-list-create')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_user_detail(self):
        """Test user detail endpoint"""
        url = reverse('user-detail', kwargs={'id': self.user.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class UserStatsTestCase(APITestCase):
    """Test cases for User Stats endpoint"""
    
    def test_user_stats(self):
        """Test user stats endpoint"""
        url = reverse('user-stats')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
