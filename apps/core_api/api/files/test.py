"""
Files API Tests
"""
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from apps.files.models import Document, Product, SiteToken, ParseProgress

__all__ = [
    'DocumentAPITestCase',
    'ProductAPITestCase',
    'SiteTokenAPITestCase',
    'ParseProgressAPITestCase'
]


class DocumentAPITestCase(APITestCase):
    """Test cases for Document API endpoints"""
    
    def test_document_list(self):
        """Test document list endpoint"""
        url = reverse('document-list-create')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_document_stats(self):
        """Test document stats endpoint"""
        url = reverse('document-stats')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class ProductAPITestCase(APITestCase):
    """Test cases for Product API endpoints"""
    
    def test_product_list(self):
        """Test product list endpoint"""
        url = reverse('product-list-create')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class SiteTokenAPITestCase(APITestCase):
    """Test cases for SiteToken API endpoints"""
    
    def test_token_list(self):
        """Test token list endpoint"""
        url = reverse('token-list-create')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class ParseProgressAPITestCase(APITestCase):
    """Test cases for ParseProgress API endpoints"""
    
    def test_parse_progress_list(self):
        """Test parse progress list endpoint"""
        url = reverse('parse-progress-list-create')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
