from django.shortcuts import render
from django.conf import settings
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .elasticsearch.documents import DocumentIndex
from .models import Document
from .serializers import DocumentSerializer, SearchResultSerializer

def index(request):
    """Main page view"""
    recent_documents = Document.objects.filter(
        completed=True
    ).select_related('product').order_by('-created_at')[:10]

    context = {
        'project_name': 'FileFinderBot',
        'description': 'Hujjatlarni qidirish va saqlash tizimi',
    }
    return render(request, 'index.html', context)

@api_view(['GET'])
def search_documents(request):
    """API endpoint for searching documents"""
    query = request.GET.get('q', '')
    if not query:
        return Response(
            {'error': 'Query parameter is required'},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        search_results = DocumentIndex.search_documents(query=query)
        serializer = SearchResultSerializer(search_results.hits, many=True)
        return Response({
            'results': serializer.data,
            'total': search_results.hits.total.value if hasattr(search_results.hits.total, 'value') else 0
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

