"""
bot/tasks.py
============
Celery tasks for the TradeLink NG bot.

send_bot_message_task
    Fire-and-forget task to send a plain-text message to any phone number.
    Uses the currently configured provider (BOT_PROVIDER setting).
    Retries up to 3 times on transient API failures.

send_bot_notification_task
    Higher-level wrapper that resolves a User → linked phone number →
    calls send_bot_message_task.  Safe to call from signals or other apps.

Provider independence
─────────────────────
Both tasks call ``get_provider()`` at execution time, so they
automatically use whichever channel is set in BOT_PROVIDER without
any code changes.  Switching from Twilio to Meta (or back) only
requires an env-var change and a Celery worker restart.
"""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    name='bot.tasks.send_bot_message_task',
)
def send_bot_message_task(self, phone_number: str, message: str) -> dict:
    """
    Send a text message to *phone_number* (E.164 without leading +).

    Retries up to 3 times with 30-second delays on transient API errors.
    """
    from bot.providers import get_provider
    from .models import WhatsAppSession, WhatsAppMessage

    provider = get_provider()
    try:
        result = provider.send_text(phone_number, message)

        # Log as outbound if we have a session for this number
        session = WhatsAppSession.objects.filter(phone_number=phone_number).first()
        if session:
            WhatsAppMessage.objects.create(
                session=session,
                direction=WhatsAppMessage.Direction.OUTBOUND,
                content=message,
            )

        logger.info('Bot message sent to +%s via %s', phone_number, provider.__class__.__name__)
        return result

    except Exception as exc:
        logger.warning(
            'send_bot_message_task failed for +%s (attempt %d): %s',
            phone_number, self.request.retries + 1, exc,
        )
        raise self.retry(exc=exc)


@shared_task(
    name='bot.tasks.send_bot_notification_task',
)
def send_bot_notification_task(user_id: str, message: str) -> None:
    """
    Resolve *user_id* → linked phone number → send a message via the active provider.

    Silently skips if:
    • The user does not exist.
    • The user has no phone number set.
    • No bot session is linked for that phone number.
    """
    from users.models import User
    from .models import WhatsAppSession

    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        logger.warning('send_bot_notification_task: user %s not found', user_id)
        return

    if not user.phone_number:
        return

    phone = str(user.phone_number).lstrip('+')

    # Only send if a session exists and is linked to this user
    # (i.e. the user has previously messaged the bot)
    session = WhatsAppSession.objects.filter(
        phone_number=phone, user=user
    ).first()
    if not session:
        logger.debug(
            'send_bot_notification_task: no linked session for user %s', user_id
        )
        return

    send_bot_message_task.delay(phone, message)


# ── Backward-compatibility aliases ────────────────────────────────────────────
# These allow existing Celery task names (registered in the broker) to keep
# working after the rename.  Remove after the next full deployment + worker flush.

@shared_task(name='bot.tasks.send_whatsapp_message_task')
def send_whatsapp_message_task(phone_number: str, message: str) -> dict:
    """Deprecated alias → send_bot_message_task."""
    return send_bot_message_task(phone_number, message)


@shared_task(name='bot.tasks.send_whatsapp_notification_task')
def send_whatsapp_notification_task(user_id: str, message: str) -> None:
    """Deprecated alias → send_bot_notification_task."""
    return send_bot_notification_task(user_id, message)


# ── Job-match push notifications ──────────────────────────────────────────────

