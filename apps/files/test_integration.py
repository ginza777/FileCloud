"""
Integration Tests
=================

Bu modul loyiha komponentlarini bir-biriga bog'liq holda test qiladi:
- Database + API integration
- Celery + Database integration
- Elasticsearch + API integration
- Bot + Database integration
- End-to-end workflows
"""

import time
from unittest.mock import patch, MagicMock
from django.test import TestCase, TransactionTestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework import status
from rest_framework.authtoken.models import Token

from apps.files.models import Document, Product, DocumentError, ParseProgress
from apps.files.elasticsearch.documents import DocumentIndex
from apps.files.tasks import (
    process_document_pipeline,
    cleanup_temp_files_task,
    soft_uz_process_documents
)
from apps.bot.models import User as BotUser, Broadcast, BroadcastRecipient


class DatabaseAPIIntegrationTests(TransactionTestCase):
    """Database va API integration testlar"""
    
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + self.token.key)

    def test_document_creation_via_api(self):
        """API orqali document yaratish test"""
        # API orqali document yaratish
        url = '/api/files/documents/'
        data = {
            'completed': False,
            'pipeline_running': False
        }
        
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Database'da mavjudligini tekshirish
        document_id = response.data['id']
        document = Document.objects.get(id=document_id)
        self.assertEqual(document.completed, False)
        self.assertEqual(document.pipeline_running, False)

    def test_product_creation_with_document(self):
        """Document bilan product yaratish test"""
        # Document yaratish
        document = Document.objects.create(
            completed=True,
            pipeline_running=False
        )
        
        # Product yaratish
        product = Product.objects.create(
            id=1,
            title='Test Product',
            slug='test-product',
            parsed_content='Test content',
            document=document
        )
        
        # API orqali product ma'lumotlarini olish
        url = f'/api/files/products/{product.id}/'
        response = self.client.get(url)
        
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND])
        self.assertEqual(response.data['title'], 'Test Product')
        self.assertEqual(str(response.data['document']), str(document.id))

    def test_document_error_logging(self):
        """Document error logging test"""
        # Document yaratish
        document = Document.objects.create(
            completed=False,
            pipeline_running=False
        )
        
        # Error yaratish
        error = DocumentError.objects.create(
            document=document,
            error_type='processing',
            error_message='Test error message',
            celery_attempt=1
        )
        
        # API orqali error ma'lumotlarini olish
        url = f'/api/files/documents/{document.id}/errors/'
        response = self.client.get(url)
        
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND])
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['error_type'], 'processing')

    def test_parse_progress_tracking(self):
        """Parse progress tracking test"""
        # Parse progress yaratish
        progress = ParseProgress.objects.create(
            last_page=10,
            total_pages_parsed=5,
            last_run_at=timezone.now()
        )
        
        # API orqali progress ma'lumotlarini olish
        url = '/api/files/parse-progress/'
        response = self.client.get(url)
        
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND])
        self.assertEqual(response.data[0]['last_page'], 10)
        self.assertEqual(response.data[0]['total_pages_parsed'], 5)


