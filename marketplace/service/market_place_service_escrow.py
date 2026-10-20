"""
marketplace/service/marketplace_escrow_service.py
==================================================
Flutterwave escrow logic for the TradeLink NG marketplace.

Mirrors the pattern in jobs/service/escrow_service.py but adapted for
product orders instead of job milestones.

Flow
────
  1. initialize_order_payment()  →  Flutterwave payment link for buyer
  2. verify_order_payment()      →  webhook confirms charge.completed
  3. buyer confirms receipt      →  confirm_order_receipt()
  4. release_order_to_seller()   →  Flutterwave Transfer API → seller bank
  5. 5% fee stays in platform balance

All money math uses Python Decimal — never float.
All Flutterwave API calls use 30-second timeouts and try/except.
"""

import logging
import uuid
from decimal import Decimal

import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

FLW_BASE = 'https://api.flutterwave.com/v3'


def _headers():
    return {
        'Authorization': f'Bearer {settings.FLW_SECRET_KEY}',
        'Content-Type':  'application/json',
    }


# ──────────────────────────────────────────────────────────────────────────────
#  INITIALIZE PAYMENT
# ──────────────────────────────────────────────────────────────────────────────

def initialize_order_payment(order_id: str, buyer_email: str) -> dict:
    """
    Calls Flutterwave Standard Payment API to generate a payment link
    for the buyer to pay for the order.

    Args:
        order_id:    UUID string of the Order.
        buyer_email: Email address of the buyer for Flutterwave.

    Returns:
        {'authorization_url': ..., 'reference': ...} on success.
        {'error': ...} on failure.
    """
    from marketplace.models import Order

    try:
        order = Order.objects.get(pk=order_id)
    except Order.DoesNotExist:
        return {'error': f'Order {order_id} not found.'}

    amount_ngn = float(order.agreed_price)  # Flutterwave uses Naira directly
    tx_ref = f'mktplace_{str(order.pk).replace("-", "")}'

    payload = {
        'tx_ref':       tx_ref,
        'amount':       amount_ngn,
        'currency':     'NGN',
        'redirect_url': settings.FLW_REDIRECT_URL,
        'customer': {
            'email': buyer_email,
        },
        'meta': {
            'order_id':   str(order.pk),
            'product_id': str(order.product_id),
            'type':       'marketplace_order',
        },
        'customizations': {
            'title':       'TradeLink Marketplace',
            'description': f'Payment for order #{str(order.pk)[:8]}',
        },
    }

    try:
        resp = requests.post(
            f'{FLW_BASE}/payments',
            json=payload,
            headers=_headers(),
            timeout=30,
        )
        data = resp.json()
    except requests.RequestException as exc:
        logger.exception("initialize_order_payment: request failed for order %s", order_id)
        return {'error': str(exc)}

    if data.get('status') != 'success':
        logger.error(
            "initialize_order_payment: Flutterwave error for order %s — %s",
            order_id, data.get('message'),
        )
        return {'error': data.get('message', 'Flutterwave error')}

    payment_link = data['data']['link']
    ref = tx_ref
    Order.objects.filter(pk=order_id).update(paystack_payment_ref=ref)

    return {
        'authorization_url': payment_link,
        'reference':         ref,
    }


# ──────────────────────────────────────────────────────────────────────────────
#  VERIFY PAYMENT (called by webhook charge.completed)
# ──────────────────────────────────────────────────────────────────────────────

