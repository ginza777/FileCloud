"""
Core API Admin Configuration
=============================

Bu modul core_api app uchun admin konfiguratsiyalarini import qiladi.
"""

from django.contrib import admin

# Admin panel konfiguratsiyalarini import qilish
from apps.core_api.admin_panel.admin import *  # noqa: F401,F403
