"""
digital_skills/models.py
========================
TradeLink NG — Digital Skilled Worker models.

Mirrors the jobs app structure but for digital professionals:
  Graphic Designers, Web Developers, Social Media Managers,
  Content Writers, Virtual Assistants, etc.

Account-type rules
──────────────────
  digital_worker accounts:
    ✓ Build a full profile (no verification needed)
    ✓ Apply for DigitalGigs posted by employers
    ✓ Sell on the marketplace → NIN verification required AT THAT POINT
    ✗ BVN and CAC verification are BLOCKED for this account type
    ✗ Cannot apply for artisan (WorkerProfile) jobs

  employer accounts:
    ✓ Post DigitalGigs for digital workers to apply to
    ✗ Cannot list marketplace products

  worker (artisan) accounts:
    ✗ Cannot post/apply for digital gigs
"""

import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator
from django.db import models

# Re-use the Nigerian states list from the jobs app
from jobs.models import NIGERIAN_STATES


# ──────────────────────────────────────────────────────────────────────────────
#  1.  DIGITAL SKILL CATEGORY
#      Top-level taxonomy: Graphic Design, Web Dev, Digital Marketing, etc.
# ──────────────────────────────────────────────────────────────────────────────

class DigitalSkillCategory(models.Model):
    """
    A broad digital discipline.

    Seeded via management command: seed_digital_skill_categories.
    Examples: Graphic Design, Web Development, Social Media Management,
              Content Writing, Video & Animation, Virtual Assistance
    """

    id            = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name          = models.CharField(max_length=120, unique=True)
    slug          = models.SlugField(max_length=120, unique=True)
    icon_class    = models.CharField(max_length=80, blank=True,
                                     help_text='FontAwesome class e.g. fas fa-paint-brush')
    description   = models.TextField(blank=True)
    # Short description fed to the AI matcher
    ai_context    = models.TextField(
        blank=True,
        help_text="Natural-language context for embedding (e.g. 'expert graphic designer Nigeria').",
    )
    display_order = models.PositiveSmallIntegerField(default=0)
    is_active     = models.BooleanField(default=True)
    created       = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Digital Skill Category'
        verbose_name_plural = 'Digital Skill Categories'
        ordering            = ['display_order', 'name']

    def __str__(self):
        return self.name


# ──────────────────────────────────────────────────────────────────────────────
#  2.  DIGITAL SUB-SKILL
#      Granular specialisations within a category.
# ──────────────────────────────────────────────────────────────────────────────

class DigitalSubSkill(models.Model):
    """
    A specific sub-skill within a DigitalSkillCategory.

    Examples:
      Graphic Design    → { Logo Design, Flyer Design, Brand Identity, UI/UX }
      Web Development   → { Frontend, Backend, WordPress, Full-Stack }
      Digital Marketing → { SEO, Google Ads, Social Media Ads, Email Marketing }
    """

    id       = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    category = models.ForeignKey(
        DigitalSkillCategory,
        on_delete=models.CASCADE,
        related_name='sub_skills',
    )
    name     = models.CharField(max_length=120)
    slug     = models.SlugField(max_length=120)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('category', 'slug')
        ordering        = ['category', 'name']

    def __str__(self):
        return f'{self.category.name} → {self.name}'


# ──────────────────────────────────────────────────────────────────────────────
#  3.  DIGITAL WORKER PROFILE
#      The rich profile a digital professional builds to get matched to gigs.
# ──────────────────────────────────────────────────────────────────────────────

