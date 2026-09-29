"""
marketplace/service/escrow_service.py
=====================================
Business-logic layer for the milestone-based escrow payment system.

All Paystack API interactions are encapsulated here so that views and
tasks only call high-level functions.  Each function handles its own
exceptions and logs errors via Python's logging module.

Required in settings.py:
    PAYSTACK_SECRET_KEY = env('PAYSTACK_SECRET_KEY')
    PAYSTACK_PUBLIC_KEY = env('PAYSTACK_PUBLIC_KEY')
    PAYSTACK_CALLBACK_URL = env('PAYSTACK_CALLBACK_URL')  # e.g. https://tradelink.ng/escrow/paystack/callback/
    PAYSTACK_WEBHOOK_SECRET = env('PAYSTACK_SECRET_KEY')  # same key used for webhook HMAC
"""

import hashlib
import logging
import uuid
from datetime import timedelta
from decimal import Decimal

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone

from jobs.models import (
    Contract,
    Dispute,
    DisputeMessage,
    Milestone,
    Notification,
    WorkerBankAccount,
)

logger = logging.getLogger(__name__)

User = get_user_model()

PAYSTACK_BASE    = "https://api.paystack.co"
PAYSTACK_TIMEOUT = 30  # seconds

# ── Dispute policy constants ──────────────────────────────────────────────────
DISPUTE_WINDOW_DAYS     = 14    # max days after funding a dispute can be raised
MIN_DISPUTE_AGE_HOURS   = 24    # minimum hours after funding before a dispute is allowed
MEDIATION_WINDOW_DAYS   = 5     # days both parties have to self-resolve
SLA_ESCALATE_HOURS      = 72    # hours before admin is notified of stale dispute
SLA_AUTO_RELEASE_DAYS   = 7     # days before funds auto-release to worker
ABUSE_DISPUTE_THRESHOLD = 0.40  # loss rate above this → flag account
ABUSE_MIN_DISPUTES      = 3     # minimum disputes before abuse flag applies

ALLOWED_EVIDENCE_MIME = frozenset({
    'image/jpeg', 'image/png', 'image/webp',
    'video/mp4', 'application/pdf',
})


# ──────────────────────────────────────────────────────────────────────────────
#  INTERNAL HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def _paystack_headers() -> dict:
    """Return the standard Paystack authorization headers."""
    key = getattr(settings, 'PAYSTACK_SECRET_KEY', '') or ''
    return {
        "Authorization": f"Bearer {key.strip()}",
        "Content-Type": "application/json",
    }


def _safe_json(resp: requests.Response) -> dict:
    """Safely extracts JSON from a requests.Response object without raising JSONDecodeError."""
    if resp is None:
        return {}
    try:
        if not resp.text or not resp.text.strip():
            return {}
        return resp.json()
    except Exception:
        return {}


def _notify(user, notif_type, title, body, data=None):
    """Shortcut to create a Notification."""
    Notification.objects.create(
        user=user,
        notif_type=notif_type,
        title=title,
        body=body,
        data=data or {},
    )


def _hash_file(f) -> str:
    """Return SHA-256 hex digest of an uploaded file without consuming it permanently."""
    sha = hashlib.sha256()
    for chunk in f.chunks():
        sha.update(chunk)
    f.seek(0)
    return sha.hexdigest()


def _validate_evidence_mime(f) -> None:
    """
    Raise ValidationError if the uploaded file's MIME type is not in the
    ALLOWED_EVIDENCE_MIME whitelist.  Reads the first 2 KB for detection.
    Falls back gracefully if python-magic is not installed.
    """
    try:
        import magic as _magic
        header = f.read(2048)
        f.seek(0)
        mime = _magic.from_buffer(header, mime=True)
        if mime not in ALLOWED_EVIDENCE_MIME:
            raise ValidationError(
                f"File type '{mime}' is not accepted as evidence. "
                f"Please upload a JPEG, PNG, WebP, MP4, or PDF."
            )
    except ImportError:
        pass  # python-magic not installed — skip MIME check (log a warning)


def _update_dispute_flag(profile) -> None:
    """
    Auto-flag a WorkerProfile or EmployerProfile if their dispute loss rate
    exceeds ABUSE_DISPUTE_THRESHOLD with at least ABUSE_MIN_DISPUTES raised.
    """
    if profile.disputes_raised >= ABUSE_MIN_DISPUTES:
        loss_rate = profile.disputes_lost / profile.disputes_raised
        if loss_rate >= ABUSE_DISPUTE_THRESHOLD and not profile.dispute_flagged:
            profile.dispute_flagged = True
            profile.save(update_fields=['dispute_flagged'])


# ──────────────────────────────────────────────────────────────────────────────
#  1. INITIALIZE MILESTONE PAYMENT
# ──────────────────────────────────────────────────────────────────────────────

def initialize_milestone_payment(milestone_id: str, employer_email: str) -> dict:
    """
    Calls Paystack Initialize Transaction API to generate a payment link
    for the employer to fund a milestone.

    - Amount is milestone.amount * 100 (Paystack uses kobo)
    - Metadata: milestone_id, contract_id, type='milestone_funding'
    - callback_url: settings.PAYSTACK_CALLBACK_URL
    - Saves the Paystack reference to milestone.paystack_payment_ref
    - Returns {'authorization_url': ..., 'reference': ...}
    """
    try:
        milestone = Milestone.objects.select_related("contract").get(pk=milestone_id)
    except Milestone.DoesNotExist:
        logger.error("initialize_milestone_payment: Milestone %s not found.", milestone_id)
        return {}

    amount_kobo = int(milestone.amount * 100)
    reference = f"tl_ms_{uuid.uuid4().hex[:24]}"

    payload = {
        "email": employer_email,
        "amount": amount_kobo,
        "reference": reference,
        "callback_url": settings.PAYSTACK_CALLBACK_URL,
        "metadata": {
            "milestone_id": str(milestone.pk),
            "contract_id": str(milestone.contract.pk),
            "type": "milestone_funding",
        },
    }

    try:
        resp = requests.post(
            f"{PAYSTACK_BASE}/transaction/initialize",
            json=payload,
            headers=_paystack_headers(),
            timeout=PAYSTACK_TIMEOUT,
        )
    except requests.RequestException:
        logger.exception("initialize_milestone_payment: network request failed for %s", milestone_id)
        return {}

    data = _safe_json(resp)

    if resp.ok and data.get("status"):
        authorization_url = data.get("data", {}).get("authorization_url")
        ref = data.get("data", {}).get("reference")

        if authorization_url and ref:
            milestone.paystack_payment_ref = ref
            milestone.save(update_fields=["paystack_payment_ref", "updated_at"])

            logger.info(
                "initialize_milestone_payment: ref=%s for milestone %s",
                ref, milestone_id,
            )
            return {"authorization_url": authorization_url, "reference": ref}

    logger.error(
        "initialize_milestone_payment: Paystack error for %s (HTTP %s): %s",
        milestone_id, resp.status_code, data.get("message") or resp.text[:200],
    )
    return {}