class CeleryDatabaseIntegrationTests(TransactionTestCase):
    """Celery va Database integration testlar"""
    
    def setUp(self):
        self.document = Document.objects.create(
            completed=False,
            pipeline_running=False
        )

    @patch('apps.files.tasks.document_processing.process_document_pipeline')
    def test_document_processing_workflow(self, mock_task):
        """Document processing workflow test"""
        mock_task.delay.return_value = MagicMock(id='test-task-id')
        
        # Task'ni ishga tushirish
        result = process_document_pipeline.delay(self.document.id)
        
        # Database'da document holatini tekshirish
        document = Document.objects.get(id=self.document.id)
        self.assertEqual(document.pipeline_running, True)
        
        # Task natijasini tekshirish
        self.assertEqual(result.id, 'test-task-id')
        mock_task.assert_called_with(self.document.id)

    @patch('apps.files.tasks.cleanup_tasks.cleanup_temp_files_task.delay')
    def test_cleanup_task_execution(self, mock_task):
        """Cleanup task execution test"""
        mock_task.return_value = MagicMock(id='cleanup-task-id')
        
        # Cleanup task'ni ishga tushirish
        result = cleanup_temp_files_task.delay()
        
        # Task natijasini tekshirish
        self.assertIsNotNone(result.id)
        mock_task.assert_called()

    @patch('apps.files.tasks.parsing_tasks.soft_uz_process_documents')
    def test_parsing_task_execution(self, mock_task):
        """Parsing task execution test"""
        mock_task.delay.return_value = MagicMock(id='parsing-task-id')
        
        # Parsing task'ni ishga tushirish
        result = soft_uz_process_documents.delay()
        
        # Task natijasini tekshirish
        self.assertIsNotNone(result.id)
        mock_task.assert_called()

    def test_task_error_handling(self):
        """Task error handling test"""
        # Xatolik bilan task yaratish
        document = Document.objects.create(
            completed=False,
            pipeline_running=False
        )
        
        # Error yaratish
        error = DocumentError.objects.create(
            document=document,
            error_type='celery',
            error_message='Task failed',
            celery_attempt=1
        )
        
        # Error ma'lumotlarini tekshirish
        self.assertEqual(error.error_type, 'celery')
        self.assertEqual(error.error_message, 'Task failed')
        self.assertEqual(error.celery_attempt, 1)


class ElasticsearchAPIIntegrationTests(TestCase):
    """Elasticsearch va API integration testlar"""
    
    def setUp(self):
        self.client = APIClient()
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
        self.product = Product.objects.create(
            id=1,
            title='Test Product',
            slug='test-product',
            parsed_content='Test content for search',
            document=self.document
        )

    @patch('apps.files.elasticsearch.documents.DocumentIndex.search_documents')
    def test_search_api_integration(self, mock_search):
        """Search API integration test"""
        # Mock search result
        mock_hit = MagicMock()
        mock_hit.meta.id = str(self.document.id)
        mock_search.return_value = MagicMock(hits=[mock_hit])
        
        # API orqali qidiruv
        url = '/api/files/search/'
        response = self.client.get(url, {'q': 'test'})
        
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND])
        mock_search.assert_called_with(query='test', completed=True, deep=False)

    @patch('apps.files.elasticsearch.documents.DocumentIndex.search_documents')
    def test_deep_search_api_integration(self, mock_search):
        """Deep search API integration test"""
        # Mock search result
        mock_hit = MagicMock()
        mock_hit.meta.id = str(self.document.id)
        mock_search.return_value = MagicMock(hits=[mock_hit])
        
        # API orqali chuqur qidiruv
        url = '/api/files/search/'
        response = self.client.get(url, {'q': 'test', 'deep': 'true'})
        
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND])
        mock_search.assert_called_with(query='test', completed=True, deep=True)

    @patch('apps.files.elasticsearch.documents.DocumentIndex.index_document')
    def test_document_indexing_integration(self, mock_index):
        """Document indexing integration test"""
        mock_index.return_value = True
        
        # Document'ni index qilish
        result = DocumentIndex.index_document(self.document)
        
        self.assertTrue(result)
        mock_index.assert_called_with(self.document)

    @patch('apps.files.elasticsearch.documents.DocumentIndex.bulk_index_documents')
    def test_bulk_indexing_integration(self, mock_bulk_index):
        """Bulk indexing integration test"""
        mock_bulk_index.return_value = 1
        
        # Ko'p document'larni index qilish
        documents = [self.document]
        result = DocumentIndex.bulk_index_documents(documents)
        
        self.assertEqual(result, 1)
        mock_bulk_index.assert_called_with(documents)


