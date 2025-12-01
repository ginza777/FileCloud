# views.py
import logging
import os
from django.db.models import F
from asgiref.sync import sync_to_async
from django.core.paginator import Paginator, Page
from elasticsearch_dsl import Q
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultCachedDocument
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
from .models import TelegramUser, Location, Broadcast
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
PAGE_SIZE = 12

# --- Advanced Search Cache ---
from functools import lru_cache
from django.core.cache import cache
from redis.exceptions import RedisError
import hashlib
import json

def get_search_cache_key(query_text, search_mode, page_number):
    """Generate cache key for search results with better hashing"""
    cache_string = f"search_{query_text.lower().strip()}_{search_mode}_{page_number}"
    return hashlib.sha256(cache_string.encode()).hexdigest()

def get_deep_search_total_cache_key(query_text):
    """Generate cache key for deep search total results"""
    cache_string = f"deep_total_{query_text.lower().strip()}"
    return hashlib.sha256(cache_string.encode()).hexdigest()

def get_cached_search_results(cache_key):
    """Get cached search results with proper error handling"""
    try:
        cached_data = cache.get(f"search:{cache_key}")
        if cached_data:
            logger.info(f"🎯 CACHE HIT: Found cached results for key {cache_key[:8]}...")
            return cached_data
        else:
            logger.info(f"❌ CACHE MISS: No cached results for key {cache_key[:8]}...")
            return None
    except (RedisError, ConnectionError) as e:
        logger.warning(f"Redis cache get error for key {cache_key[:8]}: {str(e)}")
        return None
    except Exception as e:
        logger.warning(f"Unexpected cache get error: {str(e)}")
        return None

def set_cached_search_results(cache_key, results, timeout=900):  # 15 minutes cache
    """Set cached search results with proper error handling"""
    try:
        success = cache.set(f"search:{cache_key}", results, timeout)
        if success:
            logger.info(f"💾 CACHE SET: Stored results for key {cache_key[:8]}... (15 min)")
        else:
            logger.warning(f"Failed to set cache for key {cache_key[:8]}")
    except (RedisError, ConnectionError) as e:
        logger.warning(f"Redis cache set error for key {cache_key[:8]}: {str(e)}")
    except Exception as e:
        logger.warning(f"Unexpected cache set error: {str(e)}")

def clear_search_cache():
    """Clear all search cache with proper error handling"""
    try:
        cache.clear()
        logger.info("🧹 CACHE CLEARED: All search cache cleared")
    except (RedisError, ConnectionError) as e:
        logger.warning(f"Redis cache clear error: {str(e)}")
    except Exception as e:
        logger.warning(f"Unexpected cache clear error: {str(e)}")


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
async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser, language: str):
    """Help handler for bot commands."""
    await update.message.reply_text(translation.help_message[language])


@get_user
async def about_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser, language: str):
    """About handler for bot information."""
    await update.message.reply_text(translation.about_message[language])


@get_user
async def share_bot_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser, language: str):
    """Share bot handler."""
    await update.message.reply_text(translation.share_bot_text[language])


