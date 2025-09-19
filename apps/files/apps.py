from django.apps import AppConfig



class FilesConfig(AppConfig):
    name = 'apps.files'

    def ready(self):
        """
        Initialize backup schedule when Django starts
        """
        from .backup_tasks import create_backup_schedule
        create_backup_schedule()

