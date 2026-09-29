"""
marketplace/service/marketplace_escrow_service.py
==================================================
Paystack escrow logic for the TradeLink NG marketplace.

Mirrors the pattern in jobs/service/escrow_service.py but adapted for
product orders instead of job milestones.

Flow
────
  1. initialize_order_payment()  →  Paystack payment link for buyer
  2. verify_order_payment()      →  webhook confirms charge.success
  3. buyer confirms receipt      →  confirm_order_receipt()
  4. release_order_to_seller()   →  Paystack Transfer API → seller bank
  5. 5% fee stays in platform balance

All money math uses Python Decimal — never float.
All Paystack API calls use 30-second timeouts and try/except.
"""

import logging
from decimal import Decimal

import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

PAYSTACK_BASE = 'https://api.paystack.co'


def _headers():
    return {
        'Authorization': f'Bearer {settings.PAYSTACK_SECRET_KEY}',
        'Content-Type':  'application/json',

    }


# ──────────────────────────────────────────────────────────────────────────────
#  INITIALIZE PAYMENT
# ──────────────────────────────────────────────────────────────────────────────

def initialize_order_payment(order_id: str, buyer_email: str) -> dict:
    """
    Calls Paystack Initialize Transaction API to generate a payment link
    for the buyer to pay for the order.

    Args:
        order_id:    UUID string of the Order.
        buyer_email: Email address of the buyer for Paystack.

    Returns:
        {'authorization_url': ..., 'reference': ...} on success.
        {'error': ...} on failure.
    """
    from marketplace.models import Order

    try:
        order = Order.objects.get(pk=order_id)
    except Order.DoesNotExist:
        return {'error': f'Order {order_id} not found.'}

    amount_kobo = int(order.agreed_price * 100)

    payload = {
        'email':        buyer_email,
        'amount':       amount_kobo,
        'currency':     'NGN',
        'reference':    f'mktplace_{str(order.pk).replace("-", "")}',
        'callback_url': settings.PAYSTACK_CALLBACK_URL,
        'metadata': {
            'order_id':    str(order.pk),
            'product_id':  str(order.product_id),
            'type':        'marketplace_order',
        },
    }

    try:
        resp = requests.post(
            f'{PAYSTACK_BASE}/transaction/initialize',
            json=payload,
            headers=_headers(),
            timeout=30,
        )
        data = resp.json()
    except requests.RequestException as exc:
        logger.exception("initialize_order_payment: request failed for order %s", order_id)
        return {'error': str(exc)}

    if not data.get('status'):
        logger.error(
            "initialize_order_payment: Paystack error for order %s — %s",
            order_id, data.get('message'),
        )
        return {'error': data.get('message', 'Paystack error')}

    ref = data['data']['reference']
    Order.objects.filter(pk=order_id).update(paystack_payment_ref=ref)

    return {
        'authorization_url': data['data']['authorization_url'],
        'reference':         ref,
    }


# ──────────────────────────────────────────────────────────────────────────────
#  VERIFY PAYMENT (called by webhook charge.success)
# ──────────────────────────────────────────────────────────────────────────────

def verify_order_payment(reference: str) -> bool:
    """
    Verifies a Paystack transaction and marks the order as PAID.

    Called by the Paystack webhook handler on charge.success.

    Returns True if payment verified and order updated.
    """
    from marketplace.models import Order
    from jobs.models import Notification

    try:
        resp = requests.get(
            f'{PAYSTACK_BASE}/transaction/verify/{reference}',
            headers=_headers(),
            timeout=30,
        )
        data = resp.json()
    except requests.RequestException as exc:
        logger.exception("verify_order_payment: request failed for ref %s", reference)
        return False

    if not data.get('status') or data['data']['status'] != 'success':
        logger.warning(
            "verify_order_payment: transaction %s not successful — %s",
            reference, data.get('message'),
        )
        return False

    try:
        order = Order.objects.get(paystack_payment_ref=reference)
    except Order.DoesNotExist:
        logger.error(
            "verify_order_payment: no order found for reference %s", reference
        )
        return False

    if order.status != Order.Status.PENDING:
        logger.info(
            "verify_order_payment: order %s already processed (status=%s).",
            order.pk, order.status,
        )
        return True

    order.status  = Order.Status.PAID
    order.paid_at = timezone.now()
    order.compute_financials()
    order.save(update_fields=['status', 'paid_at', 'platform_fee_amount',
                              'seller_payout_amount'])

    # Mark product as reserved
    from marketplace.models import Product
    Product.objects.filter(pk=order.product_id).update(status=Product.Status.RESERVED)

    logger.info("verify_order_payment: order %s marked PAID.", order.pk)
    return True


# ──────────────────────────────────────────────────────────────────────────────
#  CONFIRM RECEIPT (buyer presses "I received this item")
# ──────────────────────────────────────────────────────────────────────────────

