# handler.py

import json
import logging

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    InlineQueryHandler, filters, ConversationHandler,
)

from .translation import (
    search, deep_search, help_text, about_us,
    share_bot_button, change_language, admin_button_text, text as restart_text
)
from .views import (
    start, ask_language, language_choice_handle,
    toggle_search_mode, help_handler, about_handler, share_bot_handler,
    main_text_handler, handle_search_pagination, increment_view_count_callback,
    admin_panel, stats, backup_db, export_users, secret_level,
    ask_location, location_handler, inline_query_handler,
    start_broadcast_conversation, receive_broadcast_message,
    cancel_broadcast_conversation, handle_broadcast_confirmation,
    AWAIT_BROADCAST_MESSAGE
)

logger = logging.getLogger(__name__)

telegram_applications = {}


def get_application(token: str) -> Application:
    if token not in telegram_applications:
        application = Application.builder().token(token).build()

        broadcast_conv = ConversationHandler(
            entry_points=[CommandHandler("broadcast", start_broadcast_conversation)],
            states={AWAIT_BROADCAST_MESSAGE: [MessageHandler(~filters.COMMAND, receive_broadcast_message)]},
            fallbacks=[CommandHandler("cancel", cancel_broadcast_conversation)],
        )

        all_button_texts = [
            *search.values(), *deep_search.values(), *help_text.values(),
            *about_us.values(), *share_bot_button.values(), *change_language.values(),
            admin_button_text, *restart_text.values()
        ]
        button_filter = filters.Text(all_button_texts)

        handlers = [
            broadcast_conv,

            # --- Aniq Buyruqlar ---
            CommandHandler("start", start),
            CommandHandler("help", help_handler),
            CommandHandler("about", about_handler),
            CommandHandler("language", ask_language),

            # --- Admin Buyruqlari ---
            CommandHandler("admin", admin_panel),
            CommandHandler("stats", stats),
            CommandHandler("backup_db", backup_db),
            CommandHandler("export_users", export_users),
            CommandHandler("ask_location", ask_location),  # /ask_location BUYRUG'I QO'SHILDI

            # --- Callback So'rovlari ---
            CallbackQueryHandler(handle_broadcast_confirmation, pattern="^brdcast_"),
            CallbackQueryHandler(handle_search_pagination, pattern="^search_"),
            CallbackQueryHandler(increment_view_count_callback, pattern="^getfile_"),
            CallbackQueryHandler(language_choice_handle, pattern="^language_setting_"),
            CallbackQueryHandler(secret_level, pattern="^SCRT_LVL"),

            # --- Inline Query ---
            InlineQueryHandler(inline_query_handler),

            # --- Tugmalar va Maxsus Xabar Turlari ---
            MessageHandler(filters.Regex(f"^({'|'.join(search.values())}|{'|'.join(deep_search.values())})$"),
                           toggle_search_mode),
            MessageHandler(filters.Regex(f"^({'|'.join(help_text.values())})$"), help_handler),
            MessageHandler(filters.Regex(f"^({'|'.join(about_us.values())})$"), about_handler),
            MessageHandler(filters.Regex(f"^({'|'.join(share_bot_button.values())})$"), share_bot_handler),
            MessageHandler(filters.Regex(f"^({'|'.join(change_language.values())})$"), ask_language),
            MessageHandler(filters.Text(admin_button_text), admin_panel),
            MessageHandler(filters.Regex(f"^({'|'.join(restart_text.values())})$"), start),
            MessageHandler(filters.LOCATION, location_handler),  # YUBORILGAN LOKATSIYANI QABUL QILUVCHI HANDLER

            # --- Qolgan barcha matnli xabarlar (Qidiruv) ---
            MessageHandler(filters.TEXT & ~filters.COMMAND & ~button_filter, main_text_handler),
        ]

        application.add_handlers(handlers)
        telegram_applications[token] = application

    return telegram_applications[token]


@csrf_exempt
async def bot_webhook(request):
    """
    Telegram'dan webhook so'rovlarini qabul qiladi, tekshiradi va
    update'ni qayta ishlash uchun application'ga yuboradi.
    """
    bot_token = getattr(settings, 'BOT_TOKEN', None)
    if not bot_token:
        logger.error("BOT_TOKEN sozlamalarda topilmadi.")
        return JsonResponse({"status": "BOT_TOKEN not configured"}, status=500)

    try:
        data = json.loads(request.body.decode("utf-8"))
        
        # Validate that the data contains required fields
        if not isinstance(data, dict) or 'update_id' not in data:
            logger.warning(f"Invalid webhook data received: {data}")
            return JsonResponse({"status": "invalid update data"}, status=400)
            
    except json.JSONDecodeError:
        logger.warning("Webhook orqali yaroqsiz JSON qabul qilindi.")
        return JsonResponse({"status": "invalid json"}, status=400)

    application = get_application(bot_token)
    
    try:
        update = Update.de_json(data, application.bot)
    except Exception as e:
        logger.error(f"Error parsing update: {e}, data: {data}")
        return JsonResponse({"status": "error parsing update"}, status=400)

    # bot_instance'ni bu yerda contextga qo'shish shart emas.
    # Har bir handler'ga qo'shilgan 'inject_bot_instance' dekoratori
    # bu vazifani o'zi bajaradi.

    await application.initialize()
    await application.process_update(update)

    return JsonResponse({"status": "ok"})
