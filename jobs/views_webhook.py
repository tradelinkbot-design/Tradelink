"""
jobs/views_webhook.py
==============================
Flutterwave webhook handler.

Flutterwave sends POST events to /webhooks/flutterwave/.
The verif-hash header is compared against settings.FLW_SECRET_HASH
(a plain string token you configure in the Flutterwave dashboard).

Handled events:
  - charge.completed      → verify milestone payment
  - transfer.completed    → log success / mark milestone RELEASED
  - transfer.failed       → revert milestone to APPROVED, notify admin/worker

Security:
  - CSRF exempt (Flutterwave cannot send CSRF tokens)
  - Always returns HTTP 200 (Flutterwave retries on non-200)
  - Never logs raw webhook payloads or Flutterwave credentials
"""

import json
import logging

from django.conf import settings
from django.http import HttpResponse, HttpResponseNotAllowed
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name='dispatch')
class FlutterwaveWebhookView(View):
    """
    Receives and processes Flutterwave webhook events.

    POST /webhooks/flutterwave/
    """

    def post(self, request):
        """Handle incoming Flutterwave webhook POST."""
        # Flutterwave uses a simple secret hash comparison (not HMAC)
        received_hash = request.META.get('HTTP_VERIF_HASH', '')
        expected_hash = getattr(settings, 'FLW_SECRET_HASH', '')

        if not expected_hash or received_hash != expected_hash:
            logger.warning("FlutterwaveWebhookView: invalid verif-hash — request rejected.")
            return HttpResponse(status=400)

        # Parse the event
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            logger.warning("FlutterwaveWebhookView: malformed JSON payload.")
            return HttpResponse(status=200)

        event = data.get('event', '')
        event_data = data.get('data', {})

        logger.info("FlutterwaveWebhookView: received event '%s'.", event)

        try:
            if event == 'charge.completed':
                self._handle_charge_completed(event_data)

            elif event == 'transfer.completed':
                self._handle_transfer_completed(event_data)

            elif event == 'transfer.failed':
                self._handle_transfer_failure(event, event_data)

            else:
                logger.info("FlutterwaveWebhookView: unhandled event '%s' — ignoring.", event)

        except Exception:
            # Catch-all: log but always return 200 so Flutterwave doesn't keep retrying
            logger.exception(
                "FlutterwaveWebhookView: error processing event '%s'.", event,
            )

        # Always return 200
        return HttpResponse(status=200)

    def get(self, request):
        """Allow GET pings for webhook URL validation from Flutterwave dashboard."""
        return HttpResponse("Flutterwave webhook endpoint active.", status=200)

    # ── Event handlers ───────────────────────────────────────────────────────

    @staticmethod
    def _handle_charge_completed(event_data):
        """Process a successful charge (milestone funding or marketplace order)."""
        tx_ref = event_data.get('tx_ref', '')
        transaction_id = str(event_data.get('id', ''))
        status = event_data.get('status', '')

        if status not in ('successful', 'completed'):
            logger.info(
                "_handle_charge_completed: charge status='%s' for tx_ref=%s — ignoring.",
                status, tx_ref,
            )
            return

        if not tx_ref:
            logger.warning("_handle_charge_completed: no tx_ref in event data.")
            return

        # Route to the appropriate handler based on tx_ref prefix
        if tx_ref.startswith('mktplace_'):
            from marketplace.service.market_place_service_escrow import verify_order_payment
            result = verify_order_payment(tx_ref, transaction_id=transaction_id)
            logger.info(
                "_handle_charge_completed: verify_order_payment(tx_ref=%s) → %s",
                tx_ref, result,
            )
        else:
            from jobs.service.escrow_service import verify_milestone_payment
            result = verify_milestone_payment(tx_ref)
            logger.info(
                "_handle_charge_completed: verify_milestone_payment(tx_ref=%s) → %s",
                tx_ref, result,
            )

    @staticmethod
    def _handle_transfer_completed(event_data):
        """
        Finalises the milestone payout when Flutterwave confirms the transfer.
        Transfer ID is used as the lookup key (stored in paystack_transfer_ref field).
        """
        transfer_id = str(event_data.get('id', ''))
        transfer_status = (event_data.get('status') or '').lower()

        if not transfer_id:
            logger.warning("_handle_transfer_completed: no transfer id in event.")
            return

        if transfer_status != 'successful':
            logger.info(
                "_handle_transfer_completed: transfer %s status='%s' — not finalising.",
                transfer_id, transfer_status,
            )
            return

        from jobs.models import Milestone
        from jobs.service.escrow_service import mark_milestone_released

        try:
            milestone = Milestone.objects.select_related(
                'contract__worker__user',
                'contract__employer__user',
                'contract',
            ).get(paystack_transfer_ref=transfer_id)
        except Milestone.DoesNotExist:
            logger.info(
                "_handle_transfer_completed: no milestone with transfer_id %s — may be marketplace order.",
                transfer_id,
            )
            return

        # Only act if not already RELEASED
        if milestone.status == Milestone.Status.RELEASED:
            logger.info(
                "_handle_transfer_completed: milestone %s already RELEASED, skipping.",
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
            "_handle_transfer_completed: milestone %s marked RELEASED via webhook.",
            milestone.pk,
        )

    @staticmethod
    def _handle_transfer_failure(event, event_data):
        """
        Handle transfer.failed events.
        Reverts the milestone status to APPROVED and notifies admin + worker.
        """
        transfer_id = str(event_data.get('id', ''))
        reason = event_data.get('complete_message') or event_data.get('reason') or 'Unknown'

        logger.error(
            "_handle_transfer_failure: event=%s, transfer=%s, reason=%s",
            event, transfer_id, reason,
        )

        if not transfer_id:
            return

        from jobs.models import Milestone, Notification
        from django.contrib.auth import get_user_model
        User = get_user_model()

        try:
            milestone = Milestone.objects.select_related(
                'contract__worker__user',
                'contract__employer__user',
            ).get(paystack_transfer_ref=transfer_id)
        except Milestone.DoesNotExist:
            logger.warning(
                "_handle_transfer_failure: no milestone with transfer_id %s.",
                transfer_id,
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
                    f'Flutterwave transfer {transfer_id} failed for milestone '
                    f'"{milestone.title}" (Contract: {contract.title}). '
                    f'Status reverted to APPROVED for retry.'
                ),
                data={'milestone_id': str(milestone.pk), 'contract_id': str(contract.pk)},
            )

        logger.info(
            "_handle_transfer_failure: milestone %s reverted to APPROVED.",
            milestone.pk,
        )


# Backward-compat alias so any existing imports still resolve
PaystackWebhookView = FlutterwaveWebhookView
