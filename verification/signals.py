"""
verification/signals.py
=======================
Auto-create a VerificationProfile whenever a new User is created.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings

from .models import VerificationProfile


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_verification_profile(sender, instance, created, **kwargs):
    if created:
        VerificationProfile.objects.get_or_create(user=instance)
