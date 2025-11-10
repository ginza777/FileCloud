from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class Feedback(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='feedback', null=True, blank=True)
    message = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'Feedback'
        verbose_name_plural = 'Feedback'
        ordering = ['-created_at']

    def __str__(self):
        return f"Feedback from {self.user.username}"
