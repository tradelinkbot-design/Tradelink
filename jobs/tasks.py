"""
marketplace/tasks.py
=====================
Celery tasks for async embedding computation and match scoring.

Why async / why Celery?
────────────────────────
  Both sentence-transformer and CLIP inference take 50–300 ms on CPU.
  Running them synchronously inside a web request would block every profile
  save and job post.  Instead:

  1. User saves profile / posts job  →  view returns immediately.
  2. post_save signal fires           →  task(s) queued in Redis.
  3. Celery worker picks them up      →  ML inference runs in background.
  4. Embeddings + CLIPMatch rows written → next page load shows fresh matches.

Embedding task chain (per job)
───────────────────────────────
  compute_job_embedding_task
      ├─ compute_job_text_embedding()     sentence-transformer 768-dim → text_embedding
      ├─ compute_job_clip_embedding()     CLIP text encoder 512-dim    → clip_embedding
      └─ compute_matches_for_job_task.delay()

  compute_worker_embedding_task
      ├─ compute_worker_text_embedding()  sentence-transformer 768-dim → text_embedding
      ├─ calculate_profile_completion()
      └─ compute_matches_for_worker_task.delay()

  compute_portfolio_image_task
      └─ compute_portfolio_image_embedding()  CLIP visual encoder 512-dim → clip_image_embedding

Task design principles
───────────────────────
  bind=True          — access to self.retry()
  max_retries=3      — retries on transient failures (OOM, DB blip)
  autoretry_for      — auto-retries on any Exception
  retry_backoff      — exponential back-off (30 s, 60 s, 120 s)
  acks_late=True     — re-queued if worker crashes mid-flight
  ignore_result=True — return values not needed in result backend

Routing (add to settings.py)
──────────────────────────────
  CELERY_TASK_ROUTES = {
      'jobs.tasks.compute_worker_embedding_task':  {'queue': 'embeddings'},
      'jobs.tasks.compute_job_embedding_task':     {'queue': 'embeddings'},
      'jobs.tasks.compute_portfolio_image_task':   {'queue': 'embeddings'},
      'jobs.tasks.compute_matches_for_job_task':   {'queue': 'matching'},
      'jobs.tasks.compute_matches_for_worker_task':{'queue': 'matching'},
  }
"""

import logging
from datetime import timedelta

from celery import shared_task
from django.contrib.auth import get_user_model
from django.utils import timezone

logger = logging.getLogger(__name__)
User = get_user_model()


# ──────────────────────────────────────────────────────────────────────────────
#  DISPUTE SLA TASKS
# ──────────────────────────────────────────────────────────────────────────────

