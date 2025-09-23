# management/commands/clean.py
import os
import re
import redis
import logging
from urllib.parse import urlparse
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from celery import current_app

from apps.files.models import Document

logger = logging.getLogger(__name__)

# Fayl kengaytmalari ro'yxati
ALL_EXTS = ['pdf', 'docx', 'doc', 'pptx', 'ppt', 'xlsx', 'xls', 'txt', 'rtf', 'odt', 'ods', 'odp']
ALL_EXTS_LOWER = [ext.lower() for ext in ALL_EXTS]


class Command(BaseCommand):
    help = "Tizim holatini to'g'rilash, Celery tasklarini tozalash va fayllarni boshqarish uchun yagona komanda."

    def add_arguments(self, parser):
        parser.add_argument('--all', action='store_true',
                            help='Barcha tuzatish va tozalash amallarini tavsiya etilgan tartibda bajaradi.')
        parser.add_argument('--cancel-tasks', action='store_true',
                            help="[1] Barcha faol Celery va Celery Beat tasklarini bekor qiladi va tozalaydi.")
        parser.add_argument('--cleanup-data', action='store_true',
                            help="[2] Keraksiz hujjatlarni o'chiradi (50MB dan katta) va o'chirilmagan fayllarni qayta o'chirishga urinadi.")
        parser.add_argument('--fix-urls', action='store_true',
                            help="[3] Hujjatlarning 'parse_file_url' kengaytmasini 'poster_url' bilan moslashtiradi.")
        parser.add_argument('--fix-states', action='store_true',
                            help="[4] Barcha hujjatlar holatini qat'iy qoidalar asosida to'g'rilaydi.")
        parser.add_argument('--dry-run', action='store_true',
                            help="O'zgarishlarni bajarmasdan, nima qilinishini ko'rsatadi.")
        parser.add_argument('--force', action='store_true',
                            help="Celery tasklarini majburiy to'xtatish (terminate) uchun.")

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("===== TIZIMNI TUZATISH VA SOZLASH BOSHLANDI ====="))
        if options['dry_run']:
            self.stdout.write(self.style.WARNING("⚠️  DRY RUN rejimi yoqilgan. Hech qanday o'zgarishlar saqlanmaydi."))

        if options['all'] or options['cancel_tasks']:
            self.run_cancel_tasks(options['force'], options['dry_run'])
        if options['all'] or options['cleanup_data']:
            self.run_cleanup_data(options['dry_run'])
        if options['all'] or options['fix_urls']:
            self.run_fix_urls(options['dry_run'])
        if options['all'] or options['fix_states']:
            self.run_fix_states(options['dry_run'])

        self.stdout.write(self.style.SUCCESS("===== BARCHA AMALLAR YAKUNLANDI ====="))

    def run_cancel_tasks(self, force, dry_run):
        # ... (Bu funksiya o'zgarishsiz qoladi) ...
        self.stdout.write(self.style.HTTP_INFO("\n[1] Celery tasklarini tozalash..."))
        if dry_run:
            self.stdout.write(self.style.WARNING("   DRY RUN: Tasklar va Redis tozalanishi simulyatsiya qilinmoqda."))
            return
        try:
            inspect = current_app.control.inspect()
            active_tasks = inspect.active() or {}
            cancelled_count = 0
            for tasks in active_tasks.values():
                for task in tasks:
                    current_app.control.revoke(task.get('id'), terminate=force)
                    cancelled_count += 1
            self.stdout.write(self.style.SUCCESS(f"   ✅ {cancelled_count} ta faol task bekor qilindi."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   ❌ Faol tasklarni bekor qilishda xato: {e}"))
        try:
            redis_url = getattr(settings, 'CELERY_BROKER_URL', 'redis://redis:6379/0')
            r = redis.from_url(redis_url)
            celery_keys = r.keys('celery-task-meta-*')
            if celery_keys:
                r.delete(*celery_keys)
                self.stdout.write(self.style.SUCCESS(f"   ✅ Redis'dan {len(celery_keys)} ta task natijasi o'chirildi."))
            from django_celery_beat.models import PeriodicTask
            PeriodicTask.objects.all().update(last_run_at=None)
            self.stdout.write(self.style.SUCCESS("   ✅ Django Celery Beat jadvallari tozaladi."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   ❌ Redis tozalashda xato: {e}"))

    def run_cleanup_data(self, dry_run):
        # ... (Bu funksiya o'zgarishsiz qoladi) ...
        self.stdout.write(self.style.HTTP_INFO("\n[2] Keraksiz ma'lumotlar va fayllarni tozalash..."))
        # (Implementation is omitted for brevity as it's unchanged)

    def run_fix_urls(self, dry_run):
        # ... (Bu funksiya o'zgarishsiz qoladi) ...
        self.stdout.write(self.style.HTTP_INFO("\n[3] Hujjat URL kengaytmalarini tuzatish..."))
        # (Implementation is omitted for brevity as it's unchanged)

    def run_fix_states(self, dry_run):
        self.stdout.write(self.style.HTTP_INFO("\n[4] Hujjatlar holatini yagona qoida asosida to'g'rilash..."))

        total_docs = Document.objects.count()
        if total_docs == 0:
            self.stdout.write("   Hujjatlar topilmadi.")
            return

        self.stdout.write(f"   🔄 Jami {total_docs} ta hujjat tekshirilmoqda...")

        # Umumiy statistika uchun
        fixed_to_completed_total = 0
        reset_to_pending_total = 0
        unchanged_total = 0
        processed_count = 0
        BATCH_SIZE = 1000

        # Batch (partiya) uchun vaqtinchalik ro'yxatlar
        docs_to_set_completed = []
        docs_to_set_pending = []

        # Batch uchun statistika
        batch_completed_count = 0
        batch_pending_count = 0
        batch_unchanged_count = 0

        update_fields = [
            'download_status', 'parse_status', 'index_status', 'telegram_status',
            'delete_status', 'completed', 'pipeline_running', 'telegram_file_id'
        ]

        def process_batch():
            nonlocal fixed_to_completed_total, reset_to_pending_total
            if not dry_run:
                try:
                    with transaction.atomic():
                        if docs_to_set_completed:
                            Document.objects.bulk_update(docs_to_set_completed, update_fields)
                        if docs_to_set_pending:
                            Document.objects.bulk_update(docs_to_set_pending, update_fields)
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"\n   ❌ Batchni saqlashda tranzaksiya xatosi: {e}"))

            fixed_to_completed_total += len(docs_to_set_completed)
            reset_to_pending_total += len(docs_to_set_pending)

            docs_to_set_completed.clear()
            docs_to_set_pending.clear()

        for doc in Document.objects.iterator():
            if doc.telegram_file_id:
                doc.telegram_file_id = doc.telegram_file_id.strip()

            # Check if document meets the completion criteria from Document model save() method
            is_final_state = (
                    doc.parse_status == 'completed' and
                    doc.index_status == 'completed' and
                    doc.telegram_file_id is not None and
                    doc.telegram_file_id.strip() != ''
            )

            if is_final_state:
                # For documents that meet the core completion criteria, check if all statuses are properly set
                is_already_perfect = (
                        doc.download_status == 'completed' and
                        doc.telegram_status == 'completed' and
                        doc.delete_status == 'completed' and
                        doc.completed is True and
                        doc.pipeline_running is False
                )
                if is_already_perfect:
                    batch_unchanged_count += 1
                else:
                    # Set all statuses to completed and mark as completed
                    doc.download_status = 'completed'
                    doc.telegram_status = 'completed'
                    doc.delete_status = 'completed'
                    doc.completed = True
                    doc.pipeline_running = False
                    docs_to_set_completed.append(doc)
                    batch_completed_count += 1
            else:
                doc.download_status = 'pending'
                doc.parse_status = 'pending'
                doc.index_status = 'pending'
                doc.telegram_status = 'pending'
                doc.delete_status = 'pending'
                doc.completed = False
                doc.pipeline_running = False
                docs_to_set_pending.append(doc)
                batch_pending_count += 1

            processed_count += 1

            if processed_count % BATCH_SIZE == 0:
                progress_msg = (
                    f"   🔄 Tekshirildi: {processed_count}/{total_docs}. "
                    f"Batch [ ✅ To'g'rilandi: {batch_completed_count} |"
                    f" ⚠️  Qayta ishlashga: {batch_pending_count} |"
                    f" ➖ O'zgarishsiz: {batch_unchanged_count} ]"
                )
                self.stdout.write(progress_msg)

                process_batch()
                unchanged_total += batch_unchanged_count

                batch_completed_count = 0
                batch_pending_count = 0
                batch_unchanged_count = 0

        # Tsikl tugagandan keyin qolgan qismni qayta ishlash
        if docs_to_set_completed or docs_to_set_pending or batch_unchanged_count > 0:
            final_batch_msg = (
                f"   🔄 Oxirgi qism. "
                f"Batch [ ✅ To'g'rilandi: {batch_completed_count} |"
                f" ⚠️  Qayta ishlashga: {batch_pending_count} |"
                f" ➖ O'zgarishsiz: {batch_unchanged_count} ]"
            )
            self.stdout.write(final_batch_msg)
            self.stdout.write("   🔄 Oxirgi qism saqlanmoqda...")
            process_batch()
            unchanged_total += batch_unchanged_count

        self.stdout.write(f"\n   ✅ Tekshiruv yakunlandi. Jami tekshirildi: {processed_count}.")

        # Yakuniy statistika
        action_completed = "to'g'rilanadi" if dry_run else "to'g'rilandi"
        action_pending = "o'tkaziladi" if dry_run else "o'tkazildi"
        self.stdout.write(
            self.style.SUCCESS(
                f"   - Jami {fixed_to_completed_total} ta hujjat 'completed=True' holatiga {action_completed}."))
        self.stdout.write(
            self.style.WARNING(
                f"   - Jami {reset_to_pending_total} ta nomuvofiq hujjat 'pending' holatiga {action_pending}."))
        self.stdout.write(
            self.style.HTTP_INFO(f"   - Jami {unchanged_total} ta hujjat allaqachon to'g'ri holatda edi."))

    def _parse_file_size_to_bytes(self, file_size_str):
        # ... (Bu funksiya o'zgarishsiz qoladi) ...
        if not file_size_str: return 0
        # (Implementation is omitted for brevity as it's unchanged)

    def _fix_url_extension(self, doc, poster_url, dry_run):
        # ... (Bu funksiya o'zgarishsiz qoladi) ...
        try:
            # (Implementation is omitted for brevity as it's unchanged)
            return True
        except Exception as e:
            logger.warning(f"URL tuzatishda xato: {doc.id} - {e}")
        return False