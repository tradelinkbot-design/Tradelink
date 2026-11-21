"""
digital_skills/signals.py
=========================
Signals for the digital_skills app.

1. Auto-create DigitalWorkerProfile when a digital_worker User is created.
2. Recompute profile completion after every DigitalWorkerProfile save.
3. Queue AI embedding re-computation when bio/headline/category change.
"""

import logging
from django.db.models.signals import post_save, m2m_changed
from django.dispatch import receiver

logger = logging.getLogger(__name__)

_EMBEDDING_FIELDS = frozenset({'headline', 'bio', 'primary_category', 'primary_category_id'})


def _fields_changed(update_fields, watched: frozenset) -> bool:
    if update_fields is None:
        return True
    return bool(frozenset(update_fields) & watched)


# ── 1. Auto-create DigitalWorkerProfile on User registration ─────────────────

@receiver(post_save, sender='users.User')
def create_digital_worker_profile(sender, instance, created, **kwargs):
    """
    When a new User with account_type == 'digital_worker' is created,
    automatically create their DigitalWorkerProfile.
    """
    if created and instance.account_type == 'digital_worker':
        from digital_skills.models import DigitalWorkerProfile
        DigitalWorkerProfile.objects.get_or_create(user=instance)
        logger.debug(
            "DigitalWorkerProfile auto-created for user %s", instance.pk
        )


# ── 2. Recompute profile completion on every save ────────────────────────────

@receiver(post_save, sender='digital_skills.DigitalWorkerProfile')
def on_digital_worker_profile_save(sender, instance, created, update_fields, **kwargs):
    """
    - Recomputes profile_completion after every save.
    - Queues AI text re-embedding when bio/headline/category change.
    """
    # Avoid infinite loop: skip if only profile_completion itself changed
    if update_fields is not None and update_fields == frozenset({'profile_completion', 'updated'}):
        return

    # Recompute completion score
    new_score = instance.compute_completion()
    if new_score != instance.profile_completion:
        sender.objects.filter(pk=instance.pk).update(profile_completion=new_score)
        logger.debug(
            "DigitalWorkerProfile %s completion updated to %s%%", instance.pk, new_score
        )

    # Queue re-embedding if text fields changed
    if _fields_changed(update_fields, _EMBEDDING_FIELDS):
        logger.debug(
            "DigitalWorkerProfile %s — text fields changed, queuing embedding.", instance.pk
        )
        # Embedding task is optional; only fires if Celery + fastembed are available
        try:
            from digital_skills.tasks import compute_digital_worker_embedding_task
            compute_digital_worker_embedding_task.delay(str(instance.pk))
        except Exception as exc:
            logger.warning("Could not queue digital worker embedding task: %s", exc)


# ── 3. Re-embed when sub-skills M2M changes ──────────────────────────────────

@receiver(m2m_changed, sender='digital_skills.DigitalWorkerSubSkill')
def on_digital_worker_skills_changed(sender, instance, action, **kwargs):
    """Re-queue embedding when sub-skills are added or removed."""
    if action in ('post_add', 'post_remove', 'post_clear'):
        logger.debug(
            "DigitalWorkerProfile %s sub_skills changed — queuing embedding.", instance.pk
        )
        try:
            from digital_skills.tasks import compute_digital_worker_embedding_task
            compute_digital_worker_embedding_task.delay(str(instance.pk))
        except Exception as exc:
            logger.warning("Could not queue digital worker embedding task: %s", exc)
