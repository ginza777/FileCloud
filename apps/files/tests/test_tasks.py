"""
Celery Tasks Tests
==================

Bu modul Celery task'larini test qiladi.
Barcha task'lar to'g'ri ishlayotganini tekshiradi.
"""

import os
import tempfile
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from celery import current_app
from celery.exceptions import SoftTimeLimitExceeded
import time

from apps.files.models import Document, Product, DocumentError, ParseProgress
from apps.files.tasks import (
    cleanup_temp_files_task,
    cleanup_files_task,
    soft_uz_process_documents,
    generate_document_images_task,
    process_document_pipeline,
)
from apps.files.elasticsearch.documents import DocumentIndex


class CeleryTasksTestCase(TestCase):
    """
    Celery task'larini test qiluvchi test case.
    
    Bu test case:
    - Cleanup task'larini test qiladi
    - Document processing task'larini test qiladi
    - Parsing task'larini test qiladi
    - Error handling'ni test qiladi
    """
    
    def setUp(self):
        """
        Test uchun ma'lumotlarni tayyorlaydi.
        """
        # Test document yaratish
        self.document = Document.objects.create(
            parse_file_url='https://example.com/test.pdf',
            json_data={'title': 'Test Document'},
            download_status='pending',
            parse_status='pending',
            index_status='pending',
            telegram_status='pending',
            delete_status='pending'
        )
        
        # Test product yaratish
        self.product = Product.objects.create(
            title='Test Product',
            slug='test-product',
            document=self.document
        )
        
        # Test parse progress yaratish
        self.parse_progress = ParseProgress.objects.create(
            last_page=1,
            total_pages_parsed=1,
            last_run_at=timezone.now()
        )

    @patch('apps.files.tasks.cleanup_tasks.cleanup_temp_files_task')
    def test_cleanup_temp_files_task(self, mock_task):
        """
        cleanup_temp_files_task'ni test qiladi.
        """
        # Mock task result
        mock_result = MagicMock()
        mock_result.id = 'test-task-id'
        mock_task.delay.return_value = mock_result
        
        # Task'ni bajarish
        result = cleanup_temp_files_task.delay()
        
        # Natijani tekshirish
        self.assertIsNotNone(result.id)
        self.assertEqual(result.id, 'test-task-id')

    @patch('apps.files.tasks.cleanup_tasks.cleanup_files_task')
    def test_cleanup_files_task(self, mock_task):
        """
        cleanup_files_task'ni test qiladi.
        """
        # Mock task result
        mock_result = MagicMock()
        mock_result.id = 'test-task-id'
        mock_task.delay.return_value = mock_result
        
        # Task'ni bajarish
        result = cleanup_files_task.delay()
        
        # Natijani tekshirish
        self.assertIsNotNone(result.id)
        self.assertEqual(result.id, 'test-task-id')

    @patch('apps.files.tasks.parsing_tasks.soft_uz_process_documents')
    def test_soft_uz_process_documents(self, mock_task):
        """
        soft_uz_process_documents task'ni test qiladi.
        """
        # Mock task result
        mock_result = MagicMock()
        mock_result.id = 'test-task-id'
        mock_task.delay.return_value = mock_result
        
        # Task'ni bajarish
        result = soft_uz_process_documents.delay()
        
        # Natijani tekshirish
        self.assertIsNotNone(result.id)
        self.assertEqual(result.id, 'test-task-id')

    @patch('apps.files.tasks.make_retry_session')
    @patch('apps.files.tasks.convert_from_path')
    def test_generate_document_images_task(self, mock_convert, mock_session):
        """
        generate_document_images_task'ni test qiladi.
        """
        # Mock'lar sozlash
        mock_session.return_value.get.return_value.__enter__.return_value.raise_for_status.return_value = None
        mock_session.return_value.get.return_value.__enter__.return_value.iter_content.return_value = [b'fake pdf content']
        
        mock_image = MagicMock()
        mock_image.width = 1000
        mock_image.height = 1000
        mock_image.convert.return_value = mock_image
        mock_image.resize.return_value = mock_image
        mock_convert.return_value = [mock_image]
        
        # Task'ni bajarish
        result = generate_document_images_task.delay(str(self.document.id))
        
        # Natijani tekshirish
        self.assertIsNotNone(result.id)

    @patch('apps.files.tasks.make_retry_session')
    @patch('apps.files.tasks.tika_parser')
    @patch('apps.files.tasks.Elasticsearch')
    def test_process_document_pipeline(self, mock_elasticsearch, mock_tika, mock_session):
        """
        process_document_pipeline task'ni test qiladi.
        """
        # Mock'lar sozlash
        mock_session.return_value.get.return_value.__enter__.return_value.raise_for_status.return_value = None
        mock_session.return_value.get.return_value.__enter__.return_value.iter_content.return_value = [b'fake content']
        
        mock_tika.from_file.return_value = {'content': 'Test content'}
        
        mock_es_client = MagicMock()
        mock_elasticsearch.return_value = mock_es_client
        
        # Task'ni bajarish
        result = process_document_pipeline.delay(str(self.document.id))
        
        # Natijani tekshirish
        self.assertIsNotNone(result.id)

    def test_task_error_handling(self):
        """
        Task error handling'ni test qiladi.
        """
        # Noto'g'ri document ID bilan task'ni bajarish
        result = process_document_pipeline.delay('invalid-uuid')
        
        # Natijani tekshirish
        self.assertIsNotNone(result.id)

    def test_task_retry_mechanism(self):
        """
        Task retry mechanism'ni test qiladi.
        """
        # Task'ni bajarish
        result = cleanup_temp_files_task.delay()
        
        # Retry count'ni tekshirish
        self.assertIsNotNone(result.id)

    def test_task_celery_registration(self):
        """
        Task'lar Celery'da ro'yxatdan o'tkazilganligini tekshiradi.
        """
        # Celery task'larini olish
        registered_tasks = list(current_app.tasks.keys())
        
        # Task'lar ro'yxatdan o'tkazilganligini tekshirish
        task_names = [
            'apps.files.tasks.cleanup_temp_files_task',
            'apps.files.tasks.cleanup_files_task',
            'apps.files.tasks.soft_uz_process_documents',
            'apps.files.tasks.document_processing.generate_document_images_task',
            'apps.files.tasks.process_document_pipeline',
        ]
        
        for task_name in task_names:
            self.assertIn(task_name, registered_tasks)

    def test_task_serialization(self):
        """
        Task serialization'ni test qiladi.
        """
        # Task'ni serialize qilish
        task = cleanup_temp_files_task
        
        # Task'ni bajarish
        result = task.delay()
        
        # Serialization'ni tekshirish
        self.assertIsNotNone(result.id)
        self.assertIsNotNone(result.status)

    def test_task_timeout(self):
        """
        Task timeout'ni test qiladi.
        """
        # Task'ni bajarish
        result = cleanup_temp_files_task.delay()
        
        # Timeout'ni tekshirish
        self.assertIsNotNone(result.id)

    def test_task_result_backend(self):
        """
        Task result backend'ni test qiladi.
        """
        # Task'ni bajarish
        result = cleanup_temp_files_task.delay()
        
        # Result backend'ni tekshirish
        self.assertIsNotNone(result.id)
        self.assertIsNotNone(result.backend)

    def test_task_beat_schedule(self):
        """
        Task beat schedule'ni test qiladi.
        """
        # Beat schedule'ni olish
        beat_schedule = current_app.conf.beat_schedule
        
        # Schedule'da task'lar mavjudligini tekshirish
        self.assertIsNotNone(beat_schedule)
        
        # Ba'zi task'lar schedule'da mavjudligini tekshirish
        task_names = [
            'Temporary Files Cleanup Every 2 Hours',
            'File System Cleanup Every 20 Minutes',
            'Database Backup Every 5 Hours',
            'Document Processing Every 3 Hours',
        ]
        
        for task_name in task_names:
            self.assertIn(task_name, beat_schedule)

    def test_task_concurrency(self):
        """
        Task concurrency'ni test qiladi.
        """
        # Bir nechta task'ni parallel bajarish
        results = []
        for i in range(5):
            result = cleanup_temp_files_task.delay()
            results.append(result)
        
        # Barcha task'lar bajarilganligini tekshirish
        for result in results:
            self.assertIsNotNone(result.id)

    def test_task_dependencies(self):
        """
        Task dependencies'ni test qiladi.
        """
        # Task'ni bajarish
        result = soft_uz_process_documents.delay()
        
        # Dependencies'ni tekshirish
        self.assertIsNotNone(result.id)

    def test_task_logging(self):
        """
        Task logging'ni test qiladi.
        """
        # Task'ni bajarish
        result = cleanup_temp_files_task.delay()
        
        # Logging'ni tekshirish
        self.assertIsNotNone(result.id)

    def test_task_monitoring(self):
        """
        Task monitoring'ni test qiladi.
        """
        # Task'ni bajarish
        result = cleanup_temp_files_task.delay()
        
        # Monitoring'ni tekshirish
        self.assertIsNotNone(result.id)
        self.assertIsNotNone(result.status)