@shared_task(
    bind=True,
    max_retries=1,
    acks_late=True,
    ignore_result=True,
)
def escalate_stale_disputes(self) -> None:
    """
    Periodic task — run every 6 hours via Celery Beat.

    Phase 1 (72h+): Escalate unresolved disputes by notifying superusers.
    Phase 2 (7d+):  Auto-release funds to worker (favours completed work).

    Add to settings.py CELERY_BEAT_SCHEDULE:
        'escalate-stale-disputes': {
            'task': 'jobs.tasks.escalate_stale_disputes',
            'schedule': crontab(minute=0, hour='*/6'),
        },
    """
    from jobs.models import Dispute, Notification
    from jobs.service.escrow_service import resolve_dispute, SLA_ESCALATE_HOURS, SLA_AUTO_RELEASE_DAYS

    now            = timezone.now()
    cutoff_escalate = now - timedelta(hours=SLA_ESCALATE_HOURS)
    cutoff_release  = now - timedelta(days=SLA_AUTO_RELEASE_DAYS)

    # ── Escalate disputes older than 72h ─────────────────────────────────────
    stale_to_escalate = Dispute.objects.filter(
        resolution=Dispute.Resolution.PENDING,
        created_at__lte=cutoff_escalate,
        escalated=False,
    ).select_related('milestone__contract')

    superusers = list(User.objects.filter(is_superuser=True))
    escalated_count = 0

    for dispute in stale_to_escalate:
        milestone = dispute.milestone
        for su in superusers:
            Notification.objects.create(
                user=su,
                notif_type=Notification.NotifType.SYSTEM,
                title=f'[URGENT] Dispute unresolved 72h+: "{milestone.title}"',
                body=(
                    f'Dispute on milestone "{milestone.title}" '
                    f'(Contract: {milestone.contract.title}) has been open '
                    f'for more than {SLA_ESCALATE_HOURS} hours without resolution. '
                    f'Please review immediately.'
                ),
                data={'dispute_id': str(dispute.pk)},
            )
        dispute.escalated = True
        dispute.save(update_fields=['escalated'])
        escalated_count += 1

    if escalated_count:
        logger.warning("escalate_stale_disputes: escalated %d disputes to superusers.", escalated_count)

    # ── Auto-release disputes older than 7 days ───────────────────────────────
    auto_release = Dispute.objects.filter(
        resolution=Dispute.Resolution.PENDING,
        created_at__lte=cutoff_release,
    ).select_related('milestone__contract')

    released_count = 0
    system_user = superusers[0] if superusers else None

    for dispute in auto_release:
        if system_user is None:
            logger.error("escalate_stale_disputes: no superuser available for auto-release of dispute %s.", dispute.pk)
            continue
        success = resolve_dispute(
            dispute_id=str(dispute.pk),
            resolution=Dispute.Resolution.RELEASED_TO_WORKER,
            resolved_by_user_id=system_user.pk,
            resolution_note=(
                f'Auto-released after {SLA_AUTO_RELEASE_DAYS}-day SLA breach. '
                f'No admin action was taken within the required timeframe.'
            ),
        )
        if success:
            released_count += 1
            logger.info("escalate_stale_disputes: auto-released dispute %s to worker.", dispute.pk)
        else:
            logger.error("escalate_stale_disputes: failed to auto-release dispute %s.", dispute.pk)

    if released_count:
        logger.info("escalate_stale_disputes: auto-released %d dispute(s).", released_count)


@shared_task(
    bind=True,
    max_retries=1,
    acks_late=True,
    ignore_result=True,
)
def escalate_stale_order_disputes(self) -> None:
    """
    Same SLA logic for marketplace OrderDisputes.
    Run on the same Celery Beat schedule as escalate_stale_disputes.
    """
    from marketplace.models import OrderDispute, Order, Notification as MktNotification
    from marketplace.service.market_place_service_escrow import release_order_to_seller

    now            = timezone.now()
    cutoff_escalate = now - timedelta(hours=72)
    cutoff_release  = now - timedelta(days=7)

    superusers = list(User.objects.filter(is_superuser=True))

    # ── Escalate ─────────────────────────────────────────────────────────────
    for dispute in OrderDispute.objects.filter(
        resolution=OrderDispute.Resolution.PENDING,
        created_at__lte=cutoff_escalate,
        escalated=False,
    ).select_related('order__product'):
        for su in superusers:
            MktNotification.objects.create(
                user=su,
                notif_type=MktNotification.NotifType.SYSTEM,
                title=f'[URGENT] Order dispute 72h+: "{dispute.order.product.title}"',
                body=f'Order dispute on "{dispute.order.product.title}" unresolved for 72h+.',
                data={'dispute_id': str(dispute.pk)},
            )
        dispute.escalated = True
        dispute.save(update_fields=['escalated'])

    # ── Auto-release ──────────────────────────────────────────────────────────
    for dispute in OrderDispute.objects.filter(
        resolution=OrderDispute.Resolution.PENDING,
        created_at__lte=cutoff_release,
    ).select_related('order'):
        success = release_order_to_seller(str(dispute.order.pk))
        if success:
            dispute.resolution      = OrderDispute.Resolution.RELEASED_TO_SELLER
            dispute.resolution_note = f'Auto-released after 7-day SLA breach.'
            dispute.resolved_at     = now
            dispute.save(update_fields=['resolution', 'resolution_note', 'resolved_at'])
            logger.info("escalate_stale_order_disputes: auto-released dispute %s.", dispute.pk)
        else:
            logger.error("escalate_stale_order_disputes: failed to auto-release dispute %s.", dispute.pk)




