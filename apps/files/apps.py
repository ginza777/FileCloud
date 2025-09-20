from django.apps import AppConfig
from django.db.models.signals import post_migrate


def setup_backup_schedule(sender, **kwargs):
    from .backup_tasks import create_backup_schedule

    create_backup_schedule()


class FilesConfig(AppConfig):
    name = 'apps.files'

    def ready(self):
        # Connect post_migrate signal to ensure backup schedule is created after migrations
        post_migrate.connect(setup_backup_schedule, sender=self)
