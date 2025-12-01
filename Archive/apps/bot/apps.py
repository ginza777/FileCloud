from django.apps import AppConfig
import asyncio
import os


class CommonConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.bot'
    verbose_name = 'Telegram Bot'

