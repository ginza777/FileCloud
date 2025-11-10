"""
Bot App Models
==============

Bu modul Telegram bot bilan bog'liq barcha Django modellarini o'z ichiga oladi.
Har bir model foydalanuvchilar, kanallar, xabarlar va joylashuv ma'lumotlarini saqlaydi.

Modellar:
- TelegramUser: Telegram foydalanuvchilari
- SubscribeChannel: Obuna kanallari
- Location: Foydalanuvchi joylashuvlari
- Broadcast: Mass xabarlar
- BroadcastRecipient: Xabar oluvchilar
"""

import asyncio

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from telegram.error import TelegramError


class GetOrNoneManager(models.Manager):
    """
    Maxsus manager klassi - DoesNotExist xatoligi o'rniga None qaytaradi.
    
    Bu manager:
    - get_or_none() metodini taqdim etadi
    - Agar obyekt topilmasa, None qaytaradi
    - Xatoliklar o'rniga None qaytarish uchun ishlatiladi
    
    Ishlatish:
        user = TelegramUser.objects.get_or_none(telegram_id=123456)
        if user:
            print(f"Foydalanuvchi topildi: {user.full_name}")
        else:
            print("Foydalanuvchi topilmadi")
    """

    def get_or_none(self, **kwargs):
        """
        Obyektni topadi yoki None qaytaradi.
        
        Args:
            **kwargs: Qidirish parametrlari
        
        Returns:
            Model instance yoki None: Agar topilsa obyekt, aks holda None
        
        Raises:
            DoesNotExist: Hech qachon chiqmaydi, None qaytaradi
        """
        try:
            return self.get(**kwargs)
        except self.model.DoesNotExist:
            return None


class Language(models.TextChoices):
    """
    Til tanlovlari uchun konstantalar.
    
    Bu klass:
    - Qo'llab-quvvatlanadigan tillarni belgilaydi
    - Django TextChoices'dan foydalanadi
    - Admin panelda til tanlovi uchun ishlatiladi
    
    Tillar:
    - UZ: O'zbek tili
    - RU: Rus tili  
    - EN: Ingliz tili
    """
    UZ = 'uz', _('Uzbek')
    RU = 'ru', _('Russian')
    EN = 'en', _('English')


class SubscribeChannel(models.Model):
    """
    Foydalanuvchilar obuna bo'lishi kerak bo'lgan Telegram kanalini ifodalaydi.
    
    Bu model:
    - Telegram kanal ma'lumotlarini saqlaydi
    - Bot adminligini tekshiradi
    - Kanal holatini boshqaradi
    - Obuna majburiyatini ta'minlaydi
    
    Maydonlar:
    - channel_username: Kanal username'i
    - channel_link: Kanal havolasi
    - channel_id: Kanal ID'si
    - active: Kanal faol yoki yo'q
    - private: Shaxsiy kanal yoki yo'q
    """
    channel_username = models.CharField(
        max_length=100, 
        unique=True, 
        null=True, 
        blank=True,
        help_text="Telegram kanal username'i (@channel_name)"
    )
    channel_link = models.URLField(
        max_length=255, 
        blank=True, 
        null=True,
        help_text="Kanal havolasi (shaxsiy kanallar uchun)"
    )
    channel_id = models.CharField(
        max_length=100, 
        unique=True,
        help_text="Telegram kanal ID'si"
    )
    active = models.BooleanField(
        default=True,
        help_text="Kanal faol yoki yo'q"
    )
    private = models.BooleanField(
        default=False,
        help_text="Shaxsiy kanal yoki yo'q"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Yaratilgan vaqt"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Yangilangan vaqt"
    )

    class Meta:
        verbose_name = _("Subscription Channel")
        verbose_name_plural = _("Subscription Channels")
        ordering = ["-created_at"]

    def __str__(self):
        """
        Model obyektining string ko'rinishi.
        
        Returns:
            str: Kanal username'i yoki ID'si
        """
        return self.channel_username or self.channel_id

    def clean(self):
        """
        Model ma'lumotlarini tekshirish va validatsiya qilish.
        
        Bu metod:
        - Shaxsiy kanallar uchun havola mavjudligini tekshiradi
        - Ochiq kanallar uchun username mavjudligini tekshiradi
        - Bot adminligini tekshiradi
        
        Raises:
            ValidationError: Ma'lumotlar noto'g'ri bo'lsa
        """
        if self.private and not self.channel_link:
            raise ValidationError(_("A private channel must have an invitation link."))
        if not self.private and not self.channel_username:
            raise ValidationError(_("A public channel must have a username."))

        # Check if bot is admin in channel using token from .env
        from django.conf import settings
        bot_token = getattr(settings, 'BOT_TOKEN', None)
        if bot_token and self.channel_id:
            try:
                # Synchronous check using asyncio.run
                is_admin = asyncio.run(
                    self.some_method_that_uses_check_bot_is_admin(bot_token)
                )
                print(f"Admin status for {self.channel_id}: {is_admin}")

                if not is_admin:
                    raise ValidationError(
                        _("The bot is not an administrator in the specified channel. Please add the bot as an admin and try again.")
                    )
            except TelegramError as e:
                raise ValidationError(
                    _("Failed to verify bot admin status: {error}").format(error=str(e))
                )

    def save(self, *args, **kwargs):
        """
        Model saqlash metodini override qiladi.
        
        Bu metod:
        - clean() metodini chaqiradi
        - Validatsiyadan o'tkazadi
        - Super metodini chaqiradi
        
        Args:
            *args: Positional argumentlar
            **kwargs: Keyword argumentlar
        """
        self.clean()
        super().save(*args, **kwargs)

    def some_method_that_uses_check_bot_is_admin(self, bot_token):
        """
        Bot adminligini tekshirish uchun yordamchi metod.
        
        Args:
            bot_token (str): Bot token'i
        
        Returns:
            bool: Bot admin bo'lsa True, aks holda False
        """
        from .utils import check_bot_is_admin_in_channel  # Local import to avoid circular import
        return check_bot_is_admin_in_channel(self.channel_id, bot_token)


