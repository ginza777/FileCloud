"""
Advanced Admin Features
======================

Bu modul admin panel uchun ilg'or funksiyalarni o'z ichiga oladi.
Bulk operations, advanced filtering, export/import va boshqa professional funksiyalar.
"""

from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.contrib.admin.views.main import ChangeList
from django.db.models import Q, Count, Sum
from django.utils.html import format_html
from django.urls import path
from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from datetime import timedelta
import csv
import json

from apps.files.models import Document, Product, DocumentError, ParseProgress
from apps.bot.models import User as BotUser, Broadcast


class StatusFilter(SimpleListFilter):
    """Hujjat holati bo'yicha filter"""
    title = 'Holat'
    parameter_name = 'status'
    
    def lookups(self, request, model_admin):
        return (
            ('completed', 'Tugatilgan'),
            ('pending', 'Kutilmoqda'),
            ('processing', 'Jarayonda'),
            ('failed', 'Xatolik'),
        )
    
    def queryset(self, request, queryset):
        if self.value() == 'completed':
            return queryset.filter(completed=True)
        elif self.value() == 'pending':
            return queryset.filter(
                Q(download_status='pending') | 
                Q(parse_status='pending') | 
                Q(index_status='pending') | 
                Q(telegram_status='pending')
            )
        elif self.value() == 'processing':
            return queryset.filter(
                Q(download_status='processing') | 
                Q(parse_status='processing') | 
                Q(index_status='processing') | 
                Q(telegram_status='processing')
            )
        elif self.value() == 'failed':
            return queryset.filter(
                Q(download_status='failed') | 
                Q(parse_status='failed') | 
                Q(index_status='failed') | 
                Q(telegram_status='failed')
            )


class DateRangeFilter(SimpleListFilter):
    """Sana oralig'i bo'yicha filter"""
    title = 'Sana oralig\'i'
    parameter_name = 'date_range'
    
    def lookups(self, request, model_admin):
        return (
            ('today', 'Bugun'),
            ('week', 'Oxirgi hafta'),
            ('month', 'Oxirgi oy'),
            ('year', 'Oxirgi yil'),
        )
    
    def queryset(self, request, queryset):
        now = timezone.now()
        if self.value() == 'today':
            return queryset.filter(created_at__date=now.date())
        elif self.value() == 'week':
            return queryset.filter(created_at__gte=now - timedelta(days=7))
        elif self.value() == 'month':
            return queryset.filter(created_at__gte=now - timedelta(days=30))
        elif self.value() == 'year':
            return queryset.filter(created_at__gte=now - timedelta(days=365))


