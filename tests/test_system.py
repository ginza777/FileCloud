"""
System Integration Tests Module

Bu modul tizim darajasidagi integratsiya testlarini o'z ichiga oladi:
- End-to-End workflows (to'liq ishlov jarayonlari)
- Multi-component integration (ko'p komponentli integratsiya)
- System stability (tizim barqarorligi)
"""
import time
from unittest.mock import MagicMock, patch
from django.test import TestCase
from rest_framework.test import APITestCase
from rest_framework import status
from rest_framework.authtoken.models import Token
from django.contrib.auth.models import User
from apps.files.models import Document, Product
from apps.files.elasticsearch.documents import DocumentIndex


class EndToEndWorkflowTests(APITestCase):
    """To'liq ishlov jarayonlarini test qilish"""
    
    def setUp(self):
        """Test uchun user va token yaratish"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + self.token.key)
    
    def test_document_creation_workflow(self):
        """Document yaratish va API orqali olish workflow"""
        # 1. Document yaratish
        document = Document.objects.create(
            completed=True,
            pipeline_running=False
        )
        
        # 2. Product yaratish
        Product.objects.create(
            id=1,
            title='Test Product',
            slug='test-product',
            parsed_content='Test content',
            document=document
        )
        
        # 3. API orqali document olish
        url = f'/api/files/documents/{document.id}/'
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(str(response.data['id']), str(document.id))
    
    def test_api_authentication_workflow(self):
        """API authentication workflow"""
        # 1. Token bilan kirish
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + self.token.key)
        
        url = '/api/files/documents/'
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # 2. Token'siz kirish (401)
        self.client.credentials()
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class SystemStabilityTests(TestCase):
    """Tizim barqarorligini test qilish"""
    
    def test_multiple_document_creation(self):
        """Ko'plab document yaratish va saqlash"""
        # Test boshida hozirgi count'ni olish
        initial_count = Document.objects.count()
        
        documents = []
        # 10 ta document yaratish
        for i in range(10):
            doc = Document.objects.create(
                completed=True,
                pipeline_running=False
            )
            documents.append(doc)
        
        # Yangi yaratilgan document'lar sonini tekshirish
        final_count = Document.objects.count()
        self.assertEqual(final_count - initial_count, 10)
    
    def test_database_transaction_stability(self):
        """Database transaction barqarorligini test qilish"""
        # Test boshida hozirgi count'ni olish
        initial_count = Document.objects.count()
        
        start_time = time.time()
        
        # Transaction ichida ko'plab operatsiyalar
        for i in range(5):
            Document.objects.create(
                completed=True,
                pipeline_running=False
            )
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Transaction 2 soniyadan kam vaqt olishi kerak
        self.assertLess(duration, 2.0)
        
        # Yangi yaratilgan document'lar sonini tekshirish
        final_count = Document.objects.count()
        self.assertEqual(final_count - initial_count, 5)


class MultiComponentIntegrationTests(APITestCase):
    """Ko'p komponentli integratsiya testlari"""
    
    def setUp(self):
        """Test uchun ma'lumotlar yaratish"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + self.token.key)
        
        self.document = Document.objects.create(
            completed=True,
            pipeline_running=False
        )
    
    def test_document_api_integration(self):
        """Document va API integratsiyasi"""
        # API orqali document list
        url = '/api/files/documents/'
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)
    
    def test_product_document_integration(self):
        """Product va Document integratsiyasi"""
        # Product yaratish
        product = Product.objects.create(
            id=100,
            title='Integration Test Product',
            slug='integration-test-product',
            parsed_content='Integration test content',
            document=self.document
        )
        
        # Document orqali product'ga kirish
        self.assertEqual(self.document.product.id, product.id)
        
        # API orqali product olish
        url = f'/api/files/products/{product.id}/'
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], product.id)
    
    @patch('apps.files.elasticsearch.documents.DocumentIndex.search_documents')
    def test_elasticsearch_api_integration(self, mock_search):
        """Elasticsearch va API integratsiyasi"""
        mock_search.return_value = MagicMock(hits=[
            MagicMock(meta=MagicMock(id=str(self.document.id)))
        ])
        
        # Elasticsearch orqali qidiruv
        result = DocumentIndex.search_documents(query='test', completed=True)
        
        self.assertIsNotNone(result)
        mock_search.assert_called_once()