@shared_task(
    name='bot.tasks.notify_job_matches_task',
    bind=True,
    ignore_result=True,
    autoretry_for=(Exception,),
    max_retries=2,
    retry_backoff=True,
)
def notify_job_matches_task(self, job_id: str, score_threshold: float = 0.65) -> None:
    """
    Called after ``compute_matches_for_job_task`` finishes.

    Fetches every CLIPMatch for *job_id* where score ≥ *score_threshold* and
    the worker has a linked WhatsApp session, then fires a push notification
    to each matched worker via ``send_bot_notification_task``.

    Score tiers:
        ≥ 0.80  🔥 Excellent
        ≥ 0.65  ⭐ Strong  (default threshold)

    Design notes:
    • Runs as a *separate* Celery task so it never blocks the matching pipeline.
    • Each notification is dispatched as its own ``send_bot_notification_task``
      so a single failed send doesn't affect other workers.
    • Silently skips workers with no linked session (no opt-in → no spam).
    """
    from jobs.models import CLIPMatch, Job
    from .models import WhatsAppSession

    try:
        job = Job.objects.select_related('trade_category').get(pk=job_id)
    except Job.DoesNotExist:
        logger.warning('notify_job_matches_task: job %s not found.', job_id)
        return

    # Fetch strong-match CLIPMatch rows with the worker's user pre-joined
    matches = (
        CLIPMatch.objects
        .filter(job_id=job_id, score__gte=score_threshold)
        .select_related('worker__user')
        .order_by('-score')
    )

    if not matches.exists():
        logger.info(
            'notify_job_matches_task: no matches above %.2f for job %s.',
            score_threshold, job_id,
        )
        return

    # Build a fast lookup: phone_number → session.user_id for linked sessions
    worker_user_ids = [
        str(m.worker.user_id) for m in matches if m.worker.user_id
    ]
    linked_phones = {
        str(s.user_id): s.phone_number
        for s in WhatsAppSession.objects.filter(
            user_id__in=worker_user_ids,
            user__isnull=False,
        ).only('user_id', 'phone_number')
    }

    if not linked_phones:
        logger.info(
            'notify_job_matches_task: no linked WhatsApp sessions for job %s matches.',
            job_id,
        )
        return

    # Score → emoji tier
    def _tier(score: float) -> str:
        return '🔥' if score >= 0.80 else '⭐'

    trade_name = job.trade_category.name if job.trade_category else 'your trade'
    job_short_id = str(job.id)[:8]

    notified = 0
    for match in matches:
        user_id = str(match.worker.user_id) if match.worker.user_id else None
        if not user_id:
            continue
        phone = linked_phones.get(user_id)
        if not phone:
            continue  # worker hasn't linked their WhatsApp

        pct  = round(match.score * 100)
        tier = _tier(match.score)

        message = (
            f"{tier} *New Job Match — {pct}% Match!*\n\n"
            f"A new *{trade_name}* job matches your profile:\n\n"
            f"📋 *{job.title}*\n"
            f"📍 {job.state.title() if job.state else 'Location TBC'}  "
            f"🕐 {job.get_job_type_display()}\n\n"
            f"👉 Apply now: tradelinkng.com/jobs/{job_short_id}\n\n"
            f"_Type *matches* on this chat to see all your matches._"
        )

        send_bot_notification_task.delay(user_id, message)
        notified += 1

    logger.info(
        'notify_job_matches_task: dispatched %d notifications for job %s.',
        notified, job_id,
    )


@shared_task(
    name='bot.tasks.notify_worker_new_matches_task',
    bind=True,
    ignore_result=True,
    autoretry_for=(Exception,),
    max_retries=2,
    retry_backoff=True,
)
def notify_worker_new_matches_task(
    self,
    worker_profile_id: str,
    score_threshold: float = 0.65,
    limit: int = 3,
) -> None:
    """
    Called after ``compute_matches_for_worker_task`` finishes.

    Sends the worker a summary of their top *limit* new strong matches
    (score ≥ threshold) across all active jobs.

    Only fires if:
    • The worker's user has a linked WhatsApp session.
    • At least one match is above the threshold.
    """
    from jobs.models import CLIPMatch, WorkerProfile
    from .models import WhatsAppSession

    try:
        worker = WorkerProfile.objects.select_related(
            'user', 'trade_category'
        ).get(pk=worker_profile_id)
    except WorkerProfile.DoesNotExist:
        logger.warning(
            'notify_worker_new_matches_task: worker %s not found.', worker_profile_id
        )
        return

    if not worker.user_id:
        return

    # Check for a linked WhatsApp session
    session = WhatsAppSession.objects.filter(
        user_id=worker.user_id
    ).only('phone_number', 'user_id').first()

    if not session:
        logger.debug(
            'notify_worker_new_matches_task: no linked session for worker %s.',
            worker_profile_id,
        )
        return

    top_matches = (
        CLIPMatch.objects
        .filter(
            worker_id=worker_profile_id,
            job__status='active',
            score__gte=score_threshold,
        )
        .select_related('job', 'job__trade_category')
        .order_by('-score')[:limit]
    )

    if not top_matches:
        return

    trade_name = worker.trade_category.name if worker.trade_category else 'your trade'
    count = len(top_matches)

    lines = [
        f"💼 *{count} New Job Match{'es' if count > 1 else ''} for You!*\n",
        f"Based on your *{trade_name}* profile:\n",
    ]

    def _tier(score: float) -> str:
        return '🔥' if score >= 0.80 else '⭐'

    for i, m in enumerate(top_matches, 1):
        pct  = round(m.score * 100)
        tier = _tier(m.score)
        job  = m.job
        lines.append(
            f"{tier} *{i}. {job.title}* — {pct}% match\n"
            f"   📍 {job.state.title() if job.state else 'TBC'}  "
            f"🕐 {job.get_job_type_display()}\n"
            f"   tradelinkng.com/jobs/{str(job.id)[:8]}\n"
        )

    lines.append(
        "_Type *matches* to see all your job matches._"
    )

    send_bot_notification_task.delay(str(worker.user_id), '\n'.join(lines))
    logger.info(
        'notify_worker_new_matches_task: dispatched summary for worker %s (%d matches).',
        worker_profile_id, count,
    )