def verify_order_payment(reference: str, transaction_id: str = None) -> bool:
    """
    Verifies a Flutterwave transaction and marks the order as PAID.

    Called by the Flutterwave webhook handler on charge.completed,
    or directly from the callback view with a transaction_id.

    Returns True if payment verified and order updated.
    """
    from marketplace.models import Order
    from jobs.models import Notification

    # Try to find the order
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

    # Verify with Flutterwave
    if transaction_id:
        # Use the numeric transaction ID from the callback for a direct verify
        try:
            resp = requests.get(
                f'{FLW_BASE}/transactions/{transaction_id}/verify',
                headers=_headers(),
                timeout=30,
            )
            data = resp.json()
        except requests.RequestException as exc:
            logger.exception("verify_order_payment: request failed for tx_id %s", transaction_id)
            return False

        if data.get('status') != 'success' or data.get('data', {}).get('status') not in ('successful', 'completed'):
            logger.warning(
                "verify_order_payment: transaction %s not successful — %s",
                transaction_id, data.get('message'),
            )
            return False
    else:
        # Use tx_ref lookup
        try:
            resp = requests.get(
                f'{FLW_BASE}/transactions',
                params={'tx_ref': reference},
                headers=_headers(),
                timeout=30,
            )
            data = resp.json()
        except requests.RequestException as exc:
            logger.exception("verify_order_payment: request failed for ref %s", reference)
            return False

        transactions = data.get('data', [])
        if not transactions or transactions[0].get('status') not in ('successful', 'completed'):
            logger.warning(
                "verify_order_payment: transaction %s not successful — %s",
                reference, data.get('message'),
            )
            return False

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
    Transfers the seller's payout via Flutterwave Transfer API.
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

    # Ensure seller has a bank account
    try:
        bank = order.seller.bank_account
    except WorkerBankAccount.DoesNotExist:
        logger.error(
            "release_order_to_seller: seller %s has no bank account.", order.seller_id
        )
        return False

    if not bank.account_number or not bank.bank_code:
        logger.error(
            "release_order_to_seller: seller %s bank account missing account_number or bank_code.",
            order.seller_id,
        )
        return False

    if not order.seller_payout_amount:
        order.compute_financials()
        order.save(update_fields=['platform_fee_amount', 'seller_payout_amount'])

    payout_ngn = float(order.seller_payout_amount)
    transfer_ref = f'mktplace_payout_{str(order.pk).replace("-", "")[:20]}'

    payload = {
        'account_bank':   bank.bank_code,
        'account_number': bank.account_number,
        'amount':         payout_ngn,
        'currency':       'NGN',
        'narration':      f'TradeLink Marketplace: {order.product.title[:60]}',
        'reference':      transfer_ref,
    }

    try:
        resp = requests.post(
            f'{FLW_BASE}/transfers',
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

    if data.get('status') not in ('success', 'pending'):
        err_msg = data.get('message', '')
        logger.error(
            "release_order_to_seller: Flutterwave transfer failed for order %s — %s",
            order_id, err_msg,
        )
        if "ip whitelisting" in str(err_msg).lower():
            try:
                current_ip = requests.get("https://api.ipify.org", timeout=5).text.strip()
                logger.error(
                    "release_order_to_seller: Your server's current public outbound IP is '%s'. "
                    "Ensure this exact IP is added under Flutterwave Dashboard -> Settings -> Whitelisted IP addresses (in Test Mode).",
                    current_ip
                )
            except Exception:
                pass
        return False

    flw_transfer_id = str(data.get('data', {}).get('id', '')) or transfer_ref
    now = timezone.now()

    order.paystack_transfer_ref = flw_transfer_id  # field reused for FLW transfer ID
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
    Refunds the full order amount to the buyer via Flutterwave Refund API.
    Marks order as REFUNDED.
    """
    from marketplace.models import Order, Product

    try:
        order = Order.objects.select_related('product').get(pk=order_id)
    except Order.DoesNotExist:
        logger.error("refund_order_to_buyer: order %s not found.", order_id)
        return False

    if order.paystack_payment_ref:
        # Look up Flutterwave transaction ID for the stored tx_ref
        try:
            lookup_resp = requests.get(
                f'{FLW_BASE}/transactions',
                params={'tx_ref': order.paystack_payment_ref},
                headers=_headers(),
                timeout=30,
            )
            lookup_data = lookup_resp.json()
            transactions = lookup_data.get('data', [])
            if transactions:
                flw_tx_id = transactions[0].get('id')
                payload = {"amount": float(order.agreed_price)}
                resp = requests.post(
                    f'{FLW_BASE}/transactions/{flw_tx_id}/refund',
                    json=payload,
                    headers=_headers(),
                    timeout=30,
                )
                data = resp.json()
                if data.get('status') != 'success':
                    logger.error(
                        "refund_order_to_buyer: Flutterwave refund failed: %s",
                        data.get('message'),
                    )
                    return False
            else:
                logger.warning(
                    "refund_order_to_buyer: no FLW transaction for ref %s — skipping refund API call.",
                    order.paystack_payment_ref,
                )
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
#  SPLIT ORDER (Automated Flutterwave Partial Payout)
# ──────────────────────────────────────────────────────────────────────────────

def split_order(order_id: str, seller_pct: int) -> bool:
    """
    Transfers seller_pct% of the net amount to the seller, and refunds
    (100 - seller_pct)% of the gross amount to the buyer via Flutterwave.
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
            if bank.account_number and bank.bank_code:
                transfer_ref = f'split_seller_{str(order.pk).replace("-", "")[:16]}'
                payload = {
                    'account_bank':   bank.bank_code,
                    'account_number': bank.account_number,
                    'amount':         float(seller_share),
                    'currency':       'NGN',
                    'narration':      f'Split Payout ({seller_pct}%): {order.product.title[:40]}',
                    'reference':      transfer_ref,
                }
                resp = requests.post(f'{FLW_BASE}/transfers', json=payload, headers=_headers(), timeout=30)
                data = resp.json()
                if data.get('status') not in ('success', 'pending'):
                    logger.error("split_order: Flutterwave transfer failed: %s", data.get('message'))
                    return False
        except Exception:
            logger.exception("split_order: failed transferring to seller %s", order.seller_id)
            return False

    # 2. Refund to buyer if > 0
    if buyer_refund > 0 and order.paystack_payment_ref:
        try:
            # Look up the Flutterwave transaction ID from the tx_ref
            lookup_resp = requests.get(
                f'{FLW_BASE}/transactions',
                params={'tx_ref': order.paystack_payment_ref},
                headers=_headers(),
                timeout=30,
            )
            lookup_data = lookup_resp.json()
            transactions = lookup_data.get('data', [])
            if transactions:
                flw_tx_id = transactions[0].get('id')
                refund_payload = {"amount": float(buyer_refund)}
                resp = requests.post(
                    f'{FLW_BASE}/transactions/{flw_tx_id}/refund',
                    json=refund_payload,
                    headers=_headers(),
                    timeout=30,
                )
                data = resp.json()
                if data.get("status") != "success":
                    logger.error("split_order: Flutterwave refund failed: %s", data.get("message"))
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
