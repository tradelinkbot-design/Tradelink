"""
bot/urls.py
===========
URL configuration for the TradeLink NG bot app.

Both Meta and Twilio webhook endpoints are always registered.
Active provider is controlled by BOT_PROVIDER setting — no URL changes needed
when switching providers.

Mount this in the root urlconf with:
    path('', include('bot.urls')),

Webhook URLs to register in each provider's dashboard
──────────────────────────────────────────────────────
Meta WhatsApp:
    GET  https://yourdomain.com/bot/webhook/   ← verification
    POST https://yourdomain.com/bot/webhook/   ← incoming messages

Twilio (WhatsApp or SMS):
    POST https://yourdomain.com/bot/twilio/webhook/
"""

from django.urls import path

from .views import BotWebhookView, TwilioWebhookView

app_name = 'bot'

urlpatterns = [
    # Meta WhatsApp Business Cloud API
    # GET  — webhook verification challenge
    # POST — incoming WhatsApp messages
    path('bot/webhook/', BotWebhookView.as_view(), name='webhook'),

    # Twilio (WhatsApp Sandbox / approved sender / SMS fallback)
    # POST — incoming messages
    path('bot/twilio/webhook/', TwilioWebhookView.as_view(), name='twilio_webhook'),
]