class TelegramUser(models.Model):
    """
    Bot bilan o'zaro ishlaydigan Telegram foydalanuvchisini ifodalaydi.
    
    Bu model:
    - Telegram foydalanuvchi ma'lumotlarini saqlaydi
    - Foydalanuvchi holatini kuzatadi
    - Til tanlovini boshqaradi
    - Admin huquqlarini tekshiradi
    
    Maydonlar:
    - telegram_id: Telegram foydalanuvchi ID'si
    - first_name: Ism
    - last_name: Familiya
    - username: Username
    - last_active: Oxirgi faollik vaqti
    - is_admin: Admin yoki yo'q
    - is_blocked: Bloklangan yoki yo'q
    - stock_language: Asosiy til
    - selected_language: Tanlangan til
    - search_mode: Qidiruv rejimi
    """
    telegram_id = models.BigIntegerField(
        unique=True, 
        db_index=True, 
        help_text=_("Telegram user ID")
    )
    first_name = models.CharField(
        max_length=100, 
        blank=True, 
        null=True,
        help_text="Foydalanuvchi ismi"
    )
    last_name = models.CharField(
        max_length=100, 
        blank=True, 
        null=True,
        help_text="Foydalanuvchi familiyasi"
    )
    username = models.CharField(
        max_length=100, 
        blank=True, 
        null=True,
        help_text="Telegram username'i"
    )
    last_active = models.DateTimeField(
        auto_now=True, 
        db_index=True,
        help_text="Oxirgi faollik vaqti"
    )
    is_admin = models.BooleanField(
        default=False,
        help_text="Admin huquqlari"
    )
    is_blocked = models.BooleanField(
        default=False,
        help_text="Bloklangan holat"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Ro'yxatdan o'tgan vaqt"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Oxirgi yangilanish vaqti"
    )
    stock_language = models.CharField(
        max_length=10, 
        choices=Language.choices, 
        default=Language.UZ,
        help_text="Asosiy til"
    )
    selected_language = models.CharField(
        max_length=10, 
        choices=Language.choices, 
        null=True, 
        blank=True,
        help_text="Tanlangan til"
    )
    deeplink = models.TextField(
        blank=True, 
        null=True,
        help_text="Chuqur havola ma'lumoti"
    )
    left = models.BooleanField(
        default=False,
        help_text="Botni tark etgan yoki yo'q"
    )
    search_mode = models.CharField(
        max_length=10,
        choices=[("normal", "Normal"), ("deep", "Deep")],
        default="normal",
        db_index=True,
        help_text="Qidiruv rejimi"
    )

    class Meta:
        verbose_name = _("Telegram User")
        verbose_name_plural = _("Telegram Users")

    def __str__(self):
        """
        Model obyektining string ko'rinishi.
        
        Returns:
            str: To'liq ism va Telegram ID
        """
        return f"{self.full_name} ({self.telegram_id})"

    @property
    def full_name(self) -> str:
        """
        Foydalanuvchining to'liq ismini qaytaradi.
        
        Returns:
            str: Ism va familiya birlashtirilgan
        """
        return f"{self.first_name or ''} {self.last_name or ''}".strip()

    def get_absolute_url(self):
        """
        Foydalanuvchi sahifasiga havola qaytaradi.
        
        Returns:
            str: Admin panelidagi foydalanuvchi sahifasi URL'i
        """
        from django.urls import reverse
        return reverse('admin:bot_telegramuser_change', args=[str(self.id)])


