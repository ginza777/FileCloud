from django.core.management.base import BaseCommand
from celery import current_app
from celery.result import AsyncResult
from django_celery_beat.models import PeriodicTask
from apps.files.models import Document
import redis
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Celery tasklarini bekor qiladi va tozalaydi'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Barcha tasklarni majburiy bekor qiladi',
        )
        parser.add_argument(
            '--clear-results',
            action='store_true',
            help='Task natijalarini ham tozalaydi',
        )
        parser.add_argument(
            '--reset-documents',
            action='store_true',
            help='Document pipeline_running flaglarini qayta tiklaydi',
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.WARNING('Celery tasklarini bekor qilish va tozalash boshlandi...')
        )

        # 1. Faol tasklarni bekor qilish
        self.cancel_active_tasks(options['force'])

        # 2. Task natijalarini tozalash
        if options['clear_results']:
            self.clear_task_results()

        # 3. Document flaglarini qayta tiklash
        if options['reset_documents']:
            self.reset_document_flags()

        # 4. Periodic tasklarni tozalash
        self.cleanup_periodic_tasks()

        self.stdout.write(
            self.style.SUCCESS('✅ Celery tasklari muvaffaqiyatli bekor qilindi va tozalandi!')
        )

    def cancel_active_tasks(self, force=False):
        """Faol tasklarni bekor qiladi"""
        self.stdout.write('🔄 Faol tasklarni bekor qilish...')
        
        try:
            # Celery inspect orqali faol tasklarni olish
            inspect = current_app.control.inspect()
            active_tasks = inspect.active()
            
            if not active_tasks:
                self.stdout.write('   Hech qanday faol task topilmadi.')
                return

            cancelled_count = 0
            for worker, tasks in active_tasks.items():
                if tasks:
                    self.stdout.write(f'   Worker {worker} da {len(tasks)} ta faol task topildi')
                    
                    for task in tasks:
                        task_id = task.get('id')
                        task_name = task.get('name', 'Unknown')
                        
                        try:
                            # Taskni bekor qilish
                            current_app.control.revoke(task_id, terminate=force)
                            cancelled_count += 1
                            self.stdout.write(f'   ✅ Task bekor qilindi: {task_name} ({task_id})')
                        except Exception as e:
                            self.stdout.write(
                                self.style.ERROR(f'   ❌ Task bekor qilishda xatolik: {task_name} - {e}')
                            )

            self.stdout.write(f'   📊 Jami {cancelled_count} ta task bekor qilindi.')
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Faol tasklarni olishda xatolik: {e}')
            )

    def clear_task_results(self):
        """Task natijalarini va Redis cache ni tozalaydi"""
        self.stdout.write('🧹 Task natijalarini tozalash...')
        
        try:
            # Redis connection
            redis_url = getattr(settings, 'CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
            r = redis.from_url(redis_url)
            
            # Celery result backend ni tozalash
            result_backend = current_app.backend
            if hasattr(result_backend, 'clear'):
                result_backend.clear()
                self.stdout.write('   ✅ Celery result backend tozalandi')
            
            # Redis keys ni tozalash (Celery uchun)
            celery_keys = r.keys('celery-task-meta-*')
            if celery_keys:
                r.delete(*celery_keys)
                self.stdout.write(f'   ✅ {len(celery_keys)} ta Celery key o\'chirildi')
            
            # Celery beat keys ni tozalash
            beat_keys = r.keys('celery-beat-*')
            if beat_keys:
                r.delete(*beat_keys)
                self.stdout.write(f'   ✅ {len(beat_keys)} ta Celery beat key o\'chirildi')
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Task natijalarini tozalashda xatolik: {e}')
            )

    def reset_document_flags(self):
        """Document pipeline_running flaglarini qayta tiklaydi"""
        self.stdout.write('🔄 Document flaglarini qayta tiklash...')
        
        try:
            # pipeline_running=True bo'lgan documentlarni topish
            locked_documents = Document.objects.filter(pipeline_running=True)
            count = locked_documents.count()
            
            if count > 0:
                # Barcha pipeline_running flaglarini False qilish
                locked_documents.update(pipeline_running=False)
                self.stdout.write(f'   ✅ {count} ta document flagi qayta tiklandi')
            else:
                self.stdout.write('   ℹ️  Qayta tiklash kerak bo\'lgan document topilmadi')
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Document flaglarini qayta tiklashda xatolik: {e}')
            )

    def cleanup_periodic_tasks(self):
        """Periodic tasklarni tozalash"""
        self.stdout.write('🔄 Periodic tasklarni tekshirish...')
        
        try:
            # Barcha periodic tasklarni ko'rsatish
            periodic_tasks = PeriodicTask.objects.all()
            count = periodic_tasks.count()
            
            if count > 0:
                self.stdout.write(f'   📋 {count} ta periodic task topildi:')
                for task in periodic_tasks:
                    status = "✅ Faol" if task.enabled else "⏸️  O'chirilgan"
                    self.stdout.write(f'     - {task.name}: {status}')
            else:
                self.stdout.write('   ℹ️  Hech qanday periodic task topilmadi')
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Periodic tasklarni tekshirishda xatolik: {e}')
            )

    def get_task_statistics(self):
        """Task statistikalarini ko'rsatish"""
        self.stdout.write('\n📊 Task statistikasi:')
        
        try:
            inspect = current_app.control.inspect()
            
            # Faol tasklar
            active = inspect.active()
            active_count = sum(len(tasks) for tasks in (active or {}).values())
            
            # Navbatdagi tasklar
            scheduled = inspect.scheduled()
            scheduled_count = sum(len(tasks) for tasks in (scheduled or {}).values())
            
            # Reserve qilingan tasklar
            reserved = inspect.reserved()
            reserved_count = sum(len(tasks) for tasks in (reserved or {}).values())
            
            self.stdout.write(f'   🔄 Faol tasklar: {active_count}')
            self.stdout.write(f'   ⏰ Rejalashtirilgan tasklar: {scheduled_count}')
            self.stdout.write(f'   📦 Reserve qilingan tasklar: {reserved_count}')
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Statistikani olishda xatolik: {e}')
            )
