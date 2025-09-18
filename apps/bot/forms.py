from django import forms

from apps.bot.models import SubscribeChannel
from .utils import check_bot_is_admin_in_channel  # import from utils to avoid circular import

class SubscribeChannelForm(forms.ModelForm):
    class Meta:
        model = SubscribeChannel
        fields = "__all__"

    def clean(self):
        cleaned_data = super().clean()
        channel_id = cleaned_data.get("channel_id")
        token = cleaned_data.get("token")

        # Bot adminligini asinxron tekshirish
        if channel_id and token:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            bot_is_admin = loop.run_until_complete(check_bot_is_admin_in_channel(channel_id, token))
            if not bot_is_admin:
                raise forms.ValidationError("Bot kanal administratori emas.")
        return cleaned_data