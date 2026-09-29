"""
users/adapters.py
─────────────────
Custom django-allauth adapters for TradeLink NG.

AccountAdapter     – standard email/password flow tweaks.
SocialAccountAdapter – social-login helpers:
  • auto-generates a unique username from the social provider email.
  • connects a new social login to any existing account that shares
    the same verified email (avoids duplicate accounts).
"""

import re

from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings


# ────────────────────────────────────────────────────────────────────────────
# Standard (email/password) adapter
# ────────────────────────────────────────────────────────────────────────────

class AccountAdapter(DefaultAccountAdapter):
    """Light-touch override of the default account adapter."""

    def is_open_for_signup(self, request):
        return True


# ────────────────────────────────────────────────────────────────────────────
# Social-account adapter
# ────────────────────────────────────────────────────────────────────────────

class SocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Adapter for Google / LinkedIn / Facebook social logins.

    Key behaviours
    ──────────────
    1.  pre_social_login  – if the provider's verified email already belongs
        to a local account, *connect* the social token to that account rather
        than creating a duplicate user.

    2.  populate_user – auto-build a unique username from the social email
        so the User model's unique constraint on `username` is always satisfied.

    3.  save_user – phone_number is left NULL (it is now nullable); the
        `CompleteProfileView` captures it on the user's first visit after
        social sign-up.
    """

    def is_open_for_signup(self, request, socialaccount):
        return True

    def get_app(self, request, provider, client_id=None):
        """
        Safely retrieve the SocialApp for the given provider.
        - If not configured in DB or settings, returns a placeholder SocialApp
          so templates with {% provider_login_url %} never crash with DoesNotExist.
        - If both DB and settings exist, chooses the configured one to avoid MultipleObjectsReturned.
        """
        import os
        from allauth.socialaccount.models import SocialApp

        apps = self.list_apps(request, provider=provider, client_id=client_id)
        if not apps:
            return SocialApp(
                provider=provider,
                name=provider.title(),
                client_id=os.environ.get(f'{provider.upper()}_CLIENT_ID', ''),
                secret=os.environ.get(f'{provider.upper()}_CLIENT_SECRET', ''),
            )
        if len(apps) > 1:
            configured = [a for a in apps if getattr(a, 'client_id', '')]
            return configured[0] if configured else apps[0]
        return apps[0]

    # ── 1. Email-based account linking ───────────────────────────────────────

    def pre_social_login(self, request, sociallogin):
        """
        Called just before a social login is processed.

        If the email returned by the OAuth provider already exists in our
        database, silently connect the social account to that user so they
        can sign in with either method going forward.
        """
        from users.models import User

        # Already linked to a local user — nothing to do.
        if sociallogin.is_existing:
            return

        email = (
            (sociallogin.account.extra_data or {}).get('email') or ''
        ).strip().lower()

        if not email:
            return

        try:
            existing_user = User.objects.get(email=email)
            # Attach this social account to the existing user.
            sociallogin.connect(request, existing_user)
        except User.DoesNotExist:
            pass   # brand-new email → normal social sign-up flow

    # ── 2. Auto-generate a unique username ───────────────────────────────────

    def populate_user(self, request, sociallogin, data):
        """
        Build the User object from social data.

        If no username is available (Google, Facebook, LinkedIn don't
        provide one), derive it from the email local-part, sanitise it,
        and suffix a counter until it is unique.
        """
        from users.models import User

        user = super().populate_user(request, sociallogin, data)

        if not getattr(user, 'username', None):
            email = (data.get('email') or '').strip()
            local_part = email.split('@')[0] if email else 'user'
            # Keep only letters, digits, underscores; cap at 20 chars.
            base = re.sub(r'[^a-zA-Z0-9_]', '_', local_part)[:20] or 'user'

            username, counter = base, 1
            while User.objects.filter(username=username).exists():
                username = f'{base}_{counter}'
                counter += 1

            user.username = username

        return user

    # ── 3. Save without phone_number ─────────────────────────────────────────

    def save_user(self, request, sociallogin, form=None):
        """
        Persist the social user.  phone_number is intentionally omitted
        here (it is nullable in the model); CompleteProfileView collects
        it on the user's first post-login visit.
        """
        user = super().save_user(request, sociallogin, form)
        return user