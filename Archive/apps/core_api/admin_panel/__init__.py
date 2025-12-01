"""
Admin Panel Components
===================

Bu paket admin panel uchun barcha komponentlarni o'z ichiga oladi:
- admin.py: Admin model registrations
- admin_dashboard.py: Dashboard konfiguratsiyalari
- admin_dashboard_api.py: Dashboard API
- dashboard_stats.py: Dashboard statistics
- dashboard_charts.py: Dashboard charts
"""

from django.contrib import admin

# Register your models here
default_app_config = 'apps.core_api.apps.CoreApiConfig'