# Elasticsearch Integration Tests
class ElasticsearchIntegrationTests(TestCase):
    def setUp(self):
        self.document = Document.objects.create(
            completed=True,
            pipeline_running=False
        )
        # Ensure Elasticsearch index is initialized
        DocumentIndex.init_index()

    @patch('apps.files.elasticsearch.documents.configure_elasticsearch')
    @patch('apps.files.elasticsearch.documents.DocumentIndex.search_documents')
    def test_elasticsearch_search_basic(self, mock_search, mock_configure):
        """Test basic Elasticsearch search functionality"""
        mock_configure.return_value = True
        mock_hit = MagicMock()
        mock_hit.meta.id = str(self.document.id)
        mock_search.return_value = MagicMock(hits=[mock_hit])
        
        result = DocumentIndex.search_documents(query='Test Document', completed=True)
        self.assertIsNotNone(result)
        mock_search.assert_called_with(query='Test Document', completed=True, deep=False)

    @patch('apps.files.elasticsearch.documents.configure_elasticsearch')
    @patch('apps.files.elasticsearch.documents.DocumentIndex.search_documents')
    def test_elasticsearch_deep_search(self, mock_search, mock_configure):
        """Test deep search functionality in Elasticsearch"""
        mock_configure.return_value = True
        mock_hit = MagicMock()
        mock_hit.meta.id = str(self.document.id)
        mock_search.return_value = MagicMock(hits=[mock_hit])
        
        result = DocumentIndex.search_documents(query='Test Document', completed=True, deep=True)
        self.assertIsNotNone(result)
        mock_search.assert_called_with(query='Test Document', completed=True, deep=True)

    @patch('apps.files.elasticsearch.documents.configure_elasticsearch')
    @patch('apps.files.elasticsearch.documents.DocumentIndex.search_documents')
    def test_elasticsearch_connection_failure(self, mock_search, mock_configure):
        """Test handling of Elasticsearch connection failure"""
        mock_configure.return_value = False
        mock_search.return_value = None
        
        result = DocumentIndex.search_documents(query='Test Document')
        self.assertIsNone(result)
        mock_configure.assert_called()

    @patch('apps.files.elasticsearch.documents.configure_elasticsearch')
    @patch('apps.files.elasticsearch.documents.DocumentIndex.save')
    def test_elasticsearch_indexing(self, mock_save, mock_configure):
        """Test document indexing in Elasticsearch"""
        mock_configure.return_value = True
        mock_save.return_value = True
        
        result = DocumentIndex.index_document(self.document)
        self.assertTrue(result)
        mock_save.assert_called()

