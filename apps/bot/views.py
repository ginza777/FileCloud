# views.py
import logging
import os
from asgiref.sync import sync_to_async
from django.core.paginator import Paginator, Page
from elasticsearch_dsl.query import QueryString, Q
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler
from telegram.error import TelegramError
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse
from django.conf import settings

logger = logging.getLogger(__name__)

from . import translation
from files.elasticsearch.documents import DocumentIndex
from .keyboard import (
    build_search_results_keyboard,
    default_keyboard,
    language_list_keyboard,
    restart_keyboard,
    send_location_keyboard
)
from .models import User, Location, Broadcast
from .utils import (
    generate_csv_from_users,
    get_user_statistics,
    perform_database_backup,
    channel_subscribe,
    get_user,
    update_or_create_user,
    admin_only
)
from files.models import Document, Product, SearchQuery
from .tasks import start_broadcast_task

AWAIT_BROADCAST_MESSAGE = 0

# --- Dashboard Functions ---

@staff_member_required
def admin_dashboard_demo(request):
    """Render the demo dashboard"""
    demo_html_path = os.path.join(settings.BASE_DIR, 'dashboard_demo.html')
    try:
        with open(demo_html_path, 'r', encoding='utf-8') as f:
            demo_content = f.read()
        return HttpResponse(demo_content)
    except FileNotFoundError:
        return HttpResponse("Demo dashboard not found. Please ensure dashboard_demo.html exists.")


@staff_member_required  
def admin_dashboard_live(request):
    """Render the live dashboard"""
    try:
        from bot.admin_dashboard import AdminDashboardView
        dashboard_view = AdminDashboardView()
        context = dashboard_view.get_dashboard_context()
        from django.shortcuts import render
        return render(request, 'admin/dashboard.html', context)
    except Exception as e:
        # If there's an error, show demo instead
        return admin_dashboard_demo(request)

# --- Broadcast Functions ---

@get_user
@admin_only
async def start_broadcast_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE, user, language) -> int:
    """Reklama uchun xabar yuborishni boshlaydi."""
    await update.message.reply_text("Reklama uchun xabarni forward qiling. Bekor qilish: /cancel")
    return AWAIT_BROADCAST_MESSAGE

@get_user
@admin_only
async def receive_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE, user, language) -> int:
    """Yuborilgan xabarni qabul qilib, tasdiqlash uchun chiqaradi."""
    msg = update.message
    prefix = f"brdcast_{msg.chat_id}_{msg.message_id}"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Hozir yuborish", callback_data=f"{prefix}_send_now")],
        [InlineKeyboardButton("❌ Bekor qilish", callback_data=f"{prefix}_cancel")]
    ])
    await update.message.reply_text("Ushbu xabar barcha foydalanuvchilarga yuborilsinmi?", reply_markup=keyboard)
    return ConversationHandler.END

@get_user
@admin_only
async def handle_broadcast_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE, user, language):
    """Tasdiqlash tugmasi bosilganda ishga tushadi."""
    query = update.callback_query
    await query.answer()
    data = query.data.split('_')
    action, from_chat_id, message_id = data[-1], int(data[1]), int(data[2])

    if action == "cancel":
        await query.edit_message_text("❌ Reklama bekor qilindi.")
        return

    await query.edit_message_text("⏳ Yuborilmoqda...")
    broadcast = await Broadcast.objects.acreate(
        bot=context.bot_data.get("bot_instance"),
        from_chat_id=from_chat_id,
        message_id=message_id,
    )
    start_broadcast_task.delay(broadcast.id)
    await query.edit_message_text(f"✅ Reklama (ID: {broadcast.id}) navbatga qo'yildi!")

@get_user
@admin_only
async def cancel_broadcast_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE, user, language) -> int:
    """Suhbatni bekor qiladi."""
    await update.message.reply_text("Reklama yaratish bekor qilindi.")
    return ConversationHandler.END

# --- Admin Panel Functions ---

@get_user
@admin_only
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE, user, language):
    """Admin panelining asosiy buyruqlarini ko'rsatadi."""
    await update.message.reply_text(translation.secret_admin_commands)