# ──────────────────────────────────────────────────────────────────────────────
#  EMBEDDING TASKS
# ──────────────────────────────────────────────────────────────────────────────

@shared_task(
    bind=True,
    max_retries=3,
    acks_late=True,
    ignore_result=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=120,
    retry_jitter=True,
)
def compute_worker_embedding_task(self, worker_profile_id: str) -> None:
    """
    Encodes a WorkerProfile's text with sentence-transformers (768-dim)
    and saves it to WorkerProfile.text_embedding.

    On success:
      - Recalculates profile_completion.
      - Chains compute_matches_for_worker_task.
    """
    from jobs.service.matching_service import (
        compute_worker_embedding,
        calculate_profile_completion,
    )

    logger.info("Task: compute_worker_embedding for %s", worker_profile_id)

    success = compute_worker_embedding(worker_profile_id)
    if success:
        calculate_profile_completion(worker_profile_id)
        compute_matches_for_worker_task.delay(worker_profile_id)


@shared_task(
    bind=True,
    max_retries=3,
    acks_late=True,
    ignore_result=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=120,
    retry_jitter=True,
)
def compute_job_embedding_task(self, job_id: str) -> None:
    """
    Runs BOTH embedding encoders for a job, then triggers match computation.

    Step 1 — sentence-transformers (768-dim → Job.text_embedding)
        Used for text ↔ text similarity (50 % of the hybrid score).

    Step 2 — CLIP text encoder (512-dim → Job.clip_embedding)
        Used for cross-modal comparison: job description text vs worker
        portfolio IMAGES.  Storing it here avoids recomputing it on every
        match run.

    Step 3 — compute_matches_for_job_task
        Only fires if at least the sentence-transformer embedding succeeded,
        since that is the dominant signal.  CLIP failure is non-fatal.
    """
    from jobs.service.matching_service import (
        compute_job_embedding,
        compute_job_clip_embedding,
    )

    logger.info("Task: compute_job_embedding for %s", job_id)

    # Step 1: sentence-transformer (primary signal, must succeed)
    st_success = compute_job_embedding(job_id)

    if st_success:
        # Step 2: CLIP text encoder (secondary signal — skipped when disabled to preserve RAM)
        from jobs.service.clip_service import is_clip_enabled
        if is_clip_enabled():
            compute_job_clip_embedding(job_id)

        # Step 3: trigger match computation
        compute_matches_for_job_task.delay(job_id)


@shared_task(
    bind=True,
    max_retries=3,
    acks_late=True,
    ignore_result=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=120,
    retry_jitter=True,
)
def compute_portfolio_image_task(self, portfolio_item_id: str) -> None:
    """
    Encodes a PortfolioItem image with CLIP's visual encoder (512-dim)
    and saves it to PortfolioItem.clip_image_embedding.
    """
    from jobs.service.clip_service import is_clip_enabled
    if not is_clip_enabled():
        logger.info("compute_portfolio_image_task: CLIP is disabled — skipping %s.", portfolio_item_id)
        return

    from jobs.service.matching_service import compute_portfolio_image_embedding

    logger.info("Task: compute_portfolio_image for %s", portfolio_item_id)
    compute_portfolio_image_embedding(portfolio_item_id)


@shared_task(
    bind=True,
    max_retries=1,
    acks_late=False,
    ignore_result=False,
)
def encode_search_query_task(self, query: str) -> list[float]:
    """
    RPC task used by the web server (search_service.py) to offload PyTorch
    inference to the Celery worker process. This prevents the Daphne ASGI
    server from crashing on Windows due to PyTorch thread interactions.
    """
    from jobs.service.text_encoder import text_encoder
    # Returns a list of floats so it can be serialized as JSON by Celery
    return text_encoder.encode(query.strip())