@update_or_create_user
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser, language: str):
    """
    /start buyrug'i uchun. Foydalanuvchini yaratadi yoki oxirgi faolligini yangilaydi.
    Agar file_id parametri bilan kelgan bo'lsa, faylni yuboradi.
    """
    logger.info(f"Start command received from user {user.telegram_id}, args: {context.args}")

    # Check if there's a file ID parameter (deep linking)
    if context.args and len(context.args) > 0:
        file_id_arg = context.args[0]
        logger.info(f"Start command with file_id_arg: {file_id_arg}")

        # Extract file ID from download_ prefix
        if file_id_arg.startswith('download_'):
            file_id = file_id_arg.split('_', 1)[1]
        else:
            file_id = file_id_arg

        logger.info(f"Extracted file_id: {file_id}")

        try:
            document = await sync_to_async(Document.objects.select_related('product').get)(id=file_id)

            # Fayl tayyor va yuborish mumkin bo'lsa
            if document.completed and document.telegram_file_id:
                # Yuklab olishlar sonini oshirish
                await sync_to_async(lambda: Product.objects.filter(id=document.product.id).update(
                    download_count=F('download_count') + 1
                ))()

                await context.bot.send_document(
                    chat_id=user.telegram_id,
                    document=document.telegram_file_id,
                    caption=f"<b>{document.product.title}</b>\n\n{translation.file_sent_from_web[language]}",
                    parse_mode=ParseMode.HTML
                )
                logger.info(f"File sent successfully to user {user.telegram_id}")
            else:
                # Fayl hali tayyor emas yoki yuborib bo'lmaydi
                logger.warning(
                    f"File not available: completed={document.completed}, telegram_file_id={bool(document.telegram_file_id)}")
                await update.message.reply_text(translation.file_not_found[language])

        except Document.DoesNotExist:
            logger.error(f"Document not found: {file_id}")
            await update.message.reply_text(translation.file_not_found[language])
        except Exception as e:
            logger.error(f"Error sending file {file_id}: {e}")
            await update.message.reply_text(translation.error_occurred[language])

        # Fayl bilan bog'liq amaldan so'ng funksiyani yakunlash
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
async def ask_language(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser, language: str):
    """
    Tilni tanlash menyusini yuboradi.
    """
    await update.message.reply_text(
        translation.ask_language_text[language],
        reply_markup=language_list_keyboard()
    )


