"""
Admin Site Customization
========================

Bu modul Django admin site'ni customize qiladi va dashboard linkini qo'shadi.
"""

from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _


class CustomAdminSite(admin.AdminSite):
    """
    Custom admin site with dashboard integration.
    """
    
    site_header = _("FileFinder Administration")
    site_title = _("FileFinder Admin")
    index_title = _("Welcome to FileFinder Administration")
    
    def index(self, request, extra_context=None):
        """
        Admin index page with dashboard link.
        """
        extra_context = extra_context or {}
        extra_context.update({
            'dashboard_url': reverse('admin_dashboard'),
            'has_dashboard': True,
        })
        return super().index(request, extra_context)
    
    def get_urls(self):
        """
        Add dashboard URL to admin URLs.
        """
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path('dashboard/', self.admin_view(self.dashboard_view), name='dashboard'),
        ]
        return custom_urls + urls
    
    def dashboard_view(self, request):
        """
        Dashboard view for admin.
        """
        from apps.core_api.admin_dashboard import admin_dashboard
        return admin_dashboard(request)


# Custom admin site instance
admin_site = CustomAdminSite(name='admin')

# Register all models with custom admin site
from django.contrib.auth.models import User, Group
from django.contrib.auth.admin import UserAdmin, GroupAdmin

admin_site.register(User, UserAdmin)
admin_site.register(Group, GroupAdmin)

# Register app models
from apps.files.models import *
from apps.files.admin import *
from apps.bot.models import *
from apps.bot.admin_panel.admin import *

# Register with custom admin site
admin_site.register(Document, DocumentAdmin)
admin_site.register(Product, ProductAdmin)
admin_site.register(SiteToken, SiteTokenAdmin)
admin_site.register(DocumentError, DocumentErrorAdmin)
admin_site.register(DocumentImage, DocumentImageAdmin)
admin_site.register(SearchQuery, SearchQueryAdmin)

admin_site.register(SubscribeChannel, SubscribeChannelAdmin)
# TelegramUser is registered via apps.bot.admin_panel.admin import
admin_site.register(Location, LocationAdmin)
admin_site.register(Broadcast, BroadcastAdmin)
admin_site.register(BroadcastRecipient)

# Register django-celery-results models
try:
    from django_celery_results.models import TaskResult
    from django_celery_results.admin import TaskResultAdmin
    admin_site.register(TaskResult, TaskResultAdmin)
except ImportError:
    pass

# Register django-celery-beat models
try:
    from django_celery_beat.models import PeriodicTask, IntervalSchedule, CrontabSchedule
    from django_celery_beat.admin import PeriodicTaskAdmin, IntervalScheduleAdmin, CrontabScheduleAdmin
    admin_site.register(PeriodicTask, PeriodicTaskAdmin)
    admin_site.register(IntervalSchedule, IntervalScheduleAdmin)
    admin_site.register(CrontabSchedule, CrontabScheduleAdmin)
except ImportError:
    pass