# ──────────────────────────────────────────────────────────────────────────────
#  2. VERIFY MILESTONE PAYMENT
# ──────────────────────────────────────────────────────────────────────────────

def verify_milestone_payment(reference: str) -> bool:
    """
    Calls Paystack Verify Transaction API with the reference.
    If status == 'success' and amount matches milestone.amount:
      - Sets milestone.status = FUNDED
      - Sets milestone.funded_at = now()
      - Creates notifications for the worker and employer.
    Returns True if verified successfully.
    """
    try:
        milestone = Milestone.objects.select_related(
            "contract__employer__user",
            "contract__worker__user",
        ).get(paystack_payment_ref=reference)
    except Milestone.DoesNotExist:
        logger.error("verify_milestone_payment: no milestone with ref %s", reference)
        return False

    try:
        resp = requests.get(
            f"{PAYSTACK_BASE}/transaction/verify/{reference}",
            headers=_paystack_headers(),
            timeout=PAYSTACK_TIMEOUT,
        )
    except requests.RequestException:
        logger.exception("verify_milestone_payment: network request failed for ref %s", reference)
        return False

    data = _safe_json(resp)

    if not resp.ok or not data.get("status"):
        logger.error(
            "verify_milestone_payment: Paystack error for %s (HTTP %s): %s",
            reference, resp.status_code, data.get("message") or resp.text[:200],
        )
        return False

    txn = data.get("data") or {}
    if txn.get("status") != "success":
        logger.warning("verify_milestone_payment: txn status=%s for %s", txn.get("status"), reference)
        return False

    # Verify amount matches (Paystack returns amount in kobo)
    expected_kobo = int(milestone.amount * 100)
    if txn.get("amount") != expected_kobo:
        logger.error(
            "verify_milestone_payment: amount mismatch for %s — expected %d, got %s",
            reference, expected_kobo, txn.get("amount"),
        )
        return False

    # Update milestone
    now = timezone.now()
    milestone.status = Milestone.Status.FUNDED
    milestone.funded_at = now
    milestone.save(update_fields=["status", "funded_at", "updated_at"])

    # Activate contract if still pending
    contract = milestone.contract
    if contract.status == Contract.Status.PENDING:
        contract.status = Contract.Status.ACTIVE
        contract.save(update_fields=["status", "updated_at"])

    # Notify worker
    _notify(
        user=contract.worker.user,
        notif_type=Notification.NotifType.ESCROW_FUNDED,
        title=f'Milestone "{milestone.title}" has been funded',
        body=f'Milestone "{milestone.title}" has been funded. You can now begin work.',
        data={"milestone_id": str(milestone.pk), "contract_id": str(contract.pk)},
    )
    # Notify employer
    _notify(
        user=contract.employer.user,
        notif_type=Notification.NotifType.ESCROW_FUNDED,
        title=f'Payment secured in escrow',
        body=f'Your payment of \u20a6{milestone.amount:,.2f} for "{milestone.title}" is secured in escrow.',
        data={"milestone_id": str(milestone.pk), "contract_id": str(contract.pk)},
    )

    logger.info("verify_milestone_payment: milestone %s funded successfully.", milestone.pk)
    return True


# ──────────────────────────────────────────────────────────────────────────────
#  3. SUBMIT MILESTONE WORK
# ──────────────────────────────────────────────────────────────────────────────

def submit_milestone_work(milestone_id: str, submission_note: str) -> bool:
    """
    Called when worker clicks 'Submit Work'.
    - Validates milestone.status == FUNDED
    - Sets milestone.status = IN_REVIEW
    - Sets milestone.submitted_at = now()
    - Sets milestone.auto_release_at = now() + timedelta(days=7)
    - Creates a Notification for the employer.
    Returns True on success.
    """
    try:
        milestone = Milestone.objects.select_related(
            "contract__employer__user",
        ).get(pk=milestone_id)
    except Milestone.DoesNotExist:
        logger.error("submit_milestone_work: Milestone %s not found.", milestone_id)
        return False

    if milestone.status != Milestone.Status.FUNDED:
        logger.warning(
            "submit_milestone_work: milestone %s has status %s, expected FUNDED.",
            milestone_id, milestone.status,
        )
        return False

    now = timezone.now()
    milestone.status = Milestone.Status.IN_REVIEW
    milestone.submitted_at = now
    milestone.auto_release_at = now + timedelta(days=7)
    milestone.submission_note = submission_note
    milestone.save(update_fields=[
        "status", "submitted_at", "auto_release_at", "submission_note", "updated_at",
    ])

    _notify(
        user=milestone.contract.employer.user,
        notif_type=Notification.NotifType.ESCROW_SUBMITTED,
        title=f'Work submitted: "{milestone.title}"',
        body=(
            f'Work has been submitted for "{milestone.title}". '
            f'Review and approve within 7 days or payment will be released automatically.'
        ),
        data={"milestone_id": str(milestone.pk), "contract_id": str(milestone.contract.pk)},
    )

    logger.info("submit_milestone_work: milestone %s submitted for review.", milestone_id)
    return True


# ──────────────────────────────────────────────────────────────────────────────
#  4. APPROVE MILESTONE
# ──────────────────────────────────────────────────────────────────────────────

def approve_milestone(milestone_id: str) -> bool:
    """
    Called when employer clicks 'Approve Work'.
    - Validates milestone.status == IN_REVIEW or DISPUTED
    - Sets milestone.status = APPROVED
    - Sets milestone.approved_at = now()
    - Calls release_milestone_to_worker(milestone_id)
    Returns True on success.
    """
    try:
        milestone = Milestone.objects.get(pk=milestone_id)
    except Milestone.DoesNotExist:
        logger.error("approve_milestone: Milestone %s not found.", milestone_id)
        return False

    if milestone.status not in (Milestone.Status.IN_REVIEW, Milestone.Status.DISPUTED):
        logger.warning(
            "approve_milestone: milestone %s has status %s, expected IN_REVIEW or DISPUTED.",
            milestone_id, milestone.status,
        )
        return False

    milestone.status = Milestone.Status.APPROVED
    milestone.approved_at = timezone.now()
    milestone.save(update_fields=["status", "approved_at", "updated_at"])

    logger.info("approve_milestone: milestone %s approved, triggering payout.", milestone_id)
    return release_milestone_to_worker(milestone_id)


# ──────────────────────────────────────────────────────────────────────────────
#  5. RELEASE MILESTONE TO WORKER  (core payout)
# ──────────────────────────────────────────────────────────────────────────────

