from django.urls import path
from .handler import bot_webhook

# Bot URLs - only webhook endpoint, API endpoints moved to core_api
urlpatterns = [
    # Webhook endpoint
    path('webhook/', bot_webhook, name='bot_webhook'),

]