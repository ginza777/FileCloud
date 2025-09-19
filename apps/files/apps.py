from django.apps import AppConfig


class BotConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.files'

    def ready(self):
        """
        Initialize backup schedule when Django starts
        """
        from .backup_tasks import create_backup_schedule
        create_backup_schedule()
