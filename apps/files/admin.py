from django.contrib import admin
from .models import ParseProgress, Document, Product, SiteToken, DocumentError, DocumentImage


class ProductInline(admin.StackedInline):
    model = Product
    extra = 0
    can_delete = False
    show_change_link = True


class DocumentErrorInline(admin.TabularInline):
    model = DocumentError
    extra = 0
    can_delete = False
    readonly_fields = ('created_at',)
    fields = ('error_type', 'error_message', 'celery_attempt', 'created_at')


class DocumentImageInline(admin.TabularInline):
    model = DocumentImage
    extra = 1
    fields = ('page_number', 'image', 'created_at')
    readonly_fields = ('created_at',)


@admin.register(ParseProgress)
class ParseProgressAdmin(admin.ModelAdmin):
    list_display = ('id', 'last_page', 'total_pages_parsed', 'last_run_at', 'created_at')
    ordering = ('-last_run_at',)


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    actions = ['set_pipeline_running_to_false']
    list_display = (
        'id', 'parse_file_url', 'download_status', 'parse_status', 'index_status',
        'telegram_status', 'delete_status','pipeline_running','completed','telegram_file_id', 'created_at', 'updated_at'
    )
    ordering = ('-created_at',)
    inlines = [ProductInline, DocumentErrorInline, DocumentImageInline]
    search_fields = (
        'id', 'parse_file_url', 'telegram_file_id',
    )
    list_filter = (
        'download_status', 'parse_status', 'index_status', 'telegram_status', 'delete_status',
        'completed', 'pipeline_running'
    )

    def set_pipeline_running_to_false(self, request, queryset):
        updated_count = queryset.update(pipeline_running=False)
        self.message_user(request, f'{updated_count} ta hujjat uchun pipeline_running muvaffaqiyatli False ga o\'zgartirildi.')
    set_pipeline_running_to_false.short_description = "Tanlangan hujjatlar uchun pipeline_running ni False qilish"


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'slug', 'document', 'created_at', 'updated_at')
    ordering = ('-created_at',)
    search_fields = ('id', 'title', 'slug', 'parsed_content', 'document__id')
    list_filter = ('created_at', 'updated_at', 'document','document__completed')


@admin.register(DocumentError)
class DocumentErrorAdmin(admin.ModelAdmin):
    list_display = ('id', 'document', 'error_type', 'celery_attempt', 'error_message', 'created_at')
    ordering = ('-created_at',)
    search_fields = ('document__id', 'error_message', 'error_type')
    list_filter = ('error_type', 'celery_attempt', 'created_at')
    readonly_fields = ('created_at',)


@admin.register(SiteToken)
class SiteTokenAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'token', 'auth_token', 'created_at', 'updated_at')
    ordering = ('-created_at',)
    search_fields = ('id', 'name', 'token', 'auth_token')
    list_filter = ('created_at', 'updated_at')


@admin.register(DocumentImage)
class DocumentImageAdmin(admin.ModelAdmin):
    list_display = ('document', 'page_number', 'created_at')
    search_fields = ('document__id',)
    list_filter = ('document',)

    # Optimizing the admin panel for better performance
    list_select_related = ('document',)  # Use select_related for foreign key optimization
    raw_id_fields = ('document',)  # Use raw_id_fields for large foreign key dropdowns

    def get_queryset(self, request):
        # Use only() to limit the fields fetched from the database
        queryset = super().get_queryset(request)
        return queryset.only('document', 'page_number', 'created_at')
