"""
Files API Views
==============

Bu modul fayllar bilan bog'liq API endpoint'larini o'z ichiga oladi.
REST API orqali hujjatlar, mahsulotlar va boshqa ma'lumotlar bilan ishlash imkonini beradi.

API Endpoint'lar:
- DocumentListCreateView: Hujjatlar ro'yxati va yangi hujjat yaratish
- DocumentDetailView: Hujjat ma'lumotlarini olish/yangilash/o'chirish
- DocumentStatsView: Hujjatlar statistikasi
- ProductListCreateView: Mahsulotlar ro'yxati va yangi mahsulot yaratish
- ProductDetailView: Mahsulot ma'lumotlarini olish/yangilash/o'chirish
- SiteTokenListCreateView: Sayt tokenlari ro'yxati
- SiteTokenDetailView: Sayt token ma'lumotlari

Xususiyatlar:
- Caching: 10 daqiqa cache
- Filtering: Status, search, ordering
- Permissions: Faqat autentifikatsiya qilingan foydalanuvchilar
- Pagination: Avtomatik pagination
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
    DocumentStatsSerializer
)

__all__ = [
    'DocumentListCreateView',
    'DocumentDetailView',
    'DocumentStatsView',
    'ProductListCreateView',
    'ProductDetailView',
    'SiteTokenListCreateView',
    'SiteTokenDetailView',
]


class DocumentListCreateView(generics.ListCreateAPIView):
    """
    Hujjatlar ro'yxatini ko'rsatish va yangi hujjat yaratish uchun API view.
    
    Bu view:
    - GET: Barcha hujjatlar ro'yxatini qaytaradi
    - POST: Yangi hujjat yaratadi
    - Filtering: Status bo'yicha filtrlash
    - Search: Fayl URL bo'yicha qidiruv
    - Ordering: Vaqt bo'yicha tartiblash
    - Caching: 10 daqiqa cache
    
    Permissions:
    - Faqat autentifikatsiya qilingan foydalanuvchilar
    
    Returns:
    - GET: Hujjatlar ro'yxati (paginated)
    - POST: Yaratilgan hujjat ma'lumotlari
    """
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
        """
        Hujjatlar ro'yxatini cache bilan qaytaradi.
        
        Args:
            request: HTTP request obyekti
            *args: Positional argumentlar
            **kwargs: Keyword argumentlar
        
        Returns:
            Response: Hujjatlar ro'yxati (cached)
        """
        return super().get(request, *args, **kwargs)


class DocumentDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Hujjat ma'lumotlarini olish, yangilash va o'chirish uchun API view.
    
    Bu view:
    - GET: Hujjat ma'lumotlarini qaytaradi
    - PUT/PATCH: Hujjat ma'lumotlarini yangilaydi
    - DELETE: Hujjatni o'chiradi
    - Permissions: Faqat autentifikatsiya qilingan foydalanuvchilar
    
    Args:
        pk: Hujjat ID'si (UUID)
    
    Returns:
    - GET: Hujjat ma'lumotlari
    - PUT/PATCH: Yangilangan hujjat ma'lumotlari
    - DELETE: Bo'sh response (204 status)
    """
    queryset = Document.objects.all()
    serializer_class = DocumentSerializer
    permission_classes = [permissions.IsAuthenticated]


class ProductListCreateView(generics.ListCreateAPIView):
    """
    Mahsulotlar ro'yxatini ko'rsatish va yangi mahsulot yaratish uchun API view.
    
    Bu view:
    - GET: Barcha mahsulotlar ro'yxatini qaytaradi
    - POST: Yangi mahsulot yaratadi
    - Optimized queryset: select_related bilan
    - Filtering: Document bo'yicha
    - Search: Title, slug va parsed_content bo'yicha qidiruv
    - Ordering: ID, title va vaqt bo'yicha tartiblash
    - Caching: 10 daqiqa cache
    
    Permissions:
    - Faqat autentifikatsiya qilingan foydalanuvchilar
    
    Returns:
    - GET: Mahsulotlar ro'yxati (paginated, cached)
    - POST: Yaratilgan mahsulot ma'lumotlari
    """
    queryset = Product.objects.select_related('document').exclude(blocked=True)
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
        """
        Mahsulotlar ro'yxatini cache bilan qaytaradi.
        
        Args:
            request: HTTP request obyekti
            *args: Positional argumentlar
            **kwargs: Keyword argumentlar
        
        Returns:
            Response: Mahsulotlar ro'yxati (cached)
        """
        return super().get(request, *args, **kwargs)


class ProductDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update or delete a product"""
    queryset = Product.objects.select_related('document').exclude(blocked=True)
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


# ParseProgress view'lari o'chirildi - ParseProgress model o'chirilgan


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
        total_products = Product.objects.exclude(blocked=True).count()
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