class DigitalWorkerProfile(models.Model):
    """
    One-to-one extension of User for account_type == 'digital_worker'.

    Auto-created by digital_skills/signals.py on User creation.

    Verification rules (enforced at view level):
      - Profile creation:    no verification needed.
      - Gig applications:    no verification needed.
      - Marketplace listing: NIN-only gate fires.
      - BVN / CAC:           BLOCKED entirely for this account type.
    """

    class Availability(models.TextChoices):
        AVAILABLE      = 'available',   'Available Now'
        AVAILABLE_SOON = 'soon',        'Available Soon'
        BUSY           = 'busy',        'Currently Busy'
        NOT_AVAILABLE  = 'unavailable', 'Not Available'

    class ExperienceLevel(models.TextChoices):
        ENTRY        = 'entry',        'Entry (0–2 years)'
        INTERMEDIATE = 'mid',          'Intermediate (3–5 years)'
        EXPERIENCED  = 'experienced',  'Experienced (6–10 years)'
        EXPERT       = 'expert',       'Expert (10+ years)'

    class EmploymentPreference(models.TextChoices):
        FULL_TIME = 'full_time', 'Full-Time Employment'
        PART_TIME = 'part_time', 'Part-Time Employment'
        EITHER    = 'either',    'Either Full or Part-Time'
        GIG_ONLY  = 'gig_only',  'Gig / Contract Work Only'

    id   = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='digital_worker_profile',
    )

    # ── Category & Skills ──────────────────────────────────────────────────
    primary_category = models.ForeignKey(
        DigitalSkillCategory,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='primary_workers',
        help_text='The main discipline this worker identifies with.',
    )
    sub_skills = models.ManyToManyField(
        DigitalSubSkill,
        through='DigitalWorkerSubSkill',
        related_name='workers',
        blank=True,
    )

    # ── Bio & Headline ─────────────────────────────────────────────────────
    headline = models.CharField(
        max_length=200, blank=True,
        help_text='One-line professional headline shown on the directory card, '
                  'e.g. "Expert React Developer | 5 yrs exp"',
    )
    bio = models.TextField(
        blank=True,
        help_text="Full profile bio — primary text encoded by the AI matcher.",
    )

    # ── Experience ────────────────────────────────────────────────────────
    experience_level  = models.CharField(
        max_length=20, choices=ExperienceLevel.choices, default=ExperienceLevel.ENTRY,
    )
    years_experience  = models.PositiveSmallIntegerField(default=0)

    # ── Rates ─────────────────────────────────────────────────────────────
    hourly_rate = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text='Hourly rate in NGN',
    )
    project_rate = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text='Starting fixed price per project in NGN',
    )

    # ── Location ──────────────────────────────────────────────────────────
    state     = models.CharField(max_length=40, choices=NIGERIAN_STATES, blank=True)
    lga       = models.CharField(max_length=120, blank=True, verbose_name='Local Government Area')
    remote_ok = models.BooleanField(default=True, help_text='Can work fully remotely.')

    # ── Availability & Employment ──────────────────────────────────────────
    availability           = models.CharField(
        max_length=20, choices=Availability.choices, default=Availability.AVAILABLE,
    )
    employment_preference  = models.CharField(
        max_length=20, choices=EmploymentPreference.choices, default=EmploymentPreference.GIG_ONLY,
    )
    open_to_employment     = models.BooleanField(
        default=False,
        help_text='Shows an "Open to Work" badge on the directory listing.',
    )
    expected_monthly_salary = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text='Expected monthly salary in NGN if seeking full-time employment.',
    )
    notice_period = models.CharField(
        max_length=100, blank=True,
        help_text='e.g. "Available immediately", "2 weeks notice".',
    )

    # ── Contact & Social Links ─────────────────────────────────────────────
    whatsapp_number = models.CharField(
        max_length=20, blank=True,
        help_text='WhatsApp number for direct contact (shown to verified employers).',
    )
    portfolio_url   = models.URLField(blank=True, help_text='External portfolio / Behance / GitHub')
    linkedin_url    = models.URLField(blank=True)
    twitter_url     = models.URLField(blank=True)

    # ── Status ────────────────────────────────────────────────────────────
    is_verified       = models.BooleanField(
        default=False,
        help_text='Admin-granted verified badge (blue checkmark).',
    )
    is_featured       = models.BooleanField(
        default=False,
        help_text='Featured workers appear at the top of search results.',
    )
    profile_completion = models.PositiveSmallIntegerField(
        default=0,
        validators=[MaxValueValidator(100)],
        help_text='Percentage (0–100) calculated from filled profile fields.',
    )

    # ── AI Embedding ──────────────────────────────────────────────────────
    # Same pattern as WorkerProfile.text_embedding (jobs app).
    # Encoded from: headline + bio + category name + sub-skill names.
    text_embedding         = models.JSONField(
        null=True, blank=True,
        help_text='Sentence-transformer embedding. 768-dim float list. '
                  'Recomputed when headline, bio, or skills change.',
    )
    text_embedding_updated = models.DateTimeField(null=True, blank=True)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Digital Worker Profile'
        verbose_name_plural = 'Digital Worker Profiles'

    def __str__(self):
        cat = self.primary_category.name if self.primary_category else 'No Category'
        return f'{self.user.username} — {cat}'

    # ── Verification gates ─────────────────────────────────────────────────

    def can_list_on_marketplace(self) -> bool:
        """
        Digital workers must verify NIN *only* when posting to the marketplace.
        BVN/CAC are never required or allowed for this account type.
        """
        try:
            return self.user.verification_profile.nin_verified
        except Exception:
            return False

    # ── Profile completion ─────────────────────────────────────────────────

    def compute_completion(self) -> int:
        """
        Returns a 0–100 completion score.
        Called by the signal after each profile save.
        """
        points = 0
        checks = [
            (bool(self.headline),          15),
            (bool(self.bio),               20),
            (self.primary_category_id is not None, 15),
            (self.sub_skills.exists(),     10),
            (bool(self.hourly_rate or self.project_rate), 10),
            (bool(self.state),             10),
            (bool(self.portfolio_url),     10),
            (bool(self.whatsapp_number or self.linkedin_url), 10),
        ]
        for condition, weight in checks:
            if condition:
                points += weight
        # Portfolio items add remaining 0 → already counted above via portfolio_url
        return min(points, 100)


