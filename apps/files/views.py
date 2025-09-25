from django.shortcuts import render
from django.conf import settings
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.db.models import F, Q
from .elasticsearch.documents import DocumentIndex
from .models import Document, Product
from .serializers import DocumentSerializer, SearchResultSerializer

def login_view(request):
    """Login page view"""
    return render(request, 'login.html')

def index(request):
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
    """API endpoint for searching documents"""
    query = request.GET.get('q', '')
    is_deep_search = request.GET.get('deep', 'false').lower() == 'true'
    
    if not query:
        return Response(
            {'error': 'Query parameter is required'},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        # Try Elasticsearch first
        try:
            if is_deep_search:
                # Deep search: search in both title and parsed_content
                search_results = DocumentIndex.search_documents(query=query, completed=True, deep=True)
            else:
                # Regular search: search only in title
                search_results = DocumentIndex.search_documents(query=query, completed=True, deep=False)
            
            if search_results and hasattr(search_results, 'hits'):
                # Serialize the results from Elasticsearch
                results_data = []
                for hit in search_results.hits:
                    try:
                        # Get the product to include view/download counts
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
                        
                return Response({
                    'results': results_data,
                    'total': search_results.hits.total.value if hasattr(search_results.hits.total, 'value') else len(results_data),
                    'search_type': 'deep' if is_deep_search else 'regular'
                })
        except Exception as es_error:
            print(f"Elasticsearch error: {es_error}")
            
        # Fallback to database search if Elasticsearch fails
        if is_deep_search:
            # Deep search: search in both title and parsed_content
            products = Product.objects.filter(
                document__completed=True
            ).filter(
                Q(title__icontains=query) | 
                Q(parsed_content__icontains=query)
            ).select_related('document')[:20]
        else:
            # Regular search: search only in title
            products = Product.objects.filter(
                document__completed=True,
                title__icontains=query
            ).select_related('document')[:20]
        
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
            
        return Response({
            'results': results_data,
            'total': len(results_data),
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
    """API endpoint for getting top 9 most downloaded files"""
    try:
        products = Product.objects.filter(
            document__completed=True
        ).select_related('document').order_by('-download_count')[:9]
        
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
        
        return Response({
            'results': results,
            'total': len(results)
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

