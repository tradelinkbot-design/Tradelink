"""
bot/providers/__init__.py
=========================
Messaging provider abstraction layer.

Import ``get_provider`` to obtain the currently configured provider:

    from bot.providers import get_provider
    provider = get_provider()
    provider.send_text('+2348012345678', 'Hello!')

Switch providers by changing the ``BOT_PROVIDER`` Django setting:
    'twilio' — Twilio WhatsApp / SMS  (current default)
    'meta'   — Meta WhatsApp Business Cloud API
"""

from .registry import get_provider

__all__ = ['get_provider']
