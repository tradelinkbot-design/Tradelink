"""
chats/signals.py
=================
Django signal handlers for the TradeLink NG chat system.

Handlers
────────
  on_user_logout
      Marks the user as offline when they log out via the standard Django
      auth mechanism. Covers the case where the browser logs out without
      triggering a WebSocket disconnect (e.g. manual session termination).

  on_order_created
      When a new Order is saved for the first time, auto-creates (or finds)
      a Conversation between buyer and seller and injects a system message:
        "Order #XXXX placed — ₦{price} in escrow. Arrange handover here."
      This means the chat thread is always initialised when a deal is made,
      even if the buyer never clicked "Message Seller".

  on_order_status_changed
      Injects a system message into the existing conversation whenever the
      Order status changes to PAID, CONFIRMED, or COMPLETED so both parties
      see a clear audit trail inside the chat.
"""

import logging

from django.contrib.auth.signals import user_logged_out
from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
#  PRESENCE: mark offline on logout
# ──────────────────────────────────────────────────────────────────────────────

@receiver(user_logged_out)
def on_user_logout(sender, request, user, **kwargs):
    """Mark the user offline when they explicitly log out."""
    if user is None:
        return
    from chats.models import UserOnlineStatus
    try:
        UserOnlineStatus.objects.filter(user=user).update(is_online=False)
        logger.debug('chats.signals: user %s marked offline on logout.', user.pk)
    except Exception:
        logger.exception('chats.signals: failed to mark user %s offline.', user.pk)


# ──────────────────────────────────────────────────────────────────────────────
#  ORDER: auto-create chat + inject system messages
# ──────────────────────────────────────────────────────────────────────────────

@receiver(post_save, sender='marketplace.Order')
def on_order_save(sender, instance, created, update_fields, **kwargs):
    """
    React to Order lifecycle events by injecting system messages into chat.

    created=True  → start (or find) the conversation, post "Order placed" msg
    status=PAID   → "Payment received, arrange handover"
    status=CONFIRMED → "Buyer confirmed receipt, payout processing"
    status=COMPLETED → "Order complete"
    """
    from marketplace.models import Order

    if created:
        _ensure_order_conversation(instance)
        return

    # Status change events
    if update_fields and 'status' not in update_fields:
        return

    status_messages = {
        Order.Status.PAID: (
            f'✅ Payment of ₦{instance.agreed_price:,.0f} is now held in escrow. '
            f'Please arrange handover of "{instance.product.title}" here.'
        ),
        Order.Status.CONFIRMED: (
            f'🤝 Buyer confirmed receipt of "{instance.product.title}". '
            f'Payout of ₦{instance.seller_payout_amount or instance.agreed_price:,.0f} '
            f'is being processed.'
        ),
        Order.Status.COMPLETED: (
            f'🎉 Order complete. '
            f'₦{instance.seller_payout_amount or instance.agreed_price:,.0f} '
            f'has been transferred to the seller.'
        ),
        Order.Status.CANCELLED: (
            f'❌ Order for "{instance.product.title}" was cancelled.'
        ),
        Order.Status.DISPUTED: (
            f'⚠️ A dispute has been raised on this order. '
            f'Our team will review it and reach out within 24 hours.'
        ),
    }

    body = status_messages.get(instance.status)
    if body:
        _inject_system_message(instance, body)


def _ensure_order_conversation(order) -> None:
    """
    Find or create the buyer–seller conversation for this order.
    Injects the "Order placed" system message.
    """
    from chats.models import Conversation, Message

    try:
        buyer  = order.buyer
        seller = order.seller.user

        # Look for a conversation already linked to this order,
        # or the pre-existing product inquiry thread.
        conv = (
            Conversation.objects
            .filter(participants=buyer)
            .filter(participants=seller)
            .filter(product=order.product)
            .first()
        )

        if not conv:
            conv = Conversation.objects.create(
                product=order.product,
                order=order,
            )
            conv.participants.add(buyer, seller)
        else:
            # Upgrade the existing product inquiry thread to an order thread
            if not conv.order:
                Conversation.objects.filter(pk=conv.pk).update(order=order)

        Message.objects.create(
            conversation=conv,
            sender=None,   # system message has no sender
            body=(
                f'🛒 Order placed for "{order.product.title}" at '
                f'₦{order.agreed_price:,.0f}. '
                f'Awaiting payment — once paid, use this chat to arrange handover.'
            ),
            message_type='system',
        )

        from django.utils import timezone
        Conversation.objects.filter(pk=conv.pk).update(last_message_at=timezone.now())

        logger.info(
            'chats.signals: conversation %s initialised for order %s.',
            conv.pk, order.pk,
        )
    except Exception:
        logger.exception(
            'chats.signals: failed to initialise conversation for order %s.', order.pk
        )


def _inject_system_message(order, body: str) -> None:
    """Post a system message into the conversation linked to this order."""
    from chats.models import Conversation, Message
    from django.utils import timezone

    try:
        conv = (
            Conversation.objects
            .filter(participants=order.buyer)
            .filter(participants=order.seller.user)
            .filter(product=order.product)
            .first()
        )
        if not conv:
            logger.warning(
                'chats.signals: no conversation found for order %s to inject status msg.',
                order.pk,
            )
            return

        Message.objects.create(
            conversation=conv,
            sender=None,
            body=body,
            message_type='system',
        )
        Conversation.objects.filter(pk=conv.pk).update(last_message_at=timezone.now())

    except Exception:
        logger.exception(
            'chats.signals: failed to inject system message for order %s.', order.pk
        )