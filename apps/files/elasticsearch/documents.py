from elasticsearch_dsl import Document, Text, Keyword, Boolean, Integer
from elasticsearch_dsl.connections import connections
from django.conf import settings
from elasticsearch.exceptions import ConnectionError
from elasticsearch import Elasticsearch
import logging

logger = logging.getLogger(__name__)

def configure_elasticsearch():
    """Configure Elasticsearch connection with fallback options"""
    urls = [
        settings.ES_URL if hasattr(settings, 'ES_URL') else None,  # Try main URL first
        'http://es01:9200',  # Try Docker service name
        'http://localhost:9200',  # Try localhost
    ]

    for url in [u for u in urls if u]:  # Filter out None values
        try:
            # Create Elasticsearch client with proper configuration
            client = Elasticsearch(
                [url],
                retry_on_timeout=True,
                max_retries=3,
                timeout=20
            )

            # Test the connection
            if client.ping():
                # Register the client with elasticsearch_dsl
                connections.add_connection('default', client)
                logger.info(f"Successfully connected to Elasticsearch at {url}")
                return True

        except Exception as e:
            logger.warning(f"Failed to connect to Elasticsearch at {url}: {e}")
            continue

    logger.error("Failed to connect to any Elasticsearch instance")
    return False

# Initialize Elasticsearch connection
configure_elasticsearch()

