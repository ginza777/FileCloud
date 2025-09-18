from telegram import ReplyKeyboardMarkup, KeyboardButton
from telegram import InlineKeyboardMarkup
from telegram import ReplyKeyboardMarkup, KeyboardButton


def language_list_keyboard():
    button_list = [
        {"name": "🇺🇿 Uzbek", "id": "uz"},
        {"name": "🇬🇧 English", "id": "en"},
        {"name": "🇷🇺 Russian", "id": "ru"},
        {"name": "🇹🇷 Turkish", "id": "tr"},

    ]
    keyboard = []
    for button in button_list:
        keyboard.append([InlineKeyboardButton(button['name'], callback_data=f"language_setting_{button['id']}")])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data=f"setting_back")])

    return InlineKeyboardMarkup(keyboard)


def restart_keyboard(lang) -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(translation.text[lang])]
    ]

    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)


def make_movie_share_keyboard_with_code(bot_username, code, lang) -> InlineKeyboardMarkup:
    share_bot = {
        "uz": f"Ushbu kinoni ulashing  📤 ",
        "ru": f"Поделиться этим фильмом  📤",
        "en": f"Share this Movie 📤",
        "tr": f"Bu Filmi Paylaş 📤",
    }
    buttons = [[
        InlineKeyboardButton(share_bot[lang], switch_inline_query=f"https://t.me/{bot_username}?start={code}")
    ]]
    return InlineKeyboardMarkup(buttons)


def share_post_inline_button(post_id, lang) -> InlineKeyboardMarkup:
    share_text = {
        "uz": f"Ushbu postni ulashing 📤",
        "ru": f"Поделиться этим постом 📤",
        "en": f"Share this post 📤",
        "tr": f"Bu Gönderi Paylaş ��",
    }
    buttons = [[
        InlineKeyboardButton(share_text[lang], switch_inline_query=f"share_post_{post_id}")
    ]]
    return InlineKeyboardMarkup(buttons)


def start_with_code_keyboard(bot_username, code, lang) -> InlineKeyboardMarkup:
    share_bot = {
        "uz": f"Ushbu kinoni ulashing  📤 ",
        "ru": f"Поделиться этим фильмом  📤",
        "en": f"Share this Movie 📤",
        "tr": f"Bu Filmi Paylaş 📤",
    }
    buttons = [[
        InlineKeyboardButton(share_bot[lang], switch_inline_query=f"https://t.me/{bot_username}?start={code}")
    ]]
    return InlineKeyboardMarkup(buttons)


def make_movie_share_keyboard(lang) -> InlineKeyboardMarkup:
    share_bot = {
        "uz": f"Ushbu kinoni ulashing  📤 ",
        "ru": f"Поделиться этим фильмом  📤",
        "en": f"Share this Movie 📤",
        "tr": f"Bu Filmi Paylaş ��",
    }
    text = """🍀Bot"""
    buttons = [[
        InlineKeyboardButton(share_bot[lang], switch_inline_query=f"\n\n{text}")
    ]]
    return InlineKeyboardMarkup(buttons)


def share_bot_keyboard(lang) -> InlineKeyboardMarkup:
    share_bot = {
        "uz": f"Ushbu kinoni ulashing  📤 ",
        "ru": f"Поделиться этим фильмом  📤",
        "en": f"Share this Movie 📤",
        "tr": f"Bu Filmi Paylaş 📤",
    }
    text = """🍀Bot"""
    buttons = [[
        InlineKeyboardButton(share_bot[lang], switch_inline_query=f"\n\n{text}")
    ]]
    return InlineKeyboardMarkup(buttons)


def make_keyboard_for_about_command(lang, admin=False) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(translation.admin_button_text, url="https://t.me/@sherzamon_m")]
    ]

    if admin:
        buttons.append(
            [InlineKeyboardButton(translation.github_button_text, url="https://github.com/GinzaPro/CommonBot.git")])
        buttons.append([InlineKeyboardButton(translation.secret_level_button_text[lang], callback_data='SCRT_LVL')])

    return InlineKeyboardMarkup(buttons)


def make_keyboard_for_help_command() -> InlineKeyboardMarkup:
    buttons = [[
        InlineKeyboardButton(translation.admin_button_text, url="https://t.me/@sherzamon_m")
    ]]

    return InlineKeyboardMarkup(buttons)


from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from asgiref.sync import sync_to_async
from .models import SubscribeChannel
from . import translation


