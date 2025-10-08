"""
Files App Models
================

Bu modul fayllar bilan bog'liq barcha Django modellarini o'z ichiga oladi.
Hujjatlar, mahsulotlar, xatoliklar va indekslash jarayonlarini boshqaradi.

Modellar:
- ParseProgress: Parse jarayonini kuzatish
- Document: Hujjat ma'lumotlari
- Product: Mahsulot ma'lumotlari
- SiteToken: Sayt tokenlari
- DocumentError: Hujjat xatoliklari
- SearchQuery: Qidiruv so'rovlari
- DocumentImage: Hujjat rasmlari
"""

import uuid
from django.db import models


def upload_to(instance, filename):
    """
    Fayllar uchun yuklash yo'lini yaratadi.
    
    Args:
        instance: Model obyekti (Document yoki DocumentImage)
        filename (str): Fayl nomi
    
    Returns:
        str: Fayl saqlanish yo'li (documents/{instance.id}/{filename})
    
    Misol:
        upload_to(document, "file.pdf") -> "documents/uuid-123/file.pdf"
    """
    return f'documents/{instance.id}/{filename}'


class ParseProgress(models.Model):
    """
    Uzluksiz parse jarayonini kuzatish uchun model.
    
    Bu model:
    - Parse jarayonining holatini saqlaydi
    - Oxirgi parse qilingan sahifani kuzatadi
    - Jami parse qilingan sahifalar sonini hisoblaydi
    - Parse jarayonining vaqtini kuzatadi
    
    Maydonlar:
    - last_page: Oxirgi parse qilingan sahifa
    - total_pages_parsed: Jami parse qilingan sahifalar
    - last_run_at: Oxirgi ishga tushirilgan vaqt
    - created_at: Yaratilgan vaqt
    """
    id = models.AutoField(
        primary_key=True,
        help_text="Parse progress ID'si"
    )
    last_page = models.IntegerField(
        default=0, 
        verbose_name="Last Parsed Page",
        help_text="Oxirgi parse qilingan sahifa raqami"
    )
    total_pages_parsed = models.IntegerField(
        default=0, 
        verbose_name="Total Pages Parsed",
        help_text="Jami parse qilingan sahifalar soni"
    )
    last_run_at = models.DateTimeField(
        auto_now=True, 
        verbose_name="Last Run At",
        help_text="Oxirgi parse jarayoni boshlangan vaqt"
    )
    created_at = models.DateTimeField(
        auto_now_add=True, 
        verbose_name="Created At",
        help_text="Parse progress yaratilgan vaqt"
    )

    class Meta:
        verbose_name = "Parse Progress"
        verbose_name_plural = "Parse Progress"
        ordering = ['-last_run_at']

    def __str__(self):
        """
        Model obyektining string ko'rinishi.
        
        Returns:
            str: Oxirgi sahifa va jami sahifalar ma'lumoti
        """
        return f"Last Page: {self.last_page}, Total: {self.total_pages_parsed}"

    @classmethod
    def get_current_progress(cls):
        """
        Hozirgi parse jarayonini olish.
        
        Returns:
            ParseProgress: Mavjud yoki yangi parse progress obyekti
        
        Misol:
            progress = ParseProgress.get_current_progress()
            print(f"Oxirgi sahifa: {progress.last_page}")
        """
        progress, created = cls.objects.get_or_create(
            defaults={'last_page': 0, 'total_pages_parsed': 0}
        )
        return progress

    def update_progress(self, page_number):
        """
        Parse jarayonini yangilash.
        
        Args:
            page_number (int): Yangi parse qilingan sahifa raqami
        
        Bu metod:
        - last_page ni yangilaydi
        - total_pages_parsed ni 1 ga oshiradi
        - last_run_at ni hozirgi vaqtga o'rnatadi
        """
        self.last_page = page_number
        self.total_pages_parsed += 1
        self.save()