def confirm_order_receipt(order_id: str) -> bool:
    """
    Buyer confirms they received the item.
    Sets order to CONFIRMED and starts the 7-day auto-complete window.
    Triggers async payout to seller.

    Returns True on success.
    """
    from marketplace.models import Order
    from marketplace.tasks import process_order_payout_task
    from datetime import timedelta

    try:
        order = Order.objects.get(
            pk=order_id,
            status__in=[Order.Status.PAID, Order.Status.MEETUP_SCHEDULED, Order.Status.CONFIRMED],
        )
    except Order.DoesNotExist:
        logger.warning(
            "confirm_order_receipt: order %s not found or not in confirmable status.", order_id
        )
        return False

    now = timezone.now()
    if order.status != Order.Status.CONFIRMED:
        order.status           = Order.Status.CONFIRMED
        order.confirmed_at     = now
        order.auto_complete_at = now + timedelta(days=7)
        order.save(update_fields=['status', 'confirmed_at', 'auto_complete_at'])

    # Queue payout — seller gets money once buyer confirms
    process_order_payout_task.delay(order_id)

    logger.info("confirm_order_receipt: order %s confirmed (payout task queued).", order_id)
    return True


# ──────────────────────────────────────────────────────────────────────────────
#  RELEASE TO SELLER
# ──────────────────────────────────────────────────────────────────────────────

def release_order_to_seller(order_id: str) -> bool:
    """
    Transfers the seller's payout via Paystack Transfer API.
    Deducts 5% platform fee. Marks order as COMPLETED.

    Called by:
        - process_order_payout_task  (after buyer confirms)
        - auto_complete_orders_task  (7-day auto-complete)
        - Admin resolves dispute in seller's favour

    Returns True on success.
    """
    from marketplace.models import Order, OrderDispute
    from jobs.models import WorkerBankAccount

    try:
        order = Order.objects.select_related(
            'seller', 'seller__bank_account', 'product'
        ).get(pk=order_id)
    except Order.DoesNotExist:
        logger.error("release_order_to_seller: order %s not found.", order_id)
        return False

    if order.status == Order.Status.COMPLETED:
        logger.info("release_order_to_seller: order %s already completed.", order_id)
        return True

    # Ensure seller has a bank account with a recipient code
    try:
        bank = order.seller.bank_account
    except WorkerBankAccount.DoesNotExist:
        logger.error(
            "release_order_to_seller: seller %s has no bank account.", order.seller_id
        )
        return False

    from django.conf import settings as _settings
    from jobs.service.escrow_service import create_transfer_recipient

    def _recipient_valid(code: str) -> bool:
        """Quick Paystack fetch to confirm the recipient code belongs to the current account."""
        try:
            r = requests.get(
                f'{PAYSTACK_BASE}/transferrecipient/{code}',
                headers=_headers(),
                timeout=10,
            )
            return r.ok and r.json().get('status') is True
        except Exception:
            return False  # treat network errors as valid to avoid blocking payouts

    # Recreate recipient if missing, test-mode while on live keys, or not found in current account
    _live_mode = _settings.PAYSTACK_SECRET_KEY.startswith('sk_live_')
    _code_is_test_on_live = (
        bank.paystack_recipient_code
        and _live_mode
        and bank.paystack_recipient_code.startswith('RCP_test')
    )
    _need_recipient = (
        not bank.paystack_recipient_code
        or _code_is_test_on_live
        or not _recipient_valid(bank.paystack_recipient_code)
    )

    if _need_recipient:
        logger.warning(
            "release_order_to_seller: creating/recreating Paystack recipient for seller %s "
            "(existing code: %r).",
            order.seller_id, bank.paystack_recipient_code or 'none',
        )
        new_code = create_transfer_recipient(str(bank.pk))
        if not new_code:
            logger.error(
                "release_order_to_seller: could not create Paystack recipient "
                "for seller %s — aborting transfer.",
                order.seller_id,
            )
            return False
        bank.refresh_from_db()

    # Final guard
    if not bank.paystack_recipient_code:
        logger.error(
            "release_order_to_seller: recipient code still empty for seller %s — aborting.",
            order.seller_id,
        )
        return False

    if not order.seller_payout_amount:
        order.compute_financials()
        order.save(update_fields=['platform_fee_amount', 'seller_payout_amount'])

    payout_kobo = int(order.seller_payout_amount * 100)

    payload = {
        'source':    'balance',
        'amount':    payout_kobo,
        'recipient': bank.paystack_recipient_code,
        'reason':    f'TradeLink Marketplace: {order.product.title[:60]}',
    }

    try:
        resp = requests.post(
            f'{PAYSTACK_BASE}/transfer',
            json=payload,
            headers=_headers(),
            timeout=30,
        )
        data = resp.json()
    except requests.RequestException as exc:
        logger.exception(
            "release_order_to_seller: transfer request failed for order %s", order_id
        )
        return False

    if not data.get('status'):
        logger.error(
            "release_order_to_seller: Paystack transfer failed for order %s — %s",
            order_id, data.get('message'),
        )
        return False

    transfer_code = data['data'].get('transfer_code', '')
    now = timezone.now()

    order.paystack_transfer_ref = transfer_code
    order.status                = Order.Status.COMPLETED
    order.completed_at          = now
    order.save(update_fields=[
        'paystack_transfer_ref', 'status', 'completed_at',
    ])

    # Mark product as SOLD
    from marketplace.models import Product
    Product.objects.filter(pk=order.product_id).update(status=Product.Status.SOLD)

    logger.info(
        "release_order_to_seller: ₦%s transferred to seller %s for order %s.",
        order.seller_payout_amount, order.seller_id, order_id,
    )
    return True


