from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.db import models
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .forms import SubscribeChannelForm
from .models import (User, Broadcast, BroadcastRecipient,
                    SubscribeChannel, Location)
from files.models import SearchQuery
from .tasks import send_message_to_user_task

# Celery admin imports
try:
    from django_celery_results.models import TaskResult
    from django_celery_beat.models import PeriodicTask, CrontabSchedule, IntervalSchedule, SolarSchedule, ClockedSchedule
except ImportError:
    TaskResult = None
    PeriodicTask = None
    CrontabSchedule = None
    IntervalSchedule = None
    SolarSchedule = None
    ClockedSchedule = None


@admin.register(SubscribeChannel)
class SubscribeChannelAdmin(admin.ModelAdmin):
    """Admin for Telegram subscription channels"""
    form = SubscribeChannelForm
    # "subscriber_count" bu yerdan olib tashlandi
    list_display = ("channel_username", "channel_id", "active", "private", "created_at", "updated_at")
    list_filter = ("active", "private", "created_at")
    search_fields = ("channel_username", "channel_id")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-created_at",)

    fieldsets = (
        (_("Channel Information"), {
            "fields": ("channel_username", "channel_id", "private")
        }),
        (_("Channel Settings"), {
            "fields": ("active", "channel_link")
        }),
        (_("Timestamps"), {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    """Admin for Telegram users"""
    list_display = ('telegram_id', 'username', 'full_name', 'is_admin', 'is_blocked', 'last_active', 'created_at')
    list_filter = ('is_admin', 'is_blocked', 'last_active', 'created_at', 'stock_language', 'selected_language')
    search_fields = ('telegram_id', 'username', 'first_name', 'last_name')
    readonly_fields = ('telegram_id', 'created_at', 'updated_at')
    ordering = ('-last_active',)
    
    fieldsets = (
        (_("User Information"), {
            "fields": ("telegram_id", "first_name", "last_name", "username")
        }),
        (_("Status"), {
            "fields": ("is_admin", "is_blocked", "left")
        }),
        (_("Language"), {
            "fields": ("stock_language", "selected_language")
        }),
        (_("Activity"), {
            "fields": ("last_active", "deeplink")
        }),
        (_("Timestamps"), {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )

    actions = ['make_admin', 'remove_admin', 'block_users', 'unblock_users']

    @admin.action(description=_("Make selected users admin"))
    def make_admin(self, request, queryset):
        updated = queryset.update(is_admin=True)
        self.message_user(request, f"{updated} users were made admin.")

    @admin.action(description=_("Remove admin from selected users"))
    def remove_admin(self, request, queryset):
        updated = queryset.update(is_admin=False)
        self.message_user(request, f"Admin status removed from {updated} users.")

    @admin.action(description=_("Block selected users"))
    def block_users(self, request, queryset):
        updated = queryset.update(is_blocked=True)
        self.message_user(request, f"{updated} users were blocked.")

    @admin.action(description=_("Unblock selected users"))
    def unblock_users(self, request, queryset):
        updated = queryset.update(is_blocked=False)
        self.message_user(request, f"{updated} users were unblocked.")

    def full_name(self, obj):
        return f"{obj.first_name or ''} {obj.last_name or ''}".strip()
    full_name.short_description = _("Full Name")


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    """Admin for user locations"""
    list_display = ('user', 'latitude', 'longitude', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('user__username', 'user__first_name', 'user__last_name')
    ordering = ('-created_at',)
    readonly_fields = ('created_at',)
    
    fieldsets = (
        (_("Location Data"), {
            "fields": ("user", "latitude", "longitude")
        }),
        (_("Timestamp"), {
            "fields": ("created_at",)
        }),
    )


@admin.register(SearchQuery)
class SearchQueryAdmin(admin.ModelAdmin):
    """Admin for search queries"""
    list_display = ('query_text', 'user', 'is_deep_search', 'found_results', 'created_at')
    list_filter = ('is_deep_search', 'found_results', 'created_at')
    search_fields = ('query_text', 'user__username', 'user__first_name')
    ordering = ('-created_at',)
    readonly_fields = ('created_at',)
    
    fieldsets = (
        (_("Search Information"), {
            "fields": ("user", "query_text", "is_deep_search", "found_results")
        }),
        (_("Timestamp"), {
            "fields": ("created_at",)
        }),
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class BroadcastRecipientInline(admin.TabularInline):
    """Inline for broadcast recipients"""
    model = BroadcastRecipient
    extra = 0
    fields = ('user', 'status', 'sent_at', 'error_message')
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Broadcast)
class BroadcastAdmin(admin.ModelAdmin):
    """Admin for broadcast messages"""
    list_display = (
        'id',
        'status',
        'scheduled_time',
        'get_total_recipients',
        'get_sent_count',
        'get_failed_count',
        'get_pending_count',
        'created_at',
    )
    list_filter = ('status', 'scheduled_time', 'created_at')
    search_fields = ('from_chat_id', 'message_id')
    ordering = ('-created_at',)
    inlines = [BroadcastRecipientInline]
    readonly_fields = (
        'from_chat_id',
        'message_id',
        'created_at',
        'get_total_recipients',
        'get_sent_count',
        'get_failed_count',
        'get_pending_count',
    )
    
    fieldsets = (
        (_("Broadcast Information"), {
            "fields": ("status", "scheduled_time")
        }),
        (_("Message Details"), {
            "fields": ("from_chat_id", "message_id")
        }),
        (_("Statistics"), {
            "fields": (
                "get_total_recipients", "get_sent_count", 
                "get_failed_count", "get_pending_count"
            ),
            "classes": ("collapse",)
        }),
        (_("Timestamps"), {
            "fields": ("created_at",),
            "classes": ("collapse",)
        }),
    )

    actions = ['requeue_failed_recipients', 'mark_as_pending']

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.annotate(
            total_recipients=Count('recipients'),
            sent_recipients=Count('recipients', filter=Q(recipients__status=BroadcastRecipient.Status.SENT)),
            failed_recipients=Count('recipients', filter=Q(recipients__status=BroadcastRecipient.Status.FAILED)),
            pending_recipients=Count('recipients', filter=Q(recipients__status=BroadcastRecipient.Status.PENDING)),
        )
        return queryset

    def get_total_recipients(self, obj):
        return getattr(obj, 'total_recipients', 0)
    get_total_recipients.short_description = _("Total Recipients")

    def get_sent_count(self, obj):
        return getattr(obj, 'sent_recipients', 0)
    get_sent_count.short_description = _("✅ Sent")

    def get_failed_count(self, obj):
        return getattr(obj, 'failed_recipients', 0)
    get_failed_count.short_description = _("❌ Failed")

    def get_pending_count(self, obj):
        return getattr(obj, 'pending_recipients', 0)
    get_pending_count.short_description = _("⏳ Pending")

    @admin.action(description=_("Requeue failed recipients"))
    def requeue_failed_recipients(self, request, queryset):
        requeued_count = 0
        for broadcast in queryset:
            failed_recipients = broadcast.recipients.filter(status=BroadcastRecipient.Status.FAILED)
            for recipient in failed_recipients:
                send_message_to_user_task.delay(recipient.id)
                requeued_count += 1
            failed_recipients.update(status=BroadcastRecipient.Status.PENDING, error_message=None)
            broadcast.status = Broadcast.Status.PENDING
            broadcast.save()
        self.message_user(request, f"{requeued_count} failed recipients were requeued.")

    @admin.action(description=_("Mark as pending"))
    def mark_as_pending(self, request, queryset):
        updated = queryset.update(status=Broadcast.Status.PENDING)
        self.message_user(request, f"{updated} broadcasts were marked as pending.")


# Celery Admin Classes
if TaskResult:
    # Unregister existing admin if it exists
    try:
        admin.site.unregister(TaskResult)
    except admin.sites.NotRegistered:
        pass
    
    @admin.register(TaskResult)
    class TaskResultAdmin(admin.ModelAdmin):
        """Admin for Celery task results"""
        list_display = ('task_id', 'task_name', 'status', 'date_done', 'traceback')
        list_filter = ('status', 'task_name', 'date_done')
        search_fields = ('task_id', 'task_name')
        readonly_fields = ('task_id', 'task_name', 'task_args', 'task_kwargs', 'status', 'result', 'date_done', 'traceback', 'meta')
        ordering = ('-date_done',)
        
        fieldsets = (
            (_("Task Information"), {
                "fields": ("task_id", "task_name", "status")
            }),
            (_("Task Data"), {
                "fields": ("task_args", "task_kwargs"),
                "classes": ("collapse",)
            }),
            (_("Result"), {
                "fields": ("result", "date_done"),
                "classes": ("collapse",)
            }),
            (_("Error Information"), {
                "fields": ("traceback", "meta"),
                "classes": ("collapse",)
            }),
        )
        
        def has_add_permission(self, request):
            return False
        
        def has_change_permission(self, request, obj=None):
            return False
        
        def has_delete_permission(self, request, obj=None):
            return True

if PeriodicTask:
    # Unregister existing admin if it exists
    try:
        admin.site.unregister(PeriodicTask)
    except admin.sites.NotRegistered:
        pass
    
    @admin.register(PeriodicTask)
    class PeriodicTaskAdmin(admin.ModelAdmin):
        """Admin for periodic tasks"""
        list_display = ('name', 'task', 'enabled', 'last_run_at', 'total_run_count')
        list_filter = ('enabled', 'task', 'last_run_at')
        search_fields = ('name', 'task')
        readonly_fields = ('last_run_at', 'total_run_count')
        ordering = ('name',)
        
        fieldsets = (
            (_("Task Information"), {
                "fields": ("name", "task", "enabled")
            }),
            (_("Schedule"), {
                "fields": ("crontab", "interval", "solar", "clocked")
            }),
            (_("Statistics"), {
                "fields": ("last_run_at", "total_run_count"),
                "classes": ("collapse",)
            }),
        )

if CrontabSchedule:
    # Unregister existing admin if it exists
    try:
        admin.site.unregister(CrontabSchedule)
    except admin.sites.NotRegistered:
        pass
    
    @admin.register(CrontabSchedule)
    class CrontabScheduleAdmin(admin.ModelAdmin):
        """Admin for crontab schedules"""
        list_display = ('minute', 'hour', 'day_of_week', 'day_of_month', 'month_of_year')
        list_filter = ('day_of_week', 'month_of_year')
        ordering = ('hour', 'minute')

if IntervalSchedule:
    # Unregister existing admin if it exists
    try:
        admin.site.unregister(IntervalSchedule)
    except admin.sites.NotRegistered:
        pass
    
    @admin.register(IntervalSchedule)
    class IntervalScheduleAdmin(admin.ModelAdmin):
        """Admin for interval schedules"""
        list_display = ('every', 'period')
        list_filter = ('period',)
        ordering = ('every',)

if SolarSchedule:
    # Unregister existing admin if it exists
    try:
        admin.site.unregister(SolarSchedule)
    except admin.sites.NotRegistered:
        pass
    
    @admin.register(SolarSchedule)
    class SolarScheduleAdmin(admin.ModelAdmin):
        """Admin for solar schedules"""
        list_display = ('event', 'latitude', 'longitude')
        list_filter = ('event',)

if ClockedSchedule:
    # Unregister existing admin if it exists
    try:
        admin.site.unregister(ClockedSchedule)
    except admin.sites.NotRegistered:
        pass
    
    @admin.register(ClockedSchedule)
    class ClockedScheduleAdmin(admin.ModelAdmin):
        """Admin for clocked schedules"""
        list_display = ('clocked_time',)
        ordering = ('clocked_time',)

# Customize admin site
admin.site.site_header = _("FileFinder Administration")
admin.site.site_title = _("FileFinder Admin")
admin.site.index_title = _("Welcome to FileFinder Administration")

# Set custom index template for dashboard
admin.site.index_template = 'admin/index.html'
