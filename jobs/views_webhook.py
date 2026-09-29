"""
marketplace/views_webhook.py
==============================
Paystack webhook handler.

Paystack sends POST events to /webhooks/paystack/.
The X-Paystack-Signature header is verified using HMAC SHA512 of the
raw body with settings.PAYSTACK_SECRET_KEY.

Handled events:
  - charge.success      → verify milestone payment
  - transfer.success    → log success
  - transfer.failed     → revert milestone to APPROVED, notify admin/worker
  - transfer.reversed   → same as transfer.failed

Security:
  - CSRF exempt (Paystack cannot send CSRF tokens)
  - Always returns HTTP 200 (Paystack retries on non-200)
  - Never logs raw webhook payloads or Paystack credentials
"""

import hashlib
import hmac
import json
import logging

from django.conf import settings
from django.http import HttpResponse, HttpResponseNotAllowed
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name='dispatch')
class PaystackWebhookView(View):
    """
    Receives and processes Paystack webhook events.

    POST /webhooks/paystack/
    """

    def post(self, request):
        """Handle incoming Paystack webhook POST."""
        payload = request.body
        signature = request.META.get('HTTP_X_PAYSTACK_SIGNATURE', '')

        # Verify HMAC signature
        secret = settings.PAYSTACK_WEBHOOK_SECRET
        expected = hmac.new(
            secret.encode('utf-8'),
            payload,
            hashlib.sha512,
        ).hexdigest()

        if not hmac.compare_digest(expected, signature):
            logger.warning("PaystackWebhookView: invalid signature — request rejected.")
            return HttpResponse(status=400)

        # Parse the event
        try:
            data = json.loads(payload)
        except (json.JSONDecodeError, ValueError):
            logger.warning("PaystackWebhookView: malformed JSON payload.")
            return HttpResponse(status=200)

        event = data.get('event', '')
        event_data = data.get('data', {})

        logger.info("PaystackWebhookView: received event '%s'.", event)

        try:
            if event == 'charge.success':
                self._handle_charge_success(event_data)

            elif event == 'transfer.success':
                self._handle_transfer_success(event_data)

            elif event in ('transfer.failed', 'transfer.reversed'):
                self._handle_transfer_failure(event, event_data)

            else:
                logger.info("PaystackWebhookView: unhandled event '%s' — ignoring.", event)

        except Exception:
            # Catch-all: log the error but still return 200 so Paystack
            # doesn't keep retrying an event we can't process.
            logger.exception(
                "PaystackWebhookView: error processing event '%s'.", event,
            )

        # Always return 200
        return HttpResponse(status=200)

    def get(self, request):
        """Webhooks only accept POST."""
        return HttpResponseNotAllowed(['POST'])

    # ── Event handlers ───────────────────────────────────────────────────────

    @staticmethod
    def _handle_charge_success(event_data):
        """Process a successful charge (milestone funding)."""
        reference = event_data.get('reference')
        if not reference:
            logger.warning("_handle_charge_success: no reference in event data.")
            return

        from jobs.service.escrow_service import verify_milestone_payment
        result = verify_milestone_payment(reference)
        logger.info(
            "_handle_charge_success: verify_milestone_payment(ref=%s) → %s",
            reference, result,
        )

    @staticmethod
    def _handle_transfer_success(event_data):
        """
        Finalises the milestone payout when Paystack confirms the transfer.
        This fires for both:
          - Immediate transfers (OTP disabled on Paystack account)
          - OTP-approved transfers (OTP enabled — webhook fires after OTP accepted)
        """
        transfer_code = event_data.get('transfer_code', '')
        if not transfer_code:
            logger.warning("_handle_transfer_success: no transfer_code in event.")
            return

        from jobs.models import Milestone
        from jobs.service.escrow_service import mark_milestone_released

        try:
            milestone = Milestone.objects.select_related(
                'contract__worker__user',
                'contract__employer__user',
                'contract',
            ).get(paystack_transfer_ref=transfer_code)
        except Milestone.DoesNotExist:
            logger.warning(
                "_handle_transfer_success: no milestone with transfer_ref %s.",
                transfer_code,
            )
            return

        # Only act if not already RELEASED
        if milestone.status == Milestone.Status.RELEASED:
            logger.info(
                "_handle_transfer_success: milestone %s already RELEASED, skipping.",
                milestone.pk,
            )
            return

        # Mark RELEASED and fire notifications
        milestone.status = Milestone.Status.RELEASED
        fields_to_update = ['status', 'updated_at']
        if not milestone.worker_amount:
            from decimal import Decimal
            contract = milestone.contract
            fee_pct = Decimal(str(contract.platform_fee_pct or 10.00))
            milestone.worker_amount = (milestone.amount * (Decimal("1") - fee_pct / Decimal("100"))).quantize(Decimal("0.01"))
            fields_to_update.append('worker_amount')
        milestone.save(update_fields=fields_to_update)
        mark_milestone_released(milestone)

        logger.info(
            "_handle_transfer_success: milestone %s marked RELEASED via webhook.",
            milestone.pk,
        )

    @staticmethod
    def _handle_transfer_failure(event, event_data):
        """
        Handle transfer.failed and transfer.reversed events.
        Reverts the milestone status to APPROVED and notifies admin + worker.
        """
        transfer_code = event_data.get('transfer_code', '')
        reason = event_data.get('reason', 'Unknown')

        logger.error(
            "_handle_transfer_failure: event=%s, transfer=%s, reason=%s",
            event, transfer_code, reason,
        )

        if not transfer_code:
            return

        from jobs.models import Milestone, Notification
        from django.contrib.auth import get_user_model
        User = get_user_model()

        try:
            milestone = Milestone.objects.select_related(
                'contract__worker__user',
                'contract__employer__user',
            ).get(paystack_transfer_ref=transfer_code)
        except Milestone.DoesNotExist:
            logger.warning(
                "_handle_transfer_failure: no milestone with transfer_ref %s.",
                transfer_code,
            )
            return

        # Revert to APPROVED so payout can be retried
        milestone.status = Milestone.Status.APPROVED
        milestone.paystack_transfer_ref = None
        milestone.worker_amount = None
        milestone.save(update_fields=[
            'status', 'paystack_transfer_ref', 'worker_amount', 'updated_at',
        ])

        contract = milestone.contract

        # Notify worker
        Notification.objects.create(
            user=contract.worker.user,
            notif_type=Notification.NotifType.ESCROW_RELEASED,
            title=f'Payout failed: "{milestone.title}"',
            body=(
                f'The payout for "{milestone.title}" could not be completed. '
                f'Our team has been notified and will retry shortly.'
            ),
            data={'milestone_id': str(milestone.pk), 'contract_id': str(contract.pk)},
        )

        # Notify admins
        admin_users = User.objects.filter(is_staff=True)
        for admin_user in admin_users:
            Notification.objects.create(
                user=admin_user,
                notif_type=Notification.NotifType.SYSTEM,
                title=f'[ADMIN] Transfer failed: {milestone.title}',
                body=(
                    f'Paystack transfer {transfer_code} failed for milestone '
                    f'"{milestone.title}" (Contract: {contract.title}). '
                    f'Status reverted to APPROVED for retry.'
                ),
                data={'milestone_id': str(milestone.pk), 'contract_id': str(contract.pk)},
            )

        logger.info(
            "_handle_transfer_failure: milestone %s reverted to APPROVED.",
            milestone.pk,
        )