@get_user
async def language_choice_handle(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser, language: str):
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
@update_or_create_user
@channel_subscribe
async def main_text_handler(update, context, user, language):
    """
    Asosiy matnli xabarlarni qabul qiladi va Elasticsearch orqali qidiradi.
    'normal' va 'deep' rejimlarini qo'llab-quvvatlaydi.
    """
    query_text = update.message.text.strip()
    search_mode = context.user_data.get('search_mode', 'normal')
    context.user_data['last_search_query'] = query_text
    
    logger.info(f"🔍 SEARCH START: User {user.telegram_id} | Query: '{query_text}' | Mode: {search_mode} | Language: {language}")

    await SearchQuery.objects.acreate(
        user=user,
        query_text=query_text,
        is_deep_search=(search_mode == 'deep')
    )

    # Check cache first for faster response
    cache_key = get_search_cache_key(query_text, search_mode, 1)
    cached_results = get_cached_search_results(cache_key)
    
    if cached_results:
        # Return cached results immediately
        total_results, first_page_doc_ids = cached_results
        if total_results > 0 and first_page_doc_ids:
            # Use cached document IDs
            files_from_db = await sync_to_async(
                lambda: list(
                    Product.objects.select_related('document')
                    .filter(
                        document_id__in=first_page_doc_ids,
                        document__completed=True,
                        document__telegram_file_id__isnull=False
                    )
                    .only('id', 'title', 'view_count', 'download_count', 'document_id', 'document__telegram_file_id')
                )
            )()

            if not files_from_db:
                logger.warning(f"🔍 CACHE MISS (Invalid): No valid documents found for cached IDs")
                cached_results = None
            else:
                files_map = {str(prod.document_id): prod for prod in files_from_db}
                products_on_page = [files_map[doc_id] for doc_id in first_page_doc_ids if doc_id in files_map]

                paginator = Paginator(range(total_results), PAGE_SIZE)
                page_obj = paginator.page(1)

                keyboard = build_search_results_keyboard(products_on_page, page_obj, search_mode, language, query_text)

                search_mode_text = "🔍 Chuqurlashtirilgan qidiruv" if search_mode == 'deep' else "🔎 Oddiy qidiruv"
                results_message = f"{search_mode_text}\n\n" + translation.search_results_found[language].format(count=total_results, query=query_text)

                logger.info(f"🔍 SEARCH SUCCESS (Cache): User {user.telegram_id} | Query: '{query_text}' | Mode: {search_mode} | Results: {total_results}")

                await update.message.reply_text(
                    results_message,
                    reply_markup=keyboard
                )
                return

    # Prepare Elasticsearch query
    s = DocumentIndex.search()
    
    # Build optimized query based on search mode
    if search_mode == 'deep':
        # Deep search with improved multi-word handling
        final_query = Q(
            'bool',
            should=[
                # Exact phrase match with high boost
                Q('match_phrase', title={'query': query_text, 'boost': 10}),
                Q('match_phrase', parsed_content={'query': query_text, 'boost': 5}),

                # Multi-match for individual terms
                Q('multi_match',
                    query=query_text,
                    fields=['title^4', 'parsed_content^2', 'slug^3'],
                    type='best_fields',
                    operator='or',
                    minimum_should_match='60%',
                    fuzziness='AUTO',
                    prefix_length=2
                ),

                # Cross-field matching
                Q('multi_match',
                    query=query_text,
                    fields=['title^3', 'parsed_content^2'],
                    type='cross_fields',
                    operator='and',
                    minimum_should_match='50%'
                )
            ],
            minimum_should_match=1
        )
    else:
        # Normal search - focus on title and exact matches
        final_query = Q(
            'bool',
            should=[
                # Exact phrase match in title
                Q('match_phrase', title={'query': query_text, 'boost': 5}),

                # Multi-match for individual terms in title
                Q('multi_match',
                    query=query_text,
                    fields=['title^3', 'slug^2'],
                    type='best_fields',
                    operator='or',
                    minimum_should_match='70%',
                    fuzziness='AUTO',
                    prefix_length=2
                )
            ],
            minimum_should_match=1
        )

    # Apply filter for completed documents
    s = s.query(final_query).filter(Q('term', completed=True))

    # Get page size and calculate offset
    page_size = PAGE_SIZE
    page_number = 1
    start_index = (page_number - 1) * page_size

    try:
        # Execute search with pagination
        search_results = await sync_to_async(lambda: s[start_index:start_index + page_size].execute())()
        first_page_doc_ids = [hit.meta.id for hit in search_results]

        # Get total count
        total_results = search_results.hits.total.value if hasattr(search_results.hits.total, 'value') else len(first_page_doc_ids)

        # Cache results
        set_cached_search_results(cache_key, (total_results, first_page_doc_ids))

        if total_results > 0 and first_page_doc_ids:
            # Get documents from database
            files_from_db = await sync_to_async(
                lambda: list(
                    Product.objects.select_related('document')
                    .filter(
                        document_id__in=first_page_doc_ids,
                        document__completed=True,
                        document__telegram_file_id__isnull=False
                    )
                    .only('id', 'title', 'view_count', 'download_count', 'document_id', 'document__telegram_file_id')
                )
            )()

            # Map documents and create keyboard
            files_map = {str(prod.document_id): prod for prod in files_from_db}
            products_on_page = [files_map[doc_id] for doc_id in first_page_doc_ids if doc_id in files_map]

            if products_on_page:
                paginator = Paginator(range(total_results), page_size)
                page_obj = paginator.page(1)

                keyboard = build_search_results_keyboard(products_on_page, page_obj, search_mode, language, query_text)

                search_mode_text = "🔍 Chuqurlashtirilgan qidiruv" if search_mode == 'deep' else "🔎 Oddiy qidiruv"
                results_message = f"{search_mode_text}\n\n" + translation.search_results_found[language].format(
                    count=total_results,
                    query=query_text
                )

                logger.info(f"🔍 SEARCH SUCCESS: User {user.telegram_id} | Query: '{query_text}' | Mode: {search_mode} | Results: {total_results}")

                await update.message.reply_text(
                    results_message,
                    reply_markup=keyboard
                )
                return

    except Exception as e:
        logger.error(f"🔴 SEARCH ERROR: User {user.telegram_id} | Query: '{query_text}' | Error: {str(e)}")

    # If we get here, either no results were found or an error occurred
    logger.info(f"🔍 SEARCH NO RESULTS: User {user.telegram_id} | Query: '{query_text}' | Mode: {search_mode}")
    await update.message.reply_text(
        translation.search_no_results[language].format(query=query_text)
    )