class Document(models.Model):
    """
    Hujjat ma'lumotlarini saqlash uchun asosiy model.
    
    Bu model:
    - Hujjat faylini saqlaydi
    - Parse jarayonini kuzatadi
    - Telegram yuborish holatini boshqaradi
    - Indekslash jarayonini kuzatadi
    - Pipeline holatini boshqaradi
    
    Maydonlar:
    - parse_file_url: Hujjat fayl havolasi
    - download_status: Yuklab olish holati
    - parse_status: Parse qilish holati
    - index_status: Indekslash holati
    - telegram_status: Telegram holati
    - delete_status: O'chirish holati
    - completed: Barchasi tugatildimi
    - telegram_file_id: Telegram fayl ID'si
    - pipeline_running: Pipeline ishlayotganmi
    """
    
    STATUS_CHOICES = [
        ('pending', 'Kutilmoqda'),
        ('processing', 'Jarayonda'),
        ('completed', 'Tugatildi'),
        ('failed', 'Xatolik'),
        ('skipped', 'O`tkazib yuborildi'),
    ]

    id = models.UUIDField(
        primary_key=True, 
        default=uuid.uuid4, 
        editable=False, 
        db_index=True,
        help_text="Hujjatning noyub identifikatori"
    )

    parse_file_url = models.TextField(
        blank=True, 
        null=True, 
        verbose_name="File URL",
        help_text="Hujjat faylining to'g'ridan-to'g'ri havolasi"
    )
    
    # Status fields - Jarayon holatlari
    download_status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='pending',
        verbose_name="Yuklab olish holati", 
        db_index=True,
        help_text="Hujjat yuklab olish jarayoni holati"
    )
    parse_status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='pending',
        verbose_name="Parse qilish holati", 
        db_index=True,
        help_text="Hujjat parse qilish jarayoni holati"
    )
    index_status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='pending',
        verbose_name="Indekslash holati", 
        db_index=True,
        help_text="Hujjat indekslash jarayoni holati"
    )
    telegram_status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='pending',
        verbose_name="Telegram holati", 
        db_index=True,
        help_text="Telegram'ga yuborish jarayoni holati"
    )
    delete_status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='pending',
        verbose_name="O'chirish holati", 
        db_index=True,
        help_text="Hujjat o'chirish jarayoni holati"
    )

    completed = models.BooleanField(
        default=False, 
        verbose_name="Barchasi tugatildimi?", 
        db_index=True,
        help_text="Hujjat barcha jarayonlardan o'tganmi"
    )

    telegram_file_id = models.CharField(
        blank=True, 
        null=True, 
        verbose_name="Telegram File ID",
        help_text="Telegram kanaliga yuborilgandan keyin fayl ID'si", 
        db_index=True,
        max_length=500
    )
    created_at = models.DateTimeField(
        auto_now_add=True, 
        verbose_name="Created At", 
        db_index=True,
        help_text="Hujjat yaratilgan vaqt"
    )
    updated_at = models.DateTimeField(
        auto_now=True, 
        verbose_name="Updated At", 
        db_index=True,
        help_text="Hujjat oxirgi yangilangan vaqt"
    )
    json_data = models.JSONField(
        blank=True, 
        null=True, 
        verbose_name="JSON Data",
        help_text="Hujjat bilan bog'liq qo'shimcha JSON ma'lumotlar"
    )
    pipeline_running = models.BooleanField(
        default=False, 
        db_index=True,
        help_text="Pipeline hozir ushbu hujjat ustida ishlayotganini bildiradi"
    )

    class Meta:
        verbose_name = "Document"
        verbose_name_plural = "Documents"
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        """
        Hujjat saqlash metodini override qiladi va ideal holatni tekshiradi.

        Ideal holat qoidasi:
        1. document.product.parsed_content mavjud va bo'sh emas.
        2. telegram_file_id mavjud va bo'sh emas.
        """
        # Faqat 'update_fields' ishlatilayotganda, barcha maydonlarni yuklamaslik
        # uchun product'ni alohida olishimiz mumkin.
        if 'product' not in self.__dict__:
            # Agar product yuklanmagan bo'lsa, uni DB'dan olishga urinib ko'ramiz
            try:
                self.product
            except Product.DoesNotExist:
                # Agar product mavjud bo'lmasa, uni yaratmagunimizcha has_parsed_content
                # False bo'ladi
                pass

        has_parsed_content = (
                hasattr(self, 'product') and
                self.product is not None and
                self.product.parsed_content is not None and
                self.product.parsed_content.strip() != ''
        )

        has_telegram_file = (
                self.telegram_file_id is not None and
                self.telegram_file_id.strip() != ''
        )

        # IDEAL HOLAT TEKSHIRUVI
        if has_parsed_content and has_telegram_file:
            # Holat ideal bo'lsa, barcha statuslarni 'completed' qilamiz
            self.completed = True
            self.pipeline_running = False  # Pipeline ishini to'xtatamiz
            self.download_status = 'completed'
            self.parse_status = 'completed'
            self.index_status = 'completed'
            self.telegram_status = 'completed'
            self.delete_status = 'completed'
        else:
            # Agar ideal holat bo'lmasa, pipeline'ni qayta ishga tushirish uchun
            # barcha statuslarni 'pending' holatiga qaytaramiz.
            self.completed = False
            self.pipeline_running = False  # Yangi ishni boshlashdan oldin qulfni ochamiz
            self.download_status = 'pending'
            self.parse_status = 'pending'
            self.index_status = 'pending'
            self.telegram_status = 'pending'
            self.delete_status = 'pending'

        super().save(*args, **kwargs)

    def __str__(self):
        """
        Model obyektining string ko'rinishi.
        
        Returns:
            str: Hujjat ID va fayl havolasi
        """
        return f"Document {self.id} ({self.parse_file_url or 'no file'})"

    def check_and_set_completed(self):
        """
        Agar barcha status maydonlari 'completed' bo'lsa, completed=True ga o'zgartiring va saqlang.
        """
        if (
            self.download_status == 'completed' and
            self.parse_status == 'completed' and
            self.index_status == 'completed' and
            self.telegram_status == 'completed' and
            self.delete_status == 'completed'
        ):
            if not self.completed:
                self.completed = True
                self.save(update_fields=['completed'])


