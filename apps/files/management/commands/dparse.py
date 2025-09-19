# apps/multiparser/management/commands/dparse.py

from django.core.management.base import BaseCommand
from django.db import transaction
from django.conf import settings
from django.utils import timezone
from ...models import Document
from ...tasks import process_document_pipeline
import math, random, time
try:
    import redis  # noqa
    _redis_available = True
except ImportError:
    _redis_available = False

class Command(BaseCommand):
    help = "Qayta ishlanmagan hujjatlar uchun to'liq qayta ishlash zanjirini bosim tushirmasdan ishga tushiradi."

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=100, help="Bir martada nechta hujjatni qayta ishlash kerak.")
        parser.add_argument('--include-failed', action='store_true', help="failed statusidagi hujjatlarni ham qayta ishga tushirish")
        parser.add_argument('--rate', type=int, default=30, help='Bir daqiqada nechta task dispatch qilinsin (throttle). 0 = barcha darhol.')
        parser.add_argument('--max-active', type=int, default=200, help='Faol (pipeline_running=True) hujjatlar limiti. Oshsa yangi tasklar rejalashtirilmaydi.')
        parser.add_argument('--dry-run', action='store_true', help='Faqat nima qilinishini koʼrsatadi, tasklarni rejalashtirmaydi.')
        parser.add_argument('--burst-limit', type=int, default=300, help='rate=0 bo\'lganda darhol yuboriladigan maksimal task soni. Oshsa avtomatik spacing qo\'llanadi.')
        parser.add_argument('--jitter', type=float, default=0.0, help='Har bir dispatch countdown ga qo\'shiladigan maksimal tasodifiy (0..jitter) soniya.')
        parser.add_argument('--batch-size', type=int, default=50, help='Brokerga bir yo\'la yuboriladigan maksimal task soni (katta sonlarda uyali yuborish).')
        parser.add_argument('--batch-sleep', type=float, default=2.0, help='Batchlar orasida sekund kutish.')

    def ping_redis(self):
        if not _redis_available:
            return True, 'redis moduli topilmadi (o\'tkazildi)'
        host = getattr(settings, 'REDIS_HOST', 'redis')
        port = int(getattr(settings, 'REDIS_PORT', 6379))
        try:
            r = redis.Redis(host=host, port=port, db=0, socket_connect_timeout=2, socket_timeout=2)
            r.ping()
            return True, f'Redis OK ({host}:{port})'
        except Exception as e:
            return False, f'Redis ping xato: {e}'

    def handle(self, *args, **options):
        limit = options['limit']
        include_failed = options['include_failed']
        rate = options['rate']
        max_active = options['max_active']
        dry_run = options['dry_run']
        burst_limit = options['burst-limit']
        jitter = options['jitter']
        batch_size = options['batch_size']
        batch_sleep = options['batch_sleep']

        self.stdout.write(self.style.SUCCESS("--- Hujjatlarni qayta ishlash zanjirini rejalashtirish boshlandi (throttled) ---"))

        ok, msg = self.ping_redis()
        if not ok:
            self.stdout.write(self.style.ERROR(f"{msg}. Dispatch bekor qilindi."))
            return
        else:
            self.stdout.write(self.style.SUCCESS(msg))

        # Faol pipeline lar sonini tekshirish
        active_now = Document.objects.filter(pipeline_running=True).count()
        if active_now >= max_active:
            self.stdout.write(self.style.WARNING(f"Faol pipeline soni ({active_now}) max-active ({max_active}) ga teng yoki katta. Yangi tasklar qo'shilmadi."))
            return

        base_qs = Document.objects.filter(
            parse_file_url__isnull=False,
            completed=False,
            pipeline_running=False
        )
        if not include_failed:
            base_qs = base_qs.exclude(download_status='failed')

        # Qolgan kvota
        dispatch_capacity = max_active - active_now
        if dispatch_capacity <= 0:
            self.stdout.write(self.style.WARNING("Kvota qolmadi."))
            return

        effective_limit = min(limit, dispatch_capacity)
        candidates = list(base_qs.order_by('created_at')[:effective_limit])
        if not candidates:
            self.stdout.write(self.style.WARNING("Qayta ishlanadigan hujjatlar topilmadi (yoki barchasi band)."))
            return

        locked_ids = []
        with transaction.atomic():
            for doc in candidates:
                updated = Document.objects.filter(id=doc.id, pipeline_running=False).update(pipeline_running=True)
                if updated:
                    locked_ids.append(doc.id)

        if not locked_ids:
            self.stdout.write(self.style.WARNING("Hujjatlar band qilib bo'lingan."))
            return

        self.stdout.write(f"{len(locked_ids)} ta hujjat band qilindi. Dispatch boshlanadi...")

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry-run: hech qanday task rejalashtirilmadi."))
            return

        # Spacing logic
        if rate and rate > 0:
            spacing = 60.0 / rate
        else:
            # rate=0 bo'lsa: agar juda ko'p bo'lsa burst-limit bilan cheklaymiz
            if len(locked_ids) > burst_limit:
                spacing = 60.0 / 60.0  # ~1 task/s fallback
                self.stdout.write(self.style.WARNING(f"rate=0 va {len(locked_ids)}>burst-limit ({burst_limit}) => fallback spacing qo'llandi (≈1 task/s)."))
            else:
                spacing = 0

        # Helper to release locks on failure
        def rollback_locks(rem_ids):
            if rem_ids:
                Document.objects.filter(id__in=rem_ids).update(pipeline_running=False)

        failures = 0
        total = len(locked_ids)
        dispatched = 0

        # Batch dispatch
        for batch_start in range(0, total, batch_size):
            batch_ids = locked_ids[batch_start: batch_start + batch_size]
            for i, doc_id in enumerate(batch_ids, start=batch_start):
                # Calculate countdown
                if spacing:
                    base_delay = int(i * spacing)
                else:
                    base_delay = 0
                if jitter and jitter > 0:
                    base_delay += random.uniform(0, max(0.0, jitter))
                try:
                    process_document_pipeline.apply_async(args=[doc_id], countdown=base_delay)
                    dispatched += 1
                except Exception as e:
                    failures += 1
                    self.stdout.write(self.style.ERROR(f"Dispatch xato (doc={doc_id}): {e}"))
                    rollback_locks(batch_ids[batch_ids.index(doc_id):])
                    break
            if failures:
                break
            if batch_start + batch_size < total and batch_sleep > 0:
                time.sleep(batch_sleep)

        last_delay = int((total - 1) * spacing) if spacing else 0
        self.stdout.write(self.style.SUCCESS(
            f"Rejalashtirildi: {dispatched}/{total}. Active oldin: {active_now}, taxminan yangi active: {active_now + dispatched}. Oxirgi bazaviy countdown: {last_delay}s"))
        if jitter:
            self.stdout.write(self.style.NOTICE(f"Jitter <= {jitter:.2f}s qo'llandi"))
        if spacing:
            self.stdout.write(self.style.NOTICE(f"Rate eff: spacing ≈ {spacing:.2f}s (taxminiy ~{(60/spacing) if spacing else '∞'} task/min)"))
        if failures:
            self.stdout.write(self.style.ERROR(f"{failures} ta dispatch xatosi sodir bo'ldi, qolganlari to'xtatildi."))
