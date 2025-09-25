# views.py
import logging
import os
from asgiref.sync import sync_to_async
from django.core.paginator import Paginator, Page
from elasticsearch_dsl import Q
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler
from telegram.error import TelegramError
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse
from django.conf import settings

logger = logging.getLogger(__name__)

from . import translation
from apps.files.elasticsearch.documents import DocumentIndex
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
from apps.files.models import Document, Product, SearchQuery
from .tasks import start_broadcast_task

# --- Constants ---
AWAIT_BROADCAST_MESSAGE = 0
FIFTY_MB_IN_BYTES = 50 * 1024 * 1024
PAGE_SIZE = 10

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
        from .admin import AdminDashboardView
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
    # Remove unsupported 'bot' field
    broadcast = await Broadcast.objects.acreate(
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

@get_user
async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, user: User, language: str):
    """Help handler for bot commands."""
    await update.message.reply_text(translation.help_message[language])

@get_user
async def about_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, user: User, language: str):
    """About handler for bot information."""
    await update.message.reply_text(translation.about_message[language])

@get_user
async def share_bot_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, user: User, language: str):
    """Share bot handler."""
    await update.message.reply_text(translation.share_bot_text[language])

@update_or_create_user
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE, user: User, language: str):
    """
    /start buyrug'i uchun. Foydalanuvchini yaratadi yoki oxirgi faolligini yangilaydi.
    Agar file_id parametri bilan kelgan bo'lsa, faylni yuboradi.
    """
    logger.info(f"Start command received from user {user.telegram_id}, args: {context.args}")
    print(f"DEBUG: Start command received from user {user.telegram_id}, args: {context.args}")
    
    # Always send a test message first
    await update.message.reply_text(f"Start komandasi qabul qilindi! User: {user.telegram_id}, Args: {context.args}")
    
    # Check if there's a file ID parameter
    if context.args and len(context.args) > 0:
        file_id = context.args[0]
        logger.info(f"Start command with file_id: {file_id}")
        print(f"DEBUG: Processing file_id: {file_id}")
        try:
            # Try to find and send the file
            document = await Document.objects.select_related('product').aget(id=file_id)
            print(f"DEBUG: Document found: {document.id}, completed: {document.completed}, telegram_file_id: {bool(document.telegram_file_id)}")
            logger.info(f"Document found: {document.id}, completed: {document.completed}, telegram_file_id: {bool(document.telegram_file_id)}")
            
            if document.completed and document.telegram_file_id:
                print(f"DEBUG: Sending file to user {user.telegram_id}")
                # Send a test message first
                await update.message.reply_text(f"Fayl topildi: {document.product.title}")
                
                await context.bot.send_document(
                    chat_id=user.telegram_id,
                    document=document.telegram_file_id,
                    caption=f"<b>{document.product.title}</b>\n\n{translation.file_sent_from_web[language]}",
                    parse_mode=ParseMode.HTML
                )
                print(f"DEBUG: File sent successfully to user {user.telegram_id}")
                logger.info(f"File sent successfully to user {user.telegram_id}")
                return
            else:
                print(f"DEBUG: File not available: completed={document.completed}, telegram_file_id={bool(document.telegram_file_id)}")
                logger.warning(f"File not available: completed={document.completed}, telegram_file_id={bool(document.telegram_file_id)}")
                await update.message.reply_text(f"Fayl mavjud emas. Completed: {document.completed}, Telegram ID: {bool(document.telegram_file_id)}")
                return
        except Document.DoesNotExist:
            print(f"DEBUG: Document not found: {file_id}")
            logger.error(f"Document not found: {file_id}")
            await update.message.reply_text(f"Fayl topilmadi: {file_id}")
            return
        except Exception as e:
            print(f"DEBUG: Error sending file {file_id}: {e}")
            logger.error(f"Error sending file {file_id}: {e}")
            await update.message.reply_text(f"Xatolik: {str(e)}")
            return

    # Normal start command without file ID
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
async def toggle_search_mode(update, context, user, language):
    user_text = update.message.text.strip()
    if user_text == translation.deep_search[language]:
        new_mode = 'deep'
    elif user_text == translation.search[language]:
        new_mode = 'normal'
    else:
        new_mode = context.user_data.get('search_mode', 'normal')
    context.user_data['search_mode'] = new_mode
    response_text = (
        translation.deep_search_mode_on[language]
        if new_mode == 'deep'
        else translation.normal_search_mode_on[language]
    )
    await update.message.reply_text(response_text)

