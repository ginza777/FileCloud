from django.db import models
from django.utils import timezone

class Feedback(models.Model):
    telegram_id = models.CharField(max_length=50, null=True, blank=True)
    message = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'Feedback'
        verbose_name_plural = 'Feedback'
        ordering = ['-created_at']

    def __str__(self):
        return f"Feedback from {self.telegram_id or 'Anonymous'}"