@get_user
@admin_only
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE, user, language):
    """Bot statistikasi."""
    stats_data = await get_user_statistics(context.bot.username)
    text = translation.users_amount_stat.format(
        user_count=stats_data["total"],
        active_24=stats_data["active_24h"]
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


@get_user
@admin_only
async def backup_db(update: Update, context: ContextTypes.DEFAULT_TYPE, user, language):
    """Ma'lumotlar bazasi zaxira nusxasini yaratadi."""
    await update.message.reply_text("⏳ Baza zaxirasi yaratilmoqda...")
    dump_file, error = await perform_database_backup()
    if dump_file and not error:
        try:
            with open(dump_file, 'rb') as f:
                await update.message.reply_document(document=f, caption="Baza zaxirasi muvaffaqiyatli.")
        finally:
            os.remove(dump_file)
    else:
        await update.message.reply_text(f"🔴 Xatolik: {error}")


@get_user
@admin_only
async def export_users(update: Update, context: ContextTypes.DEFAULT_TYPE, user, language):
    """Foydalanuvchilarni CSV formatida eksport qiladi."""
    users_data = await sync_to_async(list)(User.objects.values())
    csv_file = await sync_to_async(generate_csv_from_users)(users_data)
    await update.message.reply_document(document=csv_file, filename="users.csv")


@get_user
@admin_only
async def secret_level(update: Update, context: ContextTypes.DEFAULT_TYPE, user, language):
    """Admin uchun maxfiy ma'lumotlar."""
    query = update.callback_query
    await query.answer()
    stats_data = await get_user_statistics(context.bot.username)
    text = translation.unlock_secret_room[language].format(
        user_count=stats_data["total"],
        active_24=stats_data["active_24h"]
    )
    await query.edit_message_text(text, parse_mode=ParseMode.HTML)


@get_user
@admin_only
async def ask_location(update: Update, context: ContextTypes.DEFAULT_TYPE, user, language):
    """Foydalanuvchidan (admindan) joylashuvni yuborishni so'raydi."""
    await update.message.reply_text(
        text=translation.share_location,
        reply_markup=send_location_keyboard()
    )


@get_user
@admin_only
async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, user, language):
    """Yuborilgan joylashuvni qabul qilib, bazaga saqlaydi."""
    location = update.message.location
    await Location.objects.acreate(
        user=user,
        latitude=location.latitude,
        longitude=location.longitude
    )

    await update.message.reply_text(
        text=translation.thanks_for_location,
        reply_markup=default_keyboard(language, admin=user.is_admin)
    )


# --- Asosiy Foydalanuvchi Funksiyalari ---

@update_or_create_user
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE, user: User, language: str):
    """
    /start buyrug'i uchun. Foydalanuvchini yaratadi yoki oxirgi faolligini yangilaydi.
    """
    if not user.selected_language:
        await ask_language(update, context)
    else:
        await update.message.reply_text(
            translation.start_not_created[language].format(user.full_name),
            reply_markup=default_keyboard(language, admin=user.is_admin)
        )


@get_user
async def ask_language(update: Update, context: ContextTypes.DEFAULT_TYPE, user: User, language: str):
    """
    Tilni tanlash menyusini yuboradi.
    """
    await update.message.reply_text(
        translation.ask_language_text[language],
        reply_markup=language_list_keyboard()
    )


@get_user
async def language_choice_handle(update: Update, context: ContextTypes.DEFAULT_TYPE, user: User, language: str):
    """
    Callback orqali til tanlovini qayta ishlaydi.
    """
    query = update.callback_query
    await query.answer()

    lang_code = query.data.split("language_setting_")[-1]
    user.selected_language = lang_code
    await user.asave(update_fields=['selected_language'])

    await query.edit_message_text(translation.choice_language[lang_code])
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=translation.restart_text[lang_code],
        reply_markup=restart_keyboard(lang=lang_code)
    )


# --- Tugmalar uchun alohida, kichik funksiyalar ---

@update_or_create_user
async def toggle_search_mode(update: Update, context: ContextTypes.DEFAULT_TYPE, user: User, language: str):
    user_text = update.message.text.strip()
    print("user_text: ", user_text)

    if user_text == translation.deep_search[language]:
        print("Deep search")
        new_mode = 'deep'
    elif user_text == translation.search[language]:
        print("Normal search")
        new_mode = 'normal'
    else:
        new_mode = context.user_data.get('default_search_mode', 'normal')

    # faqat sessionga yozamiz
    context.user_data['default_search_mode'] = new_mode

    response_text = (
        translation.deep_search_mode_on[language]
        if new_mode == 'deep'
        else translation.normal_search_mode_on[language]
    )
    await update.message.reply_text(response_text)




