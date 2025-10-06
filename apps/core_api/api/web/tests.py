"""
Web API Tests for FileFinder
"""
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User
from rest_framework.test import APITestCase
from rest_framework import status
from rest_framework.authtoken.models import Token
from apps.files.models import Document, Product, DocumentImage

__all__ = [
    'WebAPITestCase',
    'SearchAPITestCase',
    'DocumentAPITestCase',
    'ProductAPITestCase'
]


class WebAPITestCase(APITestCase):
    """Test cases for Web API endpoints"""
    
    def test_login_view(self):
        """Test login page view"""
        url = reverse('login')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_index_view(self):
        """Test index page view"""
        url = reverse('index')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class SearchAPITestCase(APITestCase):
    """Test cases for Search API endpoints"""
    
    def setUp(self):
        """Setup authentication for tests"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + self.token.key)
    
    def test_search_documents_without_query(self):
        """Test search documents without query parameter"""
        url = reverse('search_documents')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_search_documents_with_query(self):
        """Test search documents with query parameter"""
        url = reverse('search_documents')
        response = self.client.get(url, {'q': 'test'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_search_documents_deep_search(self):
        """Test deep search functionality"""
        url = reverse('search_documents')
        response = self.client.get(url, {'q': 'test', 'deep': 'true'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_search_documents_pagination(self):
        """Test search documents pagination"""
        url = reverse('search_documents')
        response = self.client.get(url, {'q': 'test', 'page': 2, 'page_size': 5})
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class DocumentAPITestCase(APITestCase):
    """Test cases for Document API endpoints"""
    
    def setUp(self):
        """Setup authentication for tests"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + self.token.key)
    
    def test_recent_documents(self):
        """Test recent documents endpoint"""
        url = reverse('recent_documents')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_document_images_not_found(self):
        """Test document images endpoint with non-existent document"""
        url = reverse('document_images', kwargs={'document_id': '00000000-0000-0000-0000-000000000000'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class ProductAPITestCase(APITestCase):
    """Test cases for Product API endpoints"""
    
    def setUp(self):
        """Setup authentication for tests"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + self.token.key)
    
    def test_top_downloads(self):
        """Test top downloads endpoint"""
        url = reverse('top_downloads')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_top_downloads_pagination(self):
        """Test top downloads pagination"""
        url = reverse('top_downloads')
        response = self.client.get(url, {'page': 2, 'page_size': 5})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_increment_view_count_not_found(self):
        """Test increment view count with non-existent product"""
        url = reverse('increment_view_count', kwargs={'product_id': 99999})
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    def test_increment_download_count_not_found(self):
        """Test increment download count with non-existent product"""
        url = reverse('increment_download_count', kwargs={'product_id': 99999})
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
