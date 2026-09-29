"""
hiring/models.py
================
TradeLink NG — LinkedIn-mode hiring layer.

All models here are purely about professional identity and permanent-employment
matching.  No money, no escrow, no Paystack.  The financial/gig side lives in
the jobs app; this app is about *careers*.

Models
──────
  1.  WorkHistory       — past employers & roles (LinkedIn "Experience")
  2.  Certification     — formal trade certificates
  3.  SkillEndorsement  — peer/employer skill confirmations
  4.  SavedWorker       — employer shortlists a worker (mirror of SavedJob)
  5.  HiringInterest    — employer sends a direct hire outreach to a worker
  6.  SubscriptionPlan  — employer pricing tiers (data-only; billing in Phase 4)
  7.  EmployerSubscription — active employer subscription
"""

import uuid
from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator

from jobs.models import (
    WorkerProfile,
    EmployerProfile,
    Skill,
    TradeCategory,
    Job,
    NIGERIAN_STATES,
)


# ──────────────────────────────────────────────────────────────────────────────
#  1.  WORK HISTORY
#      A worker's past employment record — like LinkedIn's "Experience" section.
# ──────────────────────────────────────────────────────────────────────────────

class WorkHistory(models.Model):
    """
    One past employment entry for a WorkerProfile.

    Workers add these manually during profile setup.  They are displayed
    chronologically on the public profile and included in the CV PDF.
    """

    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    worker          = models.ForeignKey(
        WorkerProfile, on_delete=models.CASCADE,
        related_name='work_history',
    )
    employer_name   = models.CharField(
        max_length=200,
        help_text='Name of the company, contractor, or client you worked for.',
    )
    role_title      = models.CharField(
        max_length=200,
        help_text='Your job title, e.g. Lead Electrician, Site Foreman, Head Plumber.',
    )
    trade_category  = models.ForeignKey(
        TradeCategory, on_delete=models.SET_NULL,
        null=True, blank=True,
        help_text='Which trade discipline this role fell under.',
    )
    description     = models.TextField(
        blank=True,
        help_text='What you did, what you built or fixed, tools & techniques used.',
    )
    start_date      = models.DateField(help_text='When you started this role (YYYY-MM-DD).')
    end_date        = models.DateField(
        null=True, blank=True,
        help_text='When you left. Leave blank if this is your current role.',
    )
    is_current      = models.BooleanField(
        default=False,
        help_text='Tick if this is your current employer.',
    )
    location_state  = models.CharField(
        max_length=40, choices=NIGERIAN_STATES, blank=True,
        help_text='Which state the work was based in.',
    )
    created_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Work History Entry'
        verbose_name_plural = 'Work History'
        ordering            = ['-start_date']

    def __str__(self):
        end = 'Present' if self.is_current else str(self.end_date.year if self.end_date else '')
        return f'{self.worker.user.username} — {self.role_title} @ {self.employer_name} ({self.start_date.year}–{end})'

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.end_date and self.start_date and self.end_date < self.start_date:
            raise ValidationError('End date cannot be before start date.')
        if self.is_current and self.end_date:
            raise ValidationError('A current role cannot have an end date.')

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


# ──────────────────────────────────────────────────────────────────────────────
#  2.  CERTIFICATION
#      Formal qualifications and trade certificates.
# ──────────────────────────────────────────────────────────────────────────────

class Certification(models.Model):
    """
    A formal certificate or qualification held by a worker.

    Examples:
        NABTEB Electrical Installation — 2018
        City & Guilds Level 2 Plumbing — 2020
        SON Solar PV Installer Certificate — 2022
        COREN Registered Engineer — 2021

    Workers upload a photo of the physical certificate.  Admins can verify
    it (is_verified = True) which shows a blue verified badge on the profile.
    """

    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    worker          = models.ForeignKey(
        WorkerProfile, on_delete=models.CASCADE,
        related_name='certifications',
    )
    name            = models.CharField(
        max_length=200,
        help_text='Full name of the certificate, e.g. NABTEB Electrical Installation Certificate.',
    )
    issuing_body    = models.CharField(
        max_length=200,
        help_text='Organisation that issued the certificate, e.g. NABTEB, SON, City & Guilds, COREN.',
    )
    year_obtained   = models.PositiveSmallIntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(1980), MaxValueValidator(2100)],
        help_text='Year the certificate was awarded.',
    )
    certificate_image = models.ImageField(
        upload_to='certifications/%Y/%m/',
        null=True, blank=True,
        help_text='Upload a clear photo or scan of your certificate for verification.',
    )
    is_verified     = models.BooleanField(
        default=False,
        help_text='Set by admin after reviewing the uploaded certificate image.',
    )
    created_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Certification'
        verbose_name_plural = 'Certifications'
        ordering            = ['-year_obtained', 'name']

    def __str__(self):
        return f'{self.name} — {self.worker.user.username} ({self.year_obtained or "Year unknown"})'


