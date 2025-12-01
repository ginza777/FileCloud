"""
Bot API URLs
"""
from django.urls import path
from . import views

urlpatterns = [
    # Subscribe Channels
    path('channels/', views.SubscribeChannelListCreateView.as_view(), name='channel-list-create'),
    path('channels/<int:pk>/', views.SubscribeChannelDetailView.as_view(), name='channel-detail'),
    
    # Locations
    path('locations/', views.LocationListCreateView.as_view(), name='location-list-create'),
    path('locations/<int:pk>/', views.LocationDetailView.as_view(), name='location-detail'),
    path('locations/stats/', views.LocationStatsView.as_view(), name='location-stats'),
    
    # Search Queries
    path('searches/', views.SearchQueryListCreateView.as_view(), name='search-list-create'),
    path('searches/<int:pk>/', views.SearchQueryDetailView.as_view(), name='search-detail'),
    path('searches/stats/', views.SearchStatsView.as_view(), name='search-stats'),
    
    # Broadcasts
    path('broadcasts/', views.BroadcastListCreateView.as_view(), name='broadcast-list-create'),
    path('broadcasts/<int:pk>/', views.BroadcastDetailView.as_view(), name='broadcast-detail'),
    path('broadcasts/send/', views.BroadcastSendView.as_view(), name='broadcast-send'),
    path('broadcasts/<int:broadcast_id>/retry/', views.BroadcastRetryView.as_view(), name='broadcast-retry'),
    path('broadcasts/stats/', views.BroadcastStatsView.as_view(), name='broadcast-stats'),
    
    # Broadcast Recipients
    path('recipients/', views.BroadcastRecipientListView.as_view(), name='recipient-list'),
    path('recipients/<int:pk>/', views.BroadcastRecipientDetailView.as_view(), name='recipient-detail'),
]
