"""
verification/models.py
======================
TradeLink NG — Identity Verification System

Three verification tiers (Phone OTP removed for now):

  Level 0  UNVERIFIED     — no verification at all
  Level 1  IDENTITY       — NIN verified via Dojah
  Level 2  ENHANCED       — BVN verified via Dojah
  Level 3  BUSINESS       — CAC RC Number verified via Dojah

Each user gets one VerificationProfile (auto-created on registration).
Every call to Dojah is logged as a VerificationAttempt for audit purposes.
"""

import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone


# ─────────────────────────────────────────────────────────────────────────────
#  VERIFICATION PROFILE
# ─────────────────────────────────────────────────────────────────────────────

class VerificationProfile(models.Model):

    class Level(models.IntegerChoices):
        UNVERIFIED = 0, 'Unverified'
        IDENTITY   = 1, 'Identity Verified (NIN)'
        ENHANCED   = 2, 'Enhanced Verified (BVN)'
        BUSINESS   = 3, 'Business Verified (CAC)'

    id   = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='verification_profile',
    )

    # ── Overall tier ──────────────────────────────────────────────────────────
    level = models.IntegerField(
        choices=Level.choices,
        default=Level.UNVERIFIED,
        db_index=True,
    )

    # ── NIN (Level 1) ─────────────────────────────────────────────────────────
    nin_verified       = models.BooleanField(default=False)
    nin_verified_at    = models.DateTimeField(null=True, blank=True)
    # We store the last 4 digits only — never the full NIN for privacy
    nin_last4          = models.CharField(max_length=4, blank=True)
    nin_dojah_ref      = models.CharField(max_length=120, blank=True,
                                          help_text='Dojah transaction reference')

    # ── BVN (Level 2) ─────────────────────────────────────────────────────────
    bvn_verified       = models.BooleanField(default=False)
    bvn_verified_at    = models.DateTimeField(null=True, blank=True)
    bvn_last4          = models.CharField(max_length=4, blank=True)
    bvn_dojah_ref      = models.CharField(max_length=120, blank=True)

    # ── CAC (Level 3) ─────────────────────────────────────────────────────────
    cac_verified       = models.BooleanField(default=False)
    cac_verified_at    = models.DateTimeField(null=True, blank=True)
    cac_rc_number      = models.CharField(max_length=30, blank=True)
    cac_company_name   = models.CharField(max_length=200, blank=True)
    cac_dojah_ref      = models.CharField(max_length=120, blank=True)

    # ── Metadata ──────────────────────────────────────────────────────────────
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Verification Profile'
        verbose_name_plural = 'Verification Profiles'

    def __str__(self):
        return f'{self.user.username} — {self.get_level_display()}'

    # ── Convenience properties ────────────────────────────────────────────────

    @property
    def badge_label(self):
        return {
            0: 'Unverified',
            1: 'ID Verified',
            2: 'Enhanced',
            3: 'Trusted Business',
        }.get(self.level, 'Unverified')

    @property
    def badge_colour(self):
        """CSS class suffix for the badge colour."""
        return {
            0: 'grey',
            1: 'blue',
            2: 'gold',
            3: 'green',
        }.get(self.level, 'grey')

    @property
    def badge_icon(self):
        return {
            0: 'fas fa-user-slash',
            1: 'fas fa-id-card',
            2: 'fas fa-shield-alt',
            3: 'fas fa-building',
        }.get(self.level, 'fas fa-user-slash')

    @property
    def next_level(self):
        """Returns the next Level integer or None if at max."""
        if self.level < 3:
            return self.level + 1
        return None

    @property
    def next_level_label(self):
        labels = {1: 'NIN Verification', 2: 'BVN Verification', 3: 'CAC Verification'}
        return labels.get(self.next_level, '')

    @property
    def next_verify_url_name(self):
        urls = {1: 'verify:nin', 2: 'verify:bvn', 3: 'verify:cac'}
        return urls.get(self.next_level, '')

    def recompute_level(self):
        """
        Re-derive the overall level from the individual flag fields and save.
        Called after every successful Dojah check.
        """
        if self.cac_verified:
            self.level = self.Level.BUSINESS
        elif self.bvn_verified:
            self.level = self.Level.ENHANCED
        elif self.nin_verified:
            self.level = self.Level.IDENTITY
        else:
            self.level = self.Level.UNVERIFIED
        self.save(update_fields=['level', 'updated'])

    # ── Gate helpers (used by decorators / template tags) ─────────────────────

    def can_list_product(self):
        """Creating a marketplace listing requires NIN verification."""
        return self.level >= self.Level.IDENTITY

    def can_do_large_escrow(self):
        """Escrow transactions above ₦50 000 require BVN verification."""
        return self.level >= self.Level.ENHANCED

    def can_post_corporate_job(self):
        """Corporate / Government job postings require CAC verification."""
        return self.level >= self.Level.BUSINESS


# ─────────────────────────────────────────────────────────────────────────────
#  VERIFICATION ATTEMPT  (audit log)
# ─────────────────────────────────────────────────────────────────────────────

class VerificationAttempt(models.Model):

    class VerType(models.TextChoices):
        NIN = 'nin', 'NIN'
        BVN = 'bvn', 'BVN'
        CAC = 'cac', 'CAC'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SUCCESS = 'success', 'Success'
        FAILED  = 'failed',  'Failed'
        ERROR   = 'error',   'API Error'

    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user            = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='verification_attempts',
    )
    ver_type        = models.CharField(max_length=10, choices=VerType.choices)
    status          = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING,
    )

    # The identifier submitted (partially masked for privacy)
    identifier_hint = models.CharField(
        max_length=40, blank=True,
        help_text='Last 4 chars of the submitted ID, for audit display only.',
    )

    dojah_ref       = models.CharField(max_length=200, blank=True)
    error_message   = models.TextField(blank=True)

    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Verification Attempt'
        verbose_name_plural = 'Verification Attempts'
        ordering            = ['-created']

    def __str__(self):
        return f'{self.user.username} {self.ver_type} — {self.status}'
