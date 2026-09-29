"""
chats/routing.py
=================
WebSocket URL patterns for the TradeLink NG chat system.

Registered in your project's asgi.py — NOT in urlpatterns.

Pattern
───────
  ws://<host>/ws/chats/<conversation_id>/

Where <conversation_id> is a standard hyphenated UUID v4 string,
e.g. ws://tradelinkng.com/ws/chats/3fa85f64-5717-4562-b3fc-2c963f66afa6/

The conversation_id is validated in ChatConsumer.connect() against the
database — if the connecting user is not a participant the socket is
closed immediately.
"""

from django.urls import re_path

from .consumers import ChatConsumer

websocket_urlpatterns = [
    re_path(
        r'ws/chats/(?P<conversation_id>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/$',
        ChatConsumer.as_asgi(),
        name='ws_chat',
    ),
]