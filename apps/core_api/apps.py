from django.apps import AppConfig

class CoreApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core_api'
    verbose_name = 'Core API'

    def ready(self):
        # Import signals when app is ready
        try:
            import apps.core_api.signals  # noqa
        except ImportError:
            pass