@get_user
async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, user: User, language: str):
    """
    'Help' tugmasi uchun ishlaydi.
    """
    await update.message.reply_text(translation.help_message[language])


@get_user
async def about_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, user: User, language: str):
    """
    'About Us' tugmasi uchun ishlaydi.
    """
    await update.message.reply_text(translation.about_message[language])


@get_user
async def share_bot_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, user: User, language: str):
    """
    'Share Bot' tugmasi uchun ishlaydi.
    """
    await update.message.reply_text(translation.share_bot_text[language])


# --- Qidiruv va Fayllar Bilan Ishlash ---

# apps/bot/views.py fayliga o'zgartirishlar

# ... (faylning yuqori qismi o'zgarishsiz)

# apps/bot/views.py fayliga o'zgartirishlar

# ... (faylning yuqori qismi o'zgarishsiz)

# apps/bot/views.py

# ...importlar...
from elasticsearch_dsl import Q  # <-- Q obyektini import qilamiz

FIFTY_MB_IN_BYTES = 50 * 1024 * 1024

# apps/bot/views.py fayliga qo'shiladigan importlar
from elasticsearch_dsl import Q  # <--- MUHIM: Q obyektini import qilamiz


# ... boshqa importlar ...

# Quyidagi funksiyani to'liq yangilang
@get_user
@channel_subscribe
async def main_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, user: User, language: str):
    """
    Asosiy matnli xabarlarni qabul qiladi va Elasticsearch orqali qidiradi.
    'search' va 'deep_search' rejimlarini qo'llab-quvvatlaydi.
    """
    query_text = update.message.text
    search_mode = context.user_data.get('search_mode', 'search')
    page = 1  # Har doim birinchi sahifadan boshlaymiz

    # --- 1. Qidiruv so'rovini bazaga saqlash ---
    await SearchQuery.objects.acreate(
        user=user,
        query_text=query_text,
        is_deep_search=(search_mode == 'deep_search')
    )

    # --- 2. Elasticsearch uchun aqlli so'rovni qurish ---
    s = DocumentDocument.search()

    if search_mode == 'deep_search':
        # DEEP SEARCH: Faqat document ning parsed content bo'yicha qidiruv
        final_query = Q(
            'multi_match',
            query=query_text,
            fields=[
                'content^1'  # Faqat fayl ichidagi matn
            ],
            fuzziness='AUTO',  # Avtomatik ravishda imlo xatolarini tuzatish
            type='best_fields'  # Eng yaxshi moslikni topish
        )
        # Fayl ichidan topilgan joyni ko'rsatish uchun highlighting yoqamiz
        s = s.highlight('content', fragment_size=100)

    else:
        # REGULAR SEARCH: Faqat product title va slug bo'yicha qidiruv
        final_query = Q(
            'multi_match',
            query=query_text,
            fields=[
                'product_title^3',  # Sarlavha 3 barobar muhimroq
                'product_slug^2'   # Slug 2 barobar muhimroq
            ],
            fuzziness='AUTO',  # Avtomatik ravishda imlo xatolarini tuzatish
            type='best_fields'  # Eng yaxshi moslikni topish
        )

    # Qurilgan so'rovni search obyektiga qo'llaymiz
    s = s.query(final_query)

    # --- Filtrlash: Faqat faol dokumentlar ---
    filter_query = Q(
        'bool',
        must=[
            Q('term', is_active=True),           # Document must be active
        ]
    )
    s = s.filter(filter_query)

    # --- 3. Natijalarni sahifalash (Paginatsiya) ---
    paginator = Paginator(s, 10)  # Har sahifada 10 ta natija

    if paginator.count > 0:
        page_obj = paginator.page(page)
        products_on_page = await sync_to_async(list)(page_obj)
        keyboard = build_search_results_keyboard(products_on_page, page_obj, search_mode, language)
        await update.message.reply_text(
            translation.search_results_found[language].format(count=paginator.count, query=query_text),
            reply_markup=keyboard
        )
    else:
        await update.message.reply_text(translation.search_no_results[language].format(query=query_text))


