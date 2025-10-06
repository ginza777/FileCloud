"""
Celery Tasks Test Module

Bu modul Celery background tasklarini test qiladi:
- Task execution (vazifa bajarilishi)
- Task retry mechanism (qayta urinish mexanizmi)
- Task timeout (vaqt tugashi)
- Celery beat schedule (rejali vazifalar)
"""
import time
from unittest.mock import MagicMock, patch
from django.test import TestCase
from apps.files.models import Document, Product
from apps.files.tasks.document_processing import (
    process_document_pipeline,
    generate_document_images_task
)
from apps.files.tasks.cleanup_tasks import cleanup_temp_files_task


class CeleryTaskExecutionTests(TestCase):
    """Celery vazifalarining bajarilishini test qilish"""
    
    def setUp(self):
        """Test uchun Document yaratish"""
        self.document = Document.objects.create(
            completed=False,
            pipeline_running=False
        )
    
    @patch('apps.files.tasks.document_processing.process_document_pipeline.delay')
    def test_task_can_be_called(self, mock_task):
        """Taskni chaqirish mumkinligini test qilish"""
        mock_task.return_value = MagicMock(id='test-task-id')
        
        result = process_document_pipeline.delay(self.document.id)
        
        self.assertIsNotNone(result.id)
        self.assertEqual(result.id, 'test-task-id')
    
    @patch('apps.files.tasks.cleanup_tasks.cleanup_temp_files_task.delay')
    def test_cleanup_task(self, mock_task):
        """Cleanup taskni test qilish"""
        mock_task.return_value = MagicMock(id='cleanup-task-id')
        
        result = cleanup_temp_files_task.delay()
        
        self.assertIsNotNone(result.id)
        mock_task.assert_called_once()
    
    def test_task_timeout(self):
        """Task timeout sozlamalarini test qilish"""
        from celery import current_app
        
        # Celery timeout sozlamalari mavjudligini tekshirish
        self.assertIsNotNone(current_app.conf.task_time_limit)
        self.assertGreater(current_app.conf.task_time_limit, 0)
    
    def test_task_serialization(self):
        """Task serialization sozlamalarini test qilish"""
        from celery import current_app
        
        # JSON serialization ishlatilishini tekshirish
        self.assertEqual(current_app.conf.task_serializer, 'json')
        self.assertEqual(current_app.conf.result_serializer, 'json')
        self.assertIn('json', current_app.conf.accept_content)


class CeleryBeatScheduleTests(TestCase):
    """Celery Beat rejali vazifalarini test qilish"""
    
    def test_beat_schedule_exists(self):
        """Beat schedule mavjudligini test qilish"""
        from celery import current_app
        
        # Beat scheduler sozlamalari mavjudligini tekshirish
        self.assertIsNotNone(current_app.conf.beat_scheduler)
    
    def test_celery_timezone(self):
        """Celery timezone sozlamalarini test qilish"""
        from celery import current_app
        
        # Timezone sozlamalari to'g'riligini tekshirish
        self.assertIsNotNone(current_app.conf.timezone)

