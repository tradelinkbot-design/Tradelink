"""
hiring/signals.py
=================
Django signals for the hiring app.
All notification side-effects live here — views stay thin.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import HiringInterest, SkillEndorsement, SavedWorker


@receiver(post_save, sender=HiringInterest)
def hiring_interest_status_changed(sender, instance, created, **kwargs):
    """
    When an employer replies HIRED, send a congratulations notification
    to the worker.
    """
    if not created and instance.status == HiringInterest.Status.HIRED:
        from jobs.models import Notification
        Notification.objects.get_or_create(
            user       = instance.worker.user,
            notif_type = 'hiring_interest_replied',
            title      = f'Congratulations! {instance.employer} has marked you as Hired',
            defaults={
                'body': (
                    'Update your profile availability and keep applying to more opportunities.'
                ),
                'data': {'interest_id': str(instance.pk)},
            },
        )
