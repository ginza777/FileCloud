"""
Core API Tests
"""
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from apps.core_api.models import Feedback

__all__ = [
    'FeedbackAPITestCase'
]


class FeedbackAPITestCase(APITestCase):
    """Test cases for Feedback API endpoints"""
    
    def test_feedback_create(self):
        """Test feedback create endpoint"""
        url = reverse('feedback-create')
        data = {
            'message': 'Test feedback message',
            'email': 'test@example.com'
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
