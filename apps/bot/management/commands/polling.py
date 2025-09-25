# commands/run_polling.py
from django.core.management.base import BaseCommand
from django.conf import settings
from ...handler import get_application
from telegram.error import Conflict
import time


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
        
        # Try to start polling with retry logic
        max_retries = 5
        retry_delay = 10
        
        for attempt in range(max_retries):
            try:
                application.run_polling()
                break
            except Conflict as e:
                self.stdout.write(self.style.WARNING(f"Conflict error (attempt {attempt + 1}/{max_retries}): {e}"))
                if attempt < max_retries - 1:
                    self.stdout.write(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    self.stdout.write(self.style.ERROR("Max retries reached. Another bot instance is running."))
                    self.stdout.write(self.style.ERROR("Please stop the other bot instance and try again."))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Unexpected error: {e}"))
                break