"""
chats/apps.py
==============
AppConfig for the TradeLink NG real-time chat app.
"""

from django.apps import AppConfig


class ChatsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name               = 'chats'
    verbose_name       = 'TradeLink NG — Chats'

    def ready(self):
        import chats.signals  # noqa: F401 — registers signal handlers