class Location(models.Model):
    """
    Foydalanuvchi tomonidan yuborilgan joylashuv ma'lumotlarini saqlaydi.
    
    Bu model:
    - GPS koordinatalarini saqlaydi
    - Foydalanuvchi bilan bog'laydi
    - Joylashuv tarixini kuzatadi
    
    Maydonlar:
    - user: Foydalanuvchi
    - latitude: Kenglik
    - longitude: Uzunlik
    - created_at: Yaratilgan vaqt
    """
    user = models.ForeignKey(
        TelegramUser, 
        on_delete=models.CASCADE, 
        related_name="locations",
        help_text="Joylashuv yuborgan foydalanuvchi"
    )
    latitude = models.FloatField(
        help_text="GPS kenglik koordinatasi"
    )
    longitude = models.FloatField(
        help_text="GPS uzunlik koordinatasi"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Joylashuv yuborilgan vaqt"
    )

    objects = GetOrNoneManager()

    class Meta:
        verbose_name = _("Location")
        verbose_name_plural = _("Locations")
        ordering = ["-created_at"]

    def __str__(self):
        """
        Model obyektining string ko'rinishi.
        
        Returns:
            str: Foydalanuvchi va vaqt ma'lumoti
        """
        return f"Location for {self.user} at {self.created_at.strftime('(%H:%M, %d %B %Y)')}"


class Broadcast(models.Model):
    """
    Mass xabar yuborish uchun model.
    
    Bu model:
    - Forward qilingan xabarni saqlaydi
    - Yuborish holatini kuzatadi
    - Vaqtni boshqaradi
    
    Maydonlar:
    - from_chat_id: Xabar kelgan chat ID
    - message_id: Xabar ID'si
    - status: Yuborish holati
    - scheduled_time: Rejalashtirilgan vaqt
    """
    
    class Status(models.TextChoices):
        """
        Xabar yuborish holatlari.
        
        Holatlar:
        - DRAFT: Loyiha holatida
        - PENDING: Navbatda
        - IN_PROGRESS: Yuborilmoqda
        - COMPLETED: Yakunlangan
        """
        DRAFT = 'draft', _('Draft')
        PENDING = 'pending', _('Pending')
        IN_PROGRESS = 'in_progress', _('In Progress')
        COMPLETED = 'completed', _('Completed')

    from_chat_id = models.BigIntegerField(
        help_text="Xabar kelgan chat ID'si"
    )
    message_id = models.BigIntegerField(
        help_text="Forward qilingan xabar ID'si"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Yaratilgan vaqt"
    )
    scheduled_time = models.DateTimeField(
        default=timezone.now,
        help_text="Yuborish vaqti"
    )
    status = models.CharField(
        max_length=20, 
        choices=Status.choices, 
        default=Status.DRAFT,
        help_text="Yuborish holati"
    )

    def __str__(self):
        """
        Model obyektining string ko'rinishi.
        
        Returns:
            str: Xabar ma'lumotlari
        """
        return f"Forward {self.message_id} from {self.from_chat_id}"


class BroadcastRecipient(models.Model):
    """
    Mass xabar oluvchilarini ifodalaydi.
    
    Bu model:
    - Har bir foydalanuvchi uchun yuborish holatini saqlaydi
    - Xatoliklarni kuzatadi
    - Yuborish vaqtini belgilaydi
    
    Maydonlar:
    - broadcast: Mass xabar
    - user: Xabar oluvchi foydalanuvchi
    - status: Yuborish holati
    - error_message: Xatolik xabari
    - sent_at: Yuborilgan vaqt
    """
    
    class Status(models.TextChoices):
        """
        Xabar yuborish holatlari.
        
        Holatlar:
        - PENDING: Navbatda
        - SENT: Yuborilgan
        - FAILED: Xatolik bilan tugagan
        """
        PENDING = 'pending', _('Pending')
        SENT = 'sent', _('Sent')
        FAILED = 'failed', _('Failed')

    broadcast = models.ForeignKey(
        Broadcast, 
        on_delete=models.CASCADE, 
        related_name="recipients",
        help_text="Mass xabar"
    )
    user = models.ForeignKey(
        'TelegramUser', 
        on_delete=models.CASCADE, 
        related_name="broadcast_messages",
        help_text="Xabar oluvchi foydalanuvchi"
    )
    status = models.CharField(
        max_length=10, 
        choices=Status.choices, 
        default=Status.PENDING, 
        db_index=True,
        help_text="Yuborish holati"
    )
    error_message = models.TextField(
        blank=True, 
        null=True,
        help_text="Xatolik xabari (agar bo'lsa)"
    )
    sent_at = models.DateTimeField(
        blank=True, 
        null=True,
        help_text="Xabar yuborilgan vaqt"
    )

    class Meta:
        unique_together = ('broadcast', 'user')
