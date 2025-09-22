# management/commands/maintenance.py
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
        self.stdout.write(self.style.HTTP_INFO("\n[2] Keraksiz ma'lumotlar va fayllarni tozalash..."))
        large_docs_count = 0

        # 50MB dan katta fayllarni o'chirish (iterator() xotirani tejaydi)
        for doc in Document.objects.iterator():
            file_size_str = (doc.json_data or {}).get('document', {}).get('file_size')
            if file_size_str and self._parse_file_size_to_bytes(file_size_str) > 50 * 1024 * 1024:
                log_prefix = "O'chirilmoqda" if not dry_run else "O'chiriladi"
                self.stdout.write(f"   - {log_prefix} (Hajmi katta): ID {doc.id}, Hajmi: {file_size_str}")
                large_docs_count += 1
                if not dry_run:
                    doc.delete()

        if large_docs_count > 0:
            action_verb = "o'chirildi" if not dry_run else "o'chiriladi"
            self.stdout.write(self.style.SUCCESS(
                f"   ➡️  Jami {large_docs_count} ta hujjat hajmi katta bo'lgani uchun {action_verb}."))

        # O'chirilmagan fayllarni qayta o'chirish
        retry_delete_count = 0
        done_statuses = ['completed', 'skipped']
        docs_to_retry_delete = Document.objects.filter(download_status__in=done_statuses,
                                                       parse_status__in=done_statuses, index_status__in=done_statuses,
                                                       telegram_status__in=done_statuses).exclude(
            delete_status='completed')
        for doc in docs_to_retry_delete:
            try:
                file_extension = os.path.splitext(urlparse(doc.parse_file_url).path)[1]
                file_path = os.path.join(settings.MEDIA_ROOT, 'downloads', f"{doc.id}{file_extension}")
                if os.path.exists(file_path):
                    log_prefix = "Fayl o'chirilmoqda" if not dry_run else "Fayl o'chiriladi"
                    self.stdout.write(f"   - {log_prefix} (Eskirgan fayl): ID {doc.id}")
                    if not dry_run:
                        os.remove(file_path)
                        doc.delete_status = 'completed'
                        doc.save(update_fields=['delete_status'])
                    retry_delete_count += 1
            except Exception as e:
                logger.error(f"Faylni o'chirishda xato: {doc.id} - {e}")

        if retry_delete_count > 0:
            action_verb = "o'chirildi" if not dry_run else "o'chiriladi"
            self.stdout.write(
                self.style.SUCCESS(f"   ➡️  Jami {retry_delete_count} ta eskirgan fayl qaytadan {action_verb}."))

    def run_fix_urls(self, dry_run):
        self.stdout.write(self.style.HTTP_INFO("\n[3] Hujjat URL kengaytmalarini tuzatish..."))
        fixed_count = 0
        for doc in Document.objects.filter(json_data__poster_url__isnull=False, parse_file_url__isnull=False):
            poster_url = doc.json_data.get('poster_url')
            if self._fix_url_extension(doc, poster_url, dry_run): fixed_count += 1
        if fixed_count > 0: self.stdout.write(
            self.style.SUCCESS(f"   ✅ {fixed_count} ta hujjatning URL manzili tuzatildi."))

    def run_fix_states(self, dry_run):
        self.stdout.write(self.style.HTTP_INFO("\n[4] Hujjatlar holatini qat'iy qoidalar asosida to'g'rilash..."))
        one_hour_ago = timezone.now() - timedelta(hours=1)
        stuck_pipelines = Document.objects.filter(pipeline_running=True, updated_at__lt=one_hour_ago)
        count_stuck = stuck_pipelines.count()
        if count_stuck > 0:
            if not dry_run: stuck_pipelines.update(pipeline_running=False)
            self.stdout.write(
                self.style.SUCCESS(f"   ✅ 1 soatdan ortiq qotib qolgan {count_stuck} ta 'pipeline' to'xtatildi."))

        fixed_to_true = 0
        fixed_to_false = 0
        fixed_telegram_status = 0
        reset_failed_docs = 0

        try:
            with transaction.atomic():
                self.stdout.write("   🔄 Barcha hujjatlar holati tekshirilmoqda (bu vaqt olishi mumkin)...")
                for doc in Document.objects.select_for_update().all():
                    needs_save = False

                    # 1. Agar biror status 'failed' bo'lsa, hujjatni to'liq reset qilish
                    failed_statuses = ['failed']
                    if any(status in failed_statuses for status in
                           [doc.download_status, doc.parse_status, doc.index_status, doc.telegram_status,
                            doc.delete_status]):
                        doc.download_status = 'pending'
                        doc.parse_status = 'pending'
                        doc.index_status = 'pending'
                        doc.telegram_status = 'pending'
                        doc.delete_status = 'pending'
                        doc.completed = False
                        doc.pipeline_running = False
                        needs_save = True
                        reset_failed_docs += 1
                        if needs_save and not dry_run:
                            doc.save()
                        continue

                    # 2. Telegram statusini file_id bo'yicha to'g'rilash
                    if doc.telegram_file_id and doc.telegram_status != 'completed':
                        doc.telegram_status = 'completed'
                        needs_save = True
                        fixed_telegram_status += 1

                    # 3. Asosiy holatni tekshirish
                    is_perfectly_completed = all([doc.download_status == 'completed', doc.parse_status == 'completed',
                                                  doc.index_status == 'completed', doc.telegram_status == 'completed',
                                                  doc.telegram_file_id is not None and doc.telegram_file_id.strip() != ''])

                    if doc.completed != is_perfectly_completed or doc.pipeline_running:
                        needs_save = True
                        if doc.completed != is_perfectly_completed:
                            if is_perfectly_completed:
                                fixed_to_true += 1
                            else:
                                fixed_to_false += 1
                        doc.completed = is_perfectly_completed
                        doc.pipeline_running = False

                    # 4. Agar o'zgarish bo'lsa, saqlash
                    if needs_save and not dry_run:
                        doc.save()

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   ❌ Holatlarni tuzatishda tranzaksiya xatosi: {e}"))

        if reset_failed_docs > 0: self.stdout.write(
            self.style.SUCCESS(f"   ✅ {reset_failed_docs} ta xatolikda qolgan hujjat qayta ishlash uchun tozaladi."))
        if fixed_telegram_status > 0: self.stdout.write(self.style.SUCCESS(
            f"   ✅ {fixed_telegram_status} ta hujjatning Telegram statusi 'completed' ga o'zgartirildi."))
        if fixed_to_true > 0: self.stdout.write(
            self.style.SUCCESS(f"   ✅ {fixed_to_true} ta hujjat 'completed=True' holatiga to'g'rilandi."))
        if fixed_to_false > 0: self.stdout.write(
            self.style.SUCCESS(f"   ✅ {fixed_to_false} ta hujjat 'completed=False' holatiga to'g'rilandi."))

    def _parse_file_size_to_bytes(self, file_size_str):
        if not file_size_str: return 0
        match = re.match(r'(\d+\.?\d*)\s*(MB|GB|KB)', file_size_str, re.IGNORECASE)
        if not match: return 0
        size, unit = float(match.group(1)), match.group(2).upper()
        if unit == 'GB':
            return size * 1024 * 1024 * 1024
        elif unit == 'MB':
            return size * 1024 * 1024
        elif unit == 'KB':
            return size * 1024
        return 0

    def _fix_url_extension(self, doc, poster_url, dry_run):
        try:
            poster_ext = os.path.splitext(urlparse(poster_url).path)[1]
            file_ext = os.path.splitext(urlparse(doc.parse_file_url).path)[1]
            poster_ext_nodot = (poster_ext[1:] if poster_ext.startswith('.') else poster_ext).lower()
            file_ext_nodot = (file_ext[1:] if file_ext.startswith('.') else file_ext).lower()
            if poster_ext_nodot in ALL_EXTS_LOWER and file_ext_nodot == poster_ext_nodot and file_ext != poster_ext:
                new_url = doc.parse_file_url[:-len(file_ext)] + poster_ext
                if not dry_run:
                    doc.parse_file_url = new_url
                    doc.save(update_fields=['parse_file_url'])
                return True
        except Exception as e:
            logger.warning(f"URL tuzatishda xato: {doc.id} - {e}")
        return False