# ──────────────────────────────────────────────────────────────────────────────
#  3.  SKILL ENDORSEMENT
#      Peer/employer confirmation that a worker has a specific skill.
# ──────────────────────────────────────────────────────────────────────────────

class SkillEndorsement(models.Model):
    """
    One user endorses a specific skill on another user's WorkerProfile.

    Rules:
    - Each user can only endorse a given skill on a given worker once
      (enforced by unique_together).
    - Workers cannot endorse their own skills.
    - Both employers and other workers can endorse.

    The count of endorsements per skill is shown as a badge on the
    public profile, e.g. "Solar Panel Wiring ×12".
    """

    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    worker      = models.ForeignKey(
        WorkerProfile, on_delete=models.CASCADE,
        related_name='endorsements_received',
    )
    skill       = models.ForeignKey(
        Skill, on_delete=models.CASCADE,
        related_name='endorsements',
    )
    endorsed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='endorsements_given',
    )
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('worker', 'skill', 'endorsed_by')
        ordering        = ['-created_at']
        verbose_name    = 'Skill Endorsement'

    def __str__(self):
        return f'{self.endorsed_by.username} endorsed {self.worker.user.username} for {self.skill.name}'

    def clean(self):
        from django.core.exceptions import ValidationError
        if hasattr(self.endorsed_by, 'worker_profile') and \
                self.endorsed_by.worker_profile == self.worker:
            raise ValidationError('Workers cannot endorse their own skills.')


# ──────────────────────────────────────────────────────────────────────────────
#  4.  SAVED WORKER
#      Employer bookmarks / shortlists a worker profile.
#      Mirror of the existing SavedJob model in jobs/models.py.
# ──────────────────────────────────────────────────────────────────────────────

class SavedWorker(models.Model):
    """
    An employer saves a worker profile for later review.

    This is the employer-side equivalent of the SavedJob model
    used by workers.  Saved workers appear in the employer's shortlist.
    """

    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer    = models.ForeignKey(
        EmployerProfile, on_delete=models.CASCADE,
        related_name='saved_workers',
    )
    worker      = models.ForeignKey(
        WorkerProfile, on_delete=models.CASCADE,
        related_name='saved_by_employers',
    )
    note        = models.TextField(
        blank=True,
        help_text='Private employer note — only visible to you, not the worker.',
    )
    saved_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('employer', 'worker')
        ordering        = ['-saved_at']
        verbose_name    = 'Saved Worker'

    def __str__(self):
        return f'{self.employer} saved {self.worker.user.username}'


# ──────────────────────────────────────────────────────────────────────────────
#  5.  HIRING INTEREST
#      Core LinkedIn-mode action: employer reaches out to worker directly.
#      This flips the traditional flow — company finds worker, not the other
#      way around.
# ──────────────────────────────────────────────────────────────────────────────

