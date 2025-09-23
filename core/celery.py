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

# Periodic tasks configuration
# app.conf.beat_schedule = {
#     'File System Cleanup Every 20 Minutes': {
#         'task': 'apps.files.tasks.cleanup_files_task',
#         'schedule': 20 * 60,  # 20 minutes in seconds
#     },
#     'Database Backup Every 5 Hours': {
#         'task': 'apps.files.backup_tasks.create_database_backup',
#         'schedule': 5 * 60 * 60,  # 5 hours in seconds
#     },
#     'Document Processing Every 3 Hours': {
#         'task': 'apps.files.tasks.soft_uz_process_documents',
#         'schedule': 3 * 60 * 60,  # 3 hours in seconds
#     },
#     'Soff.uz Data Parsing Weekly': {
#         'task': 'apps.files.tasks.soft_uz_parse',
#         'schedule': 7 * 24 * 60 * 60,  # 7 days (1 week) in seconds
#     },
# }

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')