@get_user
async def handle_search_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE, user: User, language: str):
    query = update.callback_query
    await query.answer()
    page_size = 10

    query_text = context.user_data.get('last_search_query')
    if not query_text:
        await query.edit_message_text(translation.search_no_results[language].format(query=""))
        return

    _, search_mode, page_number_str = query.data.split('_')
    page_number = int(page_number_str)

    # 🔎 Deep yoki normal qidiruv
    if search_mode == 'deep':
        exact_fields = ["product_title^10", "product_slug^8", "content^6"]
        fuzzy_fields = ["product_title^5", "product_slug^4", "content^3"]
    else:
        exact_fields = ["product_title^10", "product_slug^8"]
        fuzzy_fields = ["product_title^5", "product_slug^4"]

    exact_clause = Q("multi_match", query=query_text, fields=exact_fields, type="phrase", boost=5)
    fuzzy_clause = Q("multi_match", query=query_text, fields=fuzzy_fields, fuzziness="AUTO", boost=1)

    # Combine: at least one should match; exact matches get higher score due to boost
    q = Q('bool', should=[exact_clause, fuzzy_clause], minimum_should_match=1)

    s = DocumentDocument.search().query(q)

    # --- Filtrlash mantiqi ---
    # Only show completed documents with Telegram File ID and reasonable file size
    filter_query = Q(
        'bool',
        must=[
            Q('term', is_active=True),           # Document must be active
            Q('term', completed=True),           # Document must be fully processed
            Q('exists', field='telegram_file_id'), # Must have Telegram File ID
            Q('range', file_size_bytes={'lte': FIFTY_MB_IN_BYTES}), # File size limit for Telegram
        ]
    )
    s = s.filter(filter_query)

    total_results = await sync_to_async(s.count)()

    # Paginatsiya
    start_index = (page_number - 1) * page_size
    end_index = start_index + page_size
    search_results = await sync_to_async(lambda: s[start_index:end_index].execute())()

    all_files_ids = [hit.meta.id for hit in search_results]

    paginator = Paginator(range(total_results), page_size)
    page_obj = Page(all_files_ids, page_number, paginator)

    files_from_db = await sync_to_async(list)(
        Product.objects.filter(document_id__in=page_obj.object_list).select_related('document')
    )
    files_map = {str(product.document.id): product for product in files_from_db}
    products_on_page = [files_map[doc_id] for doc_id in all_files_ids if doc_id in files_map]

    response_text = translation.search_results_found[language].format(query=query_text, count=total_results)
    reply_markup = build_search_results_keyboard(page_obj, products_on_page, search_mode, language)
    await query.edit_message_text(text=response_text, reply_markup=reply_markup)



@get_user
async def send_file_by_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, user: User, language: str):
    """
    Callback orqali faylni Telegramning o'zidagi file_id yordamida yuboradi.
    Bu usul ancha tez va faylning serverda mavjud bo'lishini talab qilmaydi.
    """
    query = update.callback_query

    # --- 1. ID ni int() ga o'girish olib tashlandi, chunki u UUID ---
    document_uuid = query.data.split('_')[1]
    await query.answer(text=translation.file_is_being_sent[language])

    try:
        # Hujjatni bazadan olamiz
        document = await Document.objects.select_related('product').aget(id=document_uuid)

        # --- 2. Faylni Telegram file_id orqali yuborish ---
        if document.file_id:
            # Agar file_id mavjud bo'lsa (ya'ni, fayl kanalga yuborilgan bo'lsa)
            await context.bot.send_document(
                chat_id=user.telegram_id,
                document=document.file_id,  # Eng asosiy o'zgarish!
                caption=f"<b>{document.product.title}</b>",
                parse_mode=ParseMode.HTML
            )
        else:
            # Agar file_id mavjud bo'lmasa (fayl >50MB yoki kanalga yuborishda xatolik bo'lgan)
            await context.bot.send_message(
                chat_id=user.telegram_id,
                text=translation.file_not_available_for_sending[language]
            )

    except Document.DoesNotExist:
        await context.bot.send_message(chat_id=user.telegram_id,
                                       text="Xatolik: Bunday fayl ma'lumotlar bazasida topilmadi.")
    except TelegramError as e:
        logger.error(f"Telegram fayl yuborishda xatolik (file_id orqali): {e}")
        await context.bot.send_message(
            chat_id=user.telegram_id,
            text=f"Faylni yuborishda Telegram bilan bog'liq xatolik yuz berdi: {e.message}"
        )
    except Exception as e:
        logger.exception(f"Fayl yuborishda (file_id orqali) kutilmagan xatolik: {e}")
        await context.bot.send_message(chat_id=user.telegram_id, text="Faylni yuborishda noma'lum xatolik yuz berdi.")
