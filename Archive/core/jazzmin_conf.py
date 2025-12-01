"""
Jazzmin Admin Configuration
============================

Django Jazzmin - modern admin interface konfiguratsiyasi.
"""

JAZZMIN_SETTINGS = {
    # Site title
    "site_title": "FaylTop Admin",
    "site_header": "FaylTop",
    "site_brand": "FaylTop Admin",

    # Logo
    "site_logo": "fayltop_transparent.svg",
    "login_logo": None,
    "login_logo_dark": None,
    "site_logo_classes": "img-circle",
    "site_icon": "fayltop_transparent.svg",

    # Welcome text
    "welcome_sign": "FaylTop Admin Paneliga xush kelibsiz",

    # Copyright
    "copyright": "FaylTop Team",

    # Search models
    "search_model": ["auth.User", "files.Document", "files.Product", "bot.TelegramUser"],

    # User avatar
    "user_avatar": None,

    ############
    # Top Menu #
    ############
    "topmenu_links": [
        {"name": "Dashboard", "url": "admin:index", "permissions": ["auth.view_user"]},
        {"name": "API Docs", "url": "/swagger/", "new_window": True},
        {"model": "auth.User"},
    ],

    #############
    # User Menu #
    #############
    "usermenu_links": [
        {"name": "API Documentation", "url": "/swagger/", "new_window": True},
        {"model": "auth.user"}
    ],

    #############
    # Side Menu #
    #############
    "show_sidebar": True,
    "navigation_expanded": True,
    "hide_apps": [],
    "hide_models": [],

    # Order apps
    "order_with_respect_to": [
        "auth",
        "files",
        "files.document",
        "files.product",
        "bot",
        "bot.telegramuser",
        "core_api",
        "django_celery_results",
        "django_celery_beat"
    ],

    # Custom links
    "custom_links": {},

    # Icons
    "icons": {
        # Django Auth
        "auth": "fas fa-users-cog",
        "auth.user": "fas fa-user",
        "auth.Group": "fas fa-users",
        "admin.LogEntry": "fas fa-file-alt",

        # Files App
        "files": "fas fa-folder",
        "files.Document": "fas fa-file-pdf",
        "files.Product": "fas fa-box",
        "files.SiteToken": "fas fa-key",
        "files.ParseProgress": "fas fa-tasks",
        "files.DocumentError": "fas fa-exclamation-triangle",
        "files.SearchQuery": "fas fa-search",
        "files.DocumentImage": "fas fa-image",

        # Bot App
        "bot": "fas fa-robot",
        "bot.TelegramUser": "fas fa-user-friends",
        "bot.SubscribeChannel": "fas fa-bell",
        "bot.Location": "fas fa-map-marker-alt",
        "bot.Broadcast": "fas fa-bullhorn",
        "bot.BroadcastRecipient": "fas fa-users",

        # Core API App
        "core_api": "fas fa-cogs",
        "core_api.Feedback": "fas fa-comment-dots",

        # Celery Results
        "django_celery_results": "fas fa-tasks",
        "django_celery_results.TaskResult": "fas fa-check-circle",
        "django_celery_results.GroupResult": "fas fa-layer-group",

        # Celery Beat
        "django_celery_beat": "fas fa-clock",
        "django_celery_beat.PeriodicTask": "fas fa-calendar-alt",
        "django_celery_beat.CrontabSchedule": "fas fa-calendar-check",
        "django_celery_beat.IntervalSchedule": "fas fa-stopwatch",
        "django_celery_beat.SolarSchedule": "fas fa-sun",
        "django_celery_beat.ClockedSchedule": "fas fa-clock",

        # Auth Token
        "authtoken": "fas fa-key",
        "authtoken.Token": "fas fa-unlock-alt",
        "authtoken.TokenProxy": "fas fa-unlock-alt",
    },

    "default_icon_parents": "fas fa-chevron-circle-right",
    "default_icon_children": "fas fa-circle",

    #################
    # Related Modal #
    #################
    "related_modal_active": False,

    #############
    # UI Tweaks #
    #############
    "custom_css": None,
    "custom_js": None,
    "use_google_fonts_cdn": True,
    "show_ui_builder": False,

    ###############
    # Change view #
    ###############
    "changeform_format": "horizontal_tabs",
    "changeform_format_overrides": {
        "auth.user": "collapsible",
        "auth.group": "vertical_tabs"
    },

    # Language chooser
    "language_chooser": False,
}

JAZZMIN_UI_TWEAKS = {
    "show_ui_builder": False,
    "navbar_small_text": False,
    "footer_small_text": False,
    "body_small_text": False,
    "brand_small_text": False,
    "brand_colour": "navbar-primary",
    "accent": "accent-primary",
    "navbar": "navbar-dark",
    "no_navbar_border": False,
    "navbar_fixed": True,
    "layout_boxed": False,
    "footer_fixed": False,
    "sidebar_fixed": True,
    "sidebar": "sidebar-dark-primary",
    "sidebar_nav_small_text": False,
    "sidebar_disable_expand": False,
    "sidebar_nav_child_indent": False,
    "sidebar_nav_compact_style": False,
    "sidebar_nav_legacy_style": False,
    "sidebar_nav_flat_style": False,
    "button_classes": {
        "primary": "btn-primary",
        "secondary": "btn-secondary",
        "info": "btn-info",
        "warning": "btn-warning",
        "danger": "btn-danger",
        "success": "btn-success"
    },
    "actions_sticky_top": False
}
