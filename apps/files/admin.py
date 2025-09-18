from django.contrib import admin
from .models import ParseProgress, Document, Product, SiteToken


class ProductInline(admin.StackedInline):
    model = Product
    extra = 0
    can_delete = False
    show_change_link = True


@admin.register(ParseProgress)
class ParseProgressAdmin(admin.ModelAdmin):
    list_display = ('id', 'last_page', 'total_pages_parsed', 'last_run_at', 'created_at')
    ordering = ('-last_run_at',)


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'parse_file_url', 'download_status', 'parse_status', 'index_status',
        'telegram_status', 'delete_status', 'completed', 'created_at', 'updated_at'
    )
    ordering = ('-created_at',)
    inlines = [ProductInline]
    search_fields = (
        'id', 'parse_file_url', 'telegram_file_id',
    )
    list_filter = (
        'download_status', 'parse_status', 'index_status', 'telegram_status', 'delete_status',
        'completed', 'created_at', 'updated_at'
    )


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'slug', 'document', 'created_at', 'updated_at')
    ordering = ('-created_at',)
    search_fields = ('id', 'title', 'slug', 'parsed_content', 'document__id')
    list_filter = ('created_at', 'updated_at', 'document','document__completed')


@admin.register(SiteToken)
class SiteTokenAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'token', 'auth_token', 'created_at', 'updated_at')
    ordering = ('-created_at',)
    search_fields = ('id', 'name', 'token', 'auth_token')
    list_filter = ('created_at', 'updated_at')