class HiringInterest(models.Model):
    """
    A formal expression of hiring interest sent by an employer to a worker.

    Flow:
        Employer finds worker via Talent Search
        → Employer clicks "Contact" → fills HiringInterestForm
        → HiringInterest created (status=SENT)
        → Worker receives notification
        → Worker visits inbox → views message
        → Worker clicks "Interested" or "Decline"
        → Employer is notified of the reply
        → If Interested: both parties move to real-world interview/offer
        → Employer marks as HIRED when successful

    No money changes hands on-platform for this flow.
    """

    class Status(models.TextChoices):
        SENT        = 'sent',        'Sent'
        VIEWED      = 'viewed',      'Viewed by Worker'
        INTERESTED  = 'interested',  'Worker Interested'
        DECLINED    = 'declined',    'Worker Declined'
        HIRED       = 'hired',       'Hired'

    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer     = models.ForeignKey(
        EmployerProfile, on_delete=models.CASCADE,
        related_name='outreach_sent',
    )
    worker       = models.ForeignKey(
        WorkerProfile, on_delete=models.CASCADE,
        related_name='outreach_received',
    )
    # Optional: outreach can be tied to a specific full-time job posting
    job          = models.ForeignKey(
        Job, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='hiring_interests',
        help_text='Optional: link this outreach to a specific full-time job posting.',
    )
    message      = models.TextField(
        help_text='Introduction and interest message from the employer to the worker.',
    )
    salary_offer = models.DecimalField(
        max_digits=12, decimal_places=2,
        null=True, blank=True,
        help_text='Indicative monthly salary offer in NGN (optional — workers appreciate transparency).',
    )
    status       = models.CharField(
        max_length=20, choices=Status.choices, default=Status.SENT,
    )
    worker_reply = models.TextField(
        blank=True,
        help_text="Worker's response message to the employer.",
    )
    sent_at      = models.DateTimeField(auto_now_add=True)
    viewed_at    = models.DateTimeField(null=True, blank=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        # One active outreach per employer–worker–job combination
        unique_together = ('employer', 'worker', 'job')
        ordering        = ['-sent_at']
        verbose_name    = 'Hiring Interest'
        indexes         = [
            models.Index(fields=['worker', 'status']),
            models.Index(fields=['employer', 'status']),
        ]

    def __str__(self):
        return (
            f'{self.employer} → {self.worker.user.username} '
            f'[{self.get_status_display()}]'
        )


# ──────────────────────────────────────────────────────────────────────────────
#  6.  SUBSCRIPTION PLAN
#      Employer pricing tiers.  Data only for now — billing wired in Phase 4.
# ──────────────────────────────────────────────────────────────────────────────

class SubscriptionPlan(models.Model):
    """
    Defines the feature limits for each employer subscription tier.

    Phase 1 & 2: all employers are on a free implicit plan (unlimited).
    Phase 4: billing is activated; employers are gated by their plan limits.
    """

    name                        = models.CharField(max_length=100, unique=True)
    price_monthly_ngn           = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text='Monthly cost in NGN.  0 = free tier.',
    )
    talent_searches_per_month   = models.PositiveIntegerField(
        default=0,
        help_text='Max talent searches per month.  0 = unlimited.',
    )
    direct_outreach_per_month   = models.PositiveIntegerField(
        default=0,
        help_text='Max direct outreach messages per month.  0 = unlimited.',
    )
    job_posts_per_month         = models.PositiveIntegerField(
        default=0,
        help_text='Max full-time job posts per month.  0 = unlimited.',
    )
    can_download_cv             = models.BooleanField(
        default=True,
        help_text='Whether employers on this plan can download worker CV PDFs.',
    )
    is_active                   = models.BooleanField(default=True)
    created_at                  = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Subscription Plan'
        ordering     = ['price_monthly_ngn']

    def __str__(self):
        return f'{self.name} (₦{self.price_monthly_ngn:,.0f}/mo)'


# ──────────────────────────────────────────────────────────────────────────────
#  7.  EMPLOYER SUBSCRIPTION
#      Active subscription for a specific employer.
# ──────────────────────────────────────────────────────────────────────────────

class EmployerSubscription(models.Model):
    """
    Tracks which plan an employer is currently on and their usage counters.

    Usage counters (searches_used, outreach_used, posts_used) are reset
    at the start of every billing month by a Celery Beat task.
    """

    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer        = models.OneToOneField(
        EmployerProfile, on_delete=models.CASCADE,
        related_name='subscription',
    )
    plan            = models.ForeignKey(
        SubscriptionPlan, on_delete=models.PROTECT,
        related_name='subscriptions',
    )
    started_at      = models.DateTimeField(auto_now_add=True)
    expires_at      = models.DateTimeField(
        null=True, blank=True,
        help_text='Null = active until cancelled (free tier or lifetime).',
    )
    is_active       = models.BooleanField(default=True)
    paystack_ref    = models.CharField(
        max_length=100, blank=True,
        help_text='Paystack subscription code for recurring billing.',
    )

    # ── Monthly usage counters ─────────────────────────────────────────────
    searches_used   = models.PositiveIntegerField(default=0)
    outreach_used   = models.PositiveIntegerField(default=0)
    posts_used      = models.PositiveIntegerField(default=0)
    usage_reset_at  = models.DateTimeField(
        null=True, blank=True,
        help_text='Timestamp of last monthly usage counter reset.',
    )

    class Meta:
        verbose_name = 'Employer Subscription'

    def __str__(self):
        return f'{self.employer} on {self.plan.name}'