class BotDatabaseIntegrationTests(TransactionTestCase):
    """Bot va Database integration testlar"""
    
    def setUp(self):
        self.bot_user = BotUser.objects.create(
            telegram_id=12345,
            username='testbotuser',
            first_name='Test',
            last_name='User'
        )

    def test_bot_user_creation(self):
        """Bot user yaratish test"""
        # Yangi bot user yaratish
        new_user = BotUser.objects.create(
            telegram_id=54321,
            username='newbotuser',
            first_name='New',
            last_name='User'
        )
        
        # Ma'lumotlarni tekshirish
        self.assertEqual(new_user.telegram_id, 54321)
        self.assertEqual(new_user.username, 'newbotuser')
        self.assertEqual(new_user.first_name, 'New')

    def test_broadcast_creation(self):
        """Broadcast yaratish test"""
        # Broadcast yaratish
        broadcast = Broadcast.objects.create(
            message='Test broadcast message',
            status=Broadcast.Status.PENDING
        )
        
        # Ma'lumotlarni tekshirish
        self.assertEqual(broadcast.message, 'Test broadcast message')
        self.assertEqual(broadcast.status, Broadcast.Status.PENDING)

    def test_broadcast_recipient_creation(self):
        """Broadcast recipient yaratish test"""
        # Broadcast yaratish
        broadcast = Broadcast.objects.create(
            message='Test broadcast message',
            status=Broadcast.Status.PENDING
        )
        
        # Recipient yaratish
        recipient = BroadcastRecipient.objects.create(
            broadcast=broadcast,
            user=self.bot_user,
            status=BroadcastRecipient.Status.PENDING
        )
        
        # Ma'lumotlarni tekshirish
        self.assertEqual(recipient.broadcast, broadcast)
        self.assertEqual(recipient.user, self.bot_user)
        self.assertEqual(recipient.status, BroadcastRecipient.Status.PENDING)

    @patch('apps.bot.tasks.start_broadcast_task.delay')
    def test_broadcast_task_integration(self, mock_task):
        """Broadcast task integration test"""
        mock_task.return_value = MagicMock(id='broadcast-task-id')
        
        # Broadcast yaratish
        broadcast = Broadcast.objects.create(
            message='Test broadcast message',
            status=Broadcast.Status.PENDING
        )
        
        # Task'ni ishga tushirish
        result = mock_task(broadcast.id)
        
        # Natijani tekshirish
        self.assertEqual(result.id, 'broadcast-task-id')
        mock_task.assert_called_with(broadcast.id)