class Product(models.Model):
    """
    Raqamli mahsulotlar uchun model.
    
    Bu model:
    - Hujjatdan parse qilingan ma'lumotlarni saqlaydi
    - Mahsulot statistikalarini kuzatadi
    - Hujjat bilan bir-biriga bog'laydi
    - Ko'rish va yuklab olish sonlarini hisoblaydi
    
    Maydonlar:
    - id: Mahsulot ID'si
    - title: Mahsulot sarlavhasi
    - parsed_content: Parse qilingan kontent
    - slug: URL slug
    - document: Bog'langan hujjat
    - view_count: Ko'rishlar soni
    - download_count: Yuklab olishlar soni
    - file_size: Fayl hajmi
    """
    id = models.AutoField(
        primary_key=True, 
        verbose_name="Product ID",
        help_text="Mahsulotning noyub identifikatori"
    )
    title = models.TextField(
        verbose_name="Title", 
        db_index=True,
        help_text="Mahsulot sarlavhasi"
    )
    parsed_content = models.TextField(
        blank=True, 
        null=True, 
        verbose_name="Parsed Content",
        help_text="Hujjatdan parse qilingan matn kontenti"
    )
    slug = models.TextField(
        blank=True,
        null=True,
        unique=True, 
        verbose_name="Slug", 
        db_index=True,
        help_text="URL uchun slug (masalan: 'matematika-darsligi')"
    )
    document = models.OneToOneField(
        Document, 
        on_delete=models.CASCADE, 
        related_name='product', 
        verbose_name="Document",
        help_text="Bog'langan hujjat"
    )
    view_count = models.PositiveIntegerField(
        default=0, 
        verbose_name="View Count", 
        db_index=True,
        help_text="Mahsulotni ko'rishlar soni"
    )
    download_count = models.PositiveIntegerField(
        default=0, 
        verbose_name="Download Count", 
        db_index=True,
        help_text="Mahsulotni yuklab olishlar soni"
    )
    file_size = models.PositiveBigIntegerField(
        default=0, 
        verbose_name="File Size (bytes)",
        help_text="Fayl hajmi baytlarda"
    )
    created_at = models.DateTimeField(
        auto_now_add=True, 
        verbose_name="Created At", 
        db_index=True,
        help_text="Mahsulot yaratilgan vaqt"
    )
    updated_at = models.DateTimeField(
        auto_now=True, 
        verbose_name="Updated At",
        help_text="Mahsulot oxirgi yangilangan vaqt"
    )

    class Meta:
        verbose_name = "Product"
        verbose_name_plural = "Products"
        ordering = ['-created_at']


    def __str__(self):
        """
        Model obyektining string ko'rinishi.
        
        Returns:
            str: Mahsulot sarlavhasi
        """
        return self.title


