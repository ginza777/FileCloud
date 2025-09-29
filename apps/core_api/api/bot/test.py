"""
Bot API Tests
"""
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from apps.bot.models import SubscribeChannel, Location, SearchQuery, Broadcast, BroadcastRecipient

__all__ = [
    'SubscribeChannelAPITestCase',
    'LocationAPITestCase',
    'SearchQueryAPITestCase',
    'BroadcastAPITestCase'
]


class SubscribeChannelAPITestCase(APITestCase):
    """Test cases for SubscribeChannel API endpoints"""
    
    def test_channel_list(self):
        """Test channel list endpoint"""
        url = reverse('channel-list-create')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class LocationAPITestCase(APITestCase):
    """Test cases for Location API endpoints"""
    
    def test_location_list(self):
        """Test location list endpoint"""
        url = reverse('location-list-create')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_location_stats(self):
        """Test location stats endpoint"""
        url = reverse('location-stats')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class SearchQueryAPITestCase(APITestCase):
    """Test cases for SearchQuery API endpoints"""
    
    def test_search_list(self):
        """Test search list endpoint"""
        url = reverse('search-list-create')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_search_stats(self):
        """Test search stats endpoint"""
        url = reverse('search-stats')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class BroadcastAPITestCase(APITestCase):
    """Test cases for Broadcast API endpoints"""
    
    def test_broadcast_list(self):
        """Test broadcast list endpoint"""
        url = reverse('broadcast-list-create')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_broadcast_stats(self):
        """Test broadcast stats endpoint"""
        url = reverse('broadcast-stats')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_recipient_list(self):
        """Test recipient list endpoint"""
        url = reverse('recipient-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
