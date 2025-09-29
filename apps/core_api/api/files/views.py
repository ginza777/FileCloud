"""
Files API Views
"""
from rest_framework import generics, status, filters, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_cookie

from apps.files.models import *
from apps.core_api.serializers import (
    DocumentSerializer, ProductSerializer, SiteTokenSerializer, 
    ParseProgressSerializer, DocumentStatsSerializer
)

__all__ = [
    'DocumentListCreateView',
    'DocumentDetailView',
    'DocumentStatsView',
    'ProductListCreateView',
    'ProductDetailView',
    'SiteTokenListCreateView',
    'SiteTokenDetailView',
    'ParseProgressListCreateView',
    'ParseProgressDetailView'
]


class DocumentListCreateView(generics.ListCreateAPIView):
    """List all documents or create a new one"""
    queryset = Document.objects.all()
    serializer_class = DocumentSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['download_status', 'parse_status', 'index_status', 'telegram_status', 'delete_status', 'completed']
    search_fields = ['parse_file_url']
    ordering_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']

    @method_decorator(cache_page(60 * 10))  # Cache for 10 minutes
    @method_decorator(vary_on_cookie)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class DocumentDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update or delete a document"""
    queryset = Document.objects.all()
    serializer_class = DocumentSerializer
    permission_classes = [permissions.IsAuthenticated]


class ProductListCreateView(generics.ListCreateAPIView):
    """List all products or create a new one"""
    queryset = Product.objects.select_related('document')
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['document']
    search_fields = ['title', 'slug', 'parsed_content']
    ordering_fields = ['id', 'title', 'created_at']
    ordering = ['-created_at']

    @method_decorator(cache_page(60 * 10))  # Cache for 10 minutes
    @method_decorator(vary_on_cookie)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class ProductDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update or delete a product"""
    queryset = Product.objects.select_related('document')
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticated]


class SiteTokenListCreateView(generics.ListCreateAPIView):
    """List all site tokens or create a new one"""
    queryset = SiteToken.objects.all()
    serializer_class = SiteTokenSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['name']
    search_fields = ['name']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']

    @method_decorator(cache_page(60 * 15))  # Cache for 15 minutes
    @method_decorator(vary_on_cookie)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class SiteTokenDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update or delete a site token"""
    queryset = SiteToken.objects.all()
    serializer_class = SiteTokenSerializer
    permission_classes = [permissions.IsAuthenticated]


class ParseProgressListCreateView(generics.ListCreateAPIView):
    """List all parse progress records or create a new one"""
    queryset = ParseProgress.objects.all()
    serializer_class = ParseProgressSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['last_run_at', 'created_at']
    ordering = ['-last_run_at']

    @method_decorator(cache_page(60 * 5))  # Cache for 5 minutes
    @method_decorator(vary_on_cookie)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class ParseProgressDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update or delete a parse progress record"""
    queryset = ParseProgress.objects.all()
    serializer_class = ParseProgressSerializer
    permission_classes = [permissions.IsAuthenticated]


class DocumentStatsView(APIView):
    """Document statistics and analytics"""
    permission_classes = [permissions.IsAuthenticated]

    @method_decorator(cache_page(60 * 5))  # Cache for 5 minutes
    def get(self, request):
        total_documents = Document.objects.count()
        completed_documents = Document.objects.filter(completed=True).count()
        pending_documents = Document.objects.filter(
            Q(download_status='pending') | Q(parse_status='pending') | 
            Q(index_status='pending') | Q(telegram_status='pending') | 
            Q(delete_status='pending')
        ).count()
        failed_documents = Document.objects.filter(
            Q(download_status='failed') | Q(parse_status='failed') | 
            Q(index_status='failed') | Q(telegram_status='failed') | 
            Q(delete_status='failed')
        ).count()
        total_products = Product.objects.count()
        recent_documents = Document.objects.order_by('-created_at')[:10]

        data = {
            'total_documents': total_documents,
            'completed_documents': completed_documents,
            'pending_documents': pending_documents,
            'failed_documents': failed_documents,
            'total_products': total_products,
            'recent_documents': DocumentSerializer(recent_documents, many=True).data,
        }

        serializer = DocumentStatsSerializer(data)
        return Response(serializer.data)
