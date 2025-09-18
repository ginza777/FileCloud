# commands/run_polling.py
from django.core.management.base import BaseCommand
from django.conf import settings
from ...handler import get_application


class Command(BaseCommand):
    help = "Run Telegram bot in polling mode"

    def handle(self, *args, **options):
        # BOT_TOKEN ni sozlamalardan olish
        bot_token = getattr(settings, 'BOT_TOKEN', None)
        if not bot_token:
            self.stdout.write(self.style.ERROR("BOT_TOKEN sozlamalarda topilmadi!"))
            return

        application = get_application(bot_token)

        self.stdout.write(self.style.SUCCESS("🚀 Bot polling rejimida ishga tushirildi"))
        application.run_polling()