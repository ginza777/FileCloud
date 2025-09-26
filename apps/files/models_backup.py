import uuid
from django.db import models


def upload_to(instance, filename):
    """Generate upload path for files"""
    return f'documents/{instance.id}/{filename}'


class ParseProgress(models.Model):
    """Track parsing progress for continuous parsing"""
    id = models.AutoField(primary_key=True)
    last_page = models.IntegerField(default=0, verbose_name="Last Parsed Page")
    total_pages_parsed = models.IntegerField(default=0, verbose_name="Total Pages Parsed")
    last_run_at = models.DateTimeField(auto_now=True, verbose_name="Last Run At")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")

    class Meta:
        verbose_name = "Parse Progress"
        verbose_name_plural = "Parse Progress"
        ordering = ['-last_run_at']

    def __str__(self):
        return f"Last Page: {self.last_page}, Total: {self.total_pages_parsed}"

    @classmethod
    def get_current_progress(cls):
        """Get current parsing progress"""
        progress, created = cls.objects.get_or_create(
            defaults={'last_page': 0, 'total_pages_parsed': 0}
        )
        return progress

    def update_progress(self, page_number):
        """Update parsing progress"""
        self.last_page = page_number
        self.total_pages_parsed += 1
        self.save()



class Document(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Kutilmoqda'),
        ('processing', 'Jarayonda'),
        ('completed', 'Tugatildi'),
        ('failed', 'Xatolik'),
        ('skipped', 'O`tkazib yuborildi'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False,db_index=True)

    parse_file_url = models.TextField(blank=True, null=True, verbose_name="File URL",
                                help_text="Direct link to the document file")
    #status
    download_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending',
                                       verbose_name="Yuklab olish holati")
    parse_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending',
                                    verbose_name="Parse qilish holati")
    index_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending',
                                    verbose_name="Indekslash holati")
    telegram_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending',
                                       verbose_name="Telegram holati")
    delete_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending',
                                     verbose_name="O'chirish holati")

    completed = models.BooleanField(default=False, verbose_name="Barchasi tugatildimi?",db_index=True)

    telegram_file_id = models.CharField(blank=True, null=True, verbose_name="Telegram File ID",
                                        help_text="File ID after sending to Telegram channel",db_index=True,max_length=500)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At",db_index=True)
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Updated At")
    json_data = models.JSONField(blank=True, null=True, verbose_name="JSON Data")
    pipeline_running = models.BooleanField(default=False, db_index=True, help_text="Pipeline hozir ushbu hujjat ustida ishlayotganini bildiradi")

    class Meta:
        verbose_name = "Document"
        verbose_name_plural = "Documents"
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        # Yangi mantiq: faqat telegram_file_id va parsed_content ikkalasi ham bo'sh bo'lmasligi kerak
        has_parsed_content = (
            hasattr(self, 'product') and 
            self.product is not None and 
            self.product.parsed_content is not None and 
            self.product.parsed_content.strip() != ''
        )
        
        if (self.telegram_file_id is not None and 
            self.telegram_file_id.strip() != '' and
            has_parsed_content):
            self.completed = True
            self.pipeline_running = False
        else:
            # Agar shartlar bajarilmagan bo'lsa, completed=False qilamiz
            self.completed = False
        
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Document {self.id} ({self.parse_file_url or 'no file'})"


class Product(models.Model):
    """Product model for digital products"""
    id = models.IntegerField(primary_key=True, verbose_name="Product ID")
    title = models.TextField(verbose_name="Title",db_index=True)
    parsed_content = models.TextField(blank=True, null=True, verbose_name="Parsed Content")
    slug = models.TextField(unique=True, verbose_name="Slug",db_index=True)
    document = models.OneToOneField(Document, on_delete=models.CASCADE, related_name='product', verbose_name="Document")
    view_count = models.PositiveIntegerField(default=0, verbose_name="View Count", db_index=True)
    download_count = models.PositiveIntegerField(default=0, verbose_name="Download Count", db_index=True)
    file_size = models.PositiveBigIntegerField(default=0, verbose_name="File Size (bytes)")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At",db_index=True)
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Updated At")


    class Meta:
        verbose_name = "Product"
        verbose_name_plural = "Products"
        ordering = ['-created_at']

    def __str__(self):
        return self.title



class SiteToken(models.Model):
    NAME_CHOICES = [
        ('soff', 'soff'),
        ('arxiv', 'arxiv'),
    ]

    name = models.CharField(choices=NAME_CHOICES, unique=True,max_length=100)
    token = models.CharField(unique=True,max_length=300)
    auth_token = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class DocumentError(models.Model):
    """Model to store errors that occur during document processing (download, telegram sending, etc.)"""
    ERROR_TYPE_CHOICES = [
        ('download', 'Yuklab olish xatoligi'),
        ('telegram_send', 'Telegramga yuborish xatoligi'),
        ('telegram_download', 'Telegramdan yuklab olish xatoligi'),
        ('parse', 'Parse qilish xatoligi'),
        ('index', 'Indekslash xatoligi'),
        ('other', 'Boshqa xatolik'),
    ]
    
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='errors', verbose_name="Document")
    error_type = models.CharField(max_length=20, choices=ERROR_TYPE_CHOICES, verbose_name="Xatolik turi")
    error_message = models.TextField(verbose_name="Xatolik xabari")
    celery_attempt = models.PositiveIntegerField(default=1, verbose_name="Celery urinish raqami", help_text="Bu xatolik qaysi urinishda yuz bergani")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Yaratilgan vaqt")
    
    class Meta:
        verbose_name = "Document Error"
        verbose_name_plural = "Document Errors"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.get_error_type_display()} - {self.document.id} (urinish: {self.celery_attempt})"


class SearchQuery(models.Model):
    user = models.ForeignKey('bot.User', on_delete=models.CASCADE, related_name='search_queries')
    query_text = models.CharField(max_length=500)
    found_results = models.BooleanField(default=False)
    is_deep_search = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"'{self.query_text}' by {self.user}"


def document_image_upload_to(instance, filename):
    return f"file/{instance.document.id}/{filename}"


class DocumentImage(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='images')
    page_number = models.PositiveIntegerField()
    image = models.ImageField(upload_to=document_image_upload_to)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('document', 'page_number')
        ordering = ['page_number']

    def __str__(self):
        return f"Image p{self.page_number} for {self.document_id}"
