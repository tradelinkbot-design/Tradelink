"""
bot/providers/registry.py
==========================
Provider factory — returns the configured MessagingProvider instance.

Usage::

    from bot.providers import get_provider

    provider = get_provider()
    provider.send_text('2348012345678', 'Hello!')

Provider is selected by the ``BOT_PROVIDER`` Django setting:

    'twilio' (default) — TwilioProvider (WhatsApp via Twilio)
    'meta'             — MetaProvider   (Meta WhatsApp Business Cloud API)

Switching providers requires only a single env-var change and a redeploy —
no code changes.
"""

import logging

from django.conf import settings

from .base import MessagingProvider

logger = logging.getLogger(__name__)

# Valid provider names → import paths (lazy to avoid circular imports)
_PROVIDER_MAP = {
    'twilio': 'bot.providers.twilio_provider.TwilioProvider',
    'meta':   'bot.providers.meta_provider.MetaProvider',
}


def get_provider() -> MessagingProvider:
    """
    Return a MessagingProvider instance for the currently configured channel.

    The provider is NOT cached — a fresh instance is created on each call.
    This is intentional so that credential updates (e.g. token rotation)
    take effect without a server restart.  The Celery task creates a new
    instance per task execution, which is the right pattern for distributed
    workers.
    """
    provider_name = getattr(settings, 'BOT_PROVIDER', 'twilio').strip().lower()

    class_path = _PROVIDER_MAP.get(provider_name)
    if not class_path:
        logger.error(
            'Unknown BOT_PROVIDER "%s". Falling back to "twilio". '
            'Valid options: %s',
            provider_name, list(_PROVIDER_MAP.keys()),
        )
        class_path = _PROVIDER_MAP['twilio']

    module_path, class_name = class_path.rsplit('.', 1)
    import importlib
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return cls()
