"""
Files API Tests (Simplified)
=============================

Bu modul files API endpoint'larining asosiy funksionalligini test qiladi.
"""

from django.contrib.auth.models import User
from rest_framework.test import APITestCase
from rest_framework import status
from rest_framework.authtoken.models import Token
from apps.files.models import Document, Product


class FilesAPIBasicTestCase(APITestCase):
    """Files API asosiy testlari"""
    
    def setUp(self):
        """Test uchun user va ma'lumotlar yaratish"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            is_staff=True
        )
        self.token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        
        self.document = Document.objects.create(
            completed=True,
            pipeline_running=False
        )
        self.product = Product.objects.create(
            id=1,
            title='Test Product',
            slug='test-product',
            parsed_content='Test content',
            document=self.document
        )
    
    def test_document_list_endpoint(self):
        """Document list endpoint'ni test qilish"""
        url = '/api/files/documents/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_document_detail_endpoint(self):
        """Document detail endpoint'ni test qilish"""
        url = f'/api/files/documents/{self.document.id}/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_product_list_endpoint(self):
        """Product list endpoint'ni test qilish"""
        url = '/api/files/products/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_product_detail_endpoint(self):
        """Product detail endpoint'ni test qilish"""
        url = f'/api/files/products/{self.product.id}/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_authentication_required(self):
        """Authentication talab qilinishi"""
        self.client.credentials()  # Token'siz
        url = '/api/files/documents/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_document_stats_endpoint(self):
        """Document stats endpoint'ni test qilish"""
        url = '/api/files/documents/stats/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
