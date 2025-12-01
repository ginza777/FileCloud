"""
Web API Views for FileFinder
Handles web interface API endpoints
"""
from django.shortcuts import render
from django.conf import settings
from django.core.cache import cache
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_headers
import hashlib
import json
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.db.models import F, Q
from apps.files.elasticsearch.documents import DocumentIndex
from apps.files.models import Document, Product, DocumentImage, WebSearchQuery
from apps.files.serializers import DocumentSerializer, DocumentImageSerializer
import threading

MAX_PREVIEW_IMAGES = 5

__all__ = [
    'login_view',
    'index_view',
    'search_documents',
    'recent_documents',
    'top_downloads',
    'increment_view_count',
    'increment_download_count',
    'document_images'
]


def _build_preview_map(document_ids, request):
    """
    Returns {document_id: {'small': url, 'large': url}} for the first page image.
    """
    if not document_ids:
        return {}

    previews = {}
    queryset = DocumentImage.objects.filter(
        document_id__in=document_ids
    ).order_by('document_id', 'page_number')

    for image in queryset:
        if image.document_id in previews:
            continue
        small = image.image_small.url if image.image_small else None
        large = image.image_large.url if image.image_large else None
        if request:
            if small:
                small = request.build_absolute_uri(small)
            if large:
                large = request.build_absolute_uri(large)
        previews[image.document_id] = {
            'small': small,
            'large': large
        }
    return previews


def login_view(request):
    """Login page view"""
    return render(request, 'login.html')


def index_view(request):
    """Main page view with optimized caching"""
    # Try to get from cache, but handle Redis errors gracefully
    cache_key = 'recent_documents_home'
    recent_documents = None
    try:
        recent_documents = cache.get(cache_key)
    except Exception:
        # If cache fails, just continue without cache
        pass
    
    if recent_documents is None:
        recent_documents = list(Document.objects.filter(
            completed=True
        ).select_related('product').only(
            'id', 'created_at', 'product__id', 'product__title'
        ).order_by('-created_at')[:10])
        try:
            cache.set(cache_key, recent_documents, 300)  # 5 minutes cache
        except Exception:
            # If cache fails, just continue without cache
            pass

    from django.conf import settings
    bot_username = getattr(settings, 'BOT_USERNAME', 'FileFinderBot')
    # Remove @ symbol if present for URL usage
    if bot_username.startswith('@'):
        bot_username = bot_username[1:]
    main_url = getattr(settings, 'MAIN_URL', 'http://localhost:8000')

    context = {
        'project_name': 'FileFinderBot',
        'description': 'Hujjatlarni qidirish va saqlash tizimi',
        'bot_username': bot_username,
        'MAIN_URL': main_url,
        'recent_documents': recent_documents,
    }
    return render(request, 'index.html', context)


