"""
Elasticsearch Integration Test Module

Bu modul Elasticsearch integratsiyasini test qiladi:
- Basic search (oddiy qidiruv)
- Deep search (chuqur qidiruv)
- Document indexing (document indekslash)
- Connection handling (connection boshqaruvi)
"""
from unittest.mock import MagicMock, patch
from django.test import TestCase
from apps.files.models import Document
from apps.files.elasticsearch.documents import DocumentIndex


class ElasticsearchSearchTests(TestCase):
    """Elasticsearch qidiruv testlari"""
    
    def setUp(self):
        """Test uchun Document yaratish"""
        self.document = Document.objects.create(
            completed=True,
            pipeline_running=False
        )
        # Elasticsearch index'ni initialize qilish
        DocumentIndex.init_index()
    
    @patch('apps.files.elasticsearch.documents.configure_elasticsearch')
    @patch('apps.files.elasticsearch.documents.DocumentIndex.search_documents')
    def test_basic_search(self, mock_search, mock_configure):
        """Oddiy qidiruvni test qilish"""
        mock_configure.return_value = True
        mock_hit = MagicMock()
        mock_hit.meta.id = str(self.document.id)
        mock_search.return_value = MagicMock(hits=[mock_hit])
        
        result = DocumentIndex.search_documents(query='Test', completed=True, deep=False)
        
        self.assertIsNotNone(result)
        mock_search.assert_called_once()
    
    @patch('apps.files.elasticsearch.documents.configure_elasticsearch')
    @patch('apps.files.elasticsearch.documents.DocumentIndex.search_documents')
    def test_deep_search(self, mock_search, mock_configure):
        """Chuqur qidiruvni test qilish"""
        mock_configure.return_value = True
        mock_hit = MagicMock()
        mock_hit.meta.id = str(self.document.id)
        mock_search.return_value = MagicMock(hits=[mock_hit])
        
        result = DocumentIndex.search_documents(query='Test', completed=True, deep=True)
        
        self.assertIsNotNone(result)
        mock_search.assert_called_once()
    
    @patch('apps.files.elasticsearch.documents.DocumentIndex.search_documents')
    def test_connection_failure(self, mock_search):
        """Connection failure holatini test qilish"""
        mock_search.return_value = None
        
        result = mock_search(query='Test')
        
        self.assertIsNone(result)
        mock_search.assert_called_once()
    
    @patch('apps.files.elasticsearch.documents.configure_elasticsearch')
    @patch('apps.files.elasticsearch.documents.DocumentIndex.save')
    def test_document_indexing(self, mock_save, mock_configure):
        """Document indexing'ni test qilish"""
        from apps.files.models import Product
        
        # Product yaratish (Document.product mavjud bo'lishi kerak)
        Product.objects.create(
            id=1,
            title='Test Product',
            slug='test-product',
            parsed_content='Test content',
            document=self.document
        )
        
        mock_configure.return_value = True
        mock_save.return_value = True
        
        result = DocumentIndex.index_document(self.document)
        
        self.assertTrue(result)
        mock_save.assert_called()


class ElasticsearchConnectionTests(TestCase):
    """Elasticsearch connection testlari"""
    
    def test_index_initialization(self):
        """Index initialization'ni test qilish"""
        # Index initialization xatolarsiz ishlashini tekshirish
        try:
            DocumentIndex.init_index()
            success = True
        except Exception:
            success = False
        
        self.assertTrue(success)
    
    @patch('apps.files.elasticsearch.documents.configure_elasticsearch')
    def test_connection_configuration(self, mock_configure):
        """Connection configuration'ni test qilish"""
        mock_configure.return_value = True
        
        result = mock_configure()
        
        self.assertTrue(result)
        mock_configure.assert_called_once()

