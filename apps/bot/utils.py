# utils.py

import csv
import io
import logging
import os
import subprocess
from datetime import datetime, timedelta
from functools import wraps
from typing import Callable

from asgiref.sync import sync_to_async
from django.conf import settings
from django.utils.timezone import now
from telegram import Update, Bot
from telegram.ext import ContextTypes
from telegram.error import TelegramError
import requests

from . import translation
from .models import User, SubscribeChannel, InvitedUser
from django.utils import timezone

logger = logging.getLogger(__name__)


# --- Icon Constants ---
ICON_MAP = {
    'pdf': 'https://cdn-icons-png.flaticon.com/512/337/337946.png',
    'doc': 'https://cdn-icons-png.flaticon.com/512/337/337932.png',
    'zip': 'https://cdn-icons-png.flaticon.com/512/1721/1721092.png',
    'media': 'https://cdn-icons-png.flaticon.com/512/1042/1042339.png',
    'other': 'https://cdn-icons-png.flaticon.com/512/2311/2311820.png'  # Default icon
}
DEFAULT_ICON = ICON_MAP['other']


# --- Bot Utility Functions ---

async def check_bot_is_admin_in_channel(channel_id: str, bot_token: str) -> bool:
    """
    Check if bot is admin in the specified channel
    """
    try:
        bot = Bot(token=bot_token)
        chat_member = await bot.get_chat_member(chat_id=channel_id, user_id=bot.id)
        return chat_member.status in ['administrator', 'creator']
    except TelegramError as e:
        print(f"Error checking bot admin status: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error checking bot admin status: {e}")
        return False


async def get_bot_details_from_telegram(token: str) -> tuple:
    """
    Get bot details from Telegram API
    """
    try:
        bot = Bot(token=token)
        bot_info = await bot.get_me()
        return bot_info.first_name, bot_info.username
    except Exception as e:
        print(f"Error getting bot details: {e}")
        return "", ""


async def register_bot_webhook(token: str, webhook_url: str) -> str:
    """
    Register webhook URL with Telegram
    """
    try:
        bot = Bot(token=token)
        await bot.set_webhook(url=webhook_url)
        return webhook_url
    except Exception as e:
        print(f"Error setting webhook: {e}")
        return ""


# --- Decorator Functions ---

def update_or_create_user(func: Callable):
    """
    Foydalanuvchini topadi yoki yaratadi. Faqat asosiy kirish nuqtalarida
    (masalan, /start) ishlatilishi kerak.
    """

    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_data = update.effective_user
        if not user_data:
            return

        # Lazy import to avoid circular dependency
        from .models import User
        
        user, _ = await User.objects.aupdate_or_create(
            telegram_id=user_data.id,
            defaults={
                "first_name": user_data.first_name or "",
                "last_name": user_data.last_name or "",
                "username": user_data.username,
                "stock_language": user_data.language_code,
            }
        )
        user_language = user.selected_language or user.stock_language
        return await func(update, context, user=user, language=user_language, *args, **kwargs)

    return wrapper


def get_user(func: Callable):
    """
    Mavjud foydalanuvchini bazadan oladi. Agar topilmasa, /start ga yo'naltiradi.
    Bu tezkor dekorator bo'lib, bazaga yozish amalini bajarmaydi.
    """

    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_data = update.effective_user
        if not user_data:
            return

        # Lazy import to avoid circular dependency
        from .models import User
        
        user = await User.objects.filter(telegram_id=user_data.id).afirst()
        if not user:
            await update.message.reply_text(translation.start_first)
            return

        user_language = user.selected_language or user.stock_language
        return await func(update, context, user=user, language=user_language, *args, **kwargs)

    return wrapper


def admin_only(func: Callable):
    """
    Decorator to check if user is admin before allowing access to admin functions
    """
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_data = update.effective_user
        if not user_data:
            return

        # Lazy import to avoid circular dependency
        from .models import User
        
        user = await User.objects.filter(telegram_id=user_data.id).afirst()
        if not user or not user.is_admin:
            await update.message.reply_text("❌ Bu buyruq faqat adminlar uchun!")
            return

        return await func(update, context, *args, **kwargs)

    return wrapper


