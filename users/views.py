import logging

import requests
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth import views as auth_views
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin

from .forms import RegisterForm, LoginForm
from core.ratelimit import rate_limit

logger = logging.getLogger(__name__)

FLW_BASE = 'https://api.flutterwave.com/v3'


def _flw_headers():
    from django.conf import settings
    sk = getattr(settings, 'FLW_SECRET_KEY', '')
    return {
        'Authorization': f'Bearer {sk}',
        'Content-Type': 'application/json',
        'accept': 'application/json',
    }


# Keep old alias so any indirect references still resolve
PAYSTACK_BASE = FLW_BASE
_paystack_headers = _flw_headers


# ─────────────────────────────────────────────────────────────────────────────
# Auth Views
# ─────────────────────────────────────────────────────────────────────────────

class RegisterView(View):
    """
    Handles the 3-step registration wizard at accounts:register.

    GET  → render the empty form (step 1 is shown by JS by default).
    POST → validate the whole form; on success redirect to login; on failure
           re-render so Django template error tags auto-jump JS to the right step.
    """

    template_name = 'accounts/register.html'

    def get(self, request):
        if request.user.is_authenticated:
            return redirect('/')

        form = RegisterForm()
        return render(request, self.template_name, {'form': form})

    @rate_limit(key='register:{ip}', limit=5, window=3600, message='Too many registration attempts. Please try again later.')
    def post(self, request):
        if request.user.is_authenticated:
            return redirect('/')

        form = RegisterForm(request.POST)

        if form.is_valid():
            form.save()
            messages.success(
                request,
                'Your account has been created! Sign in to get started.'
            )
            return redirect('signin')

        return render(request, self.template_name, {'form': form})


class SignInView(View):
    """
    Handles email + password login at accounts:signin.

    GET  → render the empty login form.
    POST → validate credentials; on success log the user in and redirect to
           the 'next' param (or home); on failure re-render with errors.

    'Remember me' behaviour:
        Checked   → session persists for 2 weeks (SESSION_COOKIE_AGE default).
        Unchecked → session expires when the browser is closed.
    """

    template_name = 'accounts/login.html'

    def get(self, request):
        if request.user.is_authenticated:
            return redirect('marketplace:dashboard')

        form = LoginForm()
        return render(request, self.template_name, {'form': form})

    @rate_limit(key='signin:{ip}', limit=10, window=600, message='Too many login attempts. Please try again in 10 minutes.')
    def post(self, request):
        if request.user.is_authenticated:
            return redirect('marketplace:dashboard')

        form = LoginForm(request.POST)

        if form.is_valid():
            user = form.get_user()

            # "Remember me" — if unchecked, expire session on browser close
            if not request.POST.get('remember'):
                request.session.set_expiry(0)

            login(request, user)

            messages.success(request, f'Welcome back, {user.username}!')

            # Honour the ?next= redirect set by @login_required, etc.
            next_url = request.GET.get('next') or request.POST.get('next') or 'marketplace:dashboard'
            return redirect(next_url)

        # Invalid credentials — re-render with form errors
        return render(request, self.template_name, {'form': form})


class SignOutView(View):
    """POST-only logout endpoint."""

    def post(self, request):
        logout(request)
        messages.info(request, 'You have been signed out.')
        return redirect('signin')


# ─────────────────────────────────────────────────────────────────────────────
# Profile Views
# ─────────────────────────────────────────────────────────────────────────────

class EditProfileView(LoginRequiredMixin, View):
    """
    GET  /profile/edit/  → show edit profile form
    POST /profile/edit/  → save changes
    """

    login_url = 'signin'
    template_name = 'accounts/edit_profile.html'

    def get(self, request):
        from jobs.models import WorkerBankAccount
        worker_profile = getattr(request.user, 'worker_profile', None)
        bank_account = None
        if worker_profile:
            bank_account = WorkerBankAccount.objects.filter(worker=worker_profile).first()

        return render(request, self.template_name, {
            'user': request.user,
            'worker_profile': worker_profile,
            'bank_account': bank_account,
        })

    def post(self, request):
        user = request.user
        user.first_name = request.POST.get('first_name', user.first_name).strip()
        user.last_name  = request.POST.get('last_name',  user.last_name).strip()

        if 'profile_image' in request.FILES:
            print("This is the profile image", request.FILES['profile_image'])
            user.image = request.FILES['profile_image']
            
        else:
            print("There is no profile image")
            
            

        user.save()
        messages.success(request, 'Profile updated successfully.')
        return redirect('edit_profile')


