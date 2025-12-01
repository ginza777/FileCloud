"""
Database Wait Command
====================

Bu komanda ma'lumotlar bazasi tayyor bo'lguncha kutadi.
Docker container'larida ma'lumotlar bazasi tayyor bo'lishini kutish uchun ishlatiladi.
"""

import time
from django.core.management.base import BaseCommand
from django.db import connections
from django.db.utils import OperationalError
from django.core.management import call_command


class Command(BaseCommand):
    """
    Ma'lumotlar bazasi tayyor bo'lguncha kutish komandasi.
    
    Bu komanda:
    - Ma'lumotlar bazasi ulanishini tekshiradi
    - Agar ulanish muvaffaqiyatsiz bo'lsa, qayta urinadi
    - Ma'lumotlar bazasi tayyor bo'lguncha kutadi
    """
    help = 'Ma\'lumotlar bazasi tayyor bo\'lguncha kutadi'

    def add_arguments(self, parser):
        """
        Komanda argumentlarini qo'shadi.
        
        Args:
            parser: Argument parser obyekti
        """
        parser.add_argument(
            '--timeout',
            type=int,
            default=60,
            help='Maksimal kutish vaqti (soniya)'
        )
        parser.add_argument(
            '--interval',
            type=int,
            default=1,
            help='Har bir urinish orasidagi vaqt (soniya)'
        )

    def handle(self, *args, **options):
        """
        Komandani bajaradi.
        
        Args:
            *args: Pozitsion argumentlar
            **options: Kalit-so'z argumentlari
        """
        timeout = options['timeout']
        interval = options['interval']
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Ma\'lumotlar bazasi tayyor bo\'lishini kutmoqda... '
                f'(Timeout: {timeout}s, Interval: {interval}s)'
            )
        )
        
        start_time = time.time()
        
        while True:
            try:
                # Ma'lumotlar bazasi ulanishini tekshirish
                db_conn = connections['default']
                db_conn.cursor()
                
                self.stdout.write(
                    self.style.SUCCESS('✅ Ma\'lumotlar bazasi tayyor!')
                )
                break
                
            except OperationalError:
                elapsed_time = time.time() - start_time
                
                if elapsed_time >= timeout:
                    self.stdout.write(
                        self.style.ERROR(
                            f'❌ Timeout! Ma\'lumotlar bazasi {timeout} soniyada tayyor bo\'lmadi.'
                        )
                    )
                    return
                
                self.stdout.write(
                    self.style.WARNING(
                        f'⏳ Ma\'lumotlar bazasi hali tayyor emas. '
                        f'Kutmoqda... ({elapsed_time:.1f}s/{timeout}s)'
                    )
                )
                
                time.sleep(interval)
        
        # Migration'larni bajarish
        self.stdout.write(
            self.style.SUCCESS('🔄 Migration\'larni bajarish...')
        )
        try:
            call_command('migrate', verbosity=0)
            self.stdout.write(
                self.style.SUCCESS('✅ Migration\'lar muvaffaqiyatli bajarildi!')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Migration xatosi: {e}')
            )
