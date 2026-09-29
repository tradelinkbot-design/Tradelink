"""
bot/notifications.py
====================
Public helpers for sending bot notifications from other apps.

Import and call these functions from Django signals, views, or Celery tasks
in other apps (jobs, marketplace, chats) to notify users via the active
messaging channel without importing Celery tasks directly.

The active channel is controlled by BOT_PROVIDER in settings:
    'twilio' — sends via Twilio WhatsApp
    'meta'   — sends via Meta WhatsApp Business Cloud API

Usage example (in jobs/signals.py)::

    from bot.notifications import notify_user

    def on_new_application(sender, instance, created, **kwargs):
        if created:
            notify_user(
                instance.job.employer.user,
                f"📬 New application for *{instance.job.title}* from "
                f"{instance.worker.user.get_full_name()}!"
            )
"""

import logging

logger = logging.getLogger(__name__)


def _bot_configured() -> bool:
    """Return True if the bot has minimum credentials to send messages."""
    from django.conf import settings
    provider = getattr(settings, 'BOT_PROVIDER', 'twilio').lower()
    if provider == 'twilio':
        return bool(getattr(settings, 'TWILIO_ACCOUNT_SID', ''))
    elif provider == 'meta':
        return bool(getattr(settings, 'WHATSAPP_ACCESS_TOKEN', ''))
    return False


def notify_user(user, message: str) -> None:
    """
    Send *message* to *user* via the active messaging provider (async, non-blocking).

    Silently no-ops if:
    • The user has no phone number.
    • No linked bot session exists for that number.
    • The bot app is not fully configured.
    """
    try:
        if not _bot_configured():
            logger.debug('notify_user: bot not configured, skipping.')
            return

        from .tasks import send_bot_notification_task
        send_bot_notification_task.delay(str(user.pk), message)

    except Exception:
        # Never let a notification error bubble up to the caller
        logger.exception(
            'notify_user failed for user %s', getattr(user, 'pk', '?')
        )


# ── Backward-compatibility alias ──────────────────────────────────────────────
def notify_user_whatsapp(user, message: str) -> None:
    """Deprecated — use notify_user() instead."""
    notify_user(user, message)


# ── Domain-specific notification helpers ─────────────────────────────────────

def notify_job_application(job, application) -> None:
    """
    Notify the job poster that a new application has arrived.

    Call this from jobs/signals.py after a JobApplication is created.
    """
    employer_user = job.employer.user
    worker_name   = application.worker.user.get_full_name() or application.worker.user.username
    message = (
        f"📬 *New Application!*\n\n"
        f"*{worker_name}* has applied for your job:\n"
        f"*{job.title}*\n\n"
        f"🌐 Review it at: tradelinkng.com/jobs/{job.id}/applications"
    )
    notify_user(employer_user, message)


def notify_job_match(worker_user, job) -> None:
    """
    Notify a worker of a new job that matches their profile.

    Call this from the CLIPMatch Celery task after computing high-score matches.
    """
    message = (
        f"💼 *New Job Match!*\n\n"
        f"A job matching your skills has just been posted:\n\n"
        f"*{job.title}*\n"
        f"📍 {job.state.title() if job.state else 'Location TBC'} · "
        f"{job.get_job_type_display()}\n\n"
        f"🌐 Apply at: tradelinkng.com/jobs/{job.id}"
    )
    notify_user(worker_user, message)


def notify_job_status_change(job) -> None:
    """Notify the employer when their job status changes (filled, expired, etc.)."""
    employer_user = job.employer.user
    status_emoji = {
        'active':   '✅',
        'filled':   '🎉',
        'expired':  '⏰',
        'closed':   '🔒',
        'paused':   '⏸️',
    }.get(job.status, 'ℹ️')

    message = (
        f"{status_emoji} *Job Status Update*\n\n"
        f"Your job *{job.title}* is now: *{job.get_status_display()}*\n\n"
        f"🌐 Manage at: tradelinkng.com/jobs/my-jobs"
    )
    notify_user(employer_user, message)


def notify_order_update(user, order_ref: str, status_msg: str) -> None:
    """Generic order/escrow status notification."""
    message = (
        f"📦 *Order Update*\n\n"
        f"Order *#{order_ref}*: {status_msg}\n\n"
        f"🌐 View details at: tradelinkng.com/orders"
    )
    notify_user(user, message)
