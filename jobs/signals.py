"""
marketplace/signals.py
=======================
Django signals that fire Celery tasks when models are saved.

Signal → Task → Service → Database
────────────────────────────────────
  The signal layer is intentionally thin.  Its only job is to:
    1. Decide WHETHER a task should fire (based on what changed).
    2. Call task.delay() with the model PK.

  It does NOT do any CLIP work itself.  That is the task layer's concern.

Why import tasks inside the handler (not at module level)?
──────────────────────────────────────────────────────────
  Celery tasks import Django models.  If we import tasks at module level here,
  we create a circular import chain at startup:
      apps.py → signals.py → tasks.py → models.py → apps.py (again)

  Deferring the import inside the function body avoids this entirely.

Which fields trigger re-embedding?
────────────────────────────────────
  We use Django's `update_fields` argument to detect targeted updates.
  If a view calls instance.save(update_fields=['availability']), that does NOT
  change the CLIP input text, so we skip re-embedding.

  Fields that DO affect CLIP input text:
    WorkerProfile:  bio, trade_category, (skill changes via WorkerSkill signal)
    Job:            title, description, trade_category, required_skills (M2M signal)
"""

import logging
from jobs.models import Job
from django.db.models.signals import post_save, m2m_changed
from django.dispatch import receiver

logger = logging.getLogger(__name__)

# ── Fields whose change should trigger re-embedding ─────────────────────────
_WORKER_EMBEDDING_FIELDS = frozenset({'bio', 'trade_category', 'trade_category_id'})
_JOB_EMBEDDING_FIELDS    = frozenset({'title', 'description', 'trade_category', 'trade_category_id'})


def _fields_changed(update_fields, watched_fields: frozenset) -> bool:
    """
    Returns True if update_fields is None (full save) OR if any of the
    watched fields appear in update_fields.
    """
    if update_fields is None:
        return True
    return bool(frozenset(update_fields) & watched_fields)


# ──────────────────────────────────────────────────────────────────────────────
#  WORKER PROFILE
# ──────────────────────────────────────────────────────────────────────────────

@receiver(post_save, sender='jobs.WorkerProfile')
def on_worker_profile_save(sender, instance, created, update_fields, **kwargs):
    """
    Fires after a WorkerProfile is saved.
    - Always recalculates profile_completion.
    - Re-encodes with CLIP if bio or trade_category changed.
    """
    from jobs.tasks import (
        compute_worker_embedding_task,
        compute_matches_for_worker_task,
    )
    from jobs.service.matching_service import calculate_profile_completion

    # Always keep profile completion up to date, but avoid re-saving if the
    # only field that changed IS profile_completion (infinite loop guard).
    if update_fields is None or 'profile_completion' not in update_fields:
        calculate_profile_completion(str(instance.pk))

    if _fields_changed(update_fields, _WORKER_EMBEDDING_FIELDS):
        logger.debug(
            "Worker %s saved with embedding-relevant fields — queuing embedding task.",
            instance.pk,
        )
        compute_worker_embedding_task.delay(str(instance.pk))


# ──────────────────────────────────────────────────────────────────────────────
#  WORKER SKILL  (M2M through model — fires post_save like a regular model)
# ──────────────────────────────────────────────────────────────────────────────

@receiver(post_save, sender='jobs.WorkerSkill')
def on_worker_skill_save(sender, instance, **kwargs):
    """
    Fires when a skill is added to / updated on a worker profile.
    Skill names are part of the CLIP input text, so re-encode.
    """
    from jobs.tasks import compute_worker_embedding_task

    logger.debug(
        "WorkerSkill changed for worker %s — queuing embedding task.",
        instance.worker_id,
    )
    compute_worker_embedding_task.delay(str(instance.worker_id))


# ──────────────────────────────────────────────────────────────────────────────
#  PORTFOLIO ITEM
# ──────────────────────────────────────────────────────────────────────────────

@receiver(post_save, sender='jobs.PortfolioItem')
def on_portfolio_item_save(sender, instance, created, **kwargs):
    """
    Fires when a new portfolio image is uploaded.
    Queues CLIP image encoding for the new item.
    """
    from jobs.tasks import compute_portfolio_image_task

    if instance.image and not instance.clip_image_embedding:
        logger.debug(
            "PortfolioItem %s saved with new image — queuing image embedding task.",
            instance.pk,
        )
        compute_portfolio_image_task.delay(str(instance.pk))


# ──────────────────────────────────────────────────────────────────────────────
#  JOB
# ──────────────────────────────────────────────────────────────────────────────

@receiver(post_save, sender='jobs.Job')
def on_job_save(sender, instance, created, update_fields, **kwargs):
    """
    Fires after a Job is saved.
    - Re-encodes with CLIP if the job becomes active or if text fields change.
    - The task chain is: compute_job_embedding → compute_matches_for_job.
    """
    from jobs.tasks import compute_job_embedding_task
    from jobs.models import Job

    # Only process active jobs
    if instance.status != Job.Status.ACTIVE:
        return

    # Fire if:
    #   (a) the job was just created
    #   (b) it transitioned to ACTIVE (status field changed)
    #   (c) title / description / trade category changed
    status_changed  = update_fields is None or 'status' in (update_fields or [])
    content_changed = _fields_changed(update_fields, _JOB_EMBEDDING_FIELDS)

    if created or status_changed or content_changed:
        logger.debug(
            "Job %s active and content changed — queuing embedding task.", instance.pk
        )
        compute_job_embedding_task.delay(str(instance.pk))


# ──────────────────────────────────────────────────────────────────────────────
#  JOB → required_skills  (M2M signal)
# ──────────────────────────────────────────────────────────────────────────────

@receiver(m2m_changed, sender=Job.required_skills.through)
def on_job_required_skills_changed(sender, instance, action, **kwargs):
    """
    Fires when skills are added to or removed from a Job's required_skills M2M.
    Skill names are part of the CLIP input text — re-encode.
    """
    from jobs.tasks import compute_job_embedding_task
    from jobs.models import Job

    if action in ('post_add', 'post_remove', 'post_clear'):
        if instance.status == Job.Status.ACTIVE:
            logger.debug(
                "Job %s required_skills changed — queuing embedding task.", instance.pk
            )
            compute_job_embedding_task.delay(str(instance.pk))