@get_user
async def handle_search_pagination(update, context, user, language):
    query = update.callback_query
    await query.answer()
    page_size = PAGE_SIZE

    # Parse callback data to get search mode, page number, and query text
    callback_parts = query.data.split('_')
    if len(callback_parts) >= 4:
        # New format: search_{mode}_{page}_{query_text}
        _, search_mode, page_number_str, query_text = callback_parts[0], callback_parts[1], callback_parts[2], '_'.join(
            callback_parts[3:])
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

    # Check cache first for pagination
    cache_key = get_search_cache_key(query_text, search_mode, page_number)
    cached_results = get_cached_search_results(cache_key)
    
    if cached_results:
        # Return cached pagination results immediately
        total_results, current_page_doc_ids = cached_results
        if total_results > 0 and current_page_doc_ids:
            # Use cached document IDs (current page only)
            files_from_db = await sync_to_async(
                lambda: list(
                    Product.objects.select_related('document')
                    .filter(
                        document_id__in=current_page_doc_ids,
                        document__completed=True,
                        document__telegram_file_id__isnull=False
                    )
                    .only('id', 'title', 'view_count', 'download_count', 'document_id', 'document__telegram_file_id')
                )
            )()
            files_map = {str(prod.document_id): prod for prod in files_from_db}
            products_on_page = [files_map[doc_id] for doc_id in current_page_doc_ids if doc_id in files_map]

            paginator = Paginator(range(total_results), page_size)
            page_obj = Page(current_page_doc_ids, page_number, paginator)

            # Enhanced search results message with mode indication
            search_mode_text = "🔍 Chuqurlashtirilgan qidiruv" if search_mode == 'deep' else "🔎 Oddiy qidiruv"
            response_text = f"{search_mode_text}\n\n" + translation.search_results_found[language].format(query=query_text, count=total_results)
            reply_markup = build_search_results_keyboard(products_on_page, page_obj, search_mode, language, query_text)
            await query.edit_message_text(text=response_text, reply_markup=reply_markup)
            return

    # Optimized ES query - same as main search for consistency
    s = DocumentIndex.search()
    
    if search_mode == 'deep':
        # Deep search: slug + title + parsed_content
        q = Q(
            'multi_match',
            query=query_text,
            fields=['slug^5', 'title^4', 'parsed_content^1'],
            type='best_fields',
            fuzziness='AUTO',
            prefix_length=2,
            max_expansions=50
        )
        
        s = s.query(q).filter(Q('term', completed=True))
        
        # For deep search pagination, get total from cache first
        deep_total_cache_key = get_deep_search_total_cache_key(query_text)
        cached_total = cache.get(f"deep_total:{deep_total_cache_key}")
        
        if cached_total:
            total_results = cached_total
            logger.info(f"🔍 DEEP PAGINATION: Using cached total: {total_results}")
        else:
            # Get total count if not cached (fallback)
            try:
                total_count_query = await sync_to_async(lambda: s[0:0].execute())()
                total_results = total_count_query.hits.total.value if hasattr(total_count_query.hits.total, 'value') else 0
                cache.set(f"deep_total:{deep_total_cache_key}", total_results, timeout=900)
                logger.info(f"🔍 DEEP PAGINATION: Calculated total: {total_results}")
            except:
                # If total count fails, estimate based on page
                total_results = page_number * page_size * 2  # Estimate
                logger.info(f"🔍 DEEP PAGINATION: Estimated total: {total_results}")
        
        # Get current page results
        start_index = (page_number - 1) * page_size
        search_results = await sync_to_async(lambda: s[start_index:start_index + page_size].execute())()
        current_page_doc_ids = [hit.meta.id for hit in search_results]
        
        logger.info(f"🔍 DEEP PAGINATION: Page {page_number}, Results: {len(current_page_doc_ids)}")
        
    else:
        # Normal search: slug + title only
        q = Q(
            'multi_match',
            query=query_text,
            fields=['slug^4', 'title^3'],
            type='best_fields',
            fuzziness='AUTO',
            prefix_length=2,
            max_expansions=20
        )

        s = s.query(q).filter(Q('term', completed=True))

        # Optimized pagination - get only current page results
        start_index = (page_number - 1) * page_size
        search_results = await sync_to_async(lambda: s[start_index:start_index + page_size].execute())()
        total_results = search_results.hits.total.value if hasattr(search_results.hits.total, 'value') else len(search_results.hits)
        current_page_doc_ids = [hit.meta.id for hit in search_results]

    # Cache current page results for faster future access
    set_cached_search_results(cache_key, (total_results, current_page_doc_ids))

    paginator = Paginator(range(total_results), page_size)
    page_obj = Page(current_page_doc_ids, page_number, paginator)

    files_from_db = await sync_to_async(list)(
        Product.objects.filter(document_id__in=current_page_doc_ids)
        .select_related('document')
        .filter(document__completed=True, document__telegram_file_id__isnull=False)
        .only('id', 'title', 'view_count', 'download_count', 'document_id', 'document__telegram_file_id')
    )
    files_map = {str(p.document_id): p for p in files_from_db}
    products_on_page = [files_map[doc_id] for doc_id in current_page_doc_ids if doc_id in files_map]

    # Enhanced search results message with mode indication
    search_mode_text = "🔍 Chuqurlashtirilgan qidiruv" if search_mode == 'deep' else "🔎 Oddiy qidiruv"
    response_text = f"{search_mode_text}\n\n" + translation.search_results_found[language].format(query=query_text, count=total_results)
    reply_markup = build_search_results_keyboard(products_on_page, page_obj, search_mode, language, query_text)
    await query.edit_message_text(text=response_text, reply_markup=reply_markup)


