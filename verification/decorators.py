"""
verification/decorators.py
===========================
View decorators and CBV mixins for gating access by verification level.

Usage (function-based view):
    @verification_required(level=1)
    def my_view(request): ...

Usage (class-based view):
    class MyView(VerificationRequiredMixin, View):
        required_verification_level = 1
        verification_redirect_url   = 'verify:nin'
"""

from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required

from .models import VerificationProfile


LEVEL_REDIRECT = {
    1: 'verify:nin',
    2: 'verify:bvn',
    3: 'verify:cac',
}

LEVEL_LABEL = {
    1: 'NIN (Identity Verification)',
    2: 'BVN (Enhanced Verification)',
    3: 'CAC (Business Verification)',
}


def _get_profile(user):
    profile, _ = VerificationProfile.objects.get_or_create(user=user)
    return profile


def verification_required(level: int = 1):
    """
    Decorator that ensures the logged-in user has at least `level` verification.
    Redirects to the appropriate verification form if not.
    """
    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            vp = _get_profile(request.user)
            if vp.level < level:
                label    = LEVEL_LABEL.get(level, 'Verification')
                redirect_name = LEVEL_REDIRECT.get(level, 'verify:dashboard')
                messages.warning(
                    request,
                    f'You need to complete {label} before accessing this feature.',
                )
                return redirect(redirect_name)
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


class VerificationRequiredMixin:
    """
    CBV mixin. Set `required_verification_level` on your view class.
    """
    required_verification_level = 1

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())

        vp = _get_profile(request.user)
        level = self.required_verification_level

        if vp.level < level:
            label         = LEVEL_LABEL.get(level, 'Verification')
            redirect_name = LEVEL_REDIRECT.get(level, 'verify:dashboard')
            messages.warning(
                request,
                f'You need to complete {label} before accessing this feature.',
            )
            return redirect(redirect_name)

        return super().dispatch(request, *args, **kwargs)
