from django.contrib import admin
from .models import Feedback

@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ('id', 'telegram_id', 'short_message', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('telegram_id', 'message')
    readonly_fields = ('created_at',)

    def short_message(self, obj):
        """Returns truncated message for list display"""
        return obj.message[:50] + '...' if len(obj.message) > 50 else obj.message
    short_message.short_description = 'Message'
