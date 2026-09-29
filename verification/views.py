"""
verification/views.py
=====================
All views for the TradeLink NG verification system.
"""

import logging
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import TemplateView, FormView
from django.http import JsonResponse

from .forms import NINForm, BVNForm, CACForm
from .models import VerificationProfile, VerificationAttempt
from .service.dojah_client import dojah
from core.ratelimit import rate_limit

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  Helper: get-or-create profile
# ─────────────────────────────────────────────────────────────────────────────

def _get_profile(user) -> VerificationProfile:
    profile, _ = VerificationProfile.objects.get_or_create(user=user)
    return profile


# ─────────────────────────────────────────────────────────────────────────────
#  Dashboard
# ─────────────────────────────────────────────────────────────────────────────

class VerificationDashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'verification/dashboard.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['vp'] = _get_profile(self.request.user)
        ctx['recent_attempts'] = VerificationAttempt.objects.filter(
            user=self.request.user
        ).order_by('-created')[:10]
        return ctx


# ─────────────────────────────────────────────────────────────────────────────
#  Level 1 — NIN
# ─────────────────────────────────────────────────────────────────────────────

class NINVerifyView(LoginRequiredMixin, FormView):
    template_name  = 'verification/nin_verify.html'
    form_class     = NINForm
    success_url    = reverse_lazy('verify:dashboard')

    @rate_limit(key='nin:{user}', limit=3, window=86400, message='Daily NIN verification limit reached (3 attempts). Please try again tomorrow.')
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            vp = _get_profile(request.user)
            if vp.nin_verified:
                messages.info(request, 'Your NIN has already been verified.')
                return redirect('verify:dashboard')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['vp'] = _get_profile(self.request.user)
        return ctx

    def form_valid(self, form):
        nin  = form.cleaned_data['nin']
        user = self.request.user

        # Log the attempt
        attempt = VerificationAttempt.objects.create(
            user            = user,
            ver_type        = VerificationAttempt.VerType.NIN,
            status          = VerificationAttempt.Status.PENDING,
            identifier_hint = nin[-4:],
        )

        # Call Dojah
        result = dojah.verify_nin(nin)

        if result['success']:
            attempt.status     = VerificationAttempt.Status.SUCCESS
            attempt.dojah_ref  = result['ref']
            attempt.save(update_fields=['status', 'dojah_ref'])

            vp = _get_profile(user)
            vp.nin_verified    = True
            vp.nin_verified_at = timezone.now()
            vp.nin_last4       = nin[-4:]
            vp.nin_dojah_ref   = result['ref']
            vp.save(update_fields=[
                'nin_verified', 'nin_verified_at', 'nin_last4',
                'nin_dojah_ref', 'updated',
            ])
            vp.recompute_level()

            messages.success(
                self.request,
                '✅ Identity verified! You now hold a Level 1 (Identity Verified) badge.',
            )
            return redirect(self.success_url)
        else:
            attempt.status        = VerificationAttempt.Status.FAILED
            attempt.error_message = result['error']
            attempt.dojah_ref     = result['ref']
            attempt.save(update_fields=['status', 'error_message', 'dojah_ref'])

            form.add_error(None, result['error'])
            return self.form_invalid(form)


# ─────────────────────────────────────────────────────────────────────────────
#  Level 2 — BVN
# ─────────────────────────────────────────────────────────────────────────────

