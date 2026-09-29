"""
chats/views.py
===============
HTTP views for the TradeLink NG chat system.

URL namespace: 'chats'  (add to root urls.py as namespace='chats')

View map
────────
  ConversationListView    GET  /chats/
  ConversationDetailView  GET  /chats/<uuid:pk>/
  StartConversationView   POST /chats/start/
  MessageHistoryView      GET  /chats/<uuid:pk>/messages/?before=<uuid>  (AJAX)
  UploadAttachmentView    POST /chats/upload/  (AJAX — returns JSON)

Design notes
────────────
  • All views require authentication (LoginRequiredMixin).
  • The WebSocket consumer (consumers.py) handles real-time delivery.
    These HTTP views handle page rendering and two secondary operations:
      1. UploadAttachmentView — file upload before the message is sent
      2. MessageHistoryView   — "load older messages" infinite-scroll
  • ConversationDetailView marks messages as read on page load so the
    unread badge disappears even before the WebSocket connects.
  • StartConversationView is the entry-point from ProductDetailView
    ("Message Seller" button). It finds an existing thread or creates one.
"""

import logging

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from .models import (
    Conversation,
    Message,
    MessageAttachment,
    MessageReadReceipt,
    UserOnlineStatus,
)

logger = logging.getLogger(__name__)

# ── File upload constraints ───────────────────────────────────────────────────
MAX_UPLOAD_SIZE   = 10 * 1024 * 1024   # 10 MB
ALLOWED_MIME_TYPES = {
    'image/jpeg',
    'image/png',
    'image/gif',
    'image/webp',
}

# ── History pagination ────────────────────────────────────────────────────────
MESSAGES_PER_PAGE = 40


# ──────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def _online(user) -> bool:
    """Returns True if the given user is currently marked online."""
    try:
        return user.online_status.is_online
    except UserOnlineStatus.DoesNotExist:
        return False


def _serialise_message(msg: Message, current_user) -> dict:
    """Serialise a Message instance to a JSON-safe dict for AJAX responses."""
    return {
        'id':           str(msg.pk),
        'sender_id':    str(msg.sender_id) if msg.sender_id else None,
        'sender_name':  (
            msg.sender.get_full_name() or msg.sender.username
            if msg.sender else 'Deleted account'
        ),
        'is_own':       msg.sender_id == current_user.pk if msg.sender_id else False,
        'body':         msg.body,
        'message_type': msg.message_type,
        'is_edited':    msg.is_edited,
        'edited_at':    msg.edited_at.isoformat() if msg.edited_at else None,
        'is_deleted':   msg.is_deleted,
        'created_at':   msg.created_at.isoformat(),
        'attachments':  [
            {
                'id':            str(a.pk),
                'url':           a.file.url,
                'file_type':     a.file_type,
                'original_name': a.original_name,
            }
            for a in msg.attachments.all()
        ],
        'read_by': [str(r.user_id) for r in msg.read_receipts.all()],
    }


# ──────────────────────────────────────────────────────────────────────────────
#  1. CONVERSATION LIST
# ──────────────────────────────────────────────────────────────────────────────

class ConversationListView(LoginRequiredMixin, View):
    """
    GET /chats/

    Renders the inbox: all conversations for the logged-in user,
    sorted by most recent message activity.
    Each row shows the other participant's name, online status, last
    message excerpt, and unread badge count.
    """

    template_name = 'chats/conversation_list.html'

    def get(self, request):
        conversations = (
            Conversation.objects
            .filter(participants=request.user)
            .prefetch_related('participants', 'messages__read_receipts', 'messages__attachments')
            .select_related('product', 'order')
            .order_by('-last_message_at', '-created_at')
        )

        conv_data = []
        for conv in conversations:
            other        = conv.get_other_participant(request.user)
            last_msg     = conv.messages.filter(is_deleted=False).last()
            unread_count = conv.get_unread_count(request.user)

            conv_data.append({
                'conversation': conv,
                'other_user':   other,
                'other_online': _online(other) if other else False,
                'last_message': last_msg,
                'unread_count': unread_count,
            })

        return render(request, self.template_name, {
            'conv_data':    conv_data,
            'total_unread': sum(d['unread_count'] for d in conv_data),
        })


# ──────────────────────────────────────────────────────────────────────────────
#  2. CONVERSATION DETAIL (chat room page)
# ──────────────────────────────────────────────────────────────────────────────

