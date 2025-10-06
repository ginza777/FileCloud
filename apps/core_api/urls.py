from django.urls import path, include

# Core API URLs
urlpatterns = [
    # User API endpoints
    path('users/', include('apps.core_api.api.users.urls')),
    
    # Bot API endpoints
    path('bot/', include('apps.core_api.api.bot.urls')),
    
    # Files API endpoints
    path('files/', include('apps.core_api.api.files.urls')),
    
    # Web API endpoints
    path('web/', include('apps.core_api.api.web.urls')),
    
    # Core API endpoints
    path('', include('apps.core_api.api.core.urls')),
]