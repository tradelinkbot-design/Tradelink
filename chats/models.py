"""
chats/models.py
================
Real-time chat models for the TradeLink NG marketplace.

Allows buyers and sellers to message each other within the context of a
product listing or an order, with full support for:
    text messages · image attachments · edit · soft-delete
    read receipts · typing indicators · online/offline presence

Models
──────
  Conversation       — a thread between exactly two users
  Message            — one text or image unit in a conversation
  MessageAttachment  — image/file tied to a Message (nullable until sent)
  MessageReadReceipt — per-user, per-message read confirmation
  UserOnlineStatus   — last-seen / is-online presence record
"""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


# ──────────────────────────────────────────────────────────────────────────────
#  1. CONVERSATION
# ──────────────────────────────────────────────────────────────────────────────

class Conversation(models.Model):
    """
    A chat thread between exactly two users: a buyer and a seller.

    Optionally linked to a Product (pre-sale inquiry) or an Order
    (post-sale support). The same two users can have multiple
    conversations if they are talking about different products.

    Lookup pattern
    ──────────────
    Use StartConversationView which calls get_or_create_conversation()
    to find an existing thread before creating a new one. This prevents
    duplicate threads between the same pair of users on the same product.
    """

    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    participants = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='conversations',
        help_text='Exactly two participants: buyer and seller.',
    )

    # Optional context — shows product card in chat header
    product = models.ForeignKey(
        'marketplace.Product',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='conversations',
        help_text='Product this conversation is about, if any.',
    )
    order = models.ForeignKey(
        'marketplace.Order',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='conversations',
        help_text='Order this conversation is tied to, if any.',
    )

    last_message_at = models.DateTimeField(
        null=True, blank=True,
        help_text='Denormalised timestamp of the most recent message, '
                  'used to sort the conversation list without aggregation.',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-last_message_at', '-created_at']

    def __str__(self):
        names = ', '.join(u.username for u in self.participants.all()[:2])
        return f'Conversation [{names}]'

    # ── Helpers ───────────────────────────────────────────────────────────────

    def get_other_participant(self, user):
        """Returns the other user in the conversation."""
        return self.participants.exclude(pk=user.pk).first()

    def get_unread_count(self, user) -> int:
        """
        Number of unread messages for *user* in this conversation.
        Excludes the user's own messages and messages they've already read.
        """
        return (
            self.messages
            .filter(is_deleted=False)
            .exclude(sender=user)
            .exclude(read_receipts__user=user)
            .count()
        )


# ──────────────────────────────────────────────────────────────────────────────
#  2. MESSAGE
# ──────────────────────────────────────────────────────────────────────────────

class Message(models.Model):
    """
    A single message in a Conversation.

    Rules
    ─────
    • Text messages can be edited by their sender (is_edited, edited_at).
    • Any message can be soft-deleted: body is cleared and is_deleted=True.
      The UI shows "This message was deleted" in place of the content.
    • Images live on MessageAttachment. A message can have body + attachments.
    • SYSTEM messages are auto-generated (e.g. "Order #X placed") and cannot
      be edited or deleted by users.
    """

    class MessageType(models.TextChoices):
        TEXT   = 'text',   'Text'
        IMAGE  = 'image',  'Image'      # attachment-only message
        SYSTEM = 'system', 'System'     # auto-generated, read-only

    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name='messages',
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='sent_chat_messages',
        help_text='SET_NULL on user deletion so the message body is still visible.',
    )

    body = models.TextField(
        blank=True,
        help_text='Message text. May be empty for image-only messages.',
    )
    message_type = models.CharField(
        max_length=10,
        choices=MessageType.choices,
        default=MessageType.TEXT,
    )

    # ── Edit ──────────────────────────────────────────────────────────────────
    is_edited = models.BooleanField(default=False)
    edited_at = models.DateTimeField(null=True, blank=True)

    # ── Soft delete ───────────────────────────────────────────────────────────
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        sender = self.sender.username if self.sender else 'Deleted user'
        preview = (self.body[:40] + '…') if len(self.body) > 40 else self.body
        return f'{sender}: {preview or "[no text]"}'

    # ── Business logic ────────────────────────────────────────────────────────

    def edit(self, new_body: str) -> None:
        """
        Edit the body of a TEXT message.
        Raises ValueError if the message type is not TEXT or is deleted.
        """
        if self.is_deleted:
            raise ValueError('Cannot edit a deleted message.')
        if self.message_type == self.MessageType.SYSTEM:
            raise ValueError('System messages cannot be edited.')
        self.body      = new_body.strip()
        self.is_edited = True
        self.edited_at = timezone.now()
        self.save(update_fields=['body', 'is_edited', 'edited_at', 'updated_at'])

    def soft_delete(self) -> None:
        """
        Soft-delete: clears body, marks is_deleted.
        Attachments remain in the database but are hidden by the UI.
        """
        if self.is_deleted:
            return
        self.is_deleted = True
        self.body       = ''
        self.deleted_at = timezone.now()
        self.save(update_fields=['is_deleted', 'body', 'deleted_at', 'updated_at'])


