"""
chats/consumers.py
===================
Django Channels WebSocket consumers for the TradeLink NG chat system.

Consumer
────────
  ChatConsumer
      One WebSocket connection per open conversation.
      WebSocket URL:  ws://<host>/ws/chats/<conversation_id>/
      Channel group:  chat_<conversation_id>

Client → Server message types
──────────────────────────────
  text_message    — new text message (with optional pre-uploaded attachment IDs)
  typing          — user started typing
  stop_typing     — user stopped typing
  read_receipt    — mark one or more messages as read
  edit_message    — edit the body of an existing TEXT message
  delete_message  — soft-delete a message

Server → Client message types
──────────────────────────────
  new_message     — a message was added to the conversation
  message_edited  — a message body was updated
  message_deleted — a message was soft-deleted
  typing          — the other participant is typing
  stop_typing     — the other participant stopped typing
  read_receipt    — the other participant read some messages
  user_status     — a participant came online or went offline
  error           — an error occurred (only sent to the connection that caused it)

Authentication
──────────────
  The consumer closes immediately if scope['user'] is not authenticated.
  It also verifies the user is a participant of the requested conversation.
  Both checks happen in connect() before accept() is called.

Dependencies (install via pip):
  channels>=4.0
  channels-redis>=4.0
  daphne>=4.0        (or use uvicorn with channels)
"""

import json
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.core.cache import cache
from django.utils import timezone

from core.ratelimit import is_rate_limited_async

logger = logging.getLogger(__name__)


