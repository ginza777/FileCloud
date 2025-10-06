"""
Web API Views for FileFinder
Handles web interface API endpoints
"""
from django.shortcuts import render
from django.conf import settings
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.db.models import F, Q
from apps.files.elasticsearch.documents import DocumentIndex
from apps.files.models import Document, Product, DocumentImage
from apps.files.serializers import DocumentSerializer, SearchResultSerializer, DocumentImageSerializer

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


def login_view(request):
    """Login page view"""
    return render(request, 'login.html')


def index_view(request):
    """Main page view"""
    recent_documents = Document.objects.filter(
        completed=True
    ).select_related('product').order_by('-created_at')[:10]

    from django.conf import settings
    bot_username = getattr(settings, 'BOT_USERNAME', 'FileFinderBot')
    main_url = getattr(settings, 'MAIN_URL', 'http://localhost:8000')

    context = {
        'project_name': 'FileFinderBot',
        'description': 'Hujjatlarni qidirish va saqlash tizimi',
        'bot_username': bot_username,
        'MAIN_URL': main_url,
    }
    return render(request, 'index.html', context)


@api_view(['GET'])
def search_documents(request):
    """API endpoint for searching documents with pagination"""
    query = request.GET.get('q', '')
    is_deep_search = request.GET.get('deep', 'false').lower() == 'true'
    
    # Get pagination parameters
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 9))
    
    if not query:
        return Response(
            {'error': 'Query parameter is required'},
            status=status.HTTP_400_BAD_REQUEST
        )

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
                # Get total count
                total_count = search_results.hits.total.value if hasattr(search_results.hits.total, 'value') else len(search_results.hits)
                
                # Calculate pagination
                offset = (page - 1) * page_size
                paginated_hits = search_results.hits[offset:offset + page_size]
                
                # Serialize the results from Elasticsearch
                results_data = []
                for hit in paginated_hits:
                    try:
                        product = Product.objects.get(id=hit.meta.id)
                        results_data.append({
                            'id': product.id,
                            'title': product.title,
                            'view_count': product.view_count,
                            'download_count': product.download_count,
                            'file_size': product.file_size,
                            'created_at': product.created_at.isoformat(),
                            'document_id': str(product.document.id),
                            'telegram_file_id': product.document.telegram_file_id,
                            'score': hit.meta.score
                        })
                    except Product.DoesNotExist:
                        continue
                
                # Calculate pagination info
                total_pages = (total_count + page_size - 1) // page_size
                        
                return Response({
                    'results': results_data,
                    'total': total_count,
                    'page': page,
                    'page_size': page_size,
                    'total_pages': total_pages,
                    'has_next': page < total_pages,
                    'has_previous': page > 1,
                    'search_type': 'deep' if is_deep_search else 'regular'
                })
        except Exception as es_error:
            print(f"Elasticsearch error: {es_error}")
            
        # Fallback to database search if Elasticsearch fails
        if is_deep_search:
            # Deep search: search in both title and parsed_content
            products_query = Product.objects.filter(
                document__completed=True
            ).filter(
                Q(title__icontains=query) | 
                Q(parsed_content__icontains=query)
            ).select_related('document')
        else:
            # Regular search: search in title and slug
            products_query = Product.objects.filter(
                document__completed=True
            ).filter(
                Q(title__icontains=query) | 
                Q(slug__icontains=query)
            ).select_related('document')
        
        # Get total count
        total_count = products_query.count()
        
        # Calculate pagination
        offset = (page - 1) * page_size
        products = products_query[offset:offset + page_size]
        
        results_data = []
        for product in products:
            results_data.append({
                'id': product.id,
                'title': product.title,
                'view_count': product.view_count,
                'download_count': product.download_count,
                'file_size': product.file_size,
                'created_at': product.created_at.isoformat(),
                'document_id': str(product.document.id),
                'telegram_file_id': product.document.telegram_file_id
            })
        
        # Calculate pagination info
        total_pages = (total_count + page_size - 1) // page_size
            
        return Response({
            'results': results_data,
            'total': total_count,
            'page': page,
            'page_size': page_size,
            'total_pages': total_pages,
            'has_next': page < total_pages,
            'has_previous': page > 1,
            'search_type': 'deep' if is_deep_search else 'regular'
        })
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET']) 
def recent_documents(request):
    """API endpoint for getting recent documents"""
    documents = Document.objects.filter(
        completed=True
    ).select_related('product').order_by('-created_at')[:10]

    serializer = DocumentSerializer(documents, many=True)
    return Response(serializer.data)


@api_view(['GET'])
def top_downloads(request):
    """API endpoint for getting top downloaded files with pagination"""
    try:
        # Get pagination parameters
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 9))
        
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
        
        results = []
        for product in products:
            results.append({
                'id': product.id,
                'title': product.title,
                'view_count': product.view_count,
                'download_count': product.download_count,
                'file_size': product.file_size,
                'created_at': product.created_at.isoformat(),
                'document_id': str(product.document.id),
                'telegram_file_id': product.document.telegram_file_id
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
def document_images(request, document_id):
    """API endpoint to get document images"""
    try:
        doc = Document.objects.get(id=document_id)
    except Document.DoesNotExist:
        return Response({'error': 'Document not found'}, status=status.HTTP_404_NOT_FOUND)
    images = DocumentImage.objects.filter(document=doc).order_by('page_number')[:5]
    data = []
    for di in images:
        url = di.image.url
        if request is not None:
            url = request.build_absolute_uri(url)
        data.append({'page': di.page_number, 'url': url})
    return Response({'images': data, 'count': len(data)})


@api_view(['POST'])
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
