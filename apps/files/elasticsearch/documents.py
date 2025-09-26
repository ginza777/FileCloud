from elasticsearch_dsl import Document, Text, Keyword, Boolean, Integer
from elasticsearch_dsl.connections import connections
from django.conf import settings
from elasticsearch.exceptions import ConnectionError
import logging

logger = logging.getLogger(__name__)

def configure_elasticsearch():
    """Configure Elasticsearch connection with fallback options"""
    urls = [
        settings.ES_URL,  # Try main URL first
        'http://es01:9200',  # Try Docker service name
        'http://localhost:9200',  # Try localhost
    ]

    for url in urls:
        try:
            connections.create_connection(
                hosts=[url],
                timeout=20
            )
            logger.info(f"Successfully connected to Elasticsearch at {url}")
            return True
        except ConnectionError as e:
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
        analyzer='standard'
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
            }
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

        if completed is not None:
            search = search.filter('term', completed=completed)

        if query:
            if deep:
                # Deep search: Search in both title and parsed_content
                search = search.query('multi_match',
                    query=query,
                    fields=['title', 'parsed_content'],
                    operator='and'
                )
            else:
                # Regular search: Search in title and slug
                search = search.query('bool',
                    should=[
                        {'match': {'title': query}},
                        {'match': {'slug': query}}
                    ],
                    minimum_should_match=1
                )

        return search.execute()

# Initialize the index
DocumentIndex.init_index()