def release_milestone_to_worker(milestone_id: str) -> bool:
    """
    The core payout function. Called by approve_milestone() and the auto_release
    Celery task.

    Flow:
      1. Validates worker has a WorkerBankAccount with a paystack_recipient_code.
         If not, creates one first via create_transfer_recipient().
      2. Deducts the platform fee (contract.platform_fee_pct, default 10%):
             worker_amount = milestone.amount × (1 − fee_pct / 100)
      3. Calls Paystack POST /transfer.
      4. Paystack may respond with inner status "otp" or "pending" (OTP required)
         OR "success" (OTP disabled on the account).
         - OTP required  → sets milestone.status = PENDING_OTP, saves transfer_code,
                           notifies admin to approve the transfer on the Paystack
                           dashboard or via the OTP finalization endpoint.
         - Success       → calls mark_milestone_released() to set RELEASED and notify.
      Returns True if the transfer was initiated (otp/pending/success), False on error.
    """
    try:
        milestone = Milestone.objects.select_related(
            "contract__employer__user",
            "contract__worker__user",
            "contract__worker",
        ).get(pk=milestone_id)
    except Milestone.DoesNotExist:
        logger.error("release_milestone_to_worker: Milestone %s not found.", milestone_id)
        return False

    contract = milestone.contract
    worker_profile = contract.worker

    # Get or validate bank account
    try:
        bank_account = WorkerBankAccount.objects.get(worker=worker_profile)
    except WorkerBankAccount.DoesNotExist:
        logger.error(
            "release_milestone_to_worker: worker %s has no bank account.",
            worker_profile.pk,
        )
        return False

    from django.conf import settings as _settings

    def _recipient_valid(code: str) -> bool:
        """Quick Paystack fetch to confirm the recipient code belongs to the current account."""
        try:
            r = requests.get(
                f"{PAYSTACK_BASE}/transferrecipient/{code}",
                headers=_paystack_headers(),
                timeout=10,
            )
            return r.ok and r.json().get("status") is True
        except Exception:
            return False  # treat network errors as valid to avoid blocking payouts

    # Recreate recipient if missing, test-mode while on live keys, or not found in current account
    _live_mode = _settings.PAYSTACK_SECRET_KEY.startswith("sk_live_")
    _code_is_test_on_live = (
        bank_account.paystack_recipient_code
        and _live_mode
        and bank_account.paystack_recipient_code.startswith("RCP_test")
    )
    _need_recipient = (
        not bank_account.paystack_recipient_code
        or _code_is_test_on_live
        or not _recipient_valid(bank_account.paystack_recipient_code)
    )

    if _need_recipient:
        logger.warning(
            "release_milestone_to_worker: creating/recreating Paystack recipient for worker %s "
            "(existing code: %r).",
            worker_profile.pk, bank_account.paystack_recipient_code or "none",
        )
        recipient_code = create_transfer_recipient(str(bank_account.pk))
        if not recipient_code:
            logger.error(
                "release_milestone_to_worker: failed to create/recreate recipient for %s.",
                bank_account.pk,
            )
            return False
        bank_account.refresh_from_db()

    # ── Compute worker amount after platform fee deduction ─────────────────────
    fee_pct = Decimal(str(contract.platform_fee_pct))          # ensure Decimal
    worker_amount = milestone.amount * (Decimal("1") - fee_pct / Decimal("100"))
    worker_amount = worker_amount.quantize(Decimal("0.01"))
    worker_amount_kobo = int(worker_amount * 100)
    platform_fee = milestone.amount - worker_amount

    logger.info(
        "release_milestone_to_worker: milestone=%s gross=₦%s fee_pct=%s%% "
        "platform_fee=₦%s worker_amount=₦%s",
        milestone_id, milestone.amount, fee_pct, platform_fee, worker_amount,
    )

    # ── Initiate Paystack transfer ─────────────────────────────────────────────
    payload = {
        "source": "balance",
        "amount": worker_amount_kobo,
        "recipient": bank_account.paystack_recipient_code,
        "reason": f"TradeLink payout: {milestone.title}",
    }

    try:
        resp = requests.post(
            f"{PAYSTACK_BASE}/transfer",
            json=payload,
            headers=_paystack_headers(),
            timeout=PAYSTACK_TIMEOUT,
        )
    except requests.RequestException:
        logger.exception("release_milestone_to_worker: transfer request failed for milestone %s", milestone_id)
        return False

    data = _safe_json(resp)

    if not resp.ok or not data.get("status"):
        logger.error(
            "release_milestone_to_worker: Paystack transfer failed for milestone %s (HTTP %s): %s",
            milestone_id, resp.status_code, data.get("message") or resp.text[:200],
        )
        return False

    transfer_data = data.get("data", {})
    transfer_status = transfer_data.get("status", "").lower()
    transfer_code = transfer_data.get("transfer_code", "")

    # Always save transfer_code and worker_amount immediately
    milestone.paystack_transfer_ref = transfer_code
    milestone.worker_amount = worker_amount

    if transfer_status in ("success", "pending", "processing", "received"):
        # ── Automatic transfer initiated — no OTP required ───────────────
        # Paystack has accepted and queued/executed the transfer directly to the bank.
        milestone.status = Milestone.Status.RELEASED
        milestone.save(update_fields=[
            "paystack_transfer_ref", "worker_amount", "status", "updated_at",
        ])
        mark_milestone_released(milestone)
        logger.info(
            "release_milestone_to_worker: automatic transfer %s completed (status=%s) — milestone %s marked RELEASED.",
            transfer_code, transfer_status, milestone_id,
        )
        return True

    elif transfer_status == "otp":
        # ── Paystack requires OTP / dashboard approval ─────────────────
        # Only fires if OTP requirement is still active on the Paystack dashboard.
        milestone.status = Milestone.Status.PENDING_OTP
        milestone.save(update_fields=[
            "paystack_transfer_ref", "worker_amount", "status", "updated_at",
        ])

        # Notify admins to approve the OTP or disable OTP in Paystack settings
        User = get_user_model()
        admin_users = User.objects.filter(is_staff=True)
        for admin_user in admin_users:
            _notify(
                user=admin_user,
                notif_type=Notification.NotifType.SYSTEM,
                title=f"[ACTION REQUIRED] Approve Transfer OTP: {milestone.title}",
                body=(
                    f"A transfer of ₦{worker_amount:,.2f} for milestone "
                    f'"{milestone.title}" is awaiting OTP confirmation on Paystack. '
                    f"Transfer code: {transfer_code}. "
                    f"To make transfers 100% automatic, disable OTP in Paystack Dashboard preferences or via 'python manage.py disable_paystack_otp'."
                ),
                data={
                    "milestone_id": str(milestone.pk),
                    "transfer_code": transfer_code,
                    "contract_id": str(contract.pk),
                },
            )

        # Notify worker that payout is pending
        _notify(
            user=contract.worker.user,
            notif_type=Notification.NotifType.ESCROW_RELEASED,
            title=f'Payout initiated: ₦{worker_amount:,.2f}',
            body=(
                f'Your payout of ₦{worker_amount:,.2f} for "{milestone.title}" '
                f'has been initiated and is being processed by Paystack. '
                f'You will be notified once the funds arrive in your account.'
            ),
            data={"milestone_id": str(milestone.pk), "contract_id": str(contract.pk)},
        )

        logger.info(
            "release_milestone_to_worker: milestone %s PENDING_OTP — "
            "transfer_code=%s, worker_amount=₦%s.",
            milestone_id, transfer_code, worker_amount,
        )
        return True

    else:
        logger.error(
            "release_milestone_to_worker: unexpected transfer status '%s' for %s.",
            transfer_status, milestone_id,
        )
        return False