# --- Qidiruv va Fayllar Bilan Ishlash ---
@get_user
@channel_subscribe
async def main_text_handler(update, context, user, language):
    """
    Asosiy matnli xabarlarni qabul qiladi va Elasticsearch orqali qidiradi.
    'normal' va 'deep' rejimlarini qo'llab-quvvatlaydi.
    """
    query_text = update.message.text
    search_mode = context.user_data.get('search_mode', 'normal')
    context.user_data['last_search_query'] = query_text
    context.user_data['search_mode'] = search_mode

    await SearchQuery.objects.acreate(
        user=user,
        query_text=query_text,
        is_deep_search=(search_mode == 'deep')
    )

    # Build ES query using correct fields from DocumentIndex
    s = DocumentIndex.search()
    if search_mode == 'deep':
        # Deep search: parsed_content, title va slug bilan qidirish va completed=true
        # Use exact match with higher boost for better results
        exact_query = Q(
            'multi_match',
            query=query_text,
            fields=['parsed_content^6', 'title^8', 'slug^10'],
            type='phrase',
            boost=5
        )
        fuzzy_query = Q(
            'multi_match',
            query=query_text,
            fields=['parsed_content^3', 'title^4', 'slug^5'],
            fuzziness='AUTO',
            boost=1
        )
        final_query = Q('bool', should=[exact_query, fuzzy_query], minimum_should_match=1)
        s = s.highlight('parsed_content', fragment_size=100)
    else:
        # Normal search: faqat title va slug bilan qidirish va completed=true
        # Use exact match with higher boost for better results
        exact_query = Q(
            'multi_match',
            query=query_text,
            fields=['title^8', 'slug^10'],
            type='phrase',
            boost=5
        )
        fuzzy_query = Q(
            'multi_match',
            query=query_text,
            fields=['title^4', 'slug^5'],
            fuzziness='AUTO',
            boost=1
        )
        final_query = Q('bool', should=[exact_query, fuzzy_query], minimum_should_match=1)
    s = s.query(final_query)

    # Filter only completed docs (field exists in index)
    s = s.filter(Q('term', completed=True))

    # Manual pagination for ES
    page_size = PAGE_SIZE
    page_number = 1
    total_results = await sync_to_async(s.count)()
    start_index = (page_number - 1) * page_size
    end_index = start_index + page_size
    search_results = await sync_to_async(lambda: s[start_index:end_index].execute())()
    all_doc_ids = [hit.meta.id for hit in search_results]

    if total_results > 0 and all_doc_ids:
        # Fetch products from DB and ensure telegram_file_id present
        files_from_db = await sync_to_async(
            lambda: list(
                Product.objects.select_related('document')
                .filter(
                    document_id__in=all_doc_ids,
                    document__completed=True,
                    document__telegram_file_id__isnull=False
                )
            )
        )()
        files_map = {str(prod.document_id): prod for prod in files_from_db}
        products_on_page = [files_map[doc_id] for doc_id in all_doc_ids if doc_id in files_map]

        paginator = Paginator(range(total_results), page_size)
        page_obj = paginator.page(page_number)

        keyboard = build_search_results_keyboard(products_on_page, page_obj, search_mode, language, query_text)
        await update.message.reply_text(
            translation.search_results_found[language].format(count=total_results, query=query_text),
            reply_markup=keyboard
        )
    else:
        await update.message.reply_text(translation.search_no_results[language].format(query=query_text))

