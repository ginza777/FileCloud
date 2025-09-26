from rest_framework import generics, status, filters, permissions
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q, Count, Avg
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_cookie
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

from apps.bot.models import User, Broadcast, BroadcastRecipient, SubscribeChannel, Location
from apps.files.models import SearchQuery, Document, Product, SiteToken, ParseProgress
from .serializers import (
    UserSerializer, UserDetailSerializer, BroadcastSerializer, BroadcastCreateSerializer,
    BroadcastRecipientSerializer, SubscribeChannelSerializer, LocationSerializer,
    SearchQuerySerializer, UserStatsSerializer, BroadcastStatsSerializer,
    SearchStatsSerializer, LocationStatsSerializer, DocumentSerializer,
    ProductSerializer, SiteTokenSerializer, ParseProgressSerializer, DocumentStatsSerializer,
    FeedbackSerializer
)
from .models import Feedback
from apps.bot.tasks import send_message_to_user_task
from apps.bot.permissions import BOT_API_PERMISSION_CLASSES

User = get_user_model()


# Bot API Views
class UserListCreateView(generics.ListCreateAPIView):
    """List all users or create a new user"""
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = BOT_API_PERMISSION_CLASSES
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['username', 'first_name', 'last_name']
    ordering_fields = ['username', 'first_name', 'last_name', 'date_joined']
    ordering = ['-date_joined']

    @method_decorator(cache_page(60 * 10))  # Cache for 10 minutes
    @method_decorator(vary_on_cookie)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class UserDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update or delete a user"""
    queryset = User.objects.all()
    serializer_class = UserDetailSerializer
    permission_classes = BOT_API_PERMISSION_CLASSES
    lookup_field = 'id'

    def get_queryset(self):
        return User.objects.all()


class UserStatsView(APIView):
    """User statistics and analytics"""
    permission_classes = [permissions.IsAuthenticated]

    @method_decorator(cache_page(60 * 5))  # Cache for 5 minutes
    def get(self, request):
        # Basic statistics
        total_users = User.objects.count()
        active_users = User.objects.filter(
            last_active__gte=timezone.now() - timedelta(days=1)
        ).count()
        admin_users = User.objects.filter(is_admin=True).count()
        blocked_users = User.objects.filter(is_blocked=True).count()

        # Users by language
        users_by_language = User.objects.values('selected_language').annotate(
            count=Count('id')
        ).order_by('-count')

        # Recent users
        recent_users = User.objects.order_by('-created_at')[:10]

        data = {
            'total_users': total_users,
            'active_users': active_users,
            'admin_users': admin_users,
            'blocked_users': blocked_users,
            'users_by_language': {item['selected_language']: item['count'] for item in users_by_language},
            'recent_users': UserSerializer(recent_users, many=True).data,
        }

        serializer = UserStatsSerializer(data)
        return Response(serializer.data)


class SubscribeChannelListCreateView(generics.ListCreateAPIView):
    """List all subscribe channels or create a new one"""
    queryset = SubscribeChannel.objects.all()
    serializer_class = SubscribeChannelSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['active', 'private']
    search_fields = ['channel_username', 'channel_id']
    ordering_fields = ['channel_username', 'created_at']
    ordering = ['channel_username']

    @method_decorator(cache_page(60 * 15))  # Cache for 15 minutes
    @method_decorator(vary_on_cookie)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class SubscribeChannelDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update or delete a subscribe channel"""
    queryset = SubscribeChannel.objects.all()
    serializer_class = SubscribeChannelSerializer
    permission_classes = [permissions.IsAuthenticated]


class LocationListCreateView(generics.ListCreateAPIView):
    """List all locations or create a new one"""
    queryset = Location.objects.select_related('user')
    serializer_class = LocationSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['user']
    search_fields = ['user__username', 'user__first_name']
    ordering_fields = ['created_at']
    ordering = ['-created_at']

    @method_decorator(cache_page(60 * 10))  # Cache for 10 minutes
    @method_decorator(vary_on_cookie)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class LocationDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update or delete a location"""
    queryset = Location.objects.select_related('user')
    serializer_class = LocationSerializer
    permission_classes = [permissions.IsAuthenticated]


class LocationStatsView(APIView):
    """Location statistics and analytics"""
    permission_classes = [permissions.IsAuthenticated]

    @method_decorator(cache_page(60 * 5))  # Cache for 5 minutes
    def get(self, request):
        total_locations = Location.objects.count()
        unique_users_with_location = Location.objects.values('user').distinct().count()
        recent_locations = Location.objects.select_related('user').order_by('-created_at')[:10]

        data = {
            'total_locations': total_locations,
            'unique_users_with_location': unique_users_with_location,
            'recent_locations': LocationSerializer(recent_locations, many=True).data,
        }

        serializer = LocationStatsSerializer(data)
        return Response(serializer.data)


class SearchQueryListCreateView(generics.ListCreateAPIView):
    """List all search queries or create a new one"""
    queryset = SearchQuery.objects.select_related('user')
    serializer_class = SearchQuerySerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_deep_search', 'found_results']
    search_fields = ['query_text', 'user__username']
    ordering_fields = ['created_at', 'found_results']
    ordering = ['-created_at']

    @method_decorator(cache_page(60 * 5))  # Cache for 5 minutes
    @method_decorator(vary_on_cookie)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class SearchQueryDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update or delete a search query"""
    queryset = SearchQuery.objects.select_related('user')
    serializer_class = SearchQuerySerializer
    permission_classes = [permissions.IsAuthenticated]


