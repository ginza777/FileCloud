"""
Bot API module
"""
from .views import *
from .urls import urlpatterns as bot_urls

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
    'BroadcastRecipientDetailView',
    'bot_urls'
]
