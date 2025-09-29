"""
Files API module
"""
from .views import *
from .urls import urlpatterns as files_urls

__all__ = [
    'DocumentListCreateView',
    'DocumentDetailView',
    'DocumentStatsView',
    'ProductListCreateView',
    'ProductDetailView',
    'SiteTokenListCreateView',
    'SiteTokenDetailView',
    'ParseProgressListCreateView',
    'ParseProgressDetailView',
    'files_urls'
]
