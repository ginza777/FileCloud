"""
Users API module
"""
from .views import *
from .urls import urlpatterns as users_urls

__all__ = [
    'UserListCreateView',
    'UserDetailView', 
    'UserStatsView',
    'users_urls'
]