# ──────────────────────────────────────────────────────────────────────────────
#  4.  DIGITAL WORKER SUB-SKILL (through model)
# ──────────────────────────────────────────────────────────────────────────────

class DigitalWorkerSubSkill(models.Model):
    """Through model for DigitalWorkerProfile ↔ DigitalSubSkill."""
    worker    = models.ForeignKey(DigitalWorkerProfile, on_delete=models.CASCADE)
    sub_skill = models.ForeignKey(DigitalSubSkill, on_delete=models.CASCADE)
    years_exp = models.PositiveSmallIntegerField(default=0)

    class Meta:
        unique_together = ('worker', 'sub_skill')

    def __str__(self):
        return f'{self.worker.user.username} — {self.sub_skill.name}'


# ──────────────────────────────────────────────────────────────────────────────
#  5.  DIGITAL PORTFOLIO ITEM
#      Portfolio pieces: images, links, YouTube/Vimeo videos.
# ──────────────────────────────────────────────────────────────────────────────

class DigitalPortfolioItem(models.Model):
    """
    A portfolio piece uploaded or linked by a digital worker.
    Displayed on the public profile page.
    """

    class ItemType(models.TextChoices):
        IMAGE = 'image', 'Image Upload'
        LINK  = 'link',  'External Link'
        VIDEO = 'video', 'Video Link (YouTube / Vimeo)'

    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    worker       = models.ForeignKey(
        DigitalWorkerProfile, on_delete=models.CASCADE, related_name='portfolio_items',
    )
    item_type    = models.CharField(max_length=10, choices=ItemType.choices, default=ItemType.IMAGE)
    title        = models.CharField(max_length=200)
    description  = models.TextField(blank=True)
    image        = models.ImageField(upload_to='digital_portfolio/', blank=True, null=True)
    external_url = models.URLField(blank=True, help_text='URL for LINK or VIDEO items.')
    display_order = models.PositiveSmallIntegerField(default=0)
    created      = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Digital Portfolio Item'
        verbose_name_plural = 'Digital Portfolio Items'
        ordering            = ['display_order', '-created']

    def __str__(self):
        return f'{self.worker.user.username} — {self.title}'


# ──────────────────────────────────────────────────────────────────────────────
#  6.  DIGITAL GIG
#      A short-term digital project posted by an Employer.
#      Mirrors Job in jobs app but for digital work.
# ──────────────────────────────────────────────────────────────────────────────

class DigitalGig(models.Model):
    """
    A digital project or gig posted by an Employer.
    Digital workers discover and apply to these.
    """

    class Status(models.TextChoices):
        DRAFT  = 'draft',  'Draft'
        ACTIVE = 'active', 'Active'
        PAUSED = 'paused', 'Paused'
        CLOSED = 'closed', 'Closed'
        FILLED = 'filled', 'Filled'

    class BudgetType(models.TextChoices):
        FIXED  = 'fixed',  'Fixed Price'
        HOURLY = 'hourly', 'Per Hour'

    class WorkType(models.TextChoices):
        REMOTE   = 'remote',   'Fully Remote'
        ONSITE   = 'onsite',   'On-Site'
        HYBRID   = 'hybrid',   'Hybrid'

    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer    = models.ForeignKey(
        'jobs.EmployerProfile',
        on_delete=models.CASCADE,
        related_name='digital_gigs',
    )
    title       = models.CharField(max_length=200)
    description = models.TextField()
    category    = models.ForeignKey(
        DigitalSkillCategory, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='gigs',
    )
    required_sub_skills = models.ManyToManyField(DigitalSubSkill, blank=True,
                                                  related_name='gigs')

    budget_type = models.CharField(max_length=10, choices=BudgetType.choices,
                                    default=BudgetType.FIXED)
    budget_min  = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text='Minimum budget in NGN.',
    )
    budget_max  = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text='Maximum budget in NGN.',
    )

    work_type = models.CharField(max_length=10, choices=WorkType.choices, default=WorkType.REMOTE)
    state     = models.CharField(max_length=40, choices=NIGERIAN_STATES, blank=True,
                                  help_text='Required for on-site / hybrid gigs.')
    deadline  = models.DateField(null=True, blank=True, help_text='Application or project deadline.')

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT,
                               db_index=True)

    # AI embedding — same approach as Job.text_embedding in jobs app
    text_embedding         = models.JSONField(null=True, blank=True)
    text_embedding_updated = models.DateTimeField(null=True, blank=True)

    # ── External URL (optional) ───────────────────────────────────────────
    # If set, applicants are redirected to this URL to apply externally.
    # If blank, the gig is internal and workers apply within the platform.
    external_url = models.URLField(
        blank=True, default='',
        help_text='External application URL. Leave blank for on-platform applications.',
    )

    # Tracking
    views_count        = models.PositiveIntegerField(default=0, editable=False)
    applications_count = models.PositiveIntegerField(default=0, editable=False)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Digital Gig'
        ordering     = ['-created']

    def __str__(self):
        return f'{self.title} — {self.employer}'

    @property
    def budget_display(self):
        """Human-readable budget range, e.g. '₦50,000 – ₦100,000'."""
        if self.budget_min and self.budget_max:
            return f'₦{self.budget_min:,.0f} – ₦{self.budget_max:,.0f}'
        if self.budget_max:
            return f'Up to ₦{self.budget_max:,.0f}'
        if self.budget_min:
            return f'From ₦{self.budget_min:,.0f}'
        return 'Budget negotiable'

    @property
    def is_active(self):
        return self.status == self.Status.ACTIVE

    @property
    def is_external(self) -> bool:
        """True when applicants should be redirected to an external URL."""
        return bool(self.external_url)


