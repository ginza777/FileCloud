"""
Models for the Kuku AI Bot application
"""
import asyncio

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from telegram.error import TelegramError


class GetOrNoneManager(models.Manager):
    """Custom manager that returns None instead of raising DoesNotExist"""

    def get_or_none(self, **kwargs):
        try:
            return self.get(**kwargs)
        except self.model.DoesNotExist:
            return None


class Language(models.TextChoices):
    UZ = 'uz', _('Uzbek')
    RU = 'ru', _('Russian')
    EN = 'en', _('English')


class SubscribeChannel(models.Model):
    """
    Represents a Telegram channel that users must subscribe to.
    """
    channel_username = models.CharField(max_length=100, unique=True, null=True, blank=True)
    channel_link = models.URLField(max_length=255, blank=True, null=True)
    channel_id = models.CharField(max_length=100, unique=True)
    active = models.BooleanField(default=True)
    private = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Subscription Channel")
        verbose_name_plural = _("Subscription Channels")
        ordering = ["-created_at"]

    def __str__(self):
        return self.channel_username or self.channel_id

    def clean(self):
        """
        Custom validation for the model.
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
        """Override save to ensure clean validation runs"""
        self.clean()
        super().save(*args, **kwargs)

    def some_method_that_uses_check_bot_is_admin(self, bot_token):
        from .utils import check_bot_is_admin_in_channel  # Local import to avoid circular import
        return check_bot_is_admin_in_channel(self.channel_id, bot_token)


class User(models.Model):
    """
    Represents a Telegram user who interacts with the bot.
    """
    telegram_id = models.BigIntegerField(unique=True, help_text=_("Telegram user ID"))
    first_name = models.CharField(max_length=100, blank=True, null=True)
    last_name = models.CharField(max_length=100, blank=True, null=True)
    username = models.CharField(max_length=100, blank=True, null=True)
    last_active = models.DateTimeField(auto_now=True)
    is_admin = models.BooleanField(default=False)
    is_blocked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    stock_language = models.CharField(max_length=10, choices=Language.choices, default=Language.UZ)
    selected_language = models.CharField(max_length=10, choices=Language.choices, null=True, blank=True)
    deeplink = models.TextField(blank=True, null=True)
    left = models.BooleanField(default=False)
    search_mode = models.CharField(
        max_length=10,
        choices=[("normal", "Normal"), ("deep", "Deep")],
        default="normal"
    )

    class Meta:
        verbose_name = _("User")
        verbose_name_plural = _("Users")

    def __str__(self):
        return f"{self.full_name} ({self.telegram_id})"

    @property
    def full_name(self) -> str:
        """Returns the user's full name."""
        return f"{self.first_name or ''} {self.last_name or ''}".strip()


class Location(models.Model):
    """
    Stores location data sent by a user.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="locations")
    latitude = models.FloatField()
    longitude = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)

    objects = GetOrNoneManager()

    class Meta:
        verbose_name = _("Location")
        verbose_name_plural = _("Locations")
        ordering = ["-created_at"]

    def __str__(self):
        return f"Location for {self.user} at {self.created_at.strftime('(%H:%M, %d %B %Y)')}"


class Broadcast(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', _('Draft')
        PENDING = 'pending', _('Pending')
        IN_PROGRESS = 'in_progress', _('In Progress')
        COMPLETED = 'completed', _('Completed')

    from_chat_id = models.BigIntegerField()
    message_id = models.BigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    scheduled_time = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)

    def __str__(self):
        return f"Forward {self.message_id} from {self.from_chat_id}"


class BroadcastRecipient(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', _('Pending')
        SENT = 'sent', _('Sent')
        FAILED = 'failed', _('Failed')

    broadcast = models.ForeignKey(Broadcast, on_delete=models.CASCADE, related_name="recipients")
    user = models.ForeignKey('User', on_delete=models.CASCADE, related_name="broadcast_messages")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    error_message = models.TextField(blank=True, null=True)
    sent_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        unique_together = ('broadcast', 'user')