# ──────────────────────────────────────────────────────────────────────────────
#  3. MESSAGE ATTACHMENT
# ──────────────────────────────────────────────────────────────────────────────

class MessageAttachment(models.Model):
    """
    An image or file attached to a Message.

    Upload flow (two-step)
    ──────────────────────
    1. Browser POSTs file to /chats/upload/ → creates attachment with
       message=None and uploaded_by=request.user; returns attachment_id.
    2. Browser sends WebSocket event {type: "text_message", attachment_ids: [...]}
       → consumer links attachment to the created Message.

    Orphan cleanup
    ──────────────
    cleanup_orphan_attachments_task runs nightly to delete any attachment
    where message is still NULL after 24 hours (user uploaded but never sent).
    """

    class FileType(models.TextChoices):
        IMAGE    = 'image',    'Image'
        DOCUMENT = 'document', 'Document'

    id      = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name='attachments',
        null=True, blank=True,
        help_text='NULL until the message is sent (two-step upload flow).',
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='chat_uploads',
        help_text='Who uploaded this file — used to prevent another user '
                  'from claiming an attachment they did not upload.',
    )
    file = models.FileField(
        upload_to='chats/attachments/%Y/%m/',
        help_text='Stored image or document file.',
    )
    file_type    = models.CharField(
        max_length=10, choices=FileType.choices, default=FileType.IMAGE,
    )
    original_name = models.CharField(max_length=255, blank=True)
    file_size     = models.PositiveIntegerField(
        default=0, help_text='File size in bytes.',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'{self.file_type} — {self.original_name or self.file.name}'


# ──────────────────────────────────────────────────────────────────────────────
#  4. MESSAGE READ RECEIPT
# ──────────────────────────────────────────────────────────────────────────────

class MessageReadReceipt(models.Model):
    """
    Records that a specific user has read a specific message.

    Created when:
      • The recipient's WebSocket connects (marks all unread as read).
      • The chat window is open and a new message arrives.
      • The HTTP ConversationDetailView is loaded (bulk mark on page load).

    One receipt per (message, user) pair — enforced by unique_together.
    """

    id      = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name='read_receipts',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='message_read_receipts',
    )
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('message', 'user')
        ordering        = ['read_at']

    def __str__(self):
        return f'{self.user.username} read {self.message_id} at {self.read_at:%H:%M}'


# ──────────────────────────────────────────────────────────────────────────────
#  5. USER ONLINE STATUS
# ──────────────────────────────────────────────────────────────────────────────

class UserOnlineStatus(models.Model):
    """
    Tracks the online/offline presence of a user.

    Updated by
    ──────────
    • ChatConsumer.connect()    → is_online=True
    • ChatConsumer.disconnect() → is_online=False
    • chats.signals.on_user_logout → is_online=False

    The `last_seen` field auto-updates on every save, so even if the user
    never formally disconnects (browser crash), the UI can show
    "last seen X minutes ago" based on this timestamp.
    """

    user      = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='online_status',
    )
    is_online = models.BooleanField(default=False)
    last_seen = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'User Online Status'

    def __str__(self):
        if self.is_online:
            return f'{self.user.username} — online'
        return f'{self.user.username} — last seen {self.last_seen:%d %b %H:%M}'