# ──────────────────────────────────────────────────────────────────────────────
#  7.  DIGITAL APPLICATION
#      A digital worker applies to a DigitalGig.
#      Mirrors Application in jobs app.
# ──────────────────────────────────────────────────────────────────────────────

class DigitalApplication(models.Model):
    """
    A digital worker's proposal / application to a DigitalGig.
    """

    class Status(models.TextChoices):
        PENDING     = 'pending',     'Pending Review'
        SHORTLISTED = 'shortlisted', 'Shortlisted'
        REJECTED    = 'rejected',    'Rejected'
        HIRED       = 'hired',       'Hired'
        WITHDRAWN   = 'withdrawn',   'Withdrawn'

    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    gig         = models.ForeignKey(DigitalGig, on_delete=models.CASCADE,
                                     related_name='applications')
    worker      = models.ForeignKey(DigitalWorkerProfile, on_delete=models.CASCADE,
                                     related_name='applications')
    cover_note  = models.TextField(
        blank=True,
        help_text='Short pitch — why you are the best person for this gig.',
    )
    proposed_rate = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text='Your proposed fixed price or hourly rate in NGN.',
    )
    status        = models.CharField(max_length=15, choices=Status.choices,
                                      default=Status.PENDING, db_index=True)
    employer_note = models.TextField(
        blank=True,
        help_text='Private employer feedback on this application.',
    )
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('gig', 'worker')
        verbose_name    = 'Digital Application'
        ordering        = ['-created']

    def __str__(self):
        return f'{self.worker.user.username} → {self.gig.title} [{self.status}]'


# ──────────────────────────────────────────────────────────────────────────────
#  8.  DIGITAL GIG SAVED (Bookmark)
#      Digital workers can save / bookmark gigs they're interested in.
# ──────────────────────────────────────────────────────────────────────────────

class SavedDigitalGig(models.Model):
    id      = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user    = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                 related_name='saved_digital_gigs')
    gig     = models.ForeignKey(DigitalGig, on_delete=models.CASCADE,
                                 related_name='saved_by')
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'gig')
        verbose_name    = 'Saved Digital Gig'

    def __str__(self):
        return f'{self.user.username} saved {self.gig.title}'


# ──────────────────────────────────────────────────────────────────────────────
#  9.  DIGITAL WORKER REVIEW
#      Employers leave reviews on workers after a gig is completed.
# ──────────────────────────────────────────────────────────────────────────────

class DigitalWorkerReview(models.Model):
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    worker      = models.ForeignKey(DigitalWorkerProfile, on_delete=models.CASCADE,
                                     related_name='reviews')
    reviewer    = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                     related_name='digital_reviews_given')
    gig         = models.ForeignKey(DigitalGig, on_delete=models.SET_NULL,
                                     null=True, blank=True, related_name='reviews')
    rating      = models.PositiveSmallIntegerField(
        help_text='1–5 stars.',
        choices=[(i, str(i)) for i in range(1, 6)],
    )
    comment     = models.TextField(blank=True)
    is_public   = models.BooleanField(default=True)
    created     = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('worker', 'reviewer', 'gig')
        verbose_name    = 'Digital Worker Review'
        ordering        = ['-created']

    def __str__(self):
        return f'{self.reviewer.username} → {self.worker.user.username} ({self.rating}★)'
