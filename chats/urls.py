"""
chats/urls.py
==============
HTTP URL configuration for the TradeLink NG chat system.

Add to your project's root urls.py:

    from django.urls import path, include

    urlpatterns = [
        ...
        path('chats/', include('chats.urls', namespace='chats')),
    ]

All view names follow the pattern: chats:<name>
e.g.  {% url 'chats:conversation_list' %}
      {% url 'chats:conversation_detail' pk=conv.pk %}
      reverse('chats:start_conversation')

WebSocket URL is configured separately in chats/routing.py and registered
in your project's asgi.py — see SETUP.md.
"""

from django.urls import path

from .views import (
    ConversationListView,
    ConversationDetailView,
    StartConversationView,
    MessageHistoryView,
    UploadAttachmentView,
)

app_name = 'chats'

urlpatterns = [

    # ── Inbox ─────────────────────────────────────────────────────────────────
    path(
        '',
        ConversationListView.as_view(),
        name='conversation_list',
    ),

    # ── Chat room ─────────────────────────────────────────────────────────────
    path(
        '<uuid:pk>/',
        ConversationDetailView.as_view(),
        name='conversation_detail',
    ),

    # ── Start or find a conversation ──────────────────────────────────────────
    # Called by "Message Seller" buttons in marketplace templates.
    path(
        'start/',
        StartConversationView.as_view(),
        name='start_conversation',
    ),

    # ── Load older messages (AJAX / infinite scroll) ──────────────────────────
    path(
        '<uuid:pk>/messages/',
        MessageHistoryView.as_view(),
        name='message_history',
    ),

    # ── Image upload (AJAX — step 1 of two-step send) ─────────────────────────
    path(
        'upload/',
        UploadAttachmentView.as_view(),
        name='upload_attachment',
    ),
]