class DocumentIndex(Document):
    """Elasticsearch document for Product/Document model."""

    # Document fields
    id = Keyword()
    title = Text(
        analyzer='standard',
        fields={'keyword': Keyword()}
    )
    slug = Keyword()
    parsed_content = Text(
        analyzer='standard',
        index_options='docs'  # Optimize for faster search, less storage
    )
    completed = Boolean()
    document_id = Keyword()

    class Index:
        name = settings.ES_INDEX
        settings = {
            'number_of_shards': 1,
            'number_of_replicas': 0,
            'analysis': {
                'analyzer': {
                    'standard': {
                        'type': 'standard',
                        'stopwords': '_none_'
                    }
                }
            },
            'max_result_window': 5000,  # Limit maximum results for performance
            'index.refresh_interval': '30s'  # Reduce refresh frequency for bulk operations
        }

    def save(self, **kwargs):
        if not connections.get_connection():
            if not configure_elasticsearch():
                logger.error("Cannot save document: No Elasticsearch connection")
                return None
        return super().save(**kwargs)

    @classmethod
    def init_index(cls):
        """Create the index and mapping if it doesn't exist."""
        if not connections.get_connection():
            if not configure_elasticsearch():
                logger.error("Cannot initialize index: No Elasticsearch connection")
                return False
        try:
            cls._index.create(ignore=400)
            cls._index.refresh()
            return True
        except Exception as e:
            logger.error(f"Failed to initialize index: {e}")
            return False

    @classmethod
    def index_document(cls, document):
        """Index a single document."""
        if not document.product:
            return None

        # Blocked productlarni index qilmaslik
        if document.product.blocked:
            logger.warning(f"Document {document.id} blocked, skipping Elasticsearch indexing")
            return None

        if not connections.get_connection():
            if not configure_elasticsearch():
                logger.error("Cannot index document: No Elasticsearch connection")
                return None

        try:
            doc = cls(
                meta={'id': str(document.id)},
                id=str(document.id),
                title=document.product.title,
                slug=document.product.slug,
                parsed_content=document.product.parsed_content,
                completed=document.completed,
                document_id=str(document.id)
            )
            return doc.save()
        except Exception as e:
            logger.error(f"Failed to index document {document.id}: {e}")
            return None

    @classmethod
    def bulk_index_documents(cls, documents):
        """Bulk index multiple documents for better performance."""
        if not connections.get_connection():
            if not configure_elasticsearch():
                logger.error("Cannot bulk index documents: No Elasticsearch connection")
                return 0

        try:
            from elasticsearch.helpers import bulk
            
            # Prepare documents for bulk indexing
            actions = []
            for doc in documents:
                if not doc.product:
                    continue
                
                # Blocked productlarni index qilmaslik
                if doc.product.blocked:
                    logger.warning(f"Document {doc.id} blocked, skipping bulk indexing")
                    continue
                    
                action = {
                    '_index': cls._index._name,
                    '_id': str(doc.id),
                    '_source': {
                        'id': str(doc.id),
                        'title': doc.product.title,
                        'slug': doc.product.slug,
                        'parsed_content': doc.product.parsed_content or '',
                        'completed': doc.completed,
                        'document_id': str(doc.id)
                    }
                }
                actions.append(action)
            
            if not actions:
                return 0
                
            # Perform bulk indexing
            success_count, failed_items = bulk(
                connections.get_connection(),
                actions,
                chunk_size=100,
                request_timeout=30
            )
            
            if failed_items:
                logger.warning(f"Bulk indexing: {len(failed_items)} items failed")
                
            return success_count
            
        except Exception as e:
            logger.error(f"Bulk indexing failed: {e}")
            return 0

    @classmethod
    def search_documents(cls, query=None, completed=None, deep=False):
        """
        Search for documents with configurable deep search option.

        Args:
            query (str): Search query
            completed (bool): Filter by completed status
            deep (bool): If True, search in both title and parsed_content
        """
        if not connections.get_connection():
            if not configure_elasticsearch():
                logger.error("Cannot search documents: No Elasticsearch connection")
                return None

        search = cls.search()
        search = search[0:1000]  # Reduced limit for better performance
        search = search.timeout('3s')  # Reduced timeout for faster response

        if completed is not None:
            search = search.filter('term', completed=completed)

        if query:
            if deep:
                # Deep search: Optimized for speed with limited fields
                search = search.query('multi_match',
                    query=query,
                    fields=['title^4', 'parsed_content^1'],  # Higher boost for title
                    type='best_fields',  # Faster than cross_fields
                    operator='or',
                    fuzziness='AUTO',
                    prefix_length=2,
                    max_expansions=50,  # Increased for better results
                    cutoff_frequency=0.01  # Skip rare terms for speed
                )
            else:
                # Regular search: Fast title and slug search
                search = search.query('multi_match',
                    query=query,
                    fields=['title^4', 'slug^2'],  # Higher boost for title
                    type='best_fields',  # Faster than cross_fields
                    operator='or',
                    fuzziness='AUTO',
                    prefix_length=2,
                    max_expansions=20,  # Increased for better results
                    cutoff_frequency=0.01  # Skip rare terms for speed
                )

        return search.execute()

    @classmethod
    def delete_blocked_documents(cls):
        """Blocked productlarni Elasticsearch dan o'chirish"""
        if not connections.get_connection():
            if not configure_elasticsearch():
                logger.error("Cannot delete blocked documents: No Elasticsearch connection")
                return 0

        try:
            from apps.files.models import Document, Product
            
            # Blocked productli documentlarni topish
            blocked_docs = Document.objects.filter(
                product__blocked=True
            ).values_list('id', flat=True)
            
            if not blocked_docs:
                logger.info("No blocked documents to delete from Elasticsearch")
                return 0
            
            # Elasticsearch dan o'chirish
            deleted_count = 0
            for doc_id in blocked_docs:
                try:
                    cls.get(id=str(doc_id)).delete()
                    deleted_count += 1
                    logger.info(f"Deleted blocked document {doc_id} from Elasticsearch")
                except Exception as e:
                    logger.warning(f"Failed to delete document {doc_id} from Elasticsearch: {e}")
            
            logger.info(f"Deleted {deleted_count} blocked documents from Elasticsearch")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Failed to delete blocked documents from Elasticsearch: {e}")
            return 0

# Initialize the index
DocumentIndex.init_index()
