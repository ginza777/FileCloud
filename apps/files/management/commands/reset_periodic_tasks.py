"""
Reset PeriodicTasks Command
===========================

Ensures django-celery-beat's PeriodicTasks table contains a single row.
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone


class Command(BaseCommand):
    """
    Removes duplicate PeriodicTasks tracker rows and recreates the singleton if
    it is missing. Celery Beat expects exactly one record with ident=1.
    """

    help = "Ensure django-celery-beat PeriodicTasks table has a single row (ident=1)"

    def handle(self, *args, **options):
        from django_celery_beat.models import PeriodicTasks

        with transaction.atomic():
            tracker_qs = PeriodicTasks.objects.select_for_update().order_by("ident")
            trackers = list(tracker_qs)

            if trackers:
                keeper = trackers[0]
                removed = 0
                for duplicate in trackers[1:]:
                    duplicate.delete()
                    removed += 1

                updated_fields = []
                if keeper.ident != 1:
                    keeper.ident = 1
                    updated_fields.append("ident")
                if keeper.last_update is None:
                    keeper.last_update = timezone.now()
                    updated_fields.append("last_update")

                if updated_fields:
                    keeper.save(update_fields=updated_fields)

                self.stdout.write(
                    self.style.SUCCESS(
                        f"PeriodicTasks cleaned. Kept ident=1 row (id={keeper.pk}), "
                        f"removed {removed} duplicate(s)."
                    )
                )
            else:
                PeriodicTasks.objects.create(ident=1, last_update=timezone.now())
                self.stdout.write(
                    self.style.SUCCESS(
                        "PeriodicTasks table was empty. Created ident=1 tracker row."
                    )
                )