def channel_subscribe(func: Callable):
    """
    Kanalga obunani tekshiradi. Faqat qidiruv vaqtida ishlatiladi.
    O'zidan oldin @get_user yoki @update_or_create_user ishlatilishiga tayanadi.
    """

    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = kwargs.get('user')
        user_language = kwargs.get('language')
        if not user or not user_language:
            return await func(update, context, *args, **kwargs)

        # Lazy import to avoid circular dependency
        from .models import SubscribeChannel
        from .keyboard import keyboard_checked_subscription_channel
        
        has_active_channels = await SubscribeChannel.objects.filter(active=True).aexists()
        if has_active_channels:
            reply_markup, subscribed_status = await keyboard_checked_subscription_channel(user.telegram_id, context.bot)
            if not subscribed_status:
                await update.message.reply_text(
                    translation.subscribe_channel_text.get(user_language),
                    reply_markup=reply_markup
                )
                return
        return await func(update, context, *args, **kwargs)

    return wrapper


# --- Service Functions ---

async def get_user_statistics(bot_username: str) -> dict:
    """
    Foydalanuvchilarning umumiy va oxirgi 24 soatdagi faol soni
    haqida statistika qaytaradi.
    """
    user_count = await User.objects.filter(bot__username=bot_username).acount()
    active_24_count = await User.objects.filter(
        bot__username=bot_username,
        last_active__gte=now() - timedelta(hours=24)
    ).acount()
    return {"total": user_count, "active_24h": active_24_count}


async def perform_database_backup():
    """
    Sozlamalarga qarab ma'lumotlar bazasining zaxira nusxasini yaratadi.
    PostgreSQL va SQLite3'ni qo'llab-quvvatlaydi.

    Returns:
        (fayl_nomi, xatolik_matni) tuple. Muvaffaqiyatli bo'lsa xatolik None bo'ladi.
    """
    db_engine = settings.DATABASES['default']['ENGINE']
    db_config = settings.DATABASES['default']
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    dump_file = None
    command = None

    try:
        if 'postgresql' in db_engine:
            dump_file = f"backup_{timestamp}.sql"
            # Xavfsizlik uchun parol subprocess'ga environment orqali uzatiladi
            env = os.environ.copy()
            env['PGPASSWORD'] = db_config['PASSWORD']
            command = [
                'pg_dump',
                '-U', db_config['USER'],
                '-h', db_config['HOST'],
                '-p', str(db_config['PORT']),
                db_config['NAME']
            ]
            # `shell=True` ishlatmaslik xavfsizroq
            with open(dump_file, 'w') as f:
                process = await sync_to_async(subprocess.run)(
                    command, check=True, text=True, stdout=f, stderr=subprocess.PIPE, env=env
                )

        elif 'sqlite3' in db_engine:
            dump_file = f"backup_{timestamp}.sqlite3"
            command = f"sqlite3 {db_config['NAME']} .dump > {dump_file}"
            process = await sync_to_async(subprocess.run)(
                command, shell=True, check=True, capture_output=True, text=True
            )
        else:
            return None, "Qo'llab-quvvatlanmaydigan ma'lumotlar bazasi drayveri."

        return dump_file, None

    except subprocess.CalledProcessError as e:
        error_message = f"Zaxira nusxalashda xatolik yuz berdi. Return code: {e.returncode}\nXato: {e.stderr}"
        logger.error(error_message)
        return None, error_message
    except Exception as e:
        error_message = f"Zaxira nusxalashda kutilmagan xatolik: {e}"
        logger.error(error_message)
        return None, error_message


def generate_csv_from_users(users_data) -> io.BytesIO:
    """
    Foydalanuvchilar ma'lumotidan (QuerySet.values()) CSV fayl yaratib,
    uni BytesIO obyekti sifatida qaytaradi.
    """
    if not users_data:
        return io.BytesIO(b"Ma'lumotlar mavjud emas")

    # In-memory matn fayli yaratamiz
    string_io = io.StringIO()
    # Ustun nomlarini birinchi yozuvdan avtomatik olamiz
    writer = csv.DictWriter(string_io, fieldnames=users_data[0].keys())
    writer.writeheader()
    writer.writerows(users_data)

    # Matn faylini boshiga qaytarib, baytlarga o'giramiz
    string_io.seek(0)
    return io.BytesIO(string_io.getvalue().encode('utf-8'))


