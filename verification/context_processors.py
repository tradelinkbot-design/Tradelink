"""
verification/context_processors.py
====================================
Injects the user's VerificationProfile into every template context,
so that trust badges, banners, and gate checks work universally
without modifying individual views.
"""

from .models import VerificationProfile


def verification_context(request):
    if request.user.is_authenticated:
        try:
            vp = request.user.verification_profile
        except VerificationProfile.DoesNotExist:
            vp, _ = VerificationProfile.objects.get_or_create(user=request.user)
        return {'verification_profile': vp}
    return {'verification_profile': None}