class ChatConsumer(AsyncWebsocketConsumer):
    """
    Handles real-time messaging within a single Conversation.

    Lifecycle
    ─────────
    connect()    — verify auth + participation → join group → mark online
                   → broadcast presence → accept() → flush unread receipts
    receive()    — route incoming JSON to the appropriate handler
    disconnect() — leave group → mark offline → broadcast presence

    All DB access is wrapped in database_sync_to_async so the consumer
    stays fully async and never blocks the event loop.
    """

    # ── Connection lifecycle ──────────────────────────────────────────────────

    async def connect(self):
        self.user = self.scope['user']

        if not self.user.is_authenticated:
            logger.warning('ChatConsumer: unauthenticated connection rejected.')
            await self.close(code=4001)
            return

        self.conversation_id = self.scope['url_route']['kwargs']['conversation_id']
        self.group_name      = f'chat_{self.conversation_id}'

        # Gate: only participants can connect
        if not await self._is_participant():
            logger.warning(
                'ChatConsumer: user %s is not a participant in conversation %s.',
                self.user.pk, self.conversation_id,
            )
            await self.close(code=4003)
            return

        # Join the conversation's channel group
        try:
            await self.channel_layer.group_add(self.group_name, self.channel_name)
        except Exception as exc:
            logger.error('ChatConsumer: group_add failed: %s', exc)
            await self.close(code=4002)
            return

        # Persist online status
        try:
            await self._set_online_status(True)
        except Exception as exc:
            logger.warning('ChatConsumer: _set_online_status failed: %s', exc)

        # Notify the other participant that this user is online
        try:
            await self.channel_layer.group_send(
                self.group_name,
                {
                    'type':    'user_status',
                    'user_id': str(self.user.pk),
                    'status':  'online',
                },
            )
        except Exception as exc:
            logger.warning('ChatConsumer: group_send online status failed: %s', exc)

        # Handshake complete — connection is now open
        await self.accept()

        # On connect, bulk-mark any unread messages as read and broadcast receipts
        try:
            unread_ids = await self._get_unread_message_ids()
            if unread_ids:
                await self._mark_messages_read(unread_ids)
                await self.channel_layer.group_send(
                    self.group_name,
                    {
                        'type':        'read_receipt',
                        'user_id':     str(self.user.pk),
                        'message_ids': [str(mid) for mid in unread_ids],
                    },
                )
        except Exception as exc:
            logger.warning('ChatConsumer: unread messages processing failed: %s', exc)

        logger.info(
            'ChatConsumer: user %s connected to conversation %s.',
            self.user.pk, self.conversation_id,
        )

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            try:
                await self.channel_layer.group_discard(self.group_name, self.channel_name)
            except Exception as exc:
                logger.warning('ChatConsumer: group_discard failed: %s', exc)

        if hasattr(self, 'user') and self.user.is_authenticated:
            now_dt = timezone.now()
            try:
                await self._set_online_status(False)
            except Exception as exc:
                logger.warning('ChatConsumer: set_online_status offline failed: %s', exc)

            # Broadcast offline status with last_seen timestamp
            try:
                from chats.utils import format_last_seen
                friendly_last_seen = format_last_seen(now_dt)
                await self.channel_layer.group_send(
                    self.group_name,
                    {
                        'type':              'user_status',
                        'user_id':           str(self.user.pk),
                        'status':            'offline',
                        'last_seen':         now_dt.isoformat(),
                        'last_seen_display': friendly_last_seen,
                    },
                )
            except Exception:
                pass  # channel layer may be unavailable during shutdown

        logger.info(
            'ChatConsumer: user %s disconnected from conversation %s (code=%s).',
            getattr(self, 'user', '?'), self.conversation_id, close_code,
        )

    # ── Receive / routing ─────────────────────────────────────────────────────

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except (json.JSONDecodeError, TypeError):
            await self._send_error('Invalid JSON payload.')
            return

        msg_type = data.get('type')
        if msg_type == 'ping':
            try:
                await self._touch_presence()
            except Exception:
                pass
            await self.send(text_data=json.dumps({'type': 'pong'}))
            return

        handlers = {
            'text_message':  self._handle_text_message,
            'typing':        self._handle_typing,
            'stop_typing':   self._handle_stop_typing,
            'read_receipt':  self._handle_read_receipt,
            'edit_message':  self._handle_edit_message,
            'delete_message': self._handle_delete_message,
        }

        handler = handlers.get(msg_type)
        if handler:
            await handler(data)
        else:
            await self._send_error(f'Unknown message type: {msg_type!r}')

    # ── Client → Server handlers ──────────────────────────────────────────────

    async def _handle_text_message(self, data: dict):
        """
        New message from the sender.

        Payload:
            body           — str   (can be empty if attachment_ids present)
            attachment_ids — list  (UUIDs of pre-uploaded MessageAttachments)
        """
        body           = data.get('body', '').strip()
        attachment_ids = data.get('attachment_ids') or []

        if not body and not attachment_ids:
            await self._send_error('A message must have body text or at least one attachment.')
            return

        # Rate limit: max 45 messages per minute per user in chat
        if await is_rate_limited_async(self.user.pk, key='chat_msg:{user}', limit=45, window=60):
            await self._send_error('You are sending messages too quickly. Please wait a moment.')
            return

        message_data = await self._create_message(body, attachment_ids)
        await self._touch_conversation()

        await self.channel_layer.group_send(
            self.group_name,
            {
                'type':         'new_message',
                'message_id':   message_data['id'],
                'sender_id':    str(self.user.pk),
                'sender_name':  self.user.get_full_name() or self.user.username,
                'body':         message_data['body'],
                'message_type': message_data['message_type'],
                'attachments':  message_data['attachments'],
                'created_at':   message_data['created_at'],
                'is_edited':    False,
            },
        )

    async def _handle_typing(self, data: dict):
        """Broadcast "user is typing" to the other participant."""
        await self.channel_layer.group_send(
            self.group_name,
            {'type': 'typing', 'user_id': str(self.user.pk)},
        )

    async def _handle_stop_typing(self, data: dict):
        """Broadcast "user stopped typing" to the other participant."""
        await self.channel_layer.group_send(
            self.group_name,
            {'type': 'stop_typing', 'user_id': str(self.user.pk)},
        )

    async def _handle_read_receipt(self, data: dict):
        """
        Mark specific messages as read.

        Payload:
            message_ids — list of message UUID strings
        """
        message_ids = data.get('message_ids') or []
        if not message_ids:
            return

        await self._mark_messages_read(message_ids)

        await self.channel_layer.group_send(
            self.group_name,
            {
                'type':        'read_receipt',
                'user_id':     str(self.user.pk),
                'message_ids': [str(mid) for mid in message_ids],
            },
        )

    async def _handle_edit_message(self, data: dict):
        """
        Edit the body of a TEXT message the user sent.

        Payload:
            message_id — UUID string
            body       — new body text (non-empty)
        """
        message_id = data.get('message_id', '').strip()
        new_body   = data.get('body', '').strip()

        if not message_id:
            await self._send_error('edit_message requires message_id.')
            return
        if not new_body:
            await self._send_error('edit_message requires a non-empty body.')
            return

        success, edited_at = await self._edit_message(message_id, new_body)
        if not success:
            await self._send_error(
                'Cannot edit this message. It may not exist, belong to you, '
                'or be a system/deleted message.'
            )
            return

        await self.channel_layer.group_send(
            self.group_name,
            {
                'type':       'message_edited',
                'message_id': message_id,
                'body':       new_body,
                'edited_at':  edited_at,
            },
        )

    async def _handle_delete_message(self, data: dict):
        """
        Soft-delete a message the user sent.

        Payload:
            message_id — UUID string
        """
        message_id = data.get('message_id', '').strip()
        if not message_id:
            await self._send_error('delete_message requires message_id.')
            return

        success = await self._delete_message(message_id)
        if not success:
            await self._send_error(
                'Cannot delete this message. It may not exist or belong to you.'
            )
            return

        await self.channel_layer.group_send(
            self.group_name,
            {'type': 'message_deleted', 'message_id': message_id},
        )

    # ── Group event → WebSocket send (one method per event type) ─────────────
    # Django Channels maps group event['type'] to a consumer method by
    # replacing '.' with '_'. All these methods receive the full event dict
    # and forward the relevant fields to the connected WebSocket client.

    async def new_message(self, event: dict):
        await self.send(text_data=json.dumps({
            'type':         'new_message',
            'message_id':   event['message_id'],
            'sender_id':    event['sender_id'],
            'sender_name':  event['sender_name'],
            'body':         event['body'],
            'message_type': event['message_type'],
            'attachments':  event['attachments'],
            'created_at':   event['created_at'],
            'is_edited':    event.get('is_edited', False),
        }))

    async def message_edited(self, event: dict):
        await self.send(text_data=json.dumps({
            'type':       'message_edited',
            'message_id': event['message_id'],
            'body':       event['body'],
            'edited_at':  event['edited_at'],
        }))

    async def message_deleted(self, event: dict):
        await self.send(text_data=json.dumps({
            'type':       'message_deleted',
            'message_id': event['message_id'],
        }))

    async def typing(self, event: dict):
        # Do NOT echo back to the sender — they already know they are typing.
        if str(self.user.pk) != event['user_id']:
            await self.send(text_data=json.dumps({
                'type':    'typing',
                'user_id': event['user_id'],
            }))

    async def stop_typing(self, event: dict):
        if str(self.user.pk) != event['user_id']:
            await self.send(text_data=json.dumps({
                'type':    'stop_typing',
                'user_id': event['user_id'],
            }))

    async def read_receipt(self, event: dict):
        await self.send(text_data=json.dumps({
            'type':        'read_receipt',
            'user_id':     event['user_id'],
            'message_ids': event['message_ids'],
        }))

    async def user_status(self, event: dict):
        payload = {
            'type':    'user_status',
            'user_id': event['user_id'],
            'status':  event['status'],   # 'online' | 'offline'
        }
        if 'last_seen' in event:
            payload['last_seen'] = event['last_seen']
        if 'last_seen_display' in event:
            payload['last_seen_display'] = event['last_seen_display']
        await self.send(text_data=json.dumps(payload))

    # ── Database helpers (wrapped for async) ──────────────────────────────────

    @database_sync_to_async
    def _touch_presence(self) -> None:
        from chats.utils import touch_user_presence
        touch_user_presence(self.user, is_online=True)

    @database_sync_to_async
    def _is_participant(self) -> bool:
        from chats.models import Conversation
        return Conversation.objects.filter(
            pk=self.conversation_id,
            participants=self.user,
        ).exists()

    @database_sync_to_async
    def _set_online_status(self, is_online: bool) -> None:
        from chats.models import UserOnlineStatus
        from django.utils import timezone
        UserOnlineStatus.objects.update_or_create(
            user=self.user,
            defaults={'is_online': is_online, 'last_seen': timezone.now()},
        )

    @database_sync_to_async
    def _get_unread_message_ids(self) -> list:
        """Return PKs of messages in this conversation not yet read by the user."""
        from chats.models import Message
        return list(
            Message.objects.filter(
                conversation_id=self.conversation_id,
                is_deleted=False,
            )
            .exclude(sender=self.user)
            .exclude(read_receipts__user=self.user)
            .values_list('pk', flat=True)
        )

    @database_sync_to_async
    def _mark_messages_read(self, message_ids: list) -> None:
        """Bulk-create read receipts for the given message PKs, skipping duplicates."""
        from chats.models import Message, MessageReadReceipt
        messages = (
            Message.objects.filter(
                pk__in=message_ids,
                conversation_id=self.conversation_id,
            )
            .exclude(sender=self.user)
        )
        for msg in messages:
            MessageReadReceipt.objects.get_or_create(message=msg, user=self.user)

    @database_sync_to_async
    def _create_message(self, body: str, attachment_ids: list) -> dict:
        """
        Persist a new Message and link any pre-uploaded attachments.
        Returns a serialisable dict for the broadcast event.
        """
        from chats.models import Conversation, Message, MessageAttachment

        conversation = Conversation.objects.get(pk=self.conversation_id)

        # Determine message_type: IMAGE if only attachments, TEXT otherwise
        msg_type = (
            Message.MessageType.IMAGE
            if (not body and attachment_ids)
            else Message.MessageType.TEXT
        )

        msg = Message.objects.create(
            conversation=conversation,
            sender=self.user,
            body=body,
            message_type=msg_type,
        )

        # Link pre-uploaded attachments (security: only owner can claim them)
        attachments_out = []
        if attachment_ids:
            atts = MessageAttachment.objects.filter(
                pk__in=attachment_ids,
                message__isnull=True,
                uploaded_by=self.user,
            )
            for att in atts:
                att.message = msg
                att.save(update_fields=['message'])
                attachments_out.append({
                    'id':           str(att.pk),
                    'url':          att.file.url,
                    'file_type':    att.file_type,
                    'original_name': att.original_name,
                })

        return {
            'id':           str(msg.pk),
            'body':         msg.body,
            'message_type': msg.message_type,
            'attachments':  attachments_out,
            'created_at':   msg.created_at.isoformat(),
        }

    @database_sync_to_async
    def _touch_conversation(self) -> None:
        """Update Conversation.last_message_at for proper list ordering."""
        from chats.models import Conversation
        Conversation.objects.filter(pk=self.conversation_id).update(
            last_message_at=timezone.now(),
        )

    @database_sync_to_async
    def _edit_message(self, message_id: str, new_body: str):
        """
        Edit a message. Only the sender can edit, only TEXT messages,
        only non-deleted.

        Returns (True, edited_at_iso) on success, (False, None) on failure.
        """
        from chats.models import Message
        try:
            msg = Message.objects.get(
                pk=message_id,
                sender=self.user,
                conversation_id=self.conversation_id,
                is_deleted=False,
                message_type=Message.MessageType.TEXT,
            )
            msg.edit(new_body)
            return True, msg.edited_at.isoformat()
        except (Message.DoesNotExist, ValueError):
            return False, None

    @database_sync_to_async
    def _delete_message(self, message_id: str) -> bool:
        """
        Soft-delete a message. Only the sender can delete it.

        Returns True on success.
        """
        from chats.models import Message
        try:
            msg = Message.objects.get(
                pk=message_id,
                sender=self.user,
                conversation_id=self.conversation_id,
                is_deleted=False,
            )
            msg.soft_delete()
            return True
        except Message.DoesNotExist:
            return False

    # ── Utility ───────────────────────────────────────────────────────────────

    async def _send_error(self, message: str) -> None:
        """Send an error event back to the requesting connection only."""
        await self.send(text_data=json.dumps({
            'type':    'error',
            'message': message,
        }))