@get_user
async def increment_view_count_callback(update, context, user, language):
    """
    Qidiruv natijalarida fayl tugmasini bosganda ko'rishlar sonini oshirish
    """
    query = update.callback_query
    # Fix callback data parsing - document_id is after "getfile_" prefix
    document_uuid = query.data.replace('getfile_', '')

    try:
        # Document orqali Product ni topish va ko'rishlar sonini oshirish
        document = await sync_to_async(Document.objects.select_related('product').get)(id=document_uuid)
        
        # Ko'rishlar sonini oshirish
        await sync_to_async(lambda: Product.objects.filter(id=document.product.id).update(
            view_count=F('view_count') + 1
        ))()
        
        # Yangi view count ni olish
        updated_product = await sync_to_async(Product.objects.get)(id=document.product.id)
        
        logger.info(f"👁 VIEW COUNT INCREMENTED: Document: {document_uuid} | Product: {document.product.title} | Old count: {document.product.view_count} | New count: {updated_product.view_count}")

        # Faylni yuborish
        await send_file_by_callback(update, context, user, language)

    except Exception as e:
        logger.error(f"View count increment error: {e}")
        await send_file_by_callback(update, context, user, language)


async def send_file_by_callback(update, context, user, language):
    """
    Callback orqali faylni Telegramning o'zidagi file_id yordamida yuboradi.
    Bu usul ancha tez va faylning serverda mavjud bo'lishini talab qilmaydi.
    """
    query = update.callback_query
    # Fix callback data parsing - document_id is after "getfile_" prefix
    document_uuid = query.data.replace('getfile_', '')
    
    await query.answer(text=translation.file_is_being_sent[language])
    try:
        logger.info(f"📥 FILE DOWNLOAD START: User {user.telegram_id} | Document: {document_uuid} | Language: {language}")
        document = await Document.objects.select_related('product').aget(id=document_uuid)
        logger.info(f"📄 DOCUMENT FOUND: ID: {document.id} | Title: {document.product.title if document.product else 'No title'} | TelegramFileID: {document.telegram_file_id[:20] if document.telegram_file_id else 'None'}... | Status: {document.telegram_status}")
        
        if document.telegram_file_id:
            # Yuklab olishlar sonini oshirish
            await sync_to_async(lambda: Product.objects.filter(id=document.product.id).update(
                download_count=F('download_count') + 1
            ))()

            await context.bot.send_document(
                chat_id=user.telegram_id,
                document=document.telegram_file_id,
                caption=f"<b>{document.product.title}</b>",
                parse_mode=ParseMode.HTML
            )
            logger.info(f"✅ FILE SENT SUCCESS: User {user.telegram_id} | Document: {document.id} | Title: {document.product.title} | Method: telegram_file_id")
        else:
            logger.warning(f"Document {document_uuid} has no telegram_file_id. Status: {document.telegram_status}")
            # Fallback: parse_file_url orqali faylni yuborish
            if document.parse_file_url:
                logger.info(f"🔄 FALLBACK METHOD: Trying to send file via parse_file_url: {document.parse_file_url[:50]}...")
                try:
                    await context.bot.send_document(
                        chat_id=user.telegram_id,
                        document=document.parse_file_url,
                        caption=f"<b>{document.product.title}</b>",
                        parse_mode=ParseMode.HTML
                    )
                    logger.info(f"✅ FILE SENT SUCCESS: User {user.telegram_id} | Document: {document.id} | Title: {document.product.title} | Method: parse_file_url")
                except Exception as e:
                    logger.error(f"❌ FALLBACK FAILED: User {user.telegram_id} | Document: {document.id} | Error: {str(e)[:100]}")
                    await context.bot.send_message(
                        chat_id=user.telegram_id,
                        text=f"❌ Fayl yuborishda xatolik: {str(e)[:100]}"
                    )
            else:
                logger.warning(f"❌ NO FILE AVAILABLE: User {user.telegram_id} | Document: {document.id} | No telegram_file_id and no parse_file_url")
                await context.bot.send_message(
                    chat_id=user.telegram_id,
                    text=f"❌ Fayl hali Telegram'ga yuborilmagan va URL ham yo'q. Status: {document.telegram_status}"
                )

    except Document.DoesNotExist:
        logger.error(f"❌ DOCUMENT NOT FOUND: User {user.telegram_id} | Document: {document_uuid}")
        await context.bot.send_message(chat_id=user.telegram_id,
                                       text=translation.file_not_found[language])
    except TelegramError as e:
        logger.error(f"❌ TELEGRAM ERROR: User {user.telegram_id} | Document: {document_uuid} | Error: {e}")
        await context.bot.send_message(
            chat_id=user.telegram_id,
            text=f"Faylni yuborishda Telegram bilan bog'liq xatolik yuz berdi: {e.message}"
        )
    except Exception as e:
        logger.exception(f"❌ UNEXPECTED ERROR: User {user.telegram_id} | Document: {document_uuid} | Error: {e}")
        await context.bot.send_message(chat_id=user.telegram_id, text=translation.file_send_error[language])


