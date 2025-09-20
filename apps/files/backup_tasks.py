import os
import subprocess
from celery import shared_task
from django.conf import settings
import logging
from django_celery_beat.models import PeriodicTask, IntervalSchedule
from datetime import datetime

logger = logging.getLogger(__name__)

@shared_task(name="create_database_backup")
def create_database_backup():
    """
    Creates a backup of the PostgreSQL database using pg_dump.
    The backup file is stored in the 'backups/postgres/daily' directory.
    Any existing backup file is removed before creating a new one.
    """
    try:
        db_name = settings.DATABASES['default']['NAME']
        db_user = settings.DATABASES['default']['USER']
        db_password = settings.DATABASES['default']['PASSWORD']
        db_host = settings.DATABASES['default']['HOST']
        db_port = settings.DATABASES['default']['PORT']

        # Create backup directory if it doesn't exist
        backup_dir = os.path.join(settings.BASE_DIR, 'backups', 'postgres', 'daily')
        os.makedirs(backup_dir, exist_ok=True)

        # Generate backup filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f'backup_{timestamp}.sql'
        backup_file_path = os.path.join(backup_dir, backup_filename)

        # Remove old backups (keep only the last 5)
        existing_backups = sorted([f for f in os.listdir(backup_dir) if f.endswith('.sql')])
        while len(existing_backups) >= 5:
            oldest_backup = os.path.join(backup_dir, existing_backups[0])
            os.remove(oldest_backup)
            logger.info(f"Removed old backup: {oldest_backup}")
            existing_backups.pop(0)

        # Command to execute pg_dump
        command = [
            'pg_dump',
            f'--dbname=postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}',
            '-f',
            backup_file_path,
            '--clean',
            '--no-owner',
            '--no-privileges',
        ]

        logger.info(f"Starting database backup to {backup_filename}...")
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()

        if process.returncode == 0:
            logger.info(f"Database backup created successfully: {backup_filename}")
            return f"Backup created successfully: {backup_filename}"
        else:
            error_msg = f"Database backup failed. Error: {stderr.decode('utf-8')}"
            logger.error(error_msg)
            raise Exception(error_msg)

    except Exception as e:
        logger.error(f"An error occurred during database backup: {str(e)}")
        raise

# Replace async version with sync idempotent creator
def create_backup_schedule():
    """Synchronously ensure 3-hour backup periodic task exists (idempotent)."""
    try:
        schedule, _ = IntervalSchedule.objects.get_or_create(every=3, period=IntervalSchedule.HOURS)
        task_name = 'Database Backup Every 3 Hours'
        task_kwargs = {
            'task': 'create_database_backup',
            'interval': schedule,
            'enabled': True,
            'description': 'Creates a backup of the PostgreSQL database every 3 hours'
        }
        periodic_task, created = PeriodicTask.objects.get_or_create(name=task_name, defaults=task_kwargs)
        if not created:
            # Update the existing task if needed
            for key, value in task_kwargs.items():
                setattr(periodic_task, key, value)
            periodic_task.save()
        logger.info("Database backup schedule ensured (sync)")
    except Exception as e:
        logger.error(f"Error ensuring backup schedule: {e}")
