from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# Create router for API views
router = DefaultRouter()

# Core API URLs
urlpatterns = [
    # Bot API endpoints
    path('bot/users/', views.UserListCreateView.as_view(), name='user-list-create'),
    path('bot/users/<int:id>/', views.UserDetailView.as_view(), name='user-detail'),
    path('bot/users/stats/', views.UserStatsView.as_view(), name='user-stats'),
    
    # Subscribe Channel endpoints
    path('bot/channels/', views.SubscribeChannelListCreateView.as_view(), name='channel-list-create'),
    path('bot/channels/<int:pk>/', views.SubscribeChannelDetailView.as_view(), name='channel-detail'),
    
    # Location endpoints
    path('bot/locations/', views.LocationListCreateView.as_view(), name='location-list-create'),
    path('bot/locations/<int:pk>/', views.LocationDetailView.as_view(), name='location-detail'),
    path('bot/locations/stats/', views.LocationStatsView.as_view(), name='location-stats'),
    
    # Search Query endpoints
    path('bot/searches/', views.SearchQueryListCreateView.as_view(), name='search-list-create'),
    path('bot/searches/<int:pk>/', views.SearchQueryDetailView.as_view(), name='search-detail'),
    path('bot/searches/stats/', views.SearchStatsView.as_view(), name='search-stats'),
    
    # Broadcast endpoints
    path('bot/broadcasts/', views.BroadcastListCreateView.as_view(), name='broadcast-list-create'),
    path('bot/broadcasts/<int:pk>/', views.BroadcastDetailView.as_view(), name='broadcast-detail'),
    path('bot/broadcasts/send/', views.BroadcastSendView.as_view(), name='broadcast-send'),
    path('bot/broadcasts/<int:broadcast_id>/retry/', views.BroadcastRetryView.as_view(), name='broadcast-retry'),
    path('bot/broadcasts/stats/', views.BroadcastStatsView.as_view(), name='broadcast-stats'),
    
    # Broadcast Recipient endpoints
    path('bot/recipients/', views.BroadcastRecipientListView.as_view(), name='recipient-list'),
    path('bot/recipients/<int:pk>/', views.BroadcastRecipientDetailView.as_view(), name='recipient-detail'),
    
    # Files app endpoints
    path('files/documents/', views.DocumentListCreateView.as_view(), name='document-list-create'),
    path('files/documents/<uuid:pk>/', views.DocumentDetailView.as_view(), name='document-detail'),
    path('files/documents/stats/', views.DocumentStatsView.as_view(), name='document-stats'),
    
    path('files/products/', views.ProductListCreateView.as_view(), name='product-list-create'),
    path('files/products/<int:pk>/', views.ProductDetailView.as_view(), name='product-detail'),
    
    path('files/tokens/', views.SiteTokenListCreateView.as_view(), name='token-list-create'),
    path('files/tokens/<int:pk>/', views.SiteTokenDetailView.as_view(), name='token-detail'),
    
    path('files/parse-progress/', views.ParseProgressListCreateView.as_view(), name='parse-progress-list-create'),
    path('files/parse-progress/<int:pk>/', views.ParseProgressDetailView.as_view(), name='parse-progress-detail'),
]