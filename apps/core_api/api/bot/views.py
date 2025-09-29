"""
Bot API Views
"""
from rest_framework import generics, status, filters, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Count, Avg
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_cookie
from django.utils import timezone

from apps.bot.models import *
from apps.core_api.serializers import (
    SubscribeChannelSerializer, LocationSerializer, SearchQuerySerializer,
    LocationStatsSerializer, SearchStatsSerializer, BroadcastSerializer,
    BroadcastCreateSerializer, BroadcastRecipientSerializer, BroadcastStatsSerializer
)
from apps.bot.tasks import send_message_to_user_task

__all__ = [
    'SubscribeChannelListCreateView',
    'SubscribeChannelDetailView',
    'LocationListCreateView',
    'LocationDetailView',
    'LocationStatsView',
    'SearchQueryListCreateView',
    'SearchQueryDetailView',
    'SearchStatsView',
    'BroadcastListCreateView',
    'BroadcastDetailView',
    'BroadcastStatsView',
    'BroadcastSendView',
    'BroadcastRetryView',
    'BroadcastRecipientListView',
    'BroadcastRecipientDetailView'
]


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
