from django.contrib import admin
from apps.files.models import ParseProgress, Document, Product, SiteToken, DocumentError, DocumentImage


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
    """Admin for parsing progress tracking"""
    list_display = ('id', 'last_page', 'total_pages_parsed', 'last_run_at', 'created_at')
    ordering = ('-last_run_at',)
    list_per_page = 50  # Limit items per page for better performance
    readonly_fields = ('created_at',)
    
    def get_queryset(self, request):
        """Optimize queryset for better performance"""
        return super().get_queryset(request).only(
            'id', 'last_page', 'total_pages_parsed', 'last_run_at', 'created_at'
        )


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    """Admin for document management with performance optimizations"""
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
    
    # Performance optimizations
    list_per_page = 25  # Reduce items per page for faster loading
    list_select_related = ()  # No foreign keys in list_display
    raw_id_fields = ()  # No foreign key fields in forms
    
    def get_queryset(self, request):
        """Optimize queryset for better performance"""
        queryset = super().get_queryset(request)
        # Only fetch fields needed for list_display
        return queryset.only(
            'id', 'parse_file_url', 'download_status', 'parse_status', 
            'index_status', 'telegram_status', 'delete_status', 
            'pipeline_running', 'completed', 'telegram_file_id', 
            'created_at', 'updated_at'
        )
    
    def get_changelist(self, request, **kwargs):
        """Use optimized changelist for better performance"""
        from django.contrib.admin.views.main import ChangeList
        return ChangeList

    def set_pipeline_running_to_false(self, request, queryset):
        updated_count = queryset.update(pipeline_running=False)
        self.message_user(request, f'{updated_count} ta hujjat uchun pipeline_running muvaffaqiyatli False ga o\'zgartirildi.')
    set_pipeline_running_to_false.short_description = "Tanlangan hujjatlar uchun pipeline_running ni False qilish"


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    """Admin for product management with performance optimizations"""
    list_display = ('id', 'title', 'slug', 'document', 'created_at', 'updated_at')
    ordering = ('-created_at',)
    search_fields = ('id', 'title', 'slug', 'parsed_content', 'document__id')
    list_filter = ('created_at', 'updated_at', 'document','document__completed')
    
    # Performance optimizations
    list_per_page = 30  # Limit items per page
    list_select_related = ('document',)  # Optimize foreign key queries
    raw_id_fields = ('document',)  # Use raw_id for large foreign key dropdowns
    
    def get_queryset(self, request):
        """Optimize queryset for better performance"""
        queryset = super().get_queryset(request)
        return queryset.select_related('document').only(
            'id', 'title', 'slug', 'document_id', 'created_at', 'updated_at'
        )


@admin.register(DocumentError)
class DocumentErrorAdmin(admin.ModelAdmin):
    """Admin for document error tracking with performance optimizations"""
    list_display = ('id', 'document', 'error_type', 'celery_attempt', 'error_message', 'created_at')
    ordering = ('-created_at',)
    search_fields = ('document__id', 'error_message', 'error_type')
    list_filter = ('error_type', 'celery_attempt', 'created_at')
    readonly_fields = ('created_at',)
    
    # Performance optimizations
    list_per_page = 50  # Limit items per page
    list_select_related = ('document',)  # Optimize foreign key queries
    raw_id_fields = ('document',)  # Use raw_id for large foreign key dropdowns
    
    def get_queryset(self, request):
        """Optimize queryset for better performance"""
        queryset = super().get_queryset(request)
        return queryset.select_related('document').only(
            'id', 'document_id', 'error_type', 'celery_attempt', 
            'error_message', 'created_at'
        )


@admin.register(SiteToken)
class SiteTokenAdmin(admin.ModelAdmin):
    """Admin for site token management with performance optimizations"""
    list_display = ('id', 'name', 'token', 'auth_token', 'created_at', 'updated_at')
    ordering = ('-created_at',)
    search_fields = ('id', 'name', 'token', 'auth_token')
    list_filter = ('created_at', 'updated_at')
    
    # Performance optimizations
    list_per_page = 20  # Limit items per page
    readonly_fields = ('created_at', 'updated_at')
    
    def get_queryset(self, request):
        """Optimize queryset for better performance"""
        queryset = super().get_queryset(request)
        return queryset.only(
            'id', 'name', 'token', 'auth_token', 'created_at', 'updated_at'
        )


@admin.register(DocumentImage)
class DocumentImageAdmin(admin.ModelAdmin):
    """Admin for document image management with performance optimizations"""
    list_display = ('document', 'page_number', 'created_at')
    search_fields = ('document__id',)
    list_filter = ('document',)
    
    # Performance optimizations
    list_per_page = 50  # Limit items per page for better performance
    list_select_related = ('document',)  # Use select_related for foreign key optimization
    raw_id_fields = ('document',)  # Use raw_id_fields for large foreign key dropdowns
    
    def get_queryset(self, request):
        """Optimize queryset for better performance"""
        queryset = super().get_queryset(request)
        return queryset.select_related('document').only(
            'document_id', 'page_number', 'created_at'
        )