@api_view(['GET'])
@permission_classes([AllowAny])
def search_documents(request):
    """API endpoint for searching documents with pagination"""
    query = request.GET.get('q', '').strip()
    is_deep_search = request.GET.get('deep', 'false').lower() == 'true'
    
    # Get pagination parameters
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 12))
    
    # For deep search, support batch pagination (10 pages at a time)
    # batch_start_page: which batch to fetch (1 = pages 1-10, 2 = pages 11-20, etc.)
    batch_start_page = int(request.GET.get('batch_start_page', 0))
    BATCH_SIZE = 10  # Number of pages per batch
    BATCH_RESULTS_COUNT = BATCH_SIZE * page_size  # Total results per batch (120)
    
    if not query:
        return Response(
            {'error': 'Query parameter is required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Check cache first for faster response
    cache_key = f"search:{query}:{is_deep_search}:{page}:{batch_start_page}"
    cached_result = cache.get(cache_key)
    if cached_result:
        # Save search query in background (non-blocking)
        if page == 1:  # Only save on first page
            threading.Thread(
                target=lambda: WebSearchQuery.objects.create(
                    query_text=query,
                    is_deep_search=is_deep_search,
                    found_results=cached_result.get('total', 0) > 0,
                    result_count=cached_result.get('total', 0)
                ),
                daemon=True
            ).start()
        return Response(cached_result)

    try:
        # Try Elasticsearch first
        try:
            # Both regular and deep search now handle completed=True by default
            search_results = DocumentIndex.search_documents(
                query=query,
                completed=True,  # Always filter for completed=True
                deep=is_deep_search
            )

            if search_results and hasattr(search_results, 'hits'):
                # For deep search, get total count first (this is fast - just metadata)
                if is_deep_search:
                    # Get total count immediately (this is fast - doesn't fetch all documents)
                    total_count = search_results.hits.total.value if hasattr(search_results.hits.total, 'value') else 0
                    
                    # For first page of deep search, return first 12 results immediately
                    if batch_start_page == 0:
                        # Return first page immediately - don't wait for full batch
                        paginated_hits = search_results.hits[0:page_size]
                    elif batch_start_page > 0:
                        # For subsequent batches, fetch 10 pages worth of data
                        batch_offset = (batch_start_page - 1) * BATCH_RESULTS_COUNT
                        paginated_hits = search_results.hits[batch_offset:batch_offset + BATCH_RESULTS_COUNT]
                    else:
                        # Fallback
                        offset = (page - 1) * page_size
                        paginated_hits = search_results.hits[offset:offset + page_size]
                else:
                    # Regular search - get total count and paginate normally
                    total_count = search_results.hits.total.value if hasattr(search_results.hits.total, 'value') else len(search_results.hits)
                    offset = (page - 1) * page_size
                    paginated_hits = search_results.hits[offset:offset + page_size]
                
                # Optimized database query - bulk fetch with select_related
                product_ids = [hit.meta.id for hit in paginated_hits]
                if product_ids:  # Only query if we have IDs
                    products_dict = {
                        p.id: p for p in Product.objects.filter(
                            id__in=product_ids
                        ).select_related('document').only(
                            'id', 'title', 'view_count', 'download_count',
                            'file_size', 'created_at',
                            'document__id', 'document__telegram_file_id',
                            'document__page_count', 'document__file_size'
                        )
                    }
                else:
                    products_dict = {}
                
                # Serialize the results from Elasticsearch
                preview_map = _build_preview_map(
                    [p.document.id for p in products_dict.values()],
                    request
                )
                results_data = []
                for hit in paginated_hits:
                    product = products_dict.get(hit.meta.id)
                    if product:
                        preview = preview_map.get(product.document.id, {})
                        doc_meta = product.document
                        doc_size = doc_meta.file_size or product.file_size
                        results_data.append({
                            'id': product.id,
                            'title': product.title,
                            'view_count': product.view_count,
                            'download_count': product.download_count,
                            'file_size': doc_size,
                            'page_count': doc_meta.page_count,
                            'created_at': product.created_at.isoformat(),
                            'document_id': str(product.document.id),
                            'telegram_file_id': product.document.telegram_file_id,
                            'score': hit.meta.score,
                            'preview_image_small': preview.get('small'),
                            'preview_image_large': preview.get('large')
                        })
                
                # Calculate pagination info
                total_pages = (total_count + page_size - 1) // page_size
                
                # Prepare response data
                if is_deep_search and batch_start_page > 0:
                    batch_start = (batch_start_page - 1) * BATCH_SIZE + 1
                    batch_end = min(batch_start + BATCH_SIZE - 1, total_pages)
                    response_data = {
                        'results': results_data,
                        'total': total_count,
                        'page': page,
                        'page_size': page_size,
                        'total_pages': total_pages,
                        'has_next': page < total_pages,
                        'has_previous': page > 1,
                        'next_page': page + 1 if page < total_pages else None,
                        'previous_page': page - 1 if page > 1 else None,
                        'search_type': 'deep',
                        'batch_start_page': batch_start_page,
                        'batch_start': batch_start,
                        'batch_end': batch_end,
                        'is_batch': True
                    }
                else:
                    response_data = {
                        'results': results_data,
                        'total': total_count,
                        'page': page,
                        'page_size': page_size,
                        'total_pages': total_pages,
                        'has_next': page < total_pages,
                        'has_previous': page > 1,
                        'next_page': page + 1 if page < total_pages else None,
                        'previous_page': page - 1 if page > 1 else None,
                        'search_type': 'deep' if is_deep_search else 'regular',
                        'is_batch': False
                    }
                
                # Cache the result for 5 minutes
                cache.set(cache_key, response_data, 300)
                
                # Save search query in background (non-blocking) - only for first page
                if page == 1:
                    threading.Thread(
                        target=lambda: WebSearchQuery.objects.create(
                            query_text=query,
                            is_deep_search=is_deep_search,
                            found_results=total_count > 0,
                            result_count=total_count
                        ),
                        daemon=True
                    ).start()
                
                return Response(response_data)
        except Exception as es_error:
            print(f"Elasticsearch error: {es_error}")
            
        # Fallback to database search if Elasticsearch fails
        # Helper function to create fuzzy search patterns
        def create_fuzzy_patterns(search_query):
            """Create fuzzy search patterns for database fallback"""
            patterns = [search_query]  # Exact match first
            
            # Split query into words
            words = search_query.split()
            if len(words) > 1:
                # For multi-word queries, try each word separately
                for word in words:
                    if len(word) > 3:  # Only for words longer than 3 characters
                        patterns.append(word)
            
            # Create regex patterns for fuzzy matching (allow 1-2 missing characters)
            # Example: "INKLYUZIV" -> "INKL[YZ]?IV" or "INKL.*IV"
            fuzzy_patterns = []
            for pattern in patterns:
                if len(pattern) > 4:
                    # Try to match with missing characters
                    # Convert pattern to allow optional characters
                    fuzzy_pattern = pattern
                    fuzzy_patterns.append(fuzzy_pattern)
            
            return patterns + fuzzy_patterns
        
        if is_deep_search:
            # Deep search: search in both title and parsed_content
            search_patterns = create_fuzzy_patterns(query)
            title_q = Q()
            content_q = Q()
            
            for pattern in search_patterns:
                title_q |= Q(title__icontains=pattern)
                content_q |= Q(parsed_content__icontains=pattern)
            
            products_query = Product.objects.filter(
                document__completed=True
            ).exclude(
                blocked=True
            ).filter(
                title_q | content_q
            ).select_related('document')
        else:
            # Regular search: search in title and slug with fuzzy matching
            search_patterns = create_fuzzy_patterns(query)
            title_q = Q()
            slug_q = Q()
            
            # Exact match (higher priority)
            title_q |= Q(title__icontains=query)
            slug_q |= Q(slug__icontains=query)
            
            # Fuzzy matches - try variations
            for pattern in search_patterns[1:]:  # Skip first (exact match)
                if len(pattern) > 2:  # Only for meaningful patterns
                    title_q |= Q(title__icontains=pattern)
                    slug_q |= Q(slug__icontains=pattern)
            
            # Also try with missing characters using regex-like patterns
            # For "INKLZIV" also search for "INKLYUZIV" and similar
            query_words = query.split()
            for word in query_words:
                if len(word) > 4:
                    # Try variations: remove 1-2 characters
                    for i in range(len(word)):
                        if i < len(word) - 1:
                            variant = word[:i] + word[i+1:]  # Remove one character
                            if len(variant) > 3:
                                title_q |= Q(title__icontains=variant)
                                slug_q |= Q(slug__icontains=variant)
            
            products_query = Product.objects.filter(
                document__completed=True
            ).exclude(
                blocked=True
            ).filter(
                title_q | slug_q
            ).select_related('document').distinct()
        
        # Get total count
        total_count = products_query.count()
        
        # For deep search with batch pagination, fetch 10 pages worth of data
        if is_deep_search and batch_start_page > 0:
            # Calculate batch offset: batch 1 = pages 1-10, batch 2 = pages 11-20, etc.
            batch_offset = (batch_start_page - 1) * BATCH_RESULTS_COUNT
            # Fetch 10 pages worth of results (120 files)
            products = products_query.only(
                'id', 'title', 'view_count', 'download_count',
                'file_size', 'created_at',
                'document__id', 'document__telegram_file_id',
                'document__page_count', 'document__file_size'
            )[batch_offset:batch_offset + BATCH_RESULTS_COUNT]
        else:
            # Regular pagination: single page
            offset = (page - 1) * page_size
            products = products_query.only(
                'id', 'title', 'view_count', 'download_count',
                'file_size', 'created_at',
                'document__id', 'document__telegram_file_id',
                'document__page_count', 'document__file_size'
            )[offset:offset + page_size]
        
        preview_map = _build_preview_map(
            [product.document.id for product in products],
            request
        )
        results_data = []
        for product in products:
            preview = preview_map.get(product.document.id, {})
            doc_meta = product.document
            doc_size = doc_meta.file_size or product.file_size
            results_data.append({
                'id': product.id,
                'title': product.title,
                'view_count': product.view_count,
                'download_count': product.download_count,
                'file_size': doc_size,
                'page_count': doc_meta.page_count,
                'created_at': product.created_at.isoformat(),
                'document_id': str(product.document.id),
                'telegram_file_id': product.document.telegram_file_id,
                'preview_image_small': preview.get('small'),
                'preview_image_large': preview.get('large')
            })
        
        # Calculate pagination info
        total_pages = (total_count + page_size - 1) // page_size
        
        # Prepare response data
        if is_deep_search and batch_start_page > 0:
            batch_start = (batch_start_page - 1) * BATCH_SIZE + 1
            batch_end = min(batch_start + BATCH_SIZE - 1, total_pages)
            response_data = {
                'results': results_data,
                'total': total_count,
                'page': page,
                'page_size': page_size,
                'total_pages': total_pages,
                'has_next': page < total_pages,
                'has_previous': page > 1,
                'next_page': page + 1 if page < total_pages else None,
                'previous_page': page - 1 if page > 1 else None,
                'search_type': 'deep',
                'batch_start_page': batch_start_page,
                'batch_start': batch_start,
                'batch_end': batch_end,
                'is_batch': True
            }
        else:
            response_data = {
                'results': results_data,
                'total': total_count,
                'page': page,
                'page_size': page_size,
                'total_pages': total_pages,
                'has_next': page < total_pages,
                'has_previous': page > 1,
                'next_page': page + 1 if page < total_pages else None,
                'previous_page': page - 1 if page > 1 else None,
                'search_type': 'deep' if is_deep_search else 'regular',
                'is_batch': False
            }
        
        # Cache the result for 5 minutes
        cache.set(cache_key, response_data, 300)
        
        # Save search query in background (non-blocking) - only for first page
        if page == 1:
            threading.Thread(
                target=lambda: WebSearchQuery.objects.create(
                    query_text=query,
                    is_deep_search=is_deep_search,
                    found_results=total_count > 0,
                    result_count=total_count
                ),
                daemon=True
            ).start()
        
        return Response(response_data)
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([AllowAny])
def recent_documents(request):
    """API endpoint for getting recent documents"""
    documents = Document.objects.filter(
        completed=True
    ).select_related('product').order_by('-created_at')[:10]

    serializer = DocumentSerializer(documents, many=True, context={'request': request})
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([AllowAny])
def top_downloads(request):
    """API endpoint for getting top downloaded files with pagination"""
    try:
        # Get pagination parameters
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 12))
        
        # Calculate offset
        offset = (page - 1) * page_size
        
        # Get total count
        total_count = Product.objects.filter(
            document__completed=True
        ).count()
        
        # Get paginated results
        products = Product.objects.filter(
            document__completed=True
        ).select_related('document').order_by('-download_count')[offset:offset + page_size]
        
        preview_map = _build_preview_map(
            [product.document.id for product in products],
            request
        )
        results = []
        for product in products:
            preview = preview_map.get(product.document.id, {})
            doc_meta = product.document
            doc_size = doc_meta.file_size or product.file_size
            results.append({
                'id': product.id,
                'title': product.title,
                'view_count': product.view_count,
                'download_count': product.download_count,
                'file_size': doc_size,
                'page_count': doc_meta.page_count,
                'created_at': product.created_at.isoformat(),
                'document_id': str(product.document.id),
                'telegram_file_id': product.document.telegram_file_id,
                'preview_image_small': preview.get('small'),
                'preview_image_large': preview.get('large')
            })
        
        # Calculate pagination info
        total_pages = (total_count + page_size - 1) // page_size
        
        return Response({
            'results': results,
            'total': total_count,
            'page': page,
            'page_size': page_size,
            'total_pages': total_pages,
            'has_next': page < total_pages,
            'has_previous': page > 1
        })
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([AllowAny])
def increment_view_count(request, product_id):
    """API endpoint to increment view count for a product"""
    try:
        product = Product.objects.get(id=product_id)
        product.view_count = F('view_count') + 1
        product.save(update_fields=['view_count'])
        
        return Response({'success': True})
    except Product.DoesNotExist:
        return Response(
            {'error': 'Product not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([AllowAny])
def document_images(request, document_id):
    """API endpoint to get document images"""
    try:
        doc = Document.objects.get(id=document_id)
    except Document.DoesNotExist:
        return Response({'error': 'Document not found'}, status=status.HTTP_404_NOT_FOUND)
    images = DocumentImage.objects.filter(document=doc).order_by('page_number')[:MAX_PREVIEW_IMAGES]
    serializer = DocumentImageSerializer(images, many=True, context={'request': request})
    return Response({
        'images': serializer.data,
        'count': len(serializer.data),
        'page_count': doc.page_count,
        'file_size': doc.file_size
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def increment_download_count(request, product_id):
    """API endpoint to increment download count for a product"""
    try:
        product = Product.objects.get(id=product_id)
        product.download_count = F('download_count') + 1
        product.save(update_fields=['download_count'])
        
        return Response({'success': True})
    except Product.DoesNotExist:
        return Response(
            {'error': 'Product not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