class SiteToken(models.Model):
    """
    Tashqi saytlar bilan autentifikatsiya uchun tokenlar.
    
    Bu model:
    - SOFF.UZ va Arxiv.uz saytlari uchun tokenlarni saqlaydi
    - Autentifikatsiya ma'lumotlarini boshqaradi
    - Token yangilanishini kuzatadi
    
    Maydonlar:
    - name: Sayt nomi (soff, arxiv)
    - token: Asosiy token
    - auth_token: Autentifikatsiya token'i
    """
    
    NAME_CHOICES = [
        ('soff', 'soff'),
        ('arxiv', 'arxiv'),
    ]

    name = models.CharField(
        choices=NAME_CHOICES, 
        unique=True, 
        max_length=100,
        help_text="Sayt nomi (soff yoki arxiv)"
    )
    token = models.CharField(
        unique=True, 
        max_length=300,
        help_text="Asosiy autentifikatsiya token'i"
    )
    auth_token = models.TextField(
        blank=True, 
        null=True,
        help_text="Qo'shimcha autentifikatsiya token'i"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Token yaratilgan vaqt"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Token oxirgi yangilangan vaqt"
    )

    def __str__(self):
        """
        Model obyektining string ko'rinishi.
        
        Returns:
            str: Sayt nomi
        """
        return self.name


class DocumentError(models.Model):
    """
    Hujjat qayta ishlash jarayonida yuz bergan xatoliklarni saqlash uchun model.
    
    Bu model:
    - Har xil turdagi xatoliklarni kuzatadi
    - Celery urinishlarini hisoblaydi
    - Xatoliklar tarixini saqlaydi
    - Debug va monitoring uchun ishlatiladi
    
    Maydonlar:
    - document: Bog'langan hujjat
    - error_type: Xatolik turi
    - error_message: Xatolik xabari
    - celery_attempt: Celery urinish raqami
    """
    
    ERROR_TYPE_CHOICES = [
        ('download', 'Yuklab olish xatoligi'),
        ('telegram_send', 'Telegramga yuborish xatoligi'),
        ('telegram_download', 'Telegramdan yuklab olish xatoligi'),
        ('parse', 'Parse qilish xatoligi'),
        ('index', 'Indekslash xatoligi'),
        ('other', 'Boshqa xatolik'),
    ]

    document = models.ForeignKey(
        Document, 
        on_delete=models.CASCADE, 
        related_name='errors', 
        verbose_name="Document",
        db_index=True,
        help_text="Xatolik yuz bergan hujjat"
    )
    error_type = models.CharField(
        max_length=20, 
        choices=ERROR_TYPE_CHOICES, 
        verbose_name="Xatolik turi", 
        db_index=True,
        help_text="Xatolikning turi"
    )
    error_message = models.TextField(
        verbose_name="Xatolik xabari",
        help_text="Xatolikning batafsil tavsifi"
    )
    celery_attempt = models.PositiveIntegerField(
        default=1, 
        verbose_name="Celery urinish raqami",
        help_text="Bu xatolik qaysi urinishda yuz bergani"
    )
    created_at = models.DateTimeField(
        auto_now_add=True, 
        verbose_name="Yaratilgan vaqt", 
        db_index=True,
        help_text="Xatolik yuz bergan vaqt"
    )

    class Meta:
        verbose_name = "Document Error"
        verbose_name_plural = "Document Errors"
        ordering = ['-created_at']

    def __str__(self):
        """
        Model obyektining string ko'rinishi.
        
        Returns:
            str: Xatolik turi, hujjat ID va urinish raqami
        """
        return f"{self.get_error_type_display()} - {self.document.id} (urinish: {self.celery_attempt})"