async def keyboard_checked_subscription_channel(user_id, bot):
    # --- O'ZGARTIRILGAN QISM ---
    # .select_related('bot') qo'shildi. Bu SubscribeChannel obyektlari bilan birga
    # ularga bog'liq bo'lgan Bot obyektlarini ham bitta so'rovda yuklab oladi.
    channels_query = SubscribeChannel.objects.select_related('bot').filter(active=True)
    channels = await sync_to_async(list)(channels_query)
    # --- O'ZGARTIRISH TUGADI ---

    buttons = []
    is_subscribed = True

    for idx, channel in enumerate(channels):
        try:
            # Endi channel.bot.token murojaati yangi DB so'rovini yubormaydi,
            # chunki 'bot' obyekti oldindan yuklab olingan.
            token = channel.bot.token
            bot_instance = Bot(token=token)

            # Foydalanuvchining obunachiligini tekshirish
            chat_member = await bot_instance.get_chat_member(chat_id=channel.channel_id, user_id=user_id)
            subscribed = chat_member.status != 'left'

        except BadRequest as e:
            print(f"Error checking subscription: {e}")
            subscribed = False
        except Exception as e:
            print(f"Unexpected error: {e}")
            subscribed = False

        subscription_status = "✅" if subscribed else "❌"
        buttons.append([
            InlineKeyboardButton(
                text=f"Channel {idx + 1} {subscription_status}",
                url=channel.get_channel_link  # Model property ishlatilgani yaxshiroq
            )
        ])
        if not subscribed:
            is_subscribed = False

    check_channels_button = InlineKeyboardButton(translation.check_subscribing, callback_data="check_subscription")
    buttons.append([check_channels_button])

    return InlineKeyboardMarkup(buttons), is_subscribed


def send_location_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton(text=translation.SEND_LOCATION, request_location=True)]],
        resize_keyboard=True
    )


def keyboard_check_subscription_channel() -> InlineKeyboardMarkup:
    """
    Foydalanuvchiga kanalga obuna bo'lishni taklif qiluvchi klaviatura.
    Qaytaradi: InlineKeyboardMarkup
    """
    buttons = [
        [
            InlineKeyboardButton(
                text="🔔 Obuna bo‘lish",
                url="https://t.me/YOUR_CHANNEL_USERNAME"  # Kanal username yoki link
            )
        ],
        [
            InlineKeyboardButton(
                text="✅ Tekshirish",
                callback_data="check_subscription"
            )
        ]
    ]

    return InlineKeyboardMarkup(buttons)


def default_keyboard(lang, admin=False) -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(translation.search[lang]), KeyboardButton(translation.deep_search[lang])],
        [KeyboardButton(translation.change_language[lang]), KeyboardButton(translation.help_text[lang])],
        [KeyboardButton(translation.share_bot_button[lang]), KeyboardButton(translation.about_us[lang])]
    ]
    if admin:
        buttons.append([KeyboardButton(translation.admin_button_text)])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=False)

from elasticsearch_dsl.response import Hit
def build_search_results_keyboard(page_obj, products_on_page, search_mode, language):
    """
    Qidiruv natijalari va sahifalash tugmalarini yaratadi.
    callback_data uchun to'g'ri Document ID (UUID) ishlatiladi.
    """
    buttons = []

    # Fayllar ro'yxati uchun tugmalarni yaratamiz
    for product in products_on_page:  # O'zgaruvchi nomi aniqlashtirildi
        # --- ASOSIY O'ZGARISH: product.meta.id ishlatilmoqda (Elasticsearch Hit obyekti) ---
        callback_data = f"getfile_{product.meta.id}"

        button_text = f"📄 {product.product_title}"
        buttons.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

    # Sahifalash (pagination) tugmalari
    pagination_buttons = []
    if page_obj.has_previous():
        prev_page = page_obj.previous_page_number()
        pagination_buttons.append(
            InlineKeyboardButton(translation.pagination_prev[language],  # translation.py dan olingan
                                 callback_data=f"search_{search_mode}_{prev_page}")
        )

    # Joriy sahifa raqamini ko'rsatuvchi (bosilmaydigan) tugma
    current_page_text = f"{page_obj.number}/{page_obj.paginator.num_pages}"
    pagination_buttons.append(InlineKeyboardButton(current_page_text, callback_data="ignore"))

    if page_obj.has_next():
        next_page = page_obj.next_page_number()
        pagination_buttons.append(
            InlineKeyboardButton(translation.pagination_next[language],  # translation.py dan olingan
                                 callback_data=f"search_{search_mode}_{next_page}")
        )

    if pagination_buttons:  # Agar sahifalash tugmalari mavjud bo'lsa
        buttons.append(pagination_buttons)

    return InlineKeyboardMarkup(buttons)