def mark_milestone_released(milestone) -> None:
    """
    Called after a transfer is confirmed (either immediately when OTP is
    disabled, or via the transfer.success webhook).
    Marks contract completed if all milestones are done and fires notifications.
    """
    contract = milestone.contract

    # Check if all milestones are released → mark contract completed
    all_released = not contract.milestones.exclude(
        status__in=[Milestone.Status.RELEASED, Milestone.Status.REFUNDED],
    ).exists()
    if all_released:
        contract.status = Contract.Status.COMPLETED
        contract.save(update_fields=["status", "updated_at"])

    worker_amount = milestone.worker_amount or Decimal("0")

    # Notify worker
    _notify(
        user=contract.worker.user,
        notif_type=Notification.NotifType.ESCROW_RELEASED,
        title=f'Payment sent: ₦{worker_amount:,.2f}',
        body=(
            f'Payment of ₦{worker_amount:,.2f} for "{milestone.title}" '
            f'has been sent to your bank account.'
        ),
        data={"milestone_id": str(milestone.pk), "contract_id": str(contract.pk)},
    )
    # Notify employer
    _notify(
        user=contract.employer.user,
        notif_type=Notification.NotifType.ESCROW_RELEASED,
        title=f'Milestone complete: "{milestone.title}"',
        body=(
            f'Milestone "{milestone.title}" is complete. '
            f'₦{worker_amount:,.2f} paid to worker ({contract.platform_fee_pct or 10}% platform fee deducted).'
        ),
        data={"milestone_id": str(milestone.pk), "contract_id": str(contract.pk)},
    )

    logger.info(
        "mark_milestone_released: milestone %s released — ₦%s to worker.",
        milestone.pk, worker_amount,
    )


def finalize_transfer_with_otp(milestone_id: str, otp: str) -> bool:
    """
    Calls Paystack POST /transfer/finalize_transfer with the OTP entered by
    the account owner to confirm a pending transfer.

    This is used when OTP is enabled on the Paystack account.  After the OTP
    is accepted, Paystack sends a transfer.success webhook which triggers
    mark_milestone_released() via the webhook handler.

    Returns True if Paystack accepted the OTP.
    """
    try:
        milestone = Milestone.objects.select_related(
            "contract__worker__user",
            "contract__employer__user",
        ).get(pk=milestone_id)
    except Milestone.DoesNotExist:
        logger.error("finalize_transfer_with_otp: Milestone %s not found.", milestone_id)
        return False

    if milestone.status != Milestone.Status.PENDING_OTP:
        logger.warning(
            "finalize_transfer_with_otp: milestone %s has status %s, expected PENDING_OTP.",
            milestone_id, milestone.status,
        )
        return False

    if not milestone.paystack_transfer_ref:
        logger.error(
            "finalize_transfer_with_otp: milestone %s has no transfer_code.", milestone_id,
        )
        return False

    payload = {
        "transfer_code": milestone.paystack_transfer_ref,
        "otp": otp,
    }

    try:
        resp = requests.post(
            f"{PAYSTACK_BASE}/transfer/finalize_transfer",
            json=payload,
            headers=_paystack_headers(),
            timeout=PAYSTACK_TIMEOUT,
        )
    except requests.RequestException:
        logger.exception(
            "finalize_transfer_with_otp: request failed for milestone %s", milestone_id,
        )
        return False

    data = _safe_json(resp)

    if not resp.ok or not data.get("status"):
        logger.error(
            "finalize_transfer_with_otp: Paystack rejected OTP for milestone %s (HTTP %s): %s",
            milestone_id, resp.status_code, data.get("message") or resp.text[:200],
        )
        return False

    logger.info(
        "finalize_transfer_with_otp: OTP accepted for milestone %s, "
        "transfer_code=%s. Marking as released.",
        milestone_id, milestone.paystack_transfer_ref,
    )
    milestone.status = Milestone.Status.RELEASED
    milestone.save(update_fields=["status", "updated_at"])
    mark_milestone_released(milestone)
    return True