class SearchQuery(models.Model):
    """
    Foydalanuvchilar tomonidan amalga oshirilgan qidiruv so'rovlarini saqlash uchun model.
    
    Bu model:
    - Qidiruv so'rovlarini kuzatadi
    - Natijalar topilganligini belgilaydi
    - Chuqur qidiruv holatini saqlaydi
    - Foydalanuvchi faoliyatini tahlil qiladi
    
    Maydonlar:
    - user: Qidiruv qilgan foydalanuvchi
    - query_text: Qidiruv matni
    - found_results: Natijalar topildimi
    - is_deep_search: Chuqur qidiruvmi
    """
    user = models.ForeignKey(
        'bot.User', 
        on_delete=models.CASCADE, 
        related_name='search_queries', 
        db_index=True,
        help_text="Qidiruv qilgan foydalanuvchi"
    )
    query_text = models.CharField(
        max_length=500, 
        db_index=True,
        help_text="Qidiruv so'rovi matni"
    )
    found_results = models.BooleanField(
        default=False, 
        db_index=True,
        help_text="Qidiruv natijalari topildimi"
    )
    is_deep_search = models.BooleanField(
        default=False, 
        db_index=True,
        help_text="Chuqur qidiruv rejimi ishlatildimi"
    )
    created_at = models.DateTimeField(
        auto_now_add=True, 
        db_index=True,
        help_text="Qidiruv amalga oshirilgan vaqt"
    )

    def __str__(self):
        """
        Model obyektining string ko'rinishi.
        
        Returns:
            str: Qidiruv matni va foydalanuvchi
        """
        return f"'{self.query_text}' by {self.user}"


def document_image_upload_to(instance, filename):
    """
    Hujjat rasmlari uchun yuklash yo'lini yaratadi.
    
    Args:
        instance: DocumentImage obyekti
        filename (str): Rasm fayl nomi
    
    Returns:
        str: Rasm saqlanish yo'li (file/{document_id}/{filename})
    
    Misol:
        document_image_upload_to(image, "page1.jpg") -> "file/uuid-123/page1.jpg"
    """
    return f"file/{instance.document.id}/{filename}"


class DocumentImage(models.Model):
    """
    Hujjat sahifalarining rasmlarini saqlash uchun model.
    
    Bu model:
    - Hujjat sahifalarining rasmlarini saqlaydi
    - Sahifa raqamini kuzatadi
    - Hujjat bilan bog'laydi
    - Rasm fayllarini boshqaradi
    
    Maydonlar:
    - document: Bog'langan hujjat
    - page_number: Sahifa raqami
    - image: Rasm fayli
    - created_at: Yaratilgan vaqt
    """
    document = models.ForeignKey(
        Document, 
        on_delete=models.CASCADE, 
        related_name='images',
        help_text="Rasm tegishli bo'lgan hujjat"
    )
    page_number = models.PositiveIntegerField(
        help_text="Sahifa raqami"
    )
    image = models.ImageField(
        upload_to='images/',
        help_text="Hujjat sahifasining rasm fayli"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Rasm yaratilgan vaqt"
    )

    class Meta:
        unique_together = ('document', 'page_number')
        ordering = ['page_number']

    def __str__(self):
        """
        Model obyektining string ko'rinishi.
        
        Returns:
            str: Sahifa raqami va hujjat ID'si
        """
        return f"Image p{self.page_number} for {self.document_id}"