def send_telegram_notification(message: str, error_type: str = "ERROR") -> bool:
    """
    Telegram kanalga xabar yuboradi (parsing xatolari uchun)
    
    Args:
        message: Yuboriladigan xabar matni
        error_type: Xatolik turi (ERROR, WARNING, INFO)
    
    Returns:
        bool: Muvaffaqiyatli yuborilgan bo'lsa True
    """
    try:
        bot_token = getattr(settings, 'BOT_TOKEN', None)
        channel_id = getattr(settings, 'FORCE_CHANNEL_USERNAME', None)
        
        if not bot_token or not channel_id:
            logger.error("BOT_TOKEN yoki FORCE_CHANNEL_USERNAME sozlanmagan")
            return False
        
        # Xabar formatini yaratamiz
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        if error_type == "ERROR":
            emoji = "🚨"
            title = "XATOLIK"
        elif error_type == "WARNING":
            emoji = "⚠️"
            title = "OGOHLANTIRISH"
        else:
            emoji = "ℹ️"
            title = "MA'LUMOT"
        
        formatted_message = f"""
{emoji} **{title}** - Parser Bot
🕐 Vaqt: {timestamp}

{message}

---
🤖 Kuku Bot System
        """
        
        # Telegram API orqali xabar yuboramiz
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        
        data = {
            'chat_id': channel_id,
            'text': formatted_message,
            'parse_mode': 'Markdown',
            'disable_web_page_preview': True
        }
        
        response = requests.post(url, data=data, timeout=10)
        
        if response.status_code == 200:
            logger.info(f"Telegram xabar muvaffaqiyatli yuborildi: {error_type}")
            return True
        else:
            logger.error(f"Telegram xabar yuborishda xatolik: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"Telegram xabar yuborishda kutilmagan xatolik: {str(e)}")
        return False


def send_token_expired_notification() -> bool:
    """
    Token eskirgani haqida Telegram kanalga xabar yuboradi
    """
    message = """
🔑 **Token eskirgan!**

Soff.uz API tokeni eskirgan. Yangi token olish kerak.

**Kerakli amallar:**
1. Soff.uz saytiga kirish
2. Yangi token olish
3. Admin panelda token yangilash

Parser ishlay olmaydi!
    """
    return send_telegram_notification(message, "ERROR")


def send_parsing_error_notification(error_message: str, page: int = None) -> bool:
    """
    Parsing xatosi haqida Telegram kanalga xabar yuboradi
    """
    page_info = f" (Sahifa: {page})" if page else ""
    
    message = f"""
📄 **Parsing xatosi{page_info}**

Xatolik: {error_message}

Parser to'xtatildi yoki qayta ishlash kerak.
    """
    return send_telegram_notification(message, "ERROR")


def send_parsing_success_notification(pages_processed: int, products_count: int) -> bool:
    """
    Parsing muvaffaqiyatli yakunlanganini Telegram kanalga xabar yuboradi
    """
    message = f"""
✅ **Parsing muvaffaqiyatli yakunlandi**

📊 **Natijalar:**
• Sahifalar: {pages_processed}
• Mahsulotlar: {products_count}

Parser ishlashi yakunlandi.
    """
    return send_telegram_notification(message, "INFO")


# --- Invite User Functions ---

async def track_group_joins(update, context):
    """
    Track when users join groups/channels and create invite relationships
    """
    chat = update.effective_chat
    new_members = update.message.new_chat_members

    # Kanalni yoki guruhni bazadan topish / yaratish
    channel, _ = await SubscribeChannel.objects.aget_or_create(
        channel_id=str(chat.id),
        defaults={
            "channel_username": chat.username,
            "channel_link": f"https://t.me/{chat.username}" if chat.username else None,
            "bot": context.bot_data["bot_instance"],  # Bot model instance
        }
    )

    for member in new_members:
        # Foydalanuvchini bazaga qo'shish
        invited_user, _ = await User.objects.aupdate_or_create(
            telegram_id=member.id,
            bot=context.bot_data["bot_instance"],
            defaults={
                "first_name": member.first_name,
                "last_name": getattr(member, "last_name", ""),
                "username": getattr(member, "username", ""),
            }
        )

        # Kim taklif qilganini aniqlash
        inviter = update.message.from_user
        invited_by, _ = await User.objects.aupdate_or_create(
            telegram_id=inviter.id,
            bot=context.bot_data["bot_instance"],
            defaults={
                "first_name": inviter.first_name,
                "last_name": getattr(inviter, "last_name", ""),
                "username": getattr(inviter, "username", ""),
            }
        )

        # Endi InvitedUser yozuvini yaratish
        await InvitedUser.objects.aupdate_or_create(
            channel=channel,
            invited_by=invited_by,
            invited_user=invited_user,
            defaults={
                "invited_at": timezone.now()
            }
        )