class AdvancedDocumentAdmin(admin.ModelAdmin):
    """Advanced Document Admin with bulk operations and optimized queries"""
    
    list_display = [
        'id', 'status_badge', 'parse_file_url_short', 'created_at', 
        'progress_bar', 'actions_column'
    ]
    list_filter = [StatusFilter, DateRangeFilter, 'created_at', 'download_status', 'parse_status']
    search_fields = ['parse_file_url', 'json_data']
    readonly_fields = ['id', 'created_at', 'updated_at']
    list_per_page = 50
    
    # Bulk actions
    actions = ['bulk_download', 'bulk_parse', 'bulk_index', 'bulk_telegram', 'export_csv', 'export_json']
    
    def get_queryset(self, request):
        """Optimized queryset with select_related and prefetch_related"""
        return super().get_queryset(request).select_related().prefetch_related(
            'product_set', 'documenterror_set', 'parseprogress_set'
        )
    
    def status_badge(self, obj):
        """Holatni oddiy ko'rinishda ko'rsatish"""
        if obj.completed:
            text = '✅ Tugatilgan'
        elif any(status == 'failed' for status in [obj.download_status, obj.parse_status, obj.index_status, obj.telegram_status]):
            text = '❌ Xatolik'
        elif any(status == 'processing' for status in [obj.download_status, obj.parse_status, obj.index_status, obj.telegram_status]):
            text = '⏳ Jarayonda'
        else:
            text = '⏸️ Kutilmoqda'
        
        return text
    status_badge.short_description = 'Holat'
    
    def parse_file_url_short(self, obj):
        """URL'ni qisqartirilgan ko'rinishda ko'rsatish"""
        if len(obj.parse_file_url) > 50:
            return obj.parse_file_url[:47] + '...'
        return obj.parse_file_url
    parse_file_url_short.short_description = 'Fayl URL'
    
    def progress_bar(self, obj):
        """Jarayon foizini oddiy ko'rinishda ko'rsatish"""
        total_steps = 4
        completed_steps = sum([
            obj.download_status == 'completed',
            obj.parse_status == 'completed',
            obj.index_status == 'completed',
            obj.telegram_status == 'completed'
        ])
        
        percentage = (completed_steps / total_steps) * 100
        return f"{completed_steps}/{total_steps} ({percentage:.0f}%)"
    progress_bar.short_description = 'Jarayon'
    
    def actions_column(self, obj):
        """Har bir qator uchun action tugmalari"""
        return format_html(
            '<a href="/admin/files/document/{}/change/" class="btn btn-sm btn-primary">Tahrirlash</a>',
            obj.id
        )
    actions_column.short_description = 'Amallar'
    
    # Bulk operations
    def bulk_download(self, request, queryset):
        """Bulk download operation"""
        count = queryset.update(download_status='pending')
        messages.success(request, f'{count} ta hujjat yuklab olish uchun navbatga qo\'shildi.')
    bulk_download.short_description = 'Yuklab olishni boshlash'
    
    def bulk_parse(self, request, queryset):
        """Bulk parse operation"""
        count = queryset.update(parse_status='pending')
        messages.success(request, f'{count} ta hujjat parse qilish uchun navbatga qo\'shildi.')
    bulk_parse.short_description = 'Parse qilishni boshlash'
    
    def bulk_index(self, request, queryset):
        """Bulk index operation"""
        count = queryset.update(index_status='pending')
        messages.success(request, f'{count} ta hujjat indekslash uchun navbatga qo\'shildi.')
    bulk_index.short_description = 'Indekslashni boshlash'
    
    def bulk_telegram(self, request, queryset):
        """Bulk telegram operation"""
        count = queryset.update(telegram_status='pending')
        messages.success(request, f'{count} ta hujjat Telegram\'ga yuborish uchun navbatga qo\'shildi.')
    bulk_telegram.short_description = 'Telegram\'ga yuborishni boshlash'
    
    def export_csv(self, request, queryset):
        """CSV formatida eksport qilish"""
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="documents.csv"'
        
        writer = csv.writer(response)
        writer.writerow(['ID', 'URL', 'Download Status', 'Parse Status', 'Index Status', 'Telegram Status', 'Created At'])
        
        for obj in queryset:
            writer.writerow([
                obj.id,
                obj.parse_file_url,
                obj.download_status,
                obj.parse_status,
                obj.index_status,
                obj.telegram_status,
                obj.created_at
            ])
        
        return response
    export_csv.short_description = 'CSV formatida eksport qilish'
    
    def export_json(self, request, queryset):
        """JSON formatida eksport qilish"""
        data = []
        for obj in queryset:
            data.append({
                'id': str(obj.id),
                'parse_file_url': obj.parse_file_url,
                'download_status': obj.download_status,
                'parse_status': obj.parse_status,
                'index_status': obj.index_status,
                'telegram_status': obj.telegram_status,
                'completed': obj.completed,
                'created_at': obj.created_at.isoformat(),
                'updated_at': obj.updated_at.isoformat()
            })
        
        response = HttpResponse(json.dumps(data, indent=2), content_type='application/json')
        response['Content-Disposition'] = 'attachment; filename="documents.json"'
        return response
    export_json.short_description = 'JSON formatida eksport qilish'
    
    # Custom URLs
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('bulk-operations/', self.admin_site.admin_view(self.bulk_operations_view), name='files_document_bulk_operations'),
            path('statistics/', self.admin_site.admin_view(self.statistics_view), name='files_document_statistics'),
        ]
        return custom_urls + urls
    
    def bulk_operations_view(self, request):
        """Bulk operations sahifasi"""
        if request.method == 'POST':
            action = request.POST.get('action')
            document_ids = request.POST.getlist('document_ids')
            
            if action and document_ids:
                queryset = Document.objects.filter(id__in=document_ids)
                
                if action == 'download':
                    count = queryset.update(download_status='pending')
                    messages.success(request, f'{count} ta hujjat yuklab olish uchun navbatga qo\'shildi.')
                elif action == 'parse':
                    count = queryset.update(parse_status='pending')
                    messages.success(request, f'{count} ta hujjat parse qilish uchun navbatga qo\'shildi.')
                elif action == 'index':
                    count = queryset.update(index_status='pending')
                    messages.success(request, f'{count} ta hujjat indekslash uchun navbatga qo\'shildi.')
                elif action == 'telegram':
                    count = queryset.update(telegram_status='pending')
                    messages.success(request, f'{count} ta hujjat Telegram\'ga yuborish uchun navbatga qo\'shildi.')
                
                return redirect('admin:files_document_bulk_operations')
        
        # Get documents for bulk operations
        documents = Document.objects.all()[:100]  # Limit for performance
        
        context = {
            'title': 'Bulk Operations',
            'documents': documents,
            'has_permission': True,
        }
        
        return render(request, 'admin/files/document/bulk_operations.html', context)
    
    def statistics_view(self, request):
        """Statistics sahifasi"""
        # Calculate statistics
        total_documents = Document.objects.count()
        completed_documents = Document.objects.filter(completed=True).count()
        pending_documents = Document.objects.filter(
            Q(download_status='pending') | 
            Q(parse_status='pending') | 
            Q(index_status='pending') | 
            Q(telegram_status='pending')
        ).count()
        failed_documents = Document.objects.filter(
            Q(download_status='failed') | 
            Q(parse_status='failed') | 
            Q(index_status='failed') | 
            Q(telegram_status='failed')
        ).count()
        
        # Daily statistics for the last 30 days
        daily_stats = []
        for i in range(30):
            date = timezone.now().date() - timedelta(days=i)
            count = Document.objects.filter(created_at__date=date).count()
            daily_stats.append({
                'date': date.strftime('%Y-%m-%d'),
                'count': count
            })
        
        daily_stats.reverse()
        
        context = {
            'title': 'Document Statistics',
            'total_documents': total_documents,
            'completed_documents': completed_documents,
            'pending_documents': pending_documents,
            'failed_documents': failed_documents,
            'daily_stats': daily_stats,
            'has_permission': True,
        }
        
        return render(request, 'admin/files/document/statistics.html', context)


