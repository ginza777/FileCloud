from django.contrib import admin
from .models import Feedback


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ("full_name", "contact", "created_at")
    search_fields = ("full_name", "contact", "message")
    readonly_fields = ("created_at",)
