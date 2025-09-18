from django import forms
from django.conf import settings
import asyncio

from apps.bot.models import SubscribeChannel
from .utils import check_bot_is_admin_in_channel  # import from utils to avoid circular import

class SubscribeChannelForm(forms.ModelForm):
    class Meta:
        model = SubscribeChannel
        fields = "__all__"

    def clean(self):
        cleaned_data = super().clean()
        channel_id = cleaned_data.get("channel_id")
        bot_token = getattr(settings, 'BOT_TOKEN', None)

        if not bot_token:
            raise forms.ValidationError("BOT_TOKEN is not configured in settings.")

        # Bot adminligini asinxron tekshirish
        if channel_id:
            try:
                is_admin = asyncio.run(check_bot_is_admin_in_channel(channel_id, bot_token))
            except RuntimeError:
                # Fallback if already in event loop (e.g., async admin views), create a new loop
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                is_admin = loop.run_until_complete(check_bot_is_admin_in_channel(channel_id, bot_token))
                loop.close()

            if not is_admin:
                raise forms.ValidationError("Bot kanal administratori emas.")
        return cleaned_data