class SearchStatsView(APIView):
    """Search statistics and analytics"""
    permission_classes = [permissions.IsAuthenticated]

    @method_decorator(cache_page(60 * 5))  # Cache for 5 minutes
    def get(self, request):
        total_searches = SearchQuery.objects.count()
        deep_searches = SearchQuery.objects.filter(is_deep_search=True).count()
        regular_searches = SearchQuery.objects.filter(is_deep_search=False).count()
        
        avg_results = SearchQuery.objects.aggregate(
            avg_results=Avg('found_results')
        )['avg_results'] or 0

        # Popular queries
        popular_queries = SearchQuery.objects.values('query_text').annotate(
            count=Count('id')
        ).order_by('-count')[:10]

        data = {
            'total_searches': total_searches,
            'deep_searches': deep_searches,
            'regular_searches': regular_searches,
            'average_results': round(avg_results, 2),
            'popular_queries': list(popular_queries),
        }

        serializer = SearchStatsSerializer(data)
        return Response(serializer.data)


class BroadcastListCreateView(generics.ListCreateAPIView):
    """List all broadcasts or create a new one"""
    queryset = Broadcast.objects.prefetch_related('recipients')
    serializer_class = BroadcastSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status']
    ordering_fields = ['created_at', 'scheduled_time']
    ordering = ['-created_at']

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return BroadcastCreateSerializer
        return BroadcastSerializer

    @method_decorator(cache_page(60 * 5))  # Cache for 5 minutes
    @method_decorator(vary_on_cookie)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class BroadcastDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update or delete a broadcast"""
    queryset = Broadcast.objects.prefetch_related('recipients')
    serializer_class = BroadcastSerializer
    permission_classes = [permissions.IsAuthenticated]


class BroadcastRecipientListView(generics.ListAPIView):
    """List all broadcast recipients"""
    queryset = BroadcastRecipient.objects.select_related('broadcast', 'user')
    serializer_class = BroadcastRecipientSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['broadcast', 'status']
    search_fields = ['user__username', 'user__first_name']
    ordering_fields = ['sent_at', 'created_at']
    ordering = ['-sent_at']


class BroadcastRecipientDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update or delete a broadcast recipient"""
    queryset = BroadcastRecipient.objects.select_related('broadcast', 'user')
    serializer_class = BroadcastRecipientSerializer
    permission_classes = [permissions.IsAuthenticated]


class BroadcastStatsView(APIView):
    """Broadcast statistics and analytics"""
    permission_classes = [permissions.IsAuthenticated]

    @method_decorator(cache_page(60 * 5))  # Cache for 5 minutes
    def get(self, request):
        total_broadcasts = Broadcast.objects.count()
        pending_broadcasts = Broadcast.objects.filter(status=Broadcast.Status.PENDING).count()
        sent_broadcasts = Broadcast.objects.filter(status=Broadcast.Status.SENT).count()
        failed_broadcasts = Broadcast.objects.filter(status=Broadcast.Status.FAILED).count()

        total_recipients = BroadcastRecipient.objects.count()
        successful_deliveries = BroadcastRecipient.objects.filter(
            status=BroadcastRecipient.Status.SENT
        ).count()
        failed_deliveries = BroadcastRecipient.objects.filter(
            status=BroadcastRecipient.Status.FAILED
        ).count()

        data = {
            'total_broadcasts': total_broadcasts,
            'pending_broadcasts': pending_broadcasts,
            'sent_broadcasts': sent_broadcasts,
            'failed_broadcasts': failed_broadcasts,
            'total_recipients': total_recipients,
            'successful_deliveries': successful_deliveries,
            'failed_deliveries': failed_deliveries,
        }

        serializer = BroadcastStatsSerializer(data)
        return Response(serializer.data)


class BroadcastSendView(APIView):
    """Send broadcast to all users"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        message_text = request.data.get('message_text')
        scheduled_time = request.data.get('scheduled_time')
        
        if not message_text:
            return Response(
                {'error': 'Message text is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # Create broadcast
        broadcast = Broadcast.objects.create(
            status=Broadcast.Status.PENDING,
            scheduled_time=scheduled_time or timezone.now(),
            from_chat_id=request.data.get('from_chat_id'),
            message_id=request.data.get('message_id')
        )

        # Get all active users
        users = User.objects.filter(is_blocked=False, left=False)
        
        # Create recipients
        recipients = []
        for user in users:
            recipient = BroadcastRecipient.objects.create(
                broadcast=broadcast,
                user=user,
                status=BroadcastRecipient.Status.PENDING
            )
            recipients.append(recipient)

        # Send messages via Celery
        for recipient in recipients:
            send_message_to_user_task.delay(recipient.id)

        return Response({
            'message': 'Broadcast created successfully',
            'broadcast_id': broadcast.id,
            'recipients_count': len(recipients)
        }, status=status.HTTP_201_CREATED)


class BroadcastRetryView(APIView):
    """Retry failed broadcast recipients"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, broadcast_id):
        try:
            broadcast = Broadcast.objects.get(id=broadcast_id)
        except Broadcast.DoesNotExist:
            return Response(
                {'error': 'Broadcast not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )

        failed_recipients = broadcast.recipients.filter(
            status=BroadcastRecipient.Status.FAILED
        )

        retry_count = 0
        for recipient in failed_recipients:
            recipient.status = BroadcastRecipient.Status.PENDING
            recipient.error_message = None
            recipient.save()
            send_message_to_user_task.delay(recipient.id)
            retry_count += 1

        return Response({
            'message': f'Retried {retry_count} failed recipients',
            'retry_count': retry_count
        })


# Files app API views
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


# Feedback API
class FeedbackCreateView(generics.CreateAPIView):
    queryset = Feedback.objects.all()
    serializer_class = FeedbackSerializer
    permission_classes = [permissions.AllowAny]