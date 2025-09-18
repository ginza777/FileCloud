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
    def search_documents(cls, query=None, completed=None):
        """Search documents with optional filters."""
        if not connections.get_connection():
            if not configure_elasticsearch():
                logger.error("Cannot search documents: No Elasticsearch connection")
                return None

        try:
            s = cls.search()

            if query:
                s = s.query('multi_match',
                           query=query,
                           fields=['title^3', 'parsed_content', 'slug'])

            if completed is not None:
                s = s.filter('term', completed=completed)

            return s.execute()
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return None

# Initialize the index
DocumentIndex.init_index()
