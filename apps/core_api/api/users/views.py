"""
User API Views
"""
from rest_framework import generics, status, filters, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Count
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_cookie
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

from apps.bot.models import TelegramUser
from apps.core_api.serializers import UserSerializer, UserDetailSerializer, UserStatsSerializer
from apps.bot.permissions import BOT_API_PERMISSION_CLASSES

# Django's built-in User model for admin panel
DjangoUser = get_user_model()

__all__ = [
    'UserListCreateView',
    'UserDetailView', 
    'UserStatsView'
]


class UserListCreateView(generics.ListCreateAPIView):
    """List all Django admin users or create a new user"""
    queryset = DjangoUser.objects.all()
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
    """Retrieve, update or delete a Django admin user"""
    queryset = DjangoUser.objects.all()
    serializer_class = UserDetailSerializer
    permission_classes = BOT_API_PERMISSION_CLASSES
    lookup_field = 'id'

    def get_queryset(self):
        return DjangoUser.objects.all()


class UserStatsView(APIView):
    """TelegramUser statistics and analytics"""
    permission_classes = [permissions.IsAuthenticated]

    @method_decorator(cache_page(60 * 5))  # Cache for 5 minutes
    def get(self, request):
        # Basic statistics for TelegramUser
        total_users = TelegramUser.objects.count()
        active_users = TelegramUser.objects.filter(
            last_active__gte=timezone.now() - timedelta(days=1)
        ).count()
        admin_users = TelegramUser.objects.filter(is_admin=True).count()
        blocked_users = TelegramUser.objects.filter(is_blocked=True).count()

        # Users by language
        users_by_language = TelegramUser.objects.values('selected_language').annotate(
            count=Count('id')
        ).order_by('-count')

        # Recent users
        recent_users = TelegramUser.objects.order_by('-created_at')[:10]

        data = {
            'total_users': total_users,
            'active_users': active_users,
            'admin_users': admin_users,
            'blocked_users': blocked_users,
            'users_by_language': {item['selected_language']: item['count'] for item in users_by_language},
            'recent_users': [{
                'telegram_id': u.telegram_id,
                'username': u.username,
                'first_name': u.first_name,
                'last_name': u.last_name,
                'full_name': u.full_name,
                'is_admin': u.is_admin,
                'is_blocked': u.is_blocked,
                'created_at': u.created_at.isoformat() if u.created_at else None,
            } for u in recent_users],
        }

        serializer = UserStatsSerializer(data)
        return Response(serializer.data)