class ConversationDetailView(LoginRequiredMixin, View):
    """
    GET /chats/<uuid:pk>/

    Renders the chat thread with the most recent MESSAGES_PER_PAGE messages.
    Older messages are loaded on demand via MessageHistoryView (AJAX).

    On page load, all unread messages are marked as read in the DB.
    The WebSocket consumer will broadcast the read-receipt to the other user.
    """

    template_name = 'chats/conversation_detail.html'

    def get(self, request, pk):
        conversation = get_object_or_404(
            Conversation.objects
            .prefetch_related('participants')
            .select_related('product', 'product__category', 'order'),
            pk=pk,
            participants=request.user,
        )

        other_user   = conversation.get_other_participant(request.user)
        other_online = _online(other_user) if other_user else False

        # Fetch most recent messages (reversed for display order)
        messages_qs = (
            conversation.messages
            .select_related('sender')
            .prefetch_related('attachments', 'read_receipts')
            .order_by('-created_at')[:MESSAGES_PER_PAGE]
        )
        messages     = list(reversed(list(messages_qs)))
        total_count  = conversation.messages.count()

        # Bulk mark-as-read on page load (DB only; WebSocket broadcasts on connect)
        unread_qs = (
            conversation.messages
            .filter(is_deleted=False)
            .exclude(sender=request.user)
            .exclude(read_receipts__user=request.user)
        )
        receipts = [
            MessageReadReceipt(message=msg, user=request.user)
            for msg in unread_qs
        ]
        if receipts:
            MessageReadReceipt.objects.bulk_create(receipts, ignore_conflicts=True)

        return render(request, self.template_name, {
            'conversation': conversation,
            'other_user':   other_user,
            'other_online': other_online,
            'messages':     messages,
            'has_older':    total_count > MESSAGES_PER_PAGE,
            # oldest_message_id is the anchor for load-more requests
            'oldest_message_id': str(messages[0].pk) if messages else None,
        })


# ──────────────────────────────────────────────────────────────────────────────
#  3. START / FIND CONVERSATION
# ──────────────────────────────────────────────────────────────────────────────

class StartConversationView(LoginRequiredMixin, View):
    """
    POST /chats/start/

    Finds an existing Conversation between the logged-in user and a seller,
    or creates a new one. Optionally records an initial message.

    Triggered by the "Message Seller" button on ProductDetailView.

    POST params
    ───────────
      seller_user_id   — PK of the seller's User record (required)
      product_id       — UUID of the Product for context (optional)
      initial_message  — first message text (optional)

    Response
    ────────
      Redirects to ConversationDetailView on success.
      Returns JSON {'error': '...'} with 400/404 on validation failure
      (so the button can work both as a standard form and AJAX).
    """

    def post(self, request):
        from django.contrib.auth import get_user_model
        User = get_user_model()

        seller_user_id  = request.POST.get('seller_user_id', '').strip()
        product_id      = request.POST.get('product_id', '').strip()
        initial_message = request.POST.get('initial_message', '').strip()
        is_ajax         = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        # ── Validate other user ───────────────────────────────────────────────
        if not seller_user_id:
            return self._error('seller_user_id is required.', 400, is_ajax)

        try:
            other_user = User.objects.get(pk=seller_user_id)
        except User.DoesNotExist:
            return self._error('User not found.', 404, is_ajax)

        if other_user == request.user:
            return self._error('You cannot start a conversation with yourself.', 400, is_ajax)

        # ── Optional product context ──────────────────────────────────────────
        product = None
        if product_id:
            from marketplace.models import Product
            try:
                product = Product.objects.get(pk=product_id)
            except Product.DoesNotExist:
                pass   # context is optional — don't block the chat

        # ── Find or create conversation ───────────────────────────────────────
        conversation = self._get_or_create_conversation(
            request.user, other_user, product
        )

        # ── Optional initial message ──────────────────────────────────────────
        if initial_message:
            Message.objects.create(
                conversation=conversation,
                sender=request.user,
                body=initial_message,
                message_type=Message.MessageType.TEXT,
            )
            Conversation.objects.filter(pk=conversation.pk).update(
                last_message_at=timezone.now(),
            )

        if is_ajax:
            return JsonResponse({
                'conversation_id': str(conversation.pk),
                'redirect_url':    f'/chats/{conversation.pk}/',
            })

        return redirect('chats:conversation_detail', pk=conversation.pk)

    @staticmethod
    def _get_or_create_conversation(user1, user2, product=None) -> Conversation:
        """
        Atomically find or create a Conversation between user1 and user2.

        If product is given, scope the lookup to that product to allow
        separate threads per listing (e.g. buyer enquires about two products
        from the same seller → two conversations).
        """
        with transaction.atomic():
            qs = (
                Conversation.objects
                .filter(participants=user1)
                .filter(participants=user2)
            )
            if product is not None:
                qs = qs.filter(product=product)

            existing = qs.first()
            if existing:
                return existing

            conv = Conversation.objects.create(product=product)
            conv.participants.add(user1, user2)
            return conv

    @staticmethod
    def _error(msg: str, status: int, is_ajax: bool):
        if is_ajax:
            return JsonResponse({'error': msg}, status=status)
        from django.http import HttpResponseBadRequest
        return HttpResponseBadRequest(msg)