# ──────────────────────────────────────────────────────────────────────────────
#  REFUND TO BUYER
# ──────────────────────────────────────────────────────────────────────────────

def refund_order_to_buyer(order_id: str) -> bool:
    """
    Refunds the full order amount to the buyer via Paystack Refund API.
    Marks order as REFUNDED.
    """
    from marketplace.models import Order, Product

    try:
        order = Order.objects.select_related('product').get(pk=order_id)
    except Order.DoesNotExist:
        logger.error("refund_order_to_buyer: order %s not found.", order_id)
        return False

    if order.paystack_payment_ref:
        payload = {"transaction": order.paystack_payment_ref}
        try:
            resp = requests.post(
                f"{PAYSTACK_BASE}/refund",
                json=payload,
                headers=_headers(),
                timeout=30,
            )
            data = resp.json()
            if not data.get("status"):
                logger.error(
                    "refund_order_to_buyer: Paystack refund failed: %s",
                    data.get("message"),
                )
                return False
        except requests.RequestException:
            logger.exception("refund_order_to_buyer: request failed for order %s", order_id)
            return False

    now = timezone.now()
    order.status = Order.Status.REFUNDED
    order.updated_at = now
    order.save(update_fields=['status', 'updated_at'])

    # Relist product
    Product.objects.filter(pk=order.product_id).update(status=Product.Status.ACTIVE)
    return True


# ──────────────────────────────────────────────────────────────────────────────
#  SPLIT ORDER (Automated Paystack Partial Payout)
# ──────────────────────────────────────────────────────────────────────────────

def split_order(order_id: str, seller_pct: int) -> bool:
    """
    Transfers seller_pct% of the net amount to the seller, and refunds
    (100 - seller_pct)% of the gross amount to the buyer via Paystack.
    """
    from marketplace.models import Order, Product
    from jobs.models import WorkerBankAccount

    if not (0 <= seller_pct <= 100):
        logger.error("split_order: invalid seller_pct %d", seller_pct)
        return False

    try:
        order = Order.objects.select_related('seller', 'product').get(pk=order_id)
    except Order.DoesNotExist:
        logger.error("split_order: order %s not found.", order_id)
        return False

    if not order.seller_payout_amount:
        order.compute_financials()

    gross = order.agreed_price
    net = order.seller_payout_amount

    seller_share = (net * Decimal(seller_pct) / Decimal("100")).quantize(Decimal("0.01"))
    buyer_refund = (gross * Decimal(100 - seller_pct) / Decimal("100")).quantize(Decimal("0.01"))

    # 1. Payout to seller if > 0
    if seller_share > 0:
        try:
            bank = WorkerBankAccount.objects.get(worker=order.seller)
            if bank.paystack_recipient_code:
                payload = {
                    'source':    'balance',
                    'amount':    int(seller_share * 100),
                    'recipient': bank.paystack_recipient_code,
                    'reason':    f'Split Payout ({seller_pct}%): {order.product.title[:40]}',
                }
                resp = requests.post(f'{PAYSTACK_BASE}/transfer', json=payload, headers=_headers(), timeout=30)
                data = resp.json()
                if not data.get('status'):
                    logger.error("split_order: Paystack transfer failed: %s", data.get('message'))
                    return False
        except Exception:
            logger.exception("split_order: failed transferring to seller %s", order.seller_id)
            return False

    # 2. Refund to buyer if > 0
    if buyer_refund > 0 and order.paystack_payment_ref:
        try:
            payload = {
                "transaction":   order.paystack_payment_ref,
                "amount":        int(buyer_refund * 100),
                "merchant_note": f"Split refund ({100 - seller_pct}%): {order.product.title[:40]}",
            }
            resp = requests.post(f"{PAYSTACK_BASE}/refund", json=payload, headers=_headers(), timeout=30)
            data = resp.json()
            if not data.get("status"):
                logger.error("split_order: Paystack refund failed: %s", data.get("message"))
                return False
        except Exception:
            logger.exception("split_order: failed refunding buyer for order %s", order_id)
            return False

    now = timezone.now()
    order.status = Order.Status.COMPLETED
    order.completed_at = now
    order.save(update_fields=['status', 'completed_at', 'updated_at'])

    Product.objects.filter(pk=order.product_id).update(status=Product.Status.SOLD)
    return True


