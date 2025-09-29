"""
Files API URLs
"""
from django.urls import path
from . import views

urlpatterns = [
    # Documents
    path('documents/', views.DocumentListCreateView.as_view(), name='document-list-create'),
    path('documents/<uuid:pk>/', views.DocumentDetailView.as_view(), name='document-detail'),
    path('documents/stats/', views.DocumentStatsView.as_view(), name='document-stats'),
    
    # Products
    path('products/', views.ProductListCreateView.as_view(), name='product-list-create'),
    path('products/<int:pk>/', views.ProductDetailView.as_view(), name='product-detail'),
    
    # Site Tokens
    path('tokens/', views.SiteTokenListCreateView.as_view(), name='token-list-create'),
    path('tokens/<int:pk>/', views.SiteTokenDetailView.as_view(), name='token-detail'),
    
    # Parse Progress
    path('parse-progress/', views.ParseProgressListCreateView.as_view(), name='parse-progress-list-create'),
    path('parse-progress/<int:pk>/', views.ParseProgressDetailView.as_view(), name='parse-progress-detail'),
]
