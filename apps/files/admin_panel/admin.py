from django.contrib import admin
from apps.files.models import Document, Product, SiteToken, DocumentError, DocumentImage


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


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    """Admin for document management with performance optimizations"""
    actions = ['set_pipeline_running_to_false', 'unblock_products_for_documents']
    list_display = (
        'id', 'parse_file_url', 'download_status', 'parse_status', 'index_status',
        'telegram_status', 'delete_status','pipeline_running','completed','telegram_file_id', 
        'get_product_blocked_status', 'created_at', 'updated_at'
    )
    ordering = ('-created_at',)
    inlines = [ProductInline, DocumentErrorInline, DocumentImageInline]
    search_fields = (
        'id', 'parse_file_url', 'telegram_file_id',
    )
    list_filter = (
        'download_status', 'parse_status', 'index_status', 'telegram_status', 'delete_status',
        'completed', 'pipeline_running', 'product__blocked'
    )
    
    # Performance optimizations
    list_per_page = 25  # Reduce items per page for faster loading
    list_select_related = ()  # No foreign keys in list_display
    raw_id_fields = ()  # No foreign key fields in forms
    
    def get_queryset(self, request):
        """Optimize queryset for better performance"""
        queryset = super().get_queryset(request)
        # Only fetch fields needed for list_display
        return queryset.select_related('product').only(
            'id', 'parse_file_url', 'download_status', 'parse_status', 
            'index_status', 'telegram_status', 'delete_status', 
            'pipeline_running', 'completed', 'telegram_file_id', 
            'created_at', 'updated_at', 'product__blocked'
        )
    
    def get_changelist(self, request, **kwargs):
        """Use optimized changelist for better performance"""
        from django.contrib.admin.views.main import ChangeList
        return ChangeList

    def set_pipeline_running_to_false(self, request, queryset):
        updated_count = queryset.update(pipeline_running=False)
        self.message_user(request, f'{updated_count} ta hujjat uchun pipeline_running muvaffaqiyatli False ga o\'zgartirildi.')
    set_pipeline_running_to_false.short_description = "Tanlangan hujjatlar uchun pipeline_running ni False qilish"
    
    def unblock_products_for_documents(self, request, queryset):
        """Tanlangan hujjatlarning blocked productlarini unblock qilish"""
        from apps.files.models import Product
        
        # Tanlangan hujjatlarning productlarini topish
        document_ids = list(queryset.values_list('id', flat=True))
        blocked_products = Product.objects.filter(
            document_id__in=document_ids,
            blocked=True
        )
        
        if not blocked_products.exists():
            self.message_user(
                request,
                "Tanlangan hujjatlarda blocked productlar topilmadi.",
                level='warning'
            )
            return
        
        # Blocked productlarni unblock qilish
        updated_count = blocked_products.update(
            blocked=False,
            blocked_reason=None,
            blocked_at=None
        )
        
        self.message_user(
            request,
            f"{updated_count} ta blocked product unblock qilindi."
        )
    
    unblock_products_for_documents.short_description = "Tanlangan hujjatlarning blocked productlarini unblock qilish"
    
    def get_product_blocked_status(self, obj):
        """Product blocked holatini ko'rsatish"""
        if hasattr(obj, 'product') and obj.product:
            if obj.product.blocked:
                return "🔒 Blocked"
            else:
                return "✅ Active"
        return "❓ No Product"
    
    get_product_blocked_status.short_description = "Product Status"
    get_product_blocked_status.admin_order_field = 'product__blocked'


# admin.py

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    """
    Optimallashtirilgan Product admin paneli.
    - Ro'yxat va yagona mahsulot sahifalari tez ishlashi uchun sozlangan.
    """
    actions = ['unblock_products']

    # ----------------------------------------------------
    # Ro'yxat Sahifasi Sozlamalari (List View)
    # ----------------------------------------------------
    list_display = ('id', 'title', 'slug', 'blocked', 'document', 'created_at', 'updated_at')
    list_display_links = ('id', 'title')
    ordering = ('-created_at',)

    # ENG MUHIM OPTIMIZATSIYA (List View):
    # 'parsed_content' bo'yicha qidiruv olib tashlandi. Bu qidiruvni tezlashtiradi.
    search_fields = ('id', 'title', 'slug', 'document__id')

    # IKKINCHI MUHIM OPTIMIZATSIYA (List View):
    # 'document' (ForeignKey) bo'yicha filtr olib tashlandi. Bu filtr panelini tezlashtiradi.
    list_filter = ('blocked', 'document__completed', 'created_at', 'updated_at')

    # ----------------------------------------------------
    # Yagona Mahsulot Sahifasi Sozlamalari (Detail/Change View)
    # ----------------------------------------------------

    # ENG MUHIM OPTIMIZATSIYA (Detail View):
    # 'parsed_content' maydoni formadan olib tashlandi. Bu sahifa yuklanishini tezlashtiradi.
    # Agar biror maydonni ko'rsatish kerak bo'lsa, shu ro'yxatga qo'shing.
    fields = (
        'title', 'slug', 'document',
        'view_count', 'download_count', 'file_size',
        'blocked', 'blocked_reason', 'blocked_at',
        'created_at', 'updated_at'
    )

    # Vaqt maydonlarini tahrirlashni cheklash.
    readonly_fields = ('created_at', 'updated_at', 'blocked_at')

    # 'document' uchun ochiluvchi ro'yxat o'rniga qidiruv maydonini ishlatish.
    # Bu yagona mahsulot sahifasi uchun juda muhim optimizatsiya.
    raw_id_fields = ('document',)

    # ----------------------------------------------------
    # Umumiy Tezlik Sozlamalari
    # ----------------------------------------------------
    list_per_page = 30  # Bir sahifadagi yozuvlar soni

    # N+1 muammosini hal qilish uchun. Ro'yxatda 'document' ma'lumotlarini
    # bitta so'rovda olishni ta'minlaydi.
    list_select_related = ('document',)
    
    def unblock_products(self, request, queryset):
        """Tanlangan productlarni unblock qilish"""
        updated_count = queryset.filter(blocked=True).update(
            blocked=False,
            blocked_reason=None,
            blocked_at=None
        )
        self.message_user(
            request,
            f"{updated_count} ta product unblock qilindi."
        )
    
    unblock_products.short_description = "Tanlangan productlarni unblock qilish"

    # Jami yozuvlar sonini hisoblash uchun qo'shimcha so'rov yubormaslik.
    # Katta jadvallarda sezilarli tezlik beradi.
    show_full_result_count = False

    def get_queryset(self, request):
        """Ma'lumotlar bazasidan faqat kerakli ustunlarni olish uchun so'rovni optimallashtiradi."""
        queryset = super().get_queryset(request)
        return queryset.select_related('document').only(
            'id', 'title', 'slug', 'document__id', 'created_at', 'updated_at'
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
    list_display = ('id', 'document', 'page_number', 'created_at')
    search_fields = ('document__id', 'page_number')
    list_filter = ('created_at',)  # Changed from 'document' to avoid performance issues with large document lists
    
    # Performance optimizations
    list_per_page = 50  # Limit items per page for better performance
    list_select_related = ('document',)  # Use select_related for foreign key optimization
    raw_id_fields = ('document',)  # Use raw_id_fields for large foreign key dropdowns
    readonly_fields = ('created_at',)  # Make created_at readonly
    
    def get_queryset(self, request):
        """Optimize queryset for better performance"""
        queryset = super().get_queryset(request)
        return queryset.select_related('document').only(
            'id', 'document_id', 'page_number', 'created_at'
        )