class BVNVerifyView(LoginRequiredMixin, FormView):
    template_name  = 'verification/bvn_verify.html'
    form_class     = BVNForm
    success_url    = reverse_lazy('verify:dashboard')

    @rate_limit(key='bvn:{user}', limit=3, window=86400, message='Daily BVN verification limit reached (3 attempts). Please try again tomorrow.')
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            vp = _get_profile(request.user)
            if vp.bvn_verified:
                messages.info(request, 'Your BVN has already been verified.')
                return redirect('verify:dashboard')
            if not vp.nin_verified:
                messages.warning(request, 'Please complete NIN verification first.')
                return redirect('verify:nin')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['vp'] = _get_profile(self.request.user)
        return ctx

    def form_valid(self, form):
        bvn  = form.cleaned_data['bvn']
        user = self.request.user

        attempt = VerificationAttempt.objects.create(
            user            = user,
            ver_type        = VerificationAttempt.VerType.BVN,
            status          = VerificationAttempt.Status.PENDING,
            identifier_hint = bvn[-4:],
        )

        result = dojah.verify_bvn(bvn)

        if result['success']:
            attempt.status    = VerificationAttempt.Status.SUCCESS
            attempt.dojah_ref = result['ref']
            attempt.save(update_fields=['status', 'dojah_ref'])

            vp = _get_profile(user)
            vp.bvn_verified    = True
            vp.bvn_verified_at = timezone.now()
            vp.bvn_last4       = bvn[-4:]
            vp.bvn_dojah_ref   = result['ref']
            vp.save(update_fields=[
                'bvn_verified', 'bvn_verified_at', 'bvn_last4',
                'bvn_dojah_ref', 'updated',
            ])
            vp.recompute_level()

            messages.success(
                self.request,
                '✅ BVN verified! You now hold a Level 2 (Enhanced) badge.',
            )
            return redirect(self.success_url)
        else:
            attempt.status        = VerificationAttempt.Status.FAILED
            attempt.error_message = result['error']
            attempt.dojah_ref     = result['ref']
            attempt.save(update_fields=['status', 'error_message', 'dojah_ref'])

            form.add_error(None, result['error'])
            return self.form_invalid(form)


# ─────────────────────────────────────────────────────────────────────────────
#  Level 3 — CAC
# ─────────────────────────────────────────────────────────────────────────────

class CACVerifyView(LoginRequiredMixin, FormView):
    template_name  = 'verification/cac_verify.html'
    form_class     = CACForm
    success_url    = reverse_lazy('verify:dashboard')

    @rate_limit(key='cac:{user}', limit=5, window=86400, message='Daily CAC verification limit reached (5 attempts). Please try again tomorrow.')
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            vp = _get_profile(request.user)
            if vp.cac_verified:
                messages.info(request, 'Your CAC number has already been verified.')
                return redirect('verify:dashboard')
            if not vp.bvn_verified:
                messages.warning(request, 'Please complete BVN verification first.')
                return redirect('verify:bvn')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['vp'] = _get_profile(self.request.user)
        return ctx

    def form_valid(self, form):
        rc_number    = form.cleaned_data['rc_number']
        company_name = form.cleaned_data['company_name']
        user         = self.request.user

        attempt = VerificationAttempt.objects.create(
            user            = user,
            ver_type        = VerificationAttempt.VerType.CAC,
            status          = VerificationAttempt.Status.PENDING,
            identifier_hint = rc_number[-4:],
        )

        result = dojah.verify_cac(rc_number)

        if result['success']:
            attempt.status    = VerificationAttempt.Status.SUCCESS
            attempt.dojah_ref = result['ref']
            attempt.save(update_fields=['status', 'dojah_ref'])

            vp = _get_profile(user)
            vp.cac_verified    = True
            vp.cac_verified_at = timezone.now()
            vp.cac_rc_number   = rc_number
            vp.cac_company_name = company_name
            vp.cac_dojah_ref   = result['ref']
            vp.save(update_fields=[
                'cac_verified', 'cac_verified_at', 'cac_rc_number',
                'cac_company_name', 'cac_dojah_ref', 'updated',
            ])
            vp.recompute_level()

            messages.success(
                self.request,
                '✅ Business verified! You now hold a Level 3 (Trusted Business) badge.',
            )
            return redirect(self.success_url)
        else:
            attempt.status        = VerificationAttempt.Status.FAILED
            attempt.error_message = result['error']
            attempt.dojah_ref     = result['ref']
            attempt.save(update_fields=['status', 'error_message', 'dojah_ref'])

            form.add_error(None, result['error'])
            return self.form_invalid(form)


# ─────────────────────────────────────────────────────────────────────────────
#  Status API (JSON) — for AJAX polling from templates
# ─────────────────────────────────────────────────────────────────────────────

class VerificationStatusView(LoginRequiredMixin, TemplateView):
    """Returns the current verification level as JSON."""

    @rate_limit(key='ver_status:{user}', limit=60, window=60, message='Too many status checks.', json=True)
    def get(self, request, *args, **kwargs):
        vp = _get_profile(request.user)
        return JsonResponse({
            'level':       vp.level,
            'label':       vp.badge_label,
            'colour':      vp.badge_colour,
            'nin_verified': vp.nin_verified,
            'bvn_verified': vp.bvn_verified,
            'cac_verified': vp.cac_verified,
        })