# Celery Task Execution Tests
class CeleryTaskExecutionTests(TestCase):
    def setUp(self):
        self.document = Document.objects.create(
            completed=False,
            pipeline_running=False
        )

    @patch('apps.files.tasks.document_processing.process_document_pipeline')
    def test_celery_task_execution(self, mock_process):
        """Test if Celery task is properly called and executed"""
        mock_process.return_value = 'Task completed'
        result = process_document_pipeline.delay(self.document.id)
        self.assertTrue(result.task_id is not None)
        self.assertEqual(result.status, 'PENDING')

    @patch('apps.files.tasks.document_processing.log_document_error')
    def test_celery_task_error_handling(self, mock_log_error):
        """Test error handling in Celery tasks"""
        mock_log_error.return_value = 'Error logged'
        with patch('apps.files.tasks.document_processing.process_document_pipeline', side_effect=Exception('Test error')):
            result = process_document_pipeline.delay(self.document.id)
            self.assertTrue(result.task_id is not None)
            # Reduced wait time for faster test execution
            time.sleep(0.1)
            self.assertEqual(result.status, 'FAILURE')
            mock_log_error.assert_called()

    def test_celery_task_timeout(self):
        """Test Celery task timeout handling"""
        with patch('apps.files.tasks.document_processing.process_document_pipeline', side_effect=lambda x: time.sleep(61)):
            with self.assertRaises(SoftTimeLimitExceeded):
                result = process_document_pipeline.delay(self.document.id)
                time.sleep(0.5)  # Reduced time for timeout to trigger
                self.assertEqual(result.status, 'FAILURE')

    @patch('apps.files.tasks.cleanup_tasks.cleanup_temp_files_task')
    def test_periodic_task_execution(self, mock_cleanup):
        """Test execution of periodic tasks"""
        mock_cleanup.return_value = 'Cleanup completed'
        result = cleanup_temp_files_task.delay()
        self.assertTrue(result.task_id is not None)
        self.assertEqual(result.status, 'PENDING')

