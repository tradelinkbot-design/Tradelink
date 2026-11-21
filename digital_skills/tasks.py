"""
digital_skills/tasks.py
=======================
Celery tasks for the digital_skills app.

Mirrors the pattern used in jobs/tasks.py.
"""

import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def compute_digital_worker_embedding_task(self, profile_pk: str):
    """
    Encode a DigitalWorkerProfile's text (headline + bio + category + sub-skills)
    using the sentence-transformer and store the embedding.
    """
    try:
        from digital_skills.models import DigitalWorkerProfile
        from jobs.service.text_encoder import encoder   # re-use the shared encoder
        from django.utils import timezone

        profile = DigitalWorkerProfile.objects.select_related(
            'primary_category'
        ).prefetch_related('sub_skills').get(pk=profile_pk)

        parts = []
        if profile.primary_category:
            parts.append(profile.primary_category.name)
        if profile.headline:
            parts.append(profile.headline)
        if profile.bio:
            parts.append(profile.bio)
        sub_skills = list(profile.sub_skills.values_list('name', flat=True))
        if sub_skills:
            parts.append(', '.join(sub_skills))

        text = '. '.join(parts)
        if not text.strip():
            logger.warning("DigitalWorkerProfile %s has no text to embed.", profile_pk)
            return

        embedding = encoder.encode(text)

        DigitalWorkerProfile.objects.filter(pk=profile_pk).update(
            text_embedding=embedding,
            text_embedding_updated=timezone.now(),
        )
        logger.info("DigitalWorkerProfile %s embedding updated.", profile_pk)

    except DigitalWorkerProfile.DoesNotExist:
        logger.warning("DigitalWorkerProfile %s not found — skipping.", profile_pk)
    except Exception as exc:
        logger.error("Error embedding DigitalWorkerProfile %s: %s", profile_pk, exc)
        raise self.retry(exc=exc)