class BankAccountProfileView(LoginRequiredMixin, View):
    """
    POST /profile/bank-account/

    Save (or update) the user's bank account details, then asynchronously
    mark the account ready for Flutterwave payouts.

    Supports both regular form POST and AJAX (fetch) calls — detected via
    the X-Requested-With header or Accept: application/json.
    """

    login_url = 'signin'

    def post(self, request):
        is_ajax = (
            request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            or 'application/json' in request.headers.get('Accept', '')
        )

        account_number = request.POST.get('account_number', '').strip()
        bank_code      = request.POST.get('bank_code', '').strip()
        bank_name      = request.POST.get('bank_name', '').strip()
        account_name   = request.POST.get('account_name', '').strip()

        # Basic validation
        if not all([account_number, bank_code, bank_name, account_name]):
            msg = 'All bank account fields are required.'
            if is_ajax:
                return JsonResponse({'ok': False, 'error': msg}, status=400)
            messages.error(request, msg)
            return redirect('edit_profile')

        if len(account_number) != 10 or not account_number.isdigit():
            msg = 'Account number must be exactly 10 digits.'
            if is_ajax:
                return JsonResponse({'ok': False, 'error': msg}, status=400)
            messages.error(request, msg)
            return redirect('edit_profile')

        # Ensure worker profile exists
        from jobs.models import WorkerBankAccount
        worker_profile = getattr(request.user, 'worker_profile', None)
        if not worker_profile:
            # Auto-create a minimal WorkerProfile for marketplace sellers too
            from jobs.models import WorkerProfile
            worker_profile, _ = WorkerProfile.objects.get_or_create(user=request.user)

        bank_account, created = WorkerBankAccount.objects.update_or_create(
            worker=worker_profile,
            defaults={
                'account_number':          account_number,
                'account_name':            account_name,
                'bank_code':               bank_code,
                'bank_name':               bank_name,
                'paystack_recipient_code': '',   # reset — will be re-validated async
                'is_verified':             False,
            },
        )

        # Trigger async transfer recipient creation/validation task
        try:
            from jobs.tasks import create_transfer_recipient_task
            create_transfer_recipient_task.delay(str(bank_account.pk))
        except Exception:
            logger.exception(
                "BankAccountProfileView: could not queue recipient task for %s",
                bank_account.pk
            )

        action = 'added' if created else 'updated'

        if is_ajax:
            return JsonResponse({
                'ok': True,
                'action': action,
                'account_name': bank_account.account_name,
                'bank_name':    bank_account.bank_name,
                'masked':       f'****{bank_account.account_number[-4:]}',
            })

        messages.success(
            request,
            f'Bank account {action} successfully. Verification in progress.'
        )
        return redirect('edit_profile')


# ─────────────────────────────────────────────────────────────────────────────
# Flutterwave Proxy Endpoints (AJAX — keeps secret key server-side)
# ─────────────────────────────────────────────────────────────────────────────

class BankResolveAPIView(LoginRequiredMixin, View):
    """
    GET /bank-resolve/?account_number=0123456789&bank_code=044

    Server-side proxy for Flutterwave's POST /accounts/resolve endpoint.
    Returns the verified account name in real-time as the user types.
    Keeping this server-side prevents exposing the Flutterwave secret key.
    """

    login_url = 'signin'

    @rate_limit(key='bank_resolve:{user}', limit=30, window=60, message='Too many account lookup requests. Please slow down.', json=True)
    def get(self, request):
        account_number = request.GET.get('account_number', '').strip()
        bank_code      = request.GET.get('bank_code', '').strip()

        if not account_number or not bank_code:
            return JsonResponse(
                {'error': 'account_number and bank_code are required.'},
                status=400
            )

        if len(account_number) != 10 or not account_number.isdigit():
            return JsonResponse(
                {'error': 'Account number must be exactly 10 digits.'},
                status=400
            )

        try:
            resp = requests.post(
                f'{FLW_BASE}/accounts/resolve',
                json={'account_number': account_number, 'account_bank': bank_code},
                headers=_flw_headers(),
                timeout=15,
            )
            data = resp.json()
        except requests.RequestException as exc:
            logger.error("BankResolveAPIView: request failed: %s", exc)
            return JsonResponse(
                {'error': 'Could not reach payment provider. Try again.'},
                status=502
            )

        if data.get('status') == 'success' and data.get('data'):
            return JsonResponse({
                'account_name':   data['data'].get('account_name', ''),
                'account_number': data['data'].get('account_number', account_number),
            })

        logger.warning(
            "BankResolveAPIView: Flutterwave returned HTTP %s: %s",
            resp.status_code, resp.text[:200]
        )
        error_msg = data.get(
            'message',
            'Could not resolve account. Check the number and bank.'
        )

        from django.conf import settings
        sk = getattr(settings, 'FLW_SECRET_KEY', '')
        if 'invalid account' in error_msg.lower() and ('_TEST' in sk or sk.startswith('FLWSECK_TEST')):
            error_msg = (
                "Flutterwave Sandbox (Test Mode) does not verify real bank accounts. "
                "Use test account: 0690000032 with Access Bank."
            )

        return JsonResponse({'error': error_msg}, status=422)


