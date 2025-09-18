import logging
import time

from asgiref.sync import async_to_sync
from celery import shared_task
from django.utils import timezone
from django.conf import settings
from telegram import Bot as TelegramBot
from telegram.error import TelegramError

from .models import Broadcast, BroadcastRecipient, User

logger = logging.getLogger(__name__)


@shared_task
def start_broadcast_task(broadcast_id):
    """Reklamani yuborish jarayonini boshqaradi."""
    try:
        broadcast = Broadcast.objects.get(id=broadcast_id)
        if broadcast.status not in [Broadcast.Status.PENDING, Broadcast.Status.IN_PROGRESS]:
            logger.warning(f"Broadcast {broadcast_id} is not in a sendable state.")
            return
    except Broadcast.DoesNotExist:
        logger.warning(f"Broadcast {broadcast_id} topilmadi.")
        return

    broadcast.status = Broadcast.Status.IN_PROGRESS
    broadcast.save()

    users = User.objects.filter(is_blocked=False)
    for user in users:
        recipient, _ = BroadcastRecipient.objects.get_or_create(
            broadcast=broadcast, user=user
        )
        if recipient.status in [BroadcastRecipient.Status.PENDING, BroadcastRecipient.Status.FAILED]:
            send_message_to_user_task.delay(recipient.id)
            time.sleep(0.04)

    broadcast.status = Broadcast.Status.COMPLETED
    broadcast.save()
    logger.info(f"Broadcast {broadcast.id} uchun barcha vazifalar navbatga qo'yildi.")


@shared_task
def send_message_to_user_task(recipient_id):
    """
    Bitta foydalanuvchiga reklama xabarini asgiref yordamida ASINXRON yuboradi.
    """
    try:
        recipient = BroadcastRecipient.objects.select_related('broadcast', 'user').get(id=recipient_id)
    except BroadcastRecipient.DoesNotExist:
        logger.warning(f"Recipient {recipient_id} topilmadi.")
        return

    async def main_async_logic():
        broadcast = recipient.broadcast
        user = recipient.user
        bot_token = getattr(settings, 'BOT_TOKEN', None)
        if not bot_token:
            logger.error("BOT_TOKEN sozlanmagan, yuborib bo'lmaydi.")
            return
        bot = TelegramBot(token=bot_token)
        try:
            await bot.forward_message(
                chat_id=user.telegram_id,
                from_chat_id=broadcast.from_chat_id,
                message_id=broadcast.message_id
            )
            recipient.status = BroadcastRecipient.Status.SENT
            recipient.sent_at = timezone.now()
            user.left = False
            await user.asave()
        except TelegramError as e:
            logger.error(f"Foydalanuvchi {user.telegram_id} ga yuborishda xato: {e}")
            recipient.status = BroadcastRecipient.Status.FAILED
            recipient.error_message = str(e)
            if "bot was blocked by the user" in str(e).lower():
                user.left = True
                await user.asave()
        await recipient.asave()

    async_to_sync(main_async_logic)()