def sync_pending_transfers(contract) -> None:
    """
    Checks the status of any PENDING_OTP milestones on a contract by directly
    querying the Paystack API. This acts as a fallback for missed webhooks,
    especially useful in local development environments.
    """
    pending_milestones = contract.milestones.filter(status=Milestone.Status.PENDING_OTP)
    for milestone in pending_milestones:
        if not milestone.paystack_transfer_ref:
            continue

        try:
            resp = requests.get(
                f"{PAYSTACK_BASE}/transfer/{milestone.paystack_transfer_ref}",
                headers=_paystack_headers(),
                timeout=PAYSTACK_TIMEOUT,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status"):
                    transfer_status = data["data"].get("status", "").lower()
                    if transfer_status in ("success", "pending", "processing", "received"):
                        # Transfer completed successfully!
                        milestone.status = Milestone.Status.RELEASED
                        if not milestone.worker_amount:
                            fee_pct = Decimal(str(contract.platform_fee_pct or 10.00))
                            milestone.worker_amount = (milestone.amount * (Decimal("1") - fee_pct / Decimal("100"))).quantize(Decimal("0.01"))
                        milestone.save(update_fields=["status", "worker_amount", "updated_at"])
                        mark_milestone_released(milestone)
                        logger.info("sync_pending_transfers: synced milestone %s to RELEASED.", milestone.pk)
                    elif transfer_status in ("failed", "reversed", "abandoned"):
                        # Revert so it can be retried
                        milestone.status = Milestone.Status.APPROVED
                        milestone.paystack_transfer_ref = None
                        milestone.worker_amount = None
                        milestone.save(update_fields=[
                            'status', 'paystack_transfer_ref', 'worker_amount', 'updated_at',
                        ])
                        logger.warning("sync_pending_transfers: transfer %s failed on Paystack. Reverted milestone %s.", milestone.paystack_transfer_ref, milestone.pk)

        except requests.RequestException:
            logger.exception("sync_pending_transfers: failed to sync milestone %s", milestone.pk)
            pass


# ──────────────────────────────────────────────────────────────────────────────
#  PAYSTACK TRANSFER OTP MANAGEMENT (Enable / Disable OTP for transfers)
# ──────────────────────────────────────────────────────────────────────────────

def request_disable_transfer_otp() -> dict:
    """
    Calls Paystack POST /transfer/disable_otp.
    Paystack generates an OTP and sends it to the account owner's mobile/email.
    To complete the process, submit the OTP via finalize_disable_transfer_otp().
    """
    try:
        resp = requests.post(
            f"{PAYSTACK_BASE}/transfer/disable_otp",
            json={},
            headers=_paystack_headers(),
            timeout=PAYSTACK_TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.exception("request_disable_transfer_otp failed: %s", exc)
        return {"status": False, "message": str(exc)}

    data = _safe_json(resp)
    logger.info("request_disable_transfer_otp: response=%s", data)
    return data if data else {"status": False, "message": f"Invalid response (HTTP {resp.status_code})"}


def finalize_disable_transfer_otp(otp: str) -> dict:
    """
    Calls Paystack POST /transfer/disable_otp_finalize with the OTP received.
    Once successful, all future transfers from this Paystack secret key will be 100% automated without OTP.
    """
    try:
        resp = requests.post(
            f"{PAYSTACK_BASE}/transfer/disable_otp_finalize",
            json={"otp": otp.strip()},
            headers=_paystack_headers(),
            timeout=PAYSTACK_TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.exception("finalize_disable_transfer_otp failed: %s", exc)
        return {"status": False, "message": str(exc)}

    data = _safe_json(resp)
    logger.info("finalize_disable_transfer_otp: response=%s", data)
    return data if data else {"status": False, "message": f"Invalid response (HTTP {resp.status_code})"}


def enable_transfer_otp() -> dict:
    """
    Calls Paystack POST /transfer/enable_otp to re-enable OTP requirement if needed.
    """
    try:
        resp = requests.post(
            f"{PAYSTACK_BASE}/transfer/enable_otp",
            json={},
            headers=_paystack_headers(),
            timeout=PAYSTACK_TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.exception("enable_transfer_otp failed: %s", exc)
        return {"status": False, "message": str(exc)}

    data = _safe_json(resp)
    logger.info("enable_transfer_otp: response=%s", data)
    return data if data else {"status": False, "message": f"Invalid response (HTTP {resp.status_code})"}


# ──────────────────────────────────────────────────────────────────────────────
#  6. CREATE TRANSFER RECIPIENT
# ──────────────────────────────────────────────────────────────────────────────

def create_transfer_recipient(worker_bank_account_id: str) -> str:
    """
    Calls Paystack Create Transfer Recipient API.
    - POST https://api.paystack.co/transferrecipient
    - Saves recipient_code to WorkerBankAccount.paystack_recipient_code
    Returns recipient_code, or empty string on failure.
    """
    try:
        bank_account = WorkerBankAccount.objects.get(pk=worker_bank_account_id)
    except WorkerBankAccount.DoesNotExist:
        logger.error(
            "create_transfer_recipient: WorkerBankAccount %s not found.",
            worker_bank_account_id,
        )
        return ""

    payload = {
        "type": "nuban",
        "name": bank_account.account_name,
        "account_number": bank_account.account_number,
        "bank_code": bank_account.bank_code,
        "currency": "NGN",
    }

    try:
        resp = requests.post(
            f"{PAYSTACK_BASE}/transferrecipient",
            json=payload,
            headers=_paystack_headers(),
            timeout=PAYSTACK_TIMEOUT,
        )
    except requests.RequestException:
        logger.exception(
            "create_transfer_recipient: request failed for %s",
            worker_bank_account_id,
        )
        return ""

    data = _safe_json(resp)

    if not resp.ok or not data.get("status"):
        logger.error(
            "create_transfer_recipient: Paystack returned status=false: %s (HTTP %s)",
            data.get("message") or resp.text[:200], resp.status_code,
        )
        return ""

    recipient_code = data.get("data", {}).get("recipient_code", "")
    if not recipient_code:
        return ""

    bank_account.paystack_recipient_code = recipient_code
    bank_account.is_verified = True
    bank_account.save(update_fields=[
        "paystack_recipient_code", "is_verified", "updated_at",
    ])

    logger.info(
        "create_transfer_recipient: recipient %s created for bank account %s.",
        recipient_code, worker_bank_account_id,
    )
    return recipient_code


# ──────────────────────────────────────────────────────────────────────────────
#  7. RAISE DISPUTE
# ──────────────────────────────────────────────────────────────────────────────

def raise_dispute(
    milestone_id: str,
    raised_by_user_id: int,
    reason: str,
    evidence=None,
) -> tuple[bool, str]:
    """
    Raise a dispute on a funded or in-review milestone.

    Checks (in order):
      1. Milestone exists and belongs to the caller's contract
      2. Milestone is in FUNDED or IN_REVIEW status
      3. Minimum escrow age (24h) — too soon to dispute
      4. Dispute window (14 days) — too late to dispute
      5. No existing dispute on this milestone
      6. Evidence MIME whitelist (if file provided)

    Side effects on success:
      - Hashes evidence file (SHA-256) for tamper-detection
      - Creates Dispute with mediation_deadline (+5 days) and auto_release_at (+7 days)
      - Sets milestone.status = DISPUTED and contract.status = DISPUTED
      - Increments raiser's disputes_raised counter; checks abuse flag
      - Notifies both parties and all staff users

    Returns (True, '') on success or (False, reason_str) on failure.
    """
    try:
        milestone = Milestone.objects.select_related(
            "contract__employer__user",
            "contract__employer",
            "contract__worker__user",
            "contract__worker",
        ).get(pk=milestone_id)
    except Milestone.DoesNotExist:
        logger.error("raise_dispute: Milestone %s not found.", milestone_id)
        return False, "milestone_not_found"

    valid_statuses = (Milestone.Status.IN_REVIEW, Milestone.Status.FUNDED)
    if milestone.status not in valid_statuses:
        logger.warning(
            "raise_dispute: milestone %s has status %s — not disputable.",
            milestone_id, milestone.status,
        )
        return False, "invalid_milestone_status"

    # ── 24h minimum age ─────────────────────────────────────────────────────
    if milestone.funded_at:
        age_hours = (timezone.now() - milestone.funded_at).total_seconds() / 3600
        if age_hours < MIN_DISPUTE_AGE_HOURS:
            logger.warning(
                "raise_dispute: milestone %s funded only %.1fh ago (min %dh).",
                milestone_id, age_hours, MIN_DISPUTE_AGE_HOURS,
            )
            return False, "too_soon"

    # ── 14-day window ────────────────────────────────────────────────────────
    if milestone.funded_at:
        age_days = (timezone.now() - milestone.funded_at).days
        if age_days > DISPUTE_WINDOW_DAYS:
            logger.warning(
                "raise_dispute: dispute window expired for milestone %s (%d days old).",
                milestone_id, age_days,
            )
            return False, "dispute_window_expired"

    # ── No duplicate dispute ─────────────────────────────────────────────────
    if Dispute.objects.filter(milestone_id=milestone_id).exists():
        logger.warning("raise_dispute: duplicate dispute attempt on milestone %s.", milestone_id)
        return False, "dispute_already_exists"

    try:
        raised_by = User.objects.get(pk=raised_by_user_id)
    except User.DoesNotExist:
        logger.error("raise_dispute: User %s not found.", raised_by_user_id)
        return False, "user_not_found"

    # ── MIME validation + SHA-256 hash ───────────────────────────────────────
    evidence_sha256 = ""
    if evidence:
        try:
            _validate_evidence_mime(evidence)
        except ValidationError as exc:
            logger.warning("raise_dispute: invalid evidence MIME — %s", exc)
            return False, str(exc)
        evidence_sha256 = _hash_file(evidence)

    # ── Create the dispute ───────────────────────────────────────────────────
    now = timezone.now()
    dispute = Dispute.objects.create(
        milestone=milestone,
        raised_by=raised_by,
        reason=reason,
        evidence=evidence,
        evidence_sha256=evidence_sha256,
        mediation_deadline=now + timedelta(days=MEDIATION_WINDOW_DAYS),
        auto_release_at=now + timedelta(days=SLA_AUTO_RELEASE_DAYS),
    )

    milestone.status = Milestone.Status.DISPUTED
    milestone.save(update_fields=["status", "updated_at"])

    contract = milestone.contract
    contract.status = Contract.Status.DISPUTED
    contract.save(update_fields=["status", "updated_at"])

    # ── Increment raiser's dispute counter & check abuse flag ────────────────
    raiser_profile = getattr(raised_by, 'worker_profile', None) or getattr(raised_by, 'employer_profile', None)
    if raiser_profile:
        raiser_profile.disputes_raised = raiser_profile.disputes_raised + 1
        raiser_profile.save(update_fields=['disputes_raised'])
        _update_dispute_flag(raiser_profile)

    # ── Notify both parties ──────────────────────────────────────────────────
    mediation_msg = (
        f'You have {MEDIATION_WINDOW_DAYS} days to resolve this by agreement '
        f'before our admin team steps in. Use the dispute thread to share evidence.'
    )
    for user in [contract.employer.user, contract.worker.user]:
        _notify(
            user=user,
            notif_type=Notification.NotifType.ESCROW_DISPUTE,
            title=f'Dispute raised: "{milestone.title}"',
            body=(
                f'A dispute has been raised on milestone "{milestone.title}" '
                f'by {raised_by.get_full_name() or raised_by.username}. '
                f'Funds are locked until resolution. {mediation_msg}'
            ),
            data={
                "milestone_id": str(milestone.pk),
                "dispute_id":   str(dispute.pk),
                "contract_id":  str(contract.pk),
            },
        )

    # ── Notify admins (available after mediation window) ─────────────────────
    for admin_user in User.objects.filter(is_staff=True):
        _notify(
            user=admin_user,
            notif_type=Notification.NotifType.ESCROW_DISPUTE,
            title='[ADMIN] New dispute — mediation in progress',
            body=(
                f'Dispute raised on "{milestone.title}" '
                f'(Contract: {contract.title}) by {raised_by.username}. '
                f'Mediation window closes {dispute.mediation_deadline:%d %b %Y %H:%M}. '
                f'Reason: {reason[:200]}'
            ),
            data={
                "milestone_id": str(milestone.pk),
                "dispute_id":   str(dispute.pk),
                "contract_id":  str(contract.pk),
            },
        )

    logger.info(
        "raise_dispute: dispute %s created for milestone %s by user %s.",
        dispute.pk, milestone_id, raised_by_user_id,
    )
    return True, ""


# ──────────────────────────────────────────────────────────────────────────────
#  8. RESOLVE DISPUTE
# ──────────────────────────────────────────────────────────────────────────────

def resolve_dispute(
    dispute_id: str,
    resolution: str,
    resolved_by_user_id: int,
    resolution_note: str = "",
) -> bool:
    """
    Admin-only. resolution is one of: RELEASED_TO_WORKER, REFUNDED_TO_EMPLOYER.
    - If RELEASED_TO_WORKER: calls release_milestone_to_worker()
    - If REFUNDED_TO_EMPLOYER: calls Paystack refund API, sets milestone.status = REFUNDED
    - Sets dispute.resolution, dispute.resolved_at, dispute.resolved_by
    - Notifies both parties of outcome
    Returns True on success.
    """
    try:
        dispute = Dispute.objects.select_related(
            "milestone__contract__employer__user",
            "milestone__contract__worker__user",
        ).get(pk=dispute_id)
    except Dispute.DoesNotExist:
        logger.error("resolve_dispute: Dispute %s not found.", dispute_id)
        return False

    try:
        resolved_by = User.objects.get(pk=resolved_by_user_id)
    except User.DoesNotExist:
        logger.error("resolve_dispute: User %s not found.", resolved_by_user_id)
        return False

    milestone = dispute.milestone
    contract = milestone.contract

    if resolution == Dispute.Resolution.RELEASED_TO_WORKER:
        success = release_milestone_to_worker(str(milestone.pk))
        if not success:
            logger.error(
                "resolve_dispute: failed to release milestone %s to worker.",
                milestone.pk,
            )
            return False

    elif resolution == Dispute.Resolution.REFUNDED_TO_EMPLOYER:
        # Call Paystack refund API
        if milestone.paystack_payment_ref:
            payload = {
                "transaction": milestone.paystack_payment_ref,
            }
            try:
                resp = requests.post(
                    f"{PAYSTACK_BASE}/refund",
                    json=payload,
                    headers=_paystack_headers(),
                    timeout=PAYSTACK_TIMEOUT,
                )
            except requests.RequestException:
                logger.exception(
                    "resolve_dispute: refund request failed for milestone %s",
                    milestone.pk,
                )
                return False

            data = _safe_json(resp)

            if not resp.ok or not data.get("status"):
                logger.error(
                    "resolve_dispute: Paystack refund failed for milestone %s (HTTP %s): %s",
                    milestone.pk, resp.status_code, data.get("message") or resp.text[:200],
                )
                return False


        milestone.status = Milestone.Status.REFUNDED
        milestone.save(update_fields=["status", "updated_at"])

    elif resolution == Dispute.Resolution.SPLIT:
        # Handled by split_milestone() — caller must pass split_worker_pct
        pass

    else:
        logger.error("resolve_dispute: unsupported resolution '%s'.", resolution)
        return False

    # Update dispute
    dispute.resolution = resolution
    dispute.resolution_note = resolution_note
    dispute.resolved_at = timezone.now()
    dispute.resolved_by = resolved_by
    dispute.save(update_fields=[
        "resolution", "resolution_note", "resolved_at", "resolved_by",
    ])

    # ── Update disputes_lost on the losing party ─────────────────────────────
    contract = milestone.contract
    if resolution == Dispute.Resolution.RELEASED_TO_WORKER:
        # Employer lost (they disputed, worker won) — or worker is vindicated
        loser = contract.employer
    elif resolution == Dispute.Resolution.REFUNDED_TO_EMPLOYER:
        # Worker lost
        loser = contract.worker
    else:
        loser = None

    if loser:
        loser.disputes_lost = loser.disputes_lost + 1
        loser.save(update_fields=['disputes_lost'])
        _update_dispute_flag(loser)

    # Revert contract status if no more disputed milestones
    has_disputed = contract.milestones.filter(status=Milestone.Status.DISPUTED).exists()
    if not has_disputed and contract.status == Contract.Status.DISPUTED:
        contract.status = Contract.Status.ACTIVE
        contract.save(update_fields=["status", "updated_at"])

    # Notify both parties
    resolution_label = dict(Dispute.Resolution.choices).get(resolution, resolution)
    for user in [contract.employer.user, contract.worker.user]:
        _notify(
            user=user,
            notif_type=Notification.NotifType.ESCROW_DISPUTE,
            title=f'Dispute resolved: "{milestone.title}"',
            body=(
                f'The dispute on "{milestone.title}" has been resolved: '
                f'{resolution_label}. {resolution_note}'.strip()
            ),
            data={
                "milestone_id": str(milestone.pk),
                "dispute_id":   str(dispute.pk),
                "contract_id":  str(contract.pk),
            },
        )

    logger.info(
        "resolve_dispute: dispute %s resolved as %s by user %s.",
        dispute_id, resolution, resolved_by_user_id,
    )
    return True


# ──────────────────────────────────────────────────────────────────────────────
#  9. SPLIT MILESTONE  (automated Paystack partial payout)
# ──────────────────────────────────────────────────────────────────────────────

def split_milestone(
    dispute_id: str,
    worker_pct: int,
    resolved_by_user_id: int,
    resolution_note: str = "",
) -> bool:
    """
    Execute a SPLIT resolution: worker receives worker_pct% of the net amount;
    employer is refunded (100-worker_pct)% of the gross amount via Paystack.

    Steps:
      1. Compute worker_amount = (milestone.amount * worker_pct / 100) less platform fee
      2. Transfer worker_amount to worker's Paystack recipient
      3. Refund (milestone.amount * (100-worker_pct) / 100) to employer via Paystack refund
      4. Update dispute and milestone records
    """
    if not (0 <= worker_pct <= 100):
        logger.error("split_milestone: worker_pct %d out of range.", worker_pct)
        return False

    try:
        dispute = Dispute.objects.select_related(
            "milestone__contract__employer__user",
            "milestone__contract__worker__user",
            "milestone__contract",
        ).get(pk=dispute_id)
    except Dispute.DoesNotExist:
        logger.error("split_milestone: Dispute %s not found.", dispute_id)
        return False

    try:
        resolved_by = User.objects.get(pk=resolved_by_user_id)
    except User.DoesNotExist:
        logger.error("split_milestone: User %s not found.", resolved_by_user_id)
        return False

    milestone = dispute.milestone
    contract  = milestone.contract

    gross         = milestone.amount                       # total in escrow
    platform_fee  = gross * (contract.platform_fee_pct / Decimal("100"))
    net           = gross - platform_fee                   # what worker could get at 100%

    worker_share  = (net * Decimal(worker_pct) / Decimal("100")).quantize(Decimal("0.01"))
    refund_share  = (gross * Decimal(100 - worker_pct) / Decimal("100")).quantize(Decimal("0.01"))

    # ── Transfer worker's share ──────────────────────────────────────────────
    if worker_share > 0:
        try:
            bank_account = WorkerBankAccount.objects.get(worker=contract.worker)
        except WorkerBankAccount.DoesNotExist:
            logger.error("split_milestone: no bank account for worker %s.", contract.worker.pk)
            return False

        transfer_ref = f"SPLIT-{dispute_id[:8]}-W"
        transfer_payload = {
            "source":    "balance",
            "amount":    int(worker_share * 100),  # Paystack uses kobo
            "recipient": bank_account.paystack_recipient_code,
            "reason":    f"Split payout — {milestone.title} ({worker_pct}%)",
            "reference": transfer_ref,
        }
        try:
            resp = requests.post(
                f"{PAYSTACK_BASE}/transfer",
                json=transfer_payload,
                headers=_paystack_headers(),
                timeout=PAYSTACK_TIMEOUT,
            )
        except requests.RequestException:
            logger.exception("split_milestone: transfer request failed for dispute %s", dispute_id)
            return False

        transfer_data = _safe_json(resp)
        if not resp.ok or not transfer_data.get("status"):
            logger.error(
                "split_milestone: transfer failed for dispute %s (HTTP %s): %s",
                dispute_id, resp.status_code, transfer_data.get("message") or resp.text[:200],
            )
            return False

    # ── Refund employer's share ──────────────────────────────────────────────
    if refund_share > 0 and milestone.paystack_payment_ref:
        refund_payload = {
            "transaction":  milestone.paystack_payment_ref,
            "amount":       int(refund_share * 100),  # partial refund in kobo
            "merchant_note": f"Split refund — {milestone.title} ({100-worker_pct}%)",
        }
        try:
            resp = requests.post(
                f"{PAYSTACK_BASE}/refund",
                json=refund_payload,
                headers=_paystack_headers(),
                timeout=PAYSTACK_TIMEOUT,
            )
        except requests.RequestException:
            logger.exception("split_milestone: refund request failed for dispute %s", dispute_id)
            return False

        refund_data = _safe_json(resp)
        if not resp.ok or not refund_data.get("status"):
            logger.error(
                "split_milestone: refund failed for dispute %s (HTTP %s): %s",
                dispute_id, resp.status_code, refund_data.get("message") or resp.text[:200],
            )
            return False

    # ── Update records ───────────────────────────────────────────────────────
    now = timezone.now()
    milestone.worker_amount = worker_share
    milestone.status        = Milestone.Status.RELEASED
    milestone.approved_at   = now
    milestone.save(update_fields=["worker_amount", "status", "approved_at", "updated_at"])

    dispute.resolution       = Dispute.Resolution.SPLIT
    dispute.split_worker_pct = worker_pct
    dispute.resolution_note  = resolution_note
    dispute.resolved_at      = now
    dispute.resolved_by      = resolved_by
    dispute.save(update_fields=[
        "resolution", "split_worker_pct", "resolution_note", "resolved_at", "resolved_by",
    ])

    # Check if contract can be marked active again
    if not contract.milestones.filter(status=Milestone.Status.DISPUTED).exists():
        contract.status = Contract.Status.ACTIVE
        contract.save(update_fields=["status", "updated_at"])

    # Notify both parties
    for user in [contract.employer.user, contract.worker.user]:
        _notify(
            user=user,
            notif_type=Notification.NotifType.ESCROW_DISPUTE,
            title=f'Dispute split: "{milestone.title}"',
            body=(
                f'The dispute on "{milestone.title}" was resolved with a split: '
                f'worker receives {worker_pct}% (₦{worker_share:,.2f}), '
                f'employer refunded {100-worker_pct}% (₦{refund_share:,.2f}). '
                f'{resolution_note}'.strip()
            ),
            data={"dispute_id": str(dispute.pk), "milestone_id": str(milestone.pk)},
        )

    logger.info(
        "split_milestone: dispute %s split %d/%d — worker ₦%s, employer refund ₦%s.",
        dispute_id, worker_pct, 100-worker_pct, worker_share, refund_share,
    )
    return True


# ──────────────────────────────────────────────────────────────────────────────
#  10. POST DISPUTE MESSAGE  (immutable evidence thread)
# ──────────────────────────────────────────────────────────────────────────────

def post_dispute_message(
    dispute_id: str,
    author_user_id: int,
    body: str,
    attachment=None,
    is_admin_note: bool = False,
) -> tuple[bool, str]:
    """
    Append a message to a Dispute's evidence thread.

    - Only participants (employer.user, worker.user) or staff may post.
    - Staff can mark a message as admin-only (is_admin_note=True).
    - Attachment MIME is validated; SHA-256 is stored.
    - Messages are immutable once created.

    Returns (True, '') on success or (False, reason_str) on failure.
    """
    try:
        dispute = Dispute.objects.select_related(
            "milestone__contract__employer__user",
            "milestone__contract__worker__user",
        ).get(pk=dispute_id)
    except Dispute.DoesNotExist:
        return False, "dispute_not_found"

    if dispute.resolution != Dispute.Resolution.PENDING:
        return False, "dispute_already_resolved"

    try:
        author = User.objects.get(pk=author_user_id)
    except User.DoesNotExist:
        return False, "user_not_found"

    # Permission: only contract participants or staff
    contract = dispute.milestone.contract
    allowed_users = {contract.employer.user_id, contract.worker.user_id}
    if author.pk not in allowed_users and not author.is_staff:
        return False, "not_participant"

    # MIME + hash
    sha256 = ""
    if attachment:
        try:
            _validate_evidence_mime(attachment)
        except ValidationError as exc:
            return False, str(exc)
        sha256 = _hash_file(attachment)

    msg = DisputeMessage.objects.create(
        dispute=dispute,
        author=author,
        body=body,
        attachment=attachment,
        attachment_sha256=sha256,
        is_admin_note=is_admin_note and author.is_staff,
    )

    # Notify the other participant (not the author)
    for user in [contract.employer.user, contract.worker.user]:
        if user.pk != author.pk:
            _notify(
                user=user,
                notif_type=Notification.NotifType.ESCROW_DISPUTE,
                title=f'New message on dispute: "{dispute.milestone.title}"',
                body=f'{author.get_full_name() or author.username} posted: {body[:120]}',
                data={"dispute_id": str(dispute.pk)},
            )

    logger.info("post_dispute_message: message %s added to dispute %s by user %s.", msg.pk, dispute_id, author_user_id)
    return True, ""


# ──────────────────────────────────────────────────────────────────────────────
#  11. MEDIATION AGREE  (5-day self-resolution window)
# ──────────────────────────────────────────────────────────────────────────────

def mediation_agree(
    dispute_id: str,
    agreeing_user_id: int,
    agreed_resolution: str,
) -> tuple[bool, str]:
    """
    Record one party's agreement to a resolution during the mediation window.

    If BOTH parties agree to the SAME resolution before mediation_deadline:
      - Execute the resolution automatically (release or refund)
      - Return (True, 'auto_resolved')

    If only one party has agreed so far:
      - Store their choice and notify the other party
      - Return (True, 'pending_other_party')

    Returns (False, reason) on validation failure.
    """
    valid = {
        Dispute.Resolution.RELEASED_TO_WORKER,
        Dispute.Resolution.REFUNDED_TO_EMPLOYER,
    }
    if agreed_resolution not in valid:
        return False, "invalid_resolution_choice"

    try:
        dispute = Dispute.objects.select_related(
            "milestone__contract__employer__user",
            "milestone__contract__employer",
            "milestone__contract__worker__user",
            "milestone__contract__worker",
        ).get(pk=dispute_id, resolution=Dispute.Resolution.PENDING)
    except Dispute.DoesNotExist:
        return False, "dispute_not_found_or_resolved"

    # Check mediation window is still open
    if dispute.mediation_deadline and timezone.now() > dispute.mediation_deadline:
        return False, "mediation_window_closed"

    try:
        agreeing_user = User.objects.get(pk=agreeing_user_id)
    except User.DoesNotExist:
        return False, "user_not_found"

    contract = dispute.milestone.contract
    is_employer = agreeing_user.pk == contract.employer.user_id
    is_worker   = agreeing_user.pk == contract.worker.user_id

    if not (is_employer or is_worker):
        return False, "not_participant"

    # Store this party's agreement
    update_fields = []
    if is_employer:
        dispute.mediation_employer_agreed = agreed_resolution
        update_fields.append("mediation_employer_agreed")
    else:
        dispute.mediation_worker_agreed = agreed_resolution
        update_fields.append("mediation_worker_agreed")
    dispute.save(update_fields=update_fields)

    # Check if both parties now agree on the same resolution
    employer_agreed = dispute.mediation_employer_agreed
    worker_agreed   = dispute.mediation_worker_agreed

    if employer_agreed and worker_agreed and employer_agreed == worker_agreed:
        # Both agree — find a system user to act as resolver
        system_user = User.objects.filter(is_superuser=True).first() or agreeing_user
        success = resolve_dispute(
            dispute_id=dispute_id,
            resolution=agreed_resolution,
            resolved_by_user_id=system_user.pk,
            resolution_note="Resolved by mutual agreement during mediation window.",
        )
        if success:
            return True, "auto_resolved"
        return False, "resolution_execution_failed"

    # Notify the other party to also agree
    other_user = contract.worker.user if is_employer else contract.employer.user
    resolution_label = dict(Dispute.Resolution.choices).get(agreed_resolution, agreed_resolution)
    _notify(
        user=other_user,
        notif_type=Notification.NotifType.ESCROW_DISPUTE,
        title=f'Mediation: agreement proposed on "{dispute.milestone.title}"',
        body=(
            f'{agreeing_user.get_full_name() or agreeing_user.username} has agreed to: '
            f'"{resolution_label}". If you also agree, click the same option in the dispute '
            f'thread to resolve this without admin intervention.'
        ),
        data={"dispute_id": str(dispute.pk)},
    )

    logger.info(
        "mediation_agree: user %s agreed to '%s' on dispute %s. Awaiting other party.",
        agreeing_user_id, agreed_resolution, dispute_id,
    )
    return True, "pending_other_party"

