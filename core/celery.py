import os
from celery import Celery
from dotenv import load_dotenv
from celery.schedules import crontab

# Load environment variables
load_dotenv()

# Set the default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

# Initialize Celery app
app = Celery('core')

# Configure Celery using environment variables
app.conf.update(
    BROKER_URL=os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0'),
    RESULT_BACKEND=os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0'),
    ACCEPT_CONTENT=['json'],
    TASK_SERIALIZER='json',
    RESULT_SERIALIZER='json',
    TIMEZONE=os.getenv('CELERY_TIMEZONE', 'UTC'),
    CELERY_TASK_TRACK_STARTED=True,
    CELERY_TASK_TIME_LIMIT=int(os.getenv('CELERY_TASK_TIME_LIMIT', 30 * 60)),
    beat_scheduler='django_celery_beat.schedulers:DatabaseScheduler',
)

app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# Import backup tasks to register them
from apps.files import backup_tasks

# Periodic tasks
app.conf.beat_schedule = {
    'cleanup-temp-files': {
        'task': 'apps.files.tasks.cleanup_old_temp_files_task',
        'schedule': crontab(hour=2, minute=0),  # Har kuni soat 2:00 da
    },
    'cleanup-old-files': {
        'task': 'apps.files.tasks.cleanup_old_files_task',
        'schedule': crontab(minute=0, hour='*/6'),  # Har 6 soatda bir marta
    },
}

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