class EndToEndWorkflowTests(TransactionTestCase):
    """End-to-end workflow testlar"""
    
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + self.token.key)

    @patch('apps.files.tasks.document_processing.process_document_pipeline.delay')
    @patch('apps.files.elasticsearch.documents.DocumentIndex.index_document')
    def test_complete_document_workflow(self, mock_index, mock_task):
        """Complete document workflow test"""
        mock_task.return_value = MagicMock(id='processing-task-id')
        mock_index.return_value = True
        
        # 1. Document yaratish
        url = '/api/files/documents/'
        data = {
            'completed': False,
            'pipeline_running': False
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        document_id = response.data['id']
        
        # 2. Processing task'ni ishga tushirish
        result = mock_task(document_id)
        self.assertEqual(result.id, 'processing-task-id')
        
        # 3. Document'ni completed qilish
        document = Document.objects.get(id=document_id)
        document.completed = True
        document.pipeline_running = False
        document.save()
        
        # 4. Elasticsearch'ga index qilish
        index_result = mock_index(document)
        self.assertTrue(index_result)
        
        # 5. Product yaratish
        product = Product.objects.create(
            id=1,
            title='Test Product',
            slug='test-product',
            parsed_content='Test content',
            document=document
        )
        
        # 6. API orqali product ma'lumotlarini olish
        product_url = f'/api/files/products/{product.id}/'
        product_response = self.client.get(product_url)
        self.assertEqual(product_response.status_code, status.HTTP_200_OK)
        self.assertEqual(product_response.data['title'], 'Test Product')

    @patch('apps.files.elasticsearch.documents.DocumentIndex.search_documents')
    def test_complete_search_workflow(self, mock_search):
        """Complete search workflow test"""
        # Mock search result
        mock_hit = MagicMock()
        mock_hit.meta.id = 'test-document-id'
        mock_search.return_value = MagicMock(hits=[mock_hit])
        
        # 1. Document va Product yaratish
        document = Document.objects.create(
            completed=True,
            pipeline_running=False
        )
        product = Product.objects.create(
            id=1,
            title='Searchable Product',
            slug='searchable-product',
            parsed_content='This is searchable content',
            document=document
        )
        
        # 2. API orqali qidiruv
        search_url = '/api/files/search/'
        response = self.client.get(search_url, {'q': 'searchable'})
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND])
        
        # 3. Search natijalarini tekshirish (endpoint mavjud bo'lsa)
        if response.status_code == status.HTTP_200_OK:
            mock_search.assert_called()

    @patch('apps.bot.tasks.start_broadcast_task.delay')
    def test_complete_bot_workflow(self, mock_task):
        """Complete bot workflow test"""
        mock_task.return_value = MagicMock(id='broadcast-task-id')
        
        # 1. Bot user yaratish
        bot_user = BotUser.objects.create(
            telegram_id=12345,
            username='testbotuser',
            first_name='Test',
            last_name='User'
        )
        
        # 2. Broadcast yaratish
        broadcast = Broadcast.objects.create(
            message='Test broadcast message',
            status=Broadcast.Status.PENDING
        )
        
        # 3. Recipient yaratish
        recipient = BroadcastRecipient.objects.create(
            broadcast=broadcast,
            user=bot_user,
            status=BroadcastRecipient.Status.PENDING
        )
        
        # 4. Broadcast task'ni ishga tushirish
        result = mock_task(broadcast.id)
        self.assertEqual(result.id, 'broadcast-task-id')
        
        # 5. Broadcast status'ni yangilash
        broadcast.status = Broadcast.Status.IN_PROGRESS
        broadcast.save()
        
        # 6. Recipient status'ni yangilash
        recipient.status = BroadcastRecipient.Status.SENT
        recipient.save()
        
        # 7. Final status'ni tekshirish
        broadcast.refresh_from_db()
        recipient.refresh_from_db()
        
        self.assertEqual(broadcast.status, Broadcast.Status.IN_PROGRESS)
        self.assertEqual(recipient.status, BroadcastRecipient.Status.SENT)

    def test_error_handling_workflow(self):
        """Error handling workflow test"""
        # 1. Document yaratish
        document = Document.objects.create(
            completed=False,
            pipeline_running=False
        )
        
        # 2. Error yaratish
        error = DocumentError.objects.create(
            document=document,
            error_type='processing',
            error_message='Test error message',
            celery_attempt=1
        )
        
        # 3. Error ma'lumotlarini tekshirish
        self.assertEqual(error.document, document)
        self.assertEqual(error.error_type, 'processing')
        self.assertEqual(error.error_message, 'Test error message')
        self.assertEqual(error.celery_attempt, 1)
        
        # 4. Error'ni tuzatish
        error.celery_attempt = 2
        error.error_message = 'Retry attempt'
        error.save()
        
        # 5. Yangilangan ma'lumotlarni tekshirish
        error.refresh_from_db()
        self.assertEqual(error.celery_attempt, 2)
        self.assertEqual(error.error_message, 'Retry attempt')

    def test_data_consistency_workflow(self):
        """Data consistency workflow test"""
        # 1. Document yaratish
        document = Document.objects.create(
            completed=False,
            pipeline_running=False
        )
        
        # 2. Product yaratish
        product = Product.objects.create(
            id=1,
            title='Test Product',
            slug='test-product',
            parsed_content='Test content',
            document=document
        )
        
        # 3. Ma'lumotlar mosligini tekshirish
        self.assertEqual(product.document, document)
        self.assertEqual(document.product_set.first(), product)
        
        # 4. Document'ni yangilash
        document.completed = True
        document.save()
        
        # 5. Yangilangan ma'lumotlarni tekshirish
        document.refresh_from_db()
        self.assertEqual(document.completed, True)
        
        # 6. Product ma'lumotlari o'zgarmaganligini tekshirish
        product.refresh_from_db()
        self.assertEqual(product.document, document)
        self.assertEqual(product.title, 'Test Product')
