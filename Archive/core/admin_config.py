from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import path, include
from django.template.response import TemplateResponse
from apps.core_api.admin_panel.admin_dashboard import admin_dashboard

class CustomAdminSite(admin.AdminSite):
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('dashboard/', self.admin_view(admin_dashboard), name='admin_dashboard'),
        ]
        return custom_urls + urls

    def index(self, request, extra_context=None):
        # Redirect admin index to custom dashboard
        if request.path == '/admin/':
            return HttpResponseRedirect('/admin/dashboard/')
        return super().index(request, extra_context)

# Replace default admin site with custom one
admin.site = CustomAdminSite()