NIGERIAN_BANKS_FALLBACK = [
    {'name': 'Access Bank', 'code': '044'},
    {'name': 'Access Bank (Diamond)', 'code': '063'},
    {'name': 'Citibank Nigeria', 'code': '023'},
    {'name': 'Ecobank Nigeria', 'code': '050'},
    {'name': 'Fidelity Bank', 'code': '070'},
    {'name': 'First Bank of Nigeria', 'code': '011'},
    {'name': 'First City Monument Bank (FCMB)', 'code': '214'},
    {'name': 'Globus Bank', 'code': '00103'},
    {'name': 'Guaranty Trust Bank (GTBank)', 'code': '058'},
    {'name': 'Heritage Bank', 'code': '030'},
    {'name': 'Jaiz Bank', 'code': '301'},
    {'name': 'Keystone Bank', 'code': '082'},
    {'name': 'Kuda Bank', 'code': '50211'},
    {'name': 'Lotus Bank', 'code': '303'},
    {'name': 'Moniepoint Microfinance Bank', 'code': '50515'},
    {'name': 'OPay Digital Services', 'code': '999992'},
    {'name': 'Optimus Bank', 'code': '107'},
    {'name': 'PalmPay', 'code': '999991'},
    {'name': 'Parallex Bank', 'code': '104'},
    {'name': 'Polaris Bank', 'code': '076'},
    {'name': 'PremiumTrust Bank', 'code': '105'},
    {'name': 'Providus Bank', 'code': '101'},
    {'name': 'Stanbic IBTC Bank', 'code': '221'},
    {'name': 'Standard Chartered Bank', 'code': '068'},
    {'name': 'Sterling Bank', 'code': '232'},
    {'name': 'Suntrust Bank', 'code': '100'},
    {'name': 'TAJ Bank', 'code': '302'},
    {'name': 'Titan Trust Bank', 'code': '102'},
    {'name': 'Union Bank of Nigeria', 'code': '032'},
    {'name': 'United Bank for Africa (UBA)', 'code': '033'},
    {'name': 'Unity Bank', 'code': '215'},
    {'name': 'Wema Bank', 'code': '035'},
    {'name': 'Zenith Bank', 'code': '057'},
]


class BankListAPIView(LoginRequiredMixin, View):
    """
    GET /bank-list/

    Returns the list of Nigerian banks from Flutterwave, cached for 24 h in
    the Django session to avoid hammering the Flutterwave API on every page load.
    Falls back gracefully to a standard list if Flutterwave is unreachable or
    credentials are not yet configured.
    """

    login_url = 'signin'

    def get(self, request):
        cached = request.session.get('flw_bank_list')
        if cached:
            return JsonResponse({'banks': cached})

        from django.conf import settings
        sk = getattr(settings, 'FLW_SECRET_KEY', '')
        if not sk:
            return JsonResponse({'banks': NIGERIAN_BANKS_FALLBACK})

        try:
            resp = requests.get(
                f'{FLW_BASE}/banks/NG',
                headers=_flw_headers(),
                timeout=15,
            )
            data = resp.json()
        except requests.RequestException as exc:
            logger.warning("BankListAPIView: Flutterwave request exception: %s. Using fallback list.", exc)
            return JsonResponse({'banks': NIGERIAN_BANKS_FALLBACK})

        if data.get('status') == 'success' and data.get('data'):
            banks = [
                {'name': b['name'], 'code': b['code']}
                for b in data['data']
            ]
            request.session['flw_bank_list'] = banks
            return JsonResponse({'banks': banks})

        logger.info(
            "BankListAPIView: Flutterwave endpoint returned HTTP %s. Serving fallback Nigerian bank list.",
            resp.status_code
        )
        return JsonResponse({'banks': NIGERIAN_BANKS_FALLBACK})


# ─────────────────────────────────────────────────────────────────────────────
# Password Reset
# ─────────────────────────────────────────────────────────────────────────────

class PasswordResetRequestView(auth_views.PasswordResetView):
    """
    Step 1 — password_reset

    Shows the "enter your email" form and, on submit, emails a tokenised
    reset link if an account exists for that address.
    """

    template_name         = 'accounts/password_reset.html'
    subject_template_name = 'accounts/password_reset_subject.txt'
    email_template_name   = 'accounts/password_reset_email.txt'
    html_email_template_name = 'accounts/password_reset_email.html'
    success_url           = reverse_lazy('password_reset_done')

    @rate_limit(key='pw_reset:{ip}', limit=5, window=1800, message='Too many password reset requests. Please try again in 30 minutes.')
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['email'].widget.attrs.update({
            'class': 'form-control has-icon',
            'placeholder': 'you@example.com',
            'autocomplete': 'email',
        })
        return form


class PasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    """
    Step 3 — password_reset_confirm/<uidb64>/<token>/

    Reached via the link in the email. Validates the uid/token pair and,
    if valid, shows the "set a new password" form.
    """

    template_name = 'accounts/password_reset_confirm.html'
    success_url   = reverse_lazy('password_reset_complete')

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['new_password1'].widget.attrs.update({
            'class': 'form-control has-icon',
            'placeholder': 'New password',
            'autocomplete': 'new-password',
        })
        form.fields['new_password2'].widget.attrs.update({
            'class': 'form-control has-icon',
            'placeholder': 'Confirm new password',
            'autocomplete': 'new-password',
        })
        return form