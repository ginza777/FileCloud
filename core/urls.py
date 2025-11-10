"""
URL configuration for core project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

# Import all admin configurations
import apps.bot.admin  # noqa
import apps.files.admin  # noqa
import apps.core_api.admin  # noqa

from django.contrib import admin
from apps.core_api.api.web.views import index_view
from apps.core_api.admin_panel.admin_dashboard import admin_dashboard
from apps.core_api.admin_panel.dashboard_api import dashboard_stats_api, dashboard_charts_api, dashboard_activities_api, dashboard_health_api
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from rest_framework import permissions

schema_view = get_schema_view(
    openapi.Info(
        title="FileFinder API",
        default_version='v1',
        description="API documentation for FileFinder project",
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
)

# Replace admin.site.index with custom dashboard
admin.site.index_template = 'admin/dashboard.html'

urlpatterns = [
    path('', index_view, name='index'),
    # Admin API endpoints for dashboard
    path('admin/api/stats/', dashboard_stats_api, name='dashboard_stats_api'),
    path('admin/api/charts/', dashboard_charts_api, name='dashboard_charts_api'),
    path('admin/api/activities/', dashboard_activities_api, name='dashboard_activities_api'),
    path('admin/api/health/', dashboard_health_api, name='dashboard_health_api'),
    # Main admin URLs
    path('admin/', admin.site.urls),
    # Other URLs
    path('api/', include('apps.core_api.urls')),
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    path('api/bot/', include('apps.bot.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
else:
    # Production uchun static fayllar
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