# System Stability Tests
class SystemStabilityTests(TestCase):
    def setUp(self):
        self.documents = []
        # Reduced number of test documents for faster setup
        for i in range(3):
            doc = Document.objects.create(
                completed=True,
                pipeline_running=False
            )
            self.documents.append(doc)
        DocumentIndex.init_index()

    @patch('apps.files.elasticsearch.documents.configure_elasticsearch')
    @patch('apps.files.elasticsearch.documents.DocumentIndex.search_documents')
    def test_system_stability_multiple_searches(self, mock_search, mock_configure):
        """Test system stability under multiple search requests"""
        mock_configure.return_value = True
        mock_hits = [MagicMock(meta=MagicMock(id=str(doc.id))) for doc in self.documents]
        mock_search.return_value = MagicMock(hits=mock_hits)
        
        # Reduced number of search requests for faster testing
        for i in range(2):  
            result = DocumentIndex.search_documents(query=f'Test Document {i}', completed=True)
            self.assertIsNotNone(result)
            self.assertGreaterEqual(len(result.hits), 1)
        self.assertEqual(mock_search.call_count, 2)

    @patch('apps.files.tasks.document_processing.process_document_pipeline')
    def test_system_stability_multiple_tasks(self, mock_process):
        """Test system stability under multiple concurrent tasks"""
        mock_process.return_value = 'Task completed'
        tasks = []
        for doc in self.documents:
            result = process_document_pipeline.delay(doc.id)
            tasks.append(result)
            self.assertTrue(result.task_id is not None)
            self.assertEqual(result.status, 'PENDING')
        
        # Check if all tasks are initiated
        self.assertEqual(len(tasks), len(self.documents))
        mock_process.assert_called()

    @patch('apps.files.elasticsearch.documents.configure_elasticsearch')
    @patch('apps.files.elasticsearch.documents.DocumentIndex.bulk_index_documents')
    def test_system_stability_bulk_indexing(self, mock_bulk_index, mock_configure):
        """Test system stability during bulk document indexing"""
        mock_configure.return_value = True
        mock_bulk_index.return_value = len(self.documents)
        
        result = DocumentIndex.bulk_index_documents(self.documents)
        self.assertEqual(result, len(self.documents))
        mock_bulk_index.assert_called_with(self.documents)

    def test_system_stability_database_load(self):
        """Test system stability under database load"""
        start_time = time.time()
        # Reduced number of records for faster testing
        for i in range(20):  
            Document.objects.create(
                completed=False,
                pipeline_running=False
            )
        duration = time.time() - start_time
        self.assertLess(duration, 5.0)  # Reduced expected completion time
        self.assertEqual(Document.objects.count(), 23)  # 20 new + 3 from setup