# ──────────────────────────────────────────────────────────────────────────────
#  MATCHING TASKS
# ──────────────────────────────────────────────────────────────────────────────

@shared_task(
    bind=True,
    max_retries=3,
    acks_late=True,
    ignore_result=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def compute_matches_for_job_task(self, job_id: str) -> None:
    """
    Computes CLIPMatch scores between a job and all workers in the same trade.
    Safe to re-run (idempotent upsert).
    """
    from jobs.service.matching_service import compute_matches_for_job

    logger.info("Task: compute_matches_for_job for %s", job_id)
    count = compute_matches_for_job(job_id)
    logger.info(
        "Task: compute_matches_for_job — %d rows written for %s", count, job_id
    )

    # Push WhatsApp notifications to all workers who scored >= 0.65 on this job.
    # This runs as a separate task so a failed notification never retries the
    # expensive matching computation above.
    if count:
        from bot.tasks import notify_job_matches_task
        notify_job_matches_task.delay(job_id)


@shared_task(
    bind=True,
    max_retries=3,
    acks_late=True,
    ignore_result=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def compute_matches_for_worker_task(self, worker_profile_id: str) -> None:
    """
    Computes CLIPMatch scores between a worker and all active jobs in their trade.
    Safe to re-run (idempotent upsert).
    """
    from jobs.service.matching_service import compute_matches_for_worker

    logger.info("Task: compute_matches_for_worker for %s", worker_profile_id)
    count = compute_matches_for_worker(worker_profile_id)
    logger.info(
        "Task: compute_matches_for_worker — %d rows written for %s",
        count, worker_profile_id,
    )

    # Notify the worker via WhatsApp if they have strong new matches.
    if count:
        from bot.tasks import notify_worker_new_matches_task
        notify_worker_new_matches_task.delay(worker_profile_id)


# ──────────────────────────────────────────────────────────────────────────────
#  PERIODIC / MAINTENANCE TASKS
# ──────────────────────────────────────────────────────────────────────────────

@shared_task(ignore_result=True)
def recompute_all_embeddings_task() -> None:
    """
    Periodic maintenance task — re-encodes every worker and job.

    Run nightly via Celery Beat to keep embeddings fresh when a model is
    upgraded or the input text templates change.

    Add to settings.py:
        from celery.schedules import crontab
        CELERY_BEAT_SCHEDULE = {
            'recompute-all-embeddings': {
                'task': 'jobs.tasks.recompute_all_embeddings_task',
                'schedule': crontab(hour=2, minute=0),   # 2 AM daily
            },
        }
    """
    from jobs.models import WorkerProfile, Job

    logger.info("Periodic task: recomputing all embeddings.")

    worker_ids = list(WorkerProfile.objects.values_list('id', flat=True))
    for wid in worker_ids:
        compute_worker_embedding_task.delay(str(wid))

    job_ids = list(
        Job.objects.filter(status=Job.Status.ACTIVE).values_list('id', flat=True)
    )
    for jid in job_ids:
        compute_job_embedding_task.delay(str(jid))

    logger.info(
        "Periodic task: queued %d worker + %d job embedding tasks.",
        len(worker_ids), len(job_ids),
    )


@shared_task(ignore_result=True)
def expire_old_jobs_task() -> None:
    """
    Periodic task — marks jobs past their deadline as EXPIRED.
    Add to Celery Beat schedule to run hourly or nightly.
    """
    from django.utils import timezone
    from jobs.models import Job, JobApplication, Notification

    today = timezone.now().date()
    expired_jobs = Job.objects.filter(
        status=Job.Status.ACTIVE,
        deadline__lt=today,
    )

    count = 0
    for job in expired_jobs:
        # Mark as expired
        job.status = Job.Status.EXPIRED
        job.save(update_fields=['status'])

        # Notify employer
        Notification.objects.create(
            user=job.employer.user,
            notif_type=Notification.NotifType.JOB_EXPIRING,
            title="Job Listing Expired",
            body=f"Your job listing '{job.title}' has reached its deadline and is now expired.",
            data={'link': '/dashboard/employer/'}
        )

        # Archive pending applications
        pending_apps = job.applications.filter(status=JobApplication.Status.PENDING)
        for app in pending_apps:
            app.status = JobApplication.Status.REJECTED
            app.save(update_fields=['status'])
            
            # Notify applicant
            Notification.objects.create(
                user=app.worker.user,
                notif_type=Notification.NotifType.APPLICATION_UPDATE,
                title="Job Expired",
                body=f"The job '{job.title}' has expired and your application has been archived.",
                data={'link': '/dashboard/worker/'}
            )
            
        count += 1

    logger.info("expire_old_jobs_task: %d jobs expired.", count)


# ──────────────────────────────────────────────────────────────────────────────
#  ESCROW / MILESTONE TASKS
# ──────────────────────────────────────────────────────────────────────────────

# Add to settings.py CELERY_BEAT_SCHEDULE:
# 'auto-release-milestones': {
#     'task': 'jobs.tasks.auto_release_milestones_task',
#     'schedule': crontab(hour='*', minute=0),
# },

@shared_task(ignore_result=True)
def auto_release_milestones_task():
    """
    Runs every hour via Celery Beat.
    Finds all milestones where:
      status = IN_REVIEW AND auto_release_at <= now()
    Calls release_milestone_to_worker() for each.
    Logs how many were auto-released.
    """
    from django.utils import timezone
    from jobs.models import Milestone
    from jobs.service.escrow_service import release_milestone_to_worker

    now = timezone.now()
    milestones = Milestone.objects.filter(
        status=Milestone.Status.IN_REVIEW,
        auto_release_at__lte=now,
    ).select_related('contract')

    count = 0
    for milestone in milestones:
        try:
            released = release_milestone_to_worker(str(milestone.pk))
            if released:
                count += 1
        except Exception:
            logger.exception(
                "auto_release_milestones_task: failed for milestone %s",
                milestone.pk,
            )

    logger.info("auto_release_milestones_task: auto-released %d milestones.", count)


@shared_task(
    bind=True,
    max_retries=3,
    acks_late=True,
    ignore_result=True,
    retry_backoff=True,
    retry_backoff_max=120,
    retry_jitter=True,
)
def process_milestone_payout_task(self, milestone_id: str) -> None:
    """
    Async wrapper around release_milestone_to_worker().
    Called by approve_milestone() so payout doesn't block the HTTP request.
    Retries up to 3 times with exponential backoff on failure.
    """
    from jobs.service.escrow_service import release_milestone_to_worker

    logger.info("Task: process_milestone_payout for %s", milestone_id)
    try:
        release_milestone_to_worker(milestone_id)
    except Exception as exc:
        logger.exception(
            "Task: process_milestone_payout failed for %s", milestone_id
        )
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    max_retries=3,
    acks_late=True,
    ignore_result=True,
    retry_backoff=True,
    retry_backoff_max=120,
    retry_jitter=True,
)
def create_transfer_recipient_task(self, worker_bank_account_id: str) -> None:
    """
    Async wrapper around create_transfer_recipient().
    Called after WorkerBankAccount is saved/updated.
    Retries up to 3 times with exponential backoff on failure.
    """
    from jobs.service.escrow_service import create_transfer_recipient

    logger.info("Task: create_transfer_recipient for %s", worker_bank_account_id)
    try:
        create_transfer_recipient(worker_bank_account_id)
    except Exception as exc:
        logger.exception(
            "Task: create_transfer_recipient failed for %s",
            worker_bank_account_id,
        )
        raise self.retry(exc=exc)