class AdvancedProductAdmin(admin.ModelAdmin):
    """Advanced Product Admin"""
    
    list_display = ['id', 'title_short', 'document_link', 'created_at', 'word_count']
    list_filter = [DateRangeFilter, 'created_at']
    search_fields = ['title', 'parsed_content']
    readonly_fields = ['id', 'created_at', 'updated_at']
    list_per_page = 50
    
    def product_status(self, obj):
        """Mahsulot holati: Parsed/Empty/No Document"""
        if obj.parsed_content and obj.parsed_content.strip():
            return 'Parsed'
        if obj.document:
            return 'Empty'
        return 'No Document'
    product_status.short_description = 'Status'

    def title_short(self, obj):
        """Sarlavhani qisqartirilgan ko'rinishda ko'rsatish"""
        if len(obj.title) > 50:
            return obj.title[:47] + '...'
        return obj.title
    title_short.short_description = 'Sarlavha'
    
    def document_link(self, obj):
        """Hujjatga havola"""
        if obj.document:
            return format_html(
                '<a href="/admin/files/document/{}/change/">{}</a>',
                obj.document.id, str(obj.document.id)[:8] + '...'
            )
        return '-'
    document_link.short_description = 'Hujjat'
    
    def word_count(self, obj):
        """So'zlar soni"""
        if obj.parsed_content:
            return len(obj.parsed_content.split())
        return 0
    word_count.short_description = 'So\'zlar soni'


class AdvancedUserAdmin(admin.ModelAdmin):
    """Advanced Bot User Admin"""
    
    list_display = ['id', 'full_name', 'username', 'is_active_badge', 'created_at', 'last_activity']
    list_filter = ['is_blocked', 'created_at']
    search_fields = ['first_name', 'last_name', 'username']
    readonly_fields = ['id', 'created_at', 'updated_at']
    list_per_page = 50
    
    def is_active_badge(self, obj):
        """Faollik holatini oddiy ko'rinishda ko'rsatish"""
        if getattr(obj, 'is_blocked', False):
            return '🚫 Blocked'
        else:
            return '✅ Active'
    is_active_badge.short_description = 'Holat'

    def last_activity(self, obj):
        return getattr(obj, 'last_active', None)
    last_activity.short_description = 'Oxirgi faollik'


# Register advanced admins (only if not already registered)
try:
    admin.site.register(Product, AdvancedProductAdmin)
    admin.site.register(BotUser, AdvancedUserAdmin)
except admin.sites.AlreadyRegistered:
    # Models already registered, skip
    pass
