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

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
