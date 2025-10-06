"""
Database Wait Command
====================

Bu komanda ma'lumotlar bazasi mavjud bo'lgunga qadar kutadi.
Docker container'lar uchun foydalidir, chunki database container'i ishga tushishini kutadi.

Ishlatish:
    python manage.py wait_for_database
    python manage.py wait_for_database --timeout 60
"""

import time
from django.db import connections
from django.db.utils import OperationalError
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """
    Ma'lumotlar bazasi mavjud bo'lgunga qadar kutish komandasi.
    
    Bu komanda:
    1. Ma'lumotlar bazasi ulanishini tekshiradi
    2. Agar ulanish bo'lmasa, kutadi
    3. Timeout qo'llab-quvvatlaydi
    4. Docker container'lar uchun foydalidir
    """
    
    help = "Ma'lumotlar bazasi mavjud bo'lgunga qadar kutadi"

    def add_arguments(self, parser):
        parser.add_argument(
            '--timeout',
            type=int,
            default=0,
            help='Maksimal kutish vaqti sekundlarda (0 = cheksiz)'
        )
        parser.add_argument(
            '--interval',
            type=int,
            default=1,
            help='Tekshirish intervali sekundlarda (default: 1)'
        )

    def handle(self, *args, **options):
        """Asosiy kutish jarayoni."""
        timeout = options['timeout']
        interval = options['interval']
        
        self.stdout.write(
            self.style.SUCCESS("=== Ma'lumotlar Bazasi Kutish Jarayoni ===")
        )
        
        if timeout > 0:
            self.stdout.write(f"Timeout: {timeout} soniya")
        else:
            self.stdout.write("Cheksiz kutish")
        
        self.stdout.write(f"Interval: {interval} soniya")
        
        start_time = time.time()
        attempts = 0
        
        while True:
            attempts += 1
            
            try:
                # Ma'lumotlar bazasi ulanishini tekshirish
                db_conn = connections['default']
                db_conn.cursor()
                
                # Muvaffaqiyatli ulanish
                elapsed_time = time.time() - start_time
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Ma'lumotlar bazasi mavjud! "
                        f"Urinishlar: {attempts}, Vaqt: {elapsed_time:.1f}s"
                    )
                )
                break
                
            except OperationalError:
                # Ulanish xatoligi - kutish
                elapsed_time = time.time() - start_time
                
                if timeout > 0 and elapsed_time >= timeout:
                    self.stdout.write(
                        self.style.ERROR(
                            f"Timeout! {timeout} soniyadan keyin ham "
                            "ma'lumotlar bazasi mavjud emas"
                        )
                    )
                    return
                
                self.stdout.write(
                    f"Ma'lumotlar bazasi mavjud emas, "
                    f"{interval} soniya kutilmoqda... "
                    f"(Urinish: {attempts}, Vaqt: {elapsed_time:.1f}s)"
                )
                
                time.sleep(interval)
                
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"Kutilmagan xatolik: {e}")
                )
                return
