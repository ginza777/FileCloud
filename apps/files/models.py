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

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    parse_file_url = models.TextField(blank=True, null=True, verbose_name="File URL",
                                help_text="Direct link to the document file")
    file_path = models.TextField(blank=True, null=True, verbose_name="Local File Path",
                                 help_text="Path where file is saved locally")
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

    completed = models.BooleanField(default=False, verbose_name="Barchasi tugatildimi?")

    telegram_file_id = models.CharField(blank=True, null=True, verbose_name="Telegram File ID",
                                        help_text="File ID after sending to Telegram channel",db_index=True,max_length=500)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At",db_index=True)
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Updated At")
    json_data = models.JSONField(blank=True, null=True, verbose_name="JSON Data")
    class Meta:
        verbose_name = "Document"
        verbose_name_plural = "Documents"
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        self.completed = (
            self.download_status == 'completed' and
            self.parse_status == 'completed' and
            self.index_status == 'completed' and
            self.telegram_status == 'completed' and
            self.delete_status == 'completed'
        )
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


class SearchQuery(models.Model):
    user = models.ForeignKey('bot.User', on_delete=models.CASCADE, related_name='search_queries')
    query_text = models.CharField(max_length=500)
    found_results = models.BooleanField(default=False)
    is_deep_search = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"'{self.query_text}' by {self.user}"
