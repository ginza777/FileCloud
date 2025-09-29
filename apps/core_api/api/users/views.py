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

from apps.bot.models import *
from apps.core_api.serializers import UserSerializer, UserDetailSerializer, UserStatsSerializer
from apps.bot.permissions import BOT_API_PERMISSION_CLASSES

User = get_user_model()

__all__ = [
    'UserListCreateView',
    'UserDetailView', 
    'UserStatsView'
]


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
