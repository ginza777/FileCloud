import requests
from django.core.management.base import BaseCommand
from django.conf import settings


def get_bot_webhook_info(bot_token):
    url = f"https://api.telegram.org/bot{bot_token}/getWebhookInfo"
    r = requests.post(url)
    return r.json()


def get_bot_username(bot_token):
    url = f"https://api.telegram.org/bot{bot_token}/getMe"
    response = requests.post(url)
    result = response.json().get("result") or {}
    return result.get("username"), response.status_code


def set_webhook_single(bot_token, webhook_url):
    url_webhook = f"{webhook_url}/api/bot/webhook/"
    print("url_webhook", url_webhook)
    url = f"https://api.telegram.org/bot{bot_token}/setWebhook?url={url_webhook}"
    response = requests.post(url)
    return response


def delete_webhook_single(bot_token):
    url = f"https://api.telegram.org/bot{bot_token}/deleteWebhook"
    response = requests.post(url)
    return response


class Command(BaseCommand):
    help = "Set webhook for single bot from settings.BOT_TOKEN"

    def handle(self, *args, **options):
        bot_token = getattr(settings, 'BOT_TOKEN', None)
        if not bot_token:
            self.stderr.write(self.style.ERROR("BOT_TOKEN is not configured in settings"))
            return

        res = delete_webhook_single(bot_token)
        self.stdout.write(f"webhook deleted for bot: {bot_token[:6]}****** status: {res.status_code}")
        self.stdout.write("Webhook deleted successfully\n\n")
        res = set_webhook_single(bot_token, settings.WEBHOOK_URL)
        username, status = get_bot_username(bot_token)
        self.stdout.write("\n\n" + 100 * "-")
        self.stdout.write(f"webhook set for bot: https://t.me//{username}")
        self.stdout.write(f"token: {bot_token[:6]}****** status: {res.status_code}")
        info = get_bot_webhook_info(bot_token)
        self.stdout.write(f"webhook url: {info.get('result', {}).get('url')}")
        self.stdout.write("Webhook set successfully\n\n")