# ──────────────────────────────────────────────────────────────────────────────
#  4. MESSAGE HISTORY (AJAX — "load older messages")
# ──────────────────────────────────────────────────────────────────────────────

class MessageHistoryView(LoginRequiredMixin, View):
    """
    GET /chats/<uuid:pk>/messages/?before=<message_uuid>

    AJAX endpoint for the infinite-scroll "load older messages" button.

    Query params
    ────────────
      before — UUID of the oldest message currently visible in the UI.
               Only messages created before this one are returned.
               Omit to get the absolute latest PAGE_SIZE messages.

    Response
    ────────
      {
        "messages": [...],
        "has_more": true | false
      }
    """

    def get(self, request, pk):
        conversation = get_object_or_404(
            Conversation, pk=pk, participants=request.user,
        )

        qs = (
            conversation.messages
            .filter(is_deleted=False)
            .select_related('sender')
            .prefetch_related('attachments', 'read_receipts')
        )

        before_id = request.GET.get('before', '').strip()
        if before_id:
            try:
                pivot     = Message.objects.get(pk=before_id, conversation=conversation)
                qs        = qs.filter(created_at__lt=pivot.created_at)
            except Message.DoesNotExist:
                pass  # ignore invalid pivot — return all

        page      = list(qs.order_by('-created_at')[:MESSAGES_PER_PAGE])
        has_more  = qs.count() > MESSAGES_PER_PAGE
        messages  = list(reversed(page))   # oldest-first for the UI

        return JsonResponse({
            'messages': [_serialise_message(m, request.user) for m in messages],
            'has_more': has_more,
        })


# ──────────────────────────────────────────────────────────────────────────────
#  5. UPLOAD ATTACHMENT (AJAX)
# ──────────────────────────────────────────────────────────────────────────────

class UploadAttachmentView(LoginRequiredMixin, View):
    """
    POST /chats/upload/

    Step 1 of the two-step image-send flow:
      Browser selects an image → POST here → receive {attachment_id, url}
      → include attachment_id in the WebSocket text_message event.

    The consumer then links the attachment to the Message row after
    creating it. Orphan attachments (never linked) are cleaned up nightly.

    Accepts: multipart/form-data with a single field named 'file'.

    Returns (200):
      { "attachment_id": "<uuid>", "url": "<media_url>" }

    Returns (400):
      { "error": "<reason>" }
    """

    def post(self, request):
        file = request.FILES.get('file')
        if not file:
            return JsonResponse({'error': 'No file uploaded.'}, status=400)

        if file.size > MAX_UPLOAD_SIZE:
            mb = MAX_UPLOAD_SIZE // (1024 * 1024)
            return JsonResponse({'error': f'File too large. Maximum is {mb} MB.'}, status=400)

        content_type = getattr(file, 'content_type', '')
        if content_type not in ALLOWED_MIME_TYPES:
            return JsonResponse(
                {'error': 'Only JPEG, PNG, GIF, and WebP images are allowed.'},
                status=400,
            )

        att = MessageAttachment.objects.create(
            file          = file,
            file_type     = MessageAttachment.FileType.IMAGE,
            original_name = file.name[:255],
            file_size     = file.size,
            uploaded_by   = request.user,
            # message is intentionally NULL here — linked when the WS message is sent
        )

        return JsonResponse({
            'attachment_id': str(att.pk),
            'url':           att.file.url,
        })