@get_user
async def inline_query_handler(update, context, user, language):
    """
    Inline query handler - foydalanuvchi @bot_username query yozganda ishlaydi
    """
    query = update.inline_query.query.strip()
    logger.info(f"Inline query received: '{query}' from user {user.telegram_id}")
    
    if not query:
        # Bo'sh query bo'lsa, hech narsa qaytarmaymiz
        logger.info("Empty inline query, returning empty results")
        await update.inline_query.answer([])
        return
    
    try:
        # Elasticsearch orqali qidirish
        s = DocumentIndex.search()
        
        # Optimized inline search - fast and efficient
        # Inline queries use regular search for faster results (title + slug only)
        final_query = Q(
            'multi_match',
            query=query,
            fields=['title^3', 'slug^2'],
            type='best_fields',
            fuzziness='AUTO',
            prefix_length=2,
            max_expansions=20
        )
        
        s = s.query(final_query)
        s = s.filter(Q('term', completed=True))
        
        # Faqat 20 ta natija (Telegram inline query limit)
        search_results = await sync_to_async(lambda: s[:20].execute())()
        
        results = []
        for hit in search_results:
            try:
                # Database dan product ma'lumotlarini olish
                product = await sync_to_async(Product.objects.select_related('document').get)(
                    document_id=hit.meta.id,
                    document__completed=True,
                    document__telegram_file_id__isnull=False
                )
                
                # Inline query result yaratish - cached document format
                result = InlineQueryResultCachedDocument(
                    id=str(product.document_id),
                    title=product.title[:64],
                    document_file_id=product.document.telegram_file_id,
                    description=f"👁 {product.view_count} | ⬇️ {product.download_count}",
                    caption=f"📄 {product.title}\n\n👁 Ko'rishlar: {product.view_count}\n⬇️ Yuklab olishlar: {product.download_count}",
                    parse_mode=ParseMode.HTML
                )
                results.append(result)
                
            except Product.DoesNotExist:
                continue
            except Exception as e:
                logger.error(f"Inline query result creation error for {hit.meta.id}: {e}")
                continue
        
        logger.info(f"Inline query returning {len(results)} results for query: '{query}'")
        await update.inline_query.answer(results)
        
    except Exception as e:
        logger.error(f"Inline query error: {e}")
        await update.inline_query.answer([])
