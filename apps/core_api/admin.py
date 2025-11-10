from django.contrib import admin
from apps.core_api.models import Feedback

@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'message', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('user__username', 'message')
