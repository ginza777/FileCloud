"""
Core API module
"""
from .views import *
from .urls import urlpatterns as core_urls

__all__ = [
    'FeedbackCreateView',
    'core_urls'
]
