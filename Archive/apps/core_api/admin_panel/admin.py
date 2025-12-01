from django.contrib import admin
from apps.core_api.models import Feedback


class FeedbackAdmin(admin.ModelAdmin):
    list_display = ("full_name", "contact", "created_at")
    search_fields = ("full_name", "contact", "message")
    readonly_fields = ("created_at",)


# Register the model
admin.site.register(Feedback, FeedbackAdmin)
