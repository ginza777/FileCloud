from django.db import models


class Feedback(models.Model):
    full_name = models.CharField(max_length=150)
    message = models.TextField()
    contact = models.CharField(max_length=150, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f"{self.full_name} • {self.created_at:%Y-%m-%d %H:%M}"