@get_user
async def handle_search_pagination(update, context, user, language):
    query = update.callback_query
    await query.answer()
    page_size = PAGE_SIZE

    # Parse callback data to get search mode, page number, and query text
    callback_parts = query.data.split('_')
    if len(callback_parts) >= 4:
        # New format: search_{mode}_{page}_{query_text}
        _, search_mode, page_number_str, query_text = callback_parts[0], callback_parts[1], callback_parts[2], '_'.join(callback_parts[3:])
    elif len(callback_parts) == 3:
        # Old format: search_{mode}_{page} - fallback to context
        _, search_mode, page_number_str = callback_parts
        query_text = context.user_data.get('last_search_query')
    else:
        await query.edit_message_text(translation.search_no_results[language].format(query=""))
        return
    
    if not query_text:
        await query.edit_message_text(translation.search_no_results[language].format(query=""))
        return
        
    page_number = int(page_number_str)

    # Build ES query using correct fields - same as main search for consistency
    if search_mode == 'deep':
        # Deep search: parsed_content, title va slug bilan qidirish va completed=true
        exact_query = Q(
            'multi_match',
            query=query_text,
            fields=['parsed_content^6', 'title^8', 'slug^10'],
            type='phrase',
            boost=5
        )
        fuzzy_query = Q(
            'multi_match',
            query=query_text,
            fields=['parsed_content^3', 'title^4', 'slug^5'],
            fuzziness='AUTO',
            boost=1
        )
        q = Q('bool', should=[exact_query, fuzzy_query], minimum_should_match=1)
    else:
        # Normal search: faqat title va slug bilan qidirish va completed=true
        exact_query = Q(
            'multi_match',
            query=query_text,
            fields=['title^8', 'slug^10'],
            type='phrase',
            boost=5
        )
        fuzzy_query = Q(
            'multi_match',
            query=query_text,
            fields=['title^4', 'slug^5'],
            fuzziness='AUTO',
            boost=1
        )
        q = Q('bool', should=[exact_query, fuzzy_query], minimum_should_match=1)

    s = DocumentIndex.search().query(q)
    s = s.filter(Q('term', completed=True))

    total_results = await sync_to_async(s.count)()
    start_index = (page_number - 1) * page_size
    end_index = start_index + page_size
    search_results = await sync_to_async(lambda: s[start_index:end_index].execute())()
    all_doc_ids = [hit.meta.id for hit in search_results]

    paginator = Paginator(range(total_results), page_size)
    page_obj = Page(all_doc_ids, page_number, paginator)

    files_from_db = await sync_to_async(list)(
        Product.objects.filter(document_id__in=page_obj.object_list)
        .select_related('document')
        .filter(document__completed=True, document__telegram_file_id__isnull=False)
    )
    files_map = {str(p.document_id): p for p in files_from_db}
    products_on_page = [files_map[doc_id] for doc_id in all_doc_ids if doc_id in files_map]

    response_text = translation.search_results_found[language].format(query=query_text, count=total_results)
    reply_markup = build_search_results_keyboard(products_on_page, page_obj, search_mode, language, query_text)
    await query.edit_message_text(text=response_text, reply_markup=reply_markup)

@get_user
async def send_file_by_callback(update, context, user, language):
    """
    Callback orqali faylni Telegramning o'zidagi file_id yordamida yuboradi.
    Bu usul ancha tez va faylning serverda mavjud bo'lishini talab qilmaydi.
    """
    query = update.callback_query
    document_uuid = query.data.split('_')[1]
    await query.answer(text=translation.file_is_being_sent[language])
    try:
        document = await Document.objects.select_related('product').aget(id=document_uuid)
        if document.telegram_file_id:
            await context.bot.send_document(
                chat_id=user.telegram_id,
                document=document.telegram_file_id,
                caption=f"<b>{document.product.title}</b>",
                parse_mode=ParseMode.HTML
            )
        else:
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
