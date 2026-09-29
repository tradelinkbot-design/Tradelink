"""
marketplace/models.py
=====================
TradeLink NG — Core marketplace models.

Django app name: marketplace

This app is the engine of TradeLink NG. It owns every domain object that is
NOT auth: trade categories, skills, worker profiles, employer profiles, job
listings, CLIP match scores, applications, reviews, bookmarks, and
notifications.

CLIP integration overview
─────────────────────────
CLIP (Contrastive Language–Image Pre-Training) lets us embed both *text* and
*images* into the same vector space, so we can compute similarity across
modalities.

  Worker side
  ──────────
  • WorkerProfile.clip_text_embedding  — encoded from: bio + trade + skills
  • PortfolioItem.clip_image_embedding  — encoded from: portfolio photo

  Employer / Job side
  ───────────────────
  • Job.clip_embedding                  — encoded from: title + description + required skills

  Matching
  ────────
  • CLIPMatch stores the cosine similarity score between every (worker, job)
    pair whose trade categories overlap.
  • A background Celery task re-computes CLIPMatch rows whenever:
      – A new job is posted or updated
      – A worker updates their profile or portfolio
  • The recommendation endpoint simply queries:
      CLIPMatch.objects.filter(job=job).order_by('-score')[:20]

Embedding storage
─────────────────
  Embeddings are stored as JSON arrays (list[float]).  CLIP ViT-B/32 produces
  512-dimensional vectors.  For ~50K workers × 10K active jobs this is large
  but manageable as a cache table backed by pgvector in production.
  
  Swap JSONField → pgvector's VectorField in production for fast ANN queries.
"""

import uuid
import re
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError


# ──────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ──────────────────────────────────────────────────────────────────────────────

NIGERIAN_STATES = [
    ('abia',          'Abia'),
    ('adamawa',       'Adamawa'),
    ('akwa_ibom',     'Akwa Ibom'),
    ('anambra',       'Anambra'),
    ('bauchi',        'Bauchi'),
    ('bayelsa',       'Bayelsa'),
    ('benue',         'Benue'),
    ('borno',         'Borno'),
    ('cross_river',   'Cross River'),
    ('delta',         'Delta'),
    ('ebonyi',        'Ebonyi'),
    ('edo',           'Edo'),
    ('ekiti',         'Ekiti'),
    ('enugu',         'Enugu'),
    ('fct',           'FCT — Abuja'),
    ('gombe',         'Gombe'),
    ('imo',           'Imo'),
    ('jigawa',        'Jigawa'),
    ('kaduna',        'Kaduna'),
    ('kano',          'Kano'),
    ('katsina',       'Katsina'),
    ('kebbi',         'Kebbi'),
    ('kogi',          'Kogi'),
    ('kwara',         'Kwara'),
    ('lagos',         'Lagos'),
    ('nasarawa',      'Nasarawa'),
    ('niger',         'Niger'),
    ('ogun',          'Ogun'),
    ('ondo',          'Ondo'),
    ('osun',          'Osun'),
    ('oyo',           'Oyo'),
    ('plateau',       'Plateau'),
    ('rivers',        'Rivers'),
    ('sokoto',        'Sokoto'),
    ('taraba',        'Taraba'),
    ('yobe',          'Yobe'),
    ('zamfara',       'Zamfara'),
]


def validate_youtube_url(value):
    if not value:
        return
    pattern = re.compile(
        r'^https?://(www\.)?(youtube\.com/watch\?.*v=[\w\-]{11}|youtu\.be/[\w\-]{11}|youtube\.com/shorts/[\w\-]{11})',
        re.IGNORECASE,
    )
    if not pattern.match(value):
        raise ValidationError(
            'Enter a valid YouTube URL (e.g. https://www.youtube.com/watch?v=… '
            'or https://youtu.be/… or https://www.youtube.com/shorts/…).'
        )

def get_youtube_embed_url(youtube_url: str) -> str | None:
    if not youtube_url:
        return None

    # youtu.be/<id>
    short = re.match(r'https?://youtu\.be/([\w\-]{11})', youtube_url, re.IGNORECASE)
    if short:
        return f'https://www.youtube.com/embed/{short.group(1)}'

    # youtube.com/shorts/<id>
    shorts = re.match(r'https?://(www\.)?youtube\.com/shorts/([\w\-]{11})', youtube_url, re.IGNORECASE)
    if shorts:
        return f'https://www.youtube.com/embed/{shorts.group(2)}'

    # youtube.com/watch?v=<id>
    watch = re.search(r'[?&]v=([\w\-]{11})', youtube_url)
    if watch:
        return f'https://www.youtube.com/embed/{watch.group(1)}'

    return None


# ──────────────────────────────────────────────────────────────────────────────
#  1.  TRADE CATEGORY
#      The top-level taxonomy: Electrician, Plumber, Carpenter, etc.
# ──────────────────────────────────────────────────────────────────────────────

class TradeCategory(models.Model):
    """
    A broad skilled trade discipline.

    Examples from the homepage:
        Electrician · Carpenter · Plumber · Solar Installer
        Hair Stylist · Painter & Decorator · Welder · Mason
    """

    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name        = models.CharField(max_length=120, unique=True)
    slug        = models.SlugField(max_length=120, unique=True)

    # FontAwesome class shown on the homepage trade cards, e.g. "fas fa-bolt"
    icon_class  = models.CharField(max_length=80, blank=True)

    description = models.TextField(blank=True)

    # Short text fed to CLIP when we encode this category as context for jobs
    # that don't have a rich description.  e.g. "skilled electrician in Nigeria"
    clip_context_text = models.TextField(
        blank=True,
        help_text="Short natural-language description used to anchor CLIP embeddings "
                  "for this trade (e.g. 'expert electrician wiring installation Lagos').",
    )

    is_active    = models.BooleanField(default=True)
    display_order = models.PositiveSmallIntegerField(default=0)
    created      = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Trade Category'
        verbose_name_plural = 'Trade Categories'
        ordering            = ['display_order', 'name']

    def __str__(self):
        return self.name


# ──────────────────────────────────────────────────────────────────────────────
#  2.  SKILL
#      Granular skills within a trade category.
# ──────────────────────────────────────────────────────────────────────────────

class Skill(models.Model):
    """
    A specific skill or specialisation within a TradeCategory.

    Examples:
        Electrician → { Solar Panel Wiring, CCTV Installation, Generator Repair }
        Hair Stylist → { Hair Braiding, Locs, Perms, Colouring }
        Carpenter    → { Cabinet Making, Roof Framing, Furniture Fitting }
    """

    id       = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    category = models.ForeignKey(
        TradeCategory,
        on_delete=models.CASCADE,
        related_name='skills',
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
#  3.  WORKER PROFILE
#      The rich profile a tradesperson builds to get matched to jobs.
# ──────────────────────────────────────────────────────────────────────────────

class WorkerProfile(models.Model):

    class Availability(models.TextChoices):
        AVAILABLE      = 'available',    'Available Now'
        AVAILABLE_SOON = 'soon',         'Available Soon'
        BUSY           = 'busy',         'Currently Busy'
        NOT_AVAILABLE  = 'unavailable',  'Not Available'

    class ExperienceLevel(models.TextChoices):
        ENTRY       = 'entry',       'Entry (0–2 years)'
        INTERMEDIATE = 'mid',        'Intermediate (3–5 years)'
        EXPERIENCED  = 'experienced','Experienced (6–10 years)'
        EXPERT       = 'expert',     'Expert (10+ years)'

    id               = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # One-to-one link to the custom User model in the accounts app
    user             = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='worker_profile',
    )

    # ── Trade & Skills ──────────────────────────────────────────────────────
    trade_category   = models.ForeignKey(
        TradeCategory,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='workers',
    )
    skills           = models.ManyToManyField(
        Skill,
        through='WorkerSkill',
        related_name='workers',
        blank=True,
    )
    experience_level = models.CharField(
        max_length=20,
        choices=ExperienceLevel.choices,
        default=ExperienceLevel.ENTRY,
    )
    years_experience = models.PositiveSmallIntegerField(default=0)

    # ── Bio — the primary text fed into CLIP ────────────────────────────────
    # Workers should describe what they do, specialisations, work style, etc.
    # This text is the main input for the CLIP text encoder.
    bio              = models.TextField(
        blank=True,
        help_text="Natural-language description of the worker's skills and experience. "
                  "This is the primary text encoded by CLIP for job matching.",
    )

    # ── Location ────────────────────────────────────────────────────────────
    state            = models.CharField(max_length=40, choices=NIGERIAN_STATES, blank=True)
    lga              = models.CharField(
        max_length=120, blank=True,
        verbose_name='Local Government Area',
    )
    is_willing_to_relocate = models.BooleanField(default=False)

    # ── Rates ───────────────────────────────────────────────────────────────
    hourly_rate      = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        help_text='Hourly rate in NGN',
    )
    daily_rate       = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        help_text='Day rate in NGN',
    )

    # ── Status ──────────────────────────────────────────────────────────────
    availability     = models.CharField(
        max_length=20,
        choices=Availability.choices,
        default=Availability.AVAILABLE,
    )

    # ── Employment Preferences (LinkedIn / Hiring Mode) ──────────────────────
    class EmploymentPreference(models.TextChoices):
        FULL_TIME = 'full_time', 'Full-Time Employment'
        PART_TIME = 'part_time', 'Part-Time Employment'
        EITHER    = 'either',    'Either Full or Part-Time'
        GIG_ONLY  = 'gig_only',  'Gig / Contract Work Only'

    open_to_employment = models.BooleanField(
        default=False,
        help_text='Shows an "Open to Work" badge and makes profile visible in talent search.',
    )
    employment_preference = models.CharField(
        max_length=20,
        choices=EmploymentPreference.choices,
        default=EmploymentPreference.GIG_ONLY,
    )
    expected_monthly_salary = models.DecimalField(
        max_digits=12, decimal_places=2,
        null=True, blank=True,
        help_text='Expected monthly salary in NGN for full-time employment.',
    )
    notice_period = models.CharField(
        max_length=100, blank=True,
        help_text='e.g. "Available immediately", "2 weeks notice", "1 month".',
    )
    is_verified      = models.BooleanField(
        default=False,
        help_text='Set by admin after document/ID verification.',
    )
    is_featured      = models.BooleanField(
        default=False,
        help_text='Featured workers appear at the top of recommendation lists.',
    )
    profile_completion = models.PositiveSmallIntegerField(
        default=0,
        validators=[MaxValueValidator(100)],
        help_text='Percentage (0–100) calculated from filled profile fields.',
    )

    # ── Sentence-Transformer Embedding (primary text signal) ────────────────
    # 768-dim vector from all-mpnet-base-v2.  This is the main embedding used
    # for text similarity in the hybrid scoring engine.
    text_embedding = models.JSONField(
        null=True, blank=True,
        help_text="Sentence-transformer embedding of bio + trade + skills. "
                  "768-dim float list. Recomputed when profile text changes.",
    )
    text_embedding_updated = models.DateTimeField(null=True, blank=True)

    # ── CLIP Text Embedding (kept for backward compat) ───────────────────────
    clip_text_embedding = models.JSONField(
        null=True, blank=True,
        help_text="Legacy CLIP text embedding. Use text_embedding instead.",
    )
    clip_embedding_updated = models.DateTimeField(null=True, blank=True)

    # ── Dispute tracking ─────────────────────────────────────────────────
    disputes_raised  = models.PositiveIntegerField(
        default=0,
        help_text='Total disputes this worker has ever raised.',
    )
    disputes_lost    = models.PositiveIntegerField(
        default=0,
        help_text='Disputes resolved against this worker (as raiser or respondent).',
    )
    dispute_flagged  = models.BooleanField(
        default=False,
        help_text='Automatically set when dispute loss rate exceeds 40% with ≥3 disputes.',
    )

    # ── Metadata ────────────────────────────────────────────────────────────
    created          = models.DateTimeField(auto_now_add=True)
    updated          = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_featured', '-profile_completion', '-created']
        indexes  = [
            models.Index(fields=['trade_category', 'availability']),
            models.Index(fields=['state']),
        ]

    def __str__(self):
        return f'Worker: {self.user.username} ({self.trade_category})'

    # ── Helpers ─────────────────────────────────────────────────────────────

    def get_clip_input_text(self) -> str:
        """
        Build the text that is sent to the CLIP text encoder.

        Combines: trade category name + skill names + bio.
        Example: "Electrician. Solar Panel Wiring, CCTV Installation.
                  Experienced electrician in Lagos with 6 years..."
        """
        parts = []
        if self.trade_category:
            parts.append(self.trade_category.name)
        skill_names = list(
            self.skills.filter(is_active=True).values_list('name', flat=True)
        )
        if skill_names:
            parts.append(', '.join(skill_names))
        if self.bio:
            parts.append(self.bio)
        return '. '.join(parts)


# ──────────────────────────────────────────────────────────────────────────────
#  4.  WORKER SKILL  (through model)
# ──────────────────────────────────────────────────────────────────────────────

class WorkerSkill(models.Model):
    """
    Associates a WorkerProfile with a Skill, recording proficiency detail.
    The through model lets us store extra data on the M2M relationship.
    """

    class ProficiencyLevel(models.TextChoices):
        BEGINNER     = 'beginner',     'Beginner'
        COMPETENT    = 'competent',    'Competent'
        PROFICIENT   = 'proficient',   'Proficient'
        EXPERT       = 'expert',       'Expert'

    id               = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    worker           = models.ForeignKey(WorkerProfile, on_delete=models.CASCADE)
    skill            = models.ForeignKey(Skill, on_delete=models.CASCADE)
    years_experience = models.PositiveSmallIntegerField(default=0)
    proficiency      = models.CharField(
        max_length=20,
        choices=ProficiencyLevel.choices,
        default=ProficiencyLevel.COMPETENT,
    )

    class Meta:
        unique_together = ('worker', 'skill')

    def __str__(self):
        return f'{self.worker.user.username} — {self.skill.name} ({self.proficiency})'


# ──────────────────────────────────────────────────────────────────────────────
#  5.  PORTFOLIO ITEM
#      Images + optional YouTube demo video of a worker's past work.
# ──────────────────────────────────────────────────────────────────────────────

class PortfolioItem(models.Model):
    """
    A single past-work entry with a photo and/or a YouTube demo video.

    YouTube field
    ─────────────
    Workers can paste a YouTube URL of themselves performing the work
    (e.g. a time-lapse of a wiring job, a finished paint job walkthrough).
    The URL is validated to be a genuine YouTube watch/short link, and the
    helper method `get_embed_url()` converts it to an embeddable iframe src
    so templates can render it directly.

    CLIP use: the *image* is encoded by CLIP's visual encoder and the resulting
    embedding is stored in clip_image_embedding.  This lets employers who
    describe a project in text ("install solar panels on a rooftop Lagos")
    find workers whose *portfolio photos* are visually similar to that project.
    """

    id            = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    worker        = models.ForeignKey(
        WorkerProfile,
        on_delete=models.CASCADE,
        related_name='portfolio',
    )

    # ── Photo (still required for CLIP image embedding) ──────────────────────
    image         = models.ImageField(upload_to='portfolio/%Y/%m/')
    caption       = models.CharField(max_length=280, blank=True)
    trade_context = models.ForeignKey(
        TradeCategory, null=True, blank=True, on_delete=models.SET_NULL,
        help_text='Which trade this item demonstrates.',
    )

    # ── YouTube demo video ───────────────────────────────────────────────────
    youtube_url   = models.URLField(
        max_length=200,
        blank=True,
        validators=[validate_youtube_url],
        verbose_name='YouTube Demo URL',
        help_text=(
            'Optional: paste a YouTube link of you doing this work '
            '(e.g. https://www.youtube.com/watch?v=… or https://youtu.be/…). '
            'The video will be embedded on your public profile.'
        ),
    )

    # CLIP image embedding — 512-dim float list from CLIP ViT-B/32
    clip_image_embedding = models.JSONField(
        null=True, blank=True,
        help_text="CLIP image embedding of this portfolio photo.",
    )

    display_order = models.PositiveSmallIntegerField(default=0)
    created       = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['worker', 'display_order', '-created']

    def __str__(self):
        return f'{self.worker.user.username} portfolio — {self.caption[:40]}'

    # ── Helpers ──────────────────────────────────────────────────────────────

    def get_embed_url(self) -> str | None:
        """
        Returns an embeddable YouTube URL, or None if no YouTube URL is set.

        Usage in templates:
            {% if item.get_embed_url %}
              <iframe src="{{ item.get_embed_url }}" ...></iframe>
            {% endif %}
        """
        return get_youtube_embed_url(self.youtube_url)

    @property
    def has_video(self) -> bool:
        """True when a valid YouTube URL has been provided."""
        return bool(self.youtube_url)


# ──────────────────────────────────────────────────────────────────────────────
#  6.  EMPLOYER PROFILE
# ──────────────────────────────────────────────────────────────────────────────

class EmployerProfile(models.Model):

    class CompanyType(models.TextChoices):
        INDIVIDUAL  = 'individual',  'Individual / Homeowner'
        SME         = 'sme',         'Small / Medium Business'
        CORPORATE   = 'corporate',   'Corporate / Large Business'
        NGO         = 'ngo',         'NGO / Non-profit'
        GOVERNMENT  = 'government',  'Government / Public Sector'

    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user         = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='employer_profile',
    )
    company_name = models.CharField(max_length=200, blank=True)
    company_type = models.CharField(
        max_length=20, choices=CompanyType.choices, default=CompanyType.INDIVIDUAL,
    )
    description  = models.TextField(blank=True)
    website      = models.URLField(blank=True)
    phone        = models.CharField(max_length=20, blank=True)

    state        = models.CharField(max_length=40, choices=NIGERIAN_STATES, blank=True)
    lga          = models.CharField(max_length=120, blank=True)

    # ── Company Detail (LinkedIn / Hiring Mode) ───────────────────────────────
    company_size = models.CharField(
        max_length=30, blank=True,
        choices=[
            ('1_10',    '1–10 employees'),
            ('11_50',   '11–50 employees'),
            ('51_200',  '51–200 employees'),
            ('201_500', '201–500 employees'),
            ('500plus', '500+ employees'),
        ],
        help_text='Approximate number of full-time employees.',
    )
    year_founded = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text='Year the company was established.',
    )
    industry_sector = models.CharField(
        max_length=100, blank=True,
        help_text='e.g. Construction, Real Estate, Oil & Gas, Manufacturing.',
    )

    is_verified  = models.BooleanField(
        default=False,
        help_text='Admin-confirmed verified employer. Shown with a badge.',
    )

    # ── Dispute tracking ─────────────────────────────────────────────────
    disputes_raised  = models.PositiveIntegerField(
        default=0,
        help_text='Total disputes this employer has ever raised.',
    )
    disputes_lost    = models.PositiveIntegerField(
        default=0,
        help_text='Disputes resolved against this employer.',
    )
    dispute_flagged  = models.BooleanField(
        default=False,
        help_text='Automatically set when dispute loss rate exceeds 40% with ≥3 disputes.',
    )

    created      = models.DateTimeField(auto_now_add=True)
    updated      = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_verified', '-created']

    def __str__(self):
        return self.company_name or self.user.username


# ──────────────────────────────────────────────────────────────────────────────
#  7.  JOB LISTING
#      The central object employers post and workers are matched to.
# ──────────────────────────────────────────────────────────────────────────────

class Job(models.Model):

    class JobType(models.TextChoices):
        FULL_TIME  = 'full_time',  'Full-Time'
        PART_TIME  = 'part_time',  'Part-Time'
        CONTRACT   = 'contract',   'Contract'
        ONCE_OFF   = 'once_off',   'One-Off / Gig'
        INTERNSHIP = 'internship', 'Apprenticeship / Internship'

    class PayType(models.TextChoices):
        HOURLY      = 'hourly',     'Per Hour'
        DAILY       = 'daily',      'Per Day'
        WEEKLY      = 'weekly',     'Per Week'
        MONTHLY     = 'monthly',    'Per Month'
        FIXED       = 'fixed',      'Fixed Price'
        NEGOTIABLE  = 'negotiable', 'Negotiable'

    class Status(models.TextChoices):
        DRAFT   = 'draft',   'Draft'
        ACTIVE  = 'active',  'Active'
        PAUSED  = 'paused',  'Paused'
        FILLED  = 'filled',  'Filled'
        CLOSED  = 'closed',  'Closed'
        EXPIRED = 'expired', 'Expired'

    id               = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer         = models.ForeignKey(
        EmployerProfile,
        on_delete=models.CASCADE,
        related_name='jobs',
    )
    trade_category   = models.ForeignKey(
        TradeCategory,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='jobs',
    )
    required_skills  = models.ManyToManyField(
        Skill,
        blank=True,
        related_name='jobs',
    )

    # ── Content ─────────────────────────────────────────────────────────────
    title            = models.CharField(max_length=256)
    description      = models.TextField(
        help_text="Full job description. This is the primary text encoded by CLIP "
                  "for matching workers to this job.",
    )

    # ── Type / Pay ──────────────────────────────────────────────────────────
    job_type         = models.CharField(
        max_length=20, choices=JobType.choices, default=JobType.ONCE_OFF,
    )
    pay_type         = models.CharField(
        max_length=20, choices=PayType.choices, default=PayType.NEGOTIABLE,
    )
    pay_min          = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text='Minimum pay in NGN',
    )
    pay_max          = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text='Maximum pay in NGN',
    )

    # ── Location ────────────────────────────────────────────────────────────
    state            = models.CharField(max_length=40, choices=NIGERIAN_STATES, blank=True)
    lga              = models.CharField(max_length=120, blank=True)
    is_remote        = models.BooleanField(default=False)

    # ── Status & Lifecycle ──────────────────────────────────────────────────
    status           = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT,
    )
    deadline         = models.DateField(null=True, blank=True)
    slots            = models.PositiveSmallIntegerField(
        default=1,
        help_text='How many workers are needed for this job.',
    )

    # ── Sentence-Transformer Embedding (primary text signal) ────────────────
    text_embedding   = models.JSONField(
        null=True, blank=True,
        help_text="Sentence-transformer embedding of title + trade + skills + description. "
                  "768-dim float list. Recomputed when job text changes.",
    )
    text_embedding_updated = models.DateTimeField(null=True, blank=True)

    # ── CLIP Embedding (kept for backward compat) ────────────────────────────
    clip_embedding   = models.JSONField(
        null=True, blank=True,
        help_text="Legacy CLIP text embedding. Use text_embedding instead.",
    )
    clip_embedding_updated = models.DateTimeField(null=True, blank=True)

    # ── Cached counters (updated by signals) ────────────────────────────────
    applications_count = models.PositiveIntegerField(default=0)
    views_count        = models.PositiveIntegerField(default=0)

    created          = models.DateTimeField(auto_now_add=True)
    updated          = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created']
        indexes  = [
            models.Index(fields=['status', 'trade_category']),
            models.Index(fields=['state', 'status']),
        ]

    def __str__(self):
        return f'{self.title} — {self.employer}'

    # ── Helper ──────────────────────────────────────────────────────────────

    def get_clip_input_text(self) -> str:
        """
        Build the text sent to the CLIP text encoder for this job.

        Combines: title + trade category + required skills + description.
        """
        parts = [self.title]
        if self.trade_category:
            parts.append(self.trade_category.name)
        skill_names = list(
            self.required_skills.filter(is_active=True).values_list('name', flat=True)
        )
        if skill_names:
            parts.append(', '.join(skill_names))
        if self.description:
            parts.append(self.description)
        return '. '.join(parts)


# ──────────────────────────────────────────────────────────────────────────────
#  8.  CLIP MATCH  ← the recommendation engine's core table
# ──────────────────────────────────────────────────────────────────────────────

class CLIPMatch(models.Model):
    """
    Precomputed hybrid match score between a WorkerProfile and a Job.

    The final `score` is a weighted combination of six signals:
        text_score       × 0.50  — sentence-transformer semantic similarity
        location_score   × 0.15  — same state / willing to relocate
        experience_score × 0.15  — experience level fits job type
        image_score      × 0.10  — CLIP portfolio image similarity
        rating_score     × 0.05  — normalised worker avg rating
        verification     × 0.05  — admin-verified worker bonus

    Population strategy
    ───────────────────
    A Celery background task runs:
      1. Job posted/activated  → compute scores for all workers in same trade.
      2. Worker profile saved  → recompute scores for all active jobs in their trade.

    Query pattern for "recommend workers for a job":
        CLIPMatch.objects.filter(job=job, score__gte=0.60)
                         .select_related('worker__user')
                         .order_by('-score')[:20]

    Query pattern for "recommend jobs for a worker":
        CLIPMatch.objects.filter(worker=profile, job__status='active')
                         .select_related('job__employer')
                         .order_by('-score')[:20]
    """

    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    worker      = models.ForeignKey(
        WorkerProfile,
        on_delete=models.CASCADE,
        related_name='clip_matches',
    )
    job         = models.ForeignKey(
        Job,
        on_delete=models.CASCADE,
        related_name='clip_matches',
    )

    # ── Hybrid final score ∈ [0.0, 1.0] ────────────────────────────────────
    # Weighted combination of all signals below.  Values above 0.65 are strong.
    score       = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text='Weighted hybrid score: 50% text + 15% location + 15% experience '
                  '+ 10% image + 5% rating + 5% verification.',
    )

    # ── Component scores (stored for explainability & re-weighting) ──────────
    text_score          = models.FloatField(null=True, blank=True,
        help_text='Sentence-transformer cosine similarity (0–1).')
    image_score         = models.FloatField(null=True, blank=True,
        help_text='CLIP image↔text similarity avg across portfolio items (0–1).')
    location_score      = models.FloatField(null=True, blank=True,
        help_text='1.0=same state, 0.5=willing to relocate/remote, 0.0=different state.')
    experience_score    = models.FloatField(null=True, blank=True,
        help_text='How well the worker experience level fits the job type (0–1).')
    rating_score        = models.FloatField(null=True, blank=True,
        help_text='Normalised average worker rating: (avg-1)/4. Default 0.5 if no ratings.')
    verification_bonus  = models.FloatField(null=True, blank=True,
        help_text='1.0 if worker is admin-verified, 0.0 otherwise.')

    # Flag set if the worker has already applied, so we skip re-recommending
    is_applied  = models.BooleanField(default=False)

    computed_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('worker', 'job')
        indexes         = [
            models.Index(fields=['job', '-score']),
            models.Index(fields=['worker', '-score']),
        ]
        ordering        = ['-score']

    def __str__(self):
        return (
            f'{self.worker.user.username} ↔ {self.job.title} '
            f'[score={self.score:.3f}]'
        )


# ──────────────────────────────────────────────────────────────────────────────
#  9.  JOB APPLICATION
# ──────────────────────────────────────────────────────────────────────────────

class JobApplication(models.Model):

    class Status(models.TextChoices):
        PENDING      = 'pending',     'Pending Review'
        SHORTLISTED  = 'shortlisted', 'Shortlisted'
        ACCEPTED     = 'accepted',    'Accepted'
        REJECTED     = 'rejected',    'Rejected'
        WITHDRAWN    = 'withdrawn',   'Withdrawn by Worker'

    id               = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job              = models.ForeignKey(
        Job, on_delete=models.CASCADE, related_name='applications',
    )
    worker           = models.ForeignKey(
        WorkerProfile, on_delete=models.CASCADE, related_name='applications',
    )
    cover_note       = models.TextField(
        blank=True,
        help_text="Brief message from the worker to the employer.",
    )

    # The CLIP score at the time of application — preserved even if profiles change.
    clip_match_score = models.FloatField(
        null=True, blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text='Snapshot of the CLIP similarity score when the application was made.',
    )

    status           = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING,
    )
    applied_at       = models.DateTimeField(auto_now_add=True)
    updated_at       = models.DateTimeField(auto_now=True)

    # Optional employer note (only visible to employer)
    employer_note    = models.TextField(blank=True)

    class Meta:
        unique_together = ('job', 'worker')
        ordering        = ['-applied_at']
        indexes         = [
            models.Index(fields=['job', 'status']),
            models.Index(fields=['worker', 'status']),
        ]

    def __str__(self):
        return f'{self.worker.user.username} → {self.job.title} [{self.status}]'


# ──────────────────────────────────────────────────────────────────────────────
#  10.  SAVED JOB  (bookmarks)
# ──────────────────────────────────────────────────────────────────────────────

class SavedJob(models.Model):
    """
    Worker bookmarks a job listing.
    Matches the heart/save button shown on the job cards in the homepage.
    """

    id       = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    worker   = models.ForeignKey(
        WorkerProfile, on_delete=models.CASCADE, related_name='saved_jobs',
    )
    job      = models.ForeignKey(
        Job, on_delete=models.CASCADE, related_name='saved_by',
    )
    saved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('worker', 'job')
        ordering        = ['-saved_at']

    def __str__(self):
        return f'{self.worker.user.username} saved "{self.job.title}"'


# ──────────────────────────────────────────────────────────────────────────────
#  11.  REVIEW
#       Bidirectional ratings after a job is completed.
# ──────────────────────────────────────────────────────────────────────────────

class Review(models.Model):

    class ReviewType(models.TextChoices):
        EMPLOYER_TO_WORKER = 'employer_to_worker', 'Employer → Worker'
        WORKER_TO_EMPLOYER = 'worker_to_employer', 'Worker → Employer'

    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job         = models.ForeignKey(
        Job, on_delete=models.CASCADE, related_name='reviews',
    )
    reviewer    = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reviews_given',
    )
    reviewee    = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reviews_received',
    )
    review_type = models.CharField(max_length=25, choices=ReviewType.choices)

    # 1–5 star rating
    rating      = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    comment     = models.TextField(blank=True)
    is_visible  = models.BooleanField(
        default=True,
        help_text='Admin can hide inappropriate reviews.',
    )
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        # One review per reviewer per job per direction
        unique_together = ('job', 'reviewer', 'review_type')
        ordering        = ['-created_at']
        indexes         = [
            models.Index(fields=['reviewee', 'is_visible', 'review_type']),
            models.Index(fields=['job']),
        ]

    def __str__(self):
        return (
            f'{self.reviewer.username} → {self.reviewee.username} '
            f'({self.rating}★) on "{self.job.title}"'
        )


# ──────────────────────────────────────────────────────────────────────────────
#  12.  NOTIFICATION
# ──────────────────────────────────────────────────────────────────────────────

class Notification(models.Model):

    class NotifType(models.TextChoices):
        NEW_MATCH          = 'new_match',          'New Job Match'
        APPLICATION_UPDATE = 'application_update', 'Application Status Update'
        NEW_APPLICATION    = 'new_application',    'New Application Received'
        NEW_REVIEW         = 'new_review',          'New Review'
        JOB_EXPIRING       = 'job_expiring',        'Job Expiring Soon'
        PROFILE_TIP        = 'profile_tip',         'Profile Improvement Tip'
        SYSTEM             = 'system',              'System Message'
        ESCROW_FUNDED      = 'escrow_funded',       'Escrow Funded'
        ESCROW_SUBMITTED   = 'escrow_submitted',    'Work Submitted for Review'
        ESCROW_APPROVED    = 'escrow_approved',      'Milestone Approved'
        ESCROW_RELEASED    = 'escrow_released',      'Payment Released'
        ESCROW_DISPUTE     = 'escrow_dispute',       'Dispute Raised'
        # ── Hiring / LinkedIn mode ─────────────────────────────────────────
        HIRING_INTEREST_RECEIVED = 'hiring_interest_received', 'New Hire Interest Received'
        HIRING_INTEREST_REPLIED  = 'hiring_interest_replied',  'Worker Replied to Outreach'
        SKILL_ENDORSED           = 'skill_endorsed',            'Your Skill Was Endorsed'
        PROFILE_SAVED            = 'profile_saved',             'An Employer Saved Your Profile'

    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user       = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
    )
    notif_type = models.CharField(max_length=30, choices=NotifType.choices)
    title      = models.CharField(max_length=180)
    body       = models.TextField(blank=True)

    # Arbitrary JSON payload, e.g. {"job_id": "...", "score": 0.91}
    data       = models.JSONField(default=dict, blank=True)

    is_read    = models.BooleanField(default=False)
    # Soft-delete: hidden from the user's dashboard but kept for admin records
    is_deleted = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes  = [
            models.Index(fields=['user', 'is_read', 'is_deleted']),
            models.Index(fields=['user', 'is_deleted', '-created_at']),
        ]

    def __str__(self):
        return f'[{self.notif_type}] → {self.user.username}: {self.title}'

    def get_absolute_url(self):
        """
        Returns the most meaningful URL for this notification so users can
        navigate directly to the related object when they click a notification.
        """
        from django.urls import reverse

        nt   = self.notif_type
        data = self.data or {}

        job_id         = data.get('job_id')
        application_id = data.get('application_id')
        contract_id    = data.get('contract_id')

        if nt == self.NotifType.NEW_MATCH and job_id:
            return reverse('marketplace:job_detail', kwargs={'pk': job_id})

        if nt == self.NotifType.NEW_APPLICATION and job_id:
            return reverse('marketplace:job_applications', kwargs={'pk': job_id})

        if nt == self.NotifType.APPLICATION_UPDATE:
            return reverse('marketplace:worker_applications')

        if nt == self.NotifType.NEW_REVIEW and job_id:
            return reverse('marketplace:job_detail', kwargs={'pk': job_id})

        if nt in (
            self.NotifType.JOB_EXPIRING,
        ) and job_id:
            return reverse('marketplace:job_detail', kwargs={'pk': job_id})

        if nt == self.NotifType.PROFILE_TIP:
            return reverse('marketplace:worker_profile_edit')

        if nt in (
            self.NotifType.ESCROW_FUNDED,
            self.NotifType.ESCROW_SUBMITTED,
            self.NotifType.ESCROW_APPROVED,
            self.NotifType.ESCROW_RELEASED,
            self.NotifType.ESCROW_DISPUTE,
        ) and contract_id:
            return reverse('marketplace:contract_detail', kwargs={'pk': contract_id})

        # Fallback: notifications list
        return reverse('marketplace:notifications')


# ──────────────────────────────────────────────────────────────────────────────
#  13.  CONTRACT
#       Links an accepted JobApplication to an escrow-backed engagement.
# ──────────────────────────────────────────────────────────────────────────────

class Contract(models.Model):
    """
    Represents a formal engagement between an employer and a worker,
    created after a JobApplication is accepted.  Milestones (and their
    escrowed funds) live under a Contract.
    """

    class Status(models.TextChoices):
        PENDING    = 'pending',    'Pending'
        ACTIVE     = 'active',     'Active'
        COMPLETED  = 'completed',  'Completed'
        DISPUTED   = 'disputed',   'Disputed'
        CANCELLED  = 'cancelled',  'Cancelled'

    id               = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job              = models.ForeignKey(
        Job, on_delete=models.PROTECT, related_name='contracts',
    )
    application      = models.OneToOneField(
        JobApplication, on_delete=models.PROTECT, related_name='contract',
    )
    employer         = models.ForeignKey(
        EmployerProfile, on_delete=models.PROTECT, related_name='contracts',
    )
    worker           = models.ForeignKey(
        WorkerProfile, on_delete=models.PROTECT, related_name='contracts',
    )
    title            = models.CharField(
        max_length=256,
        help_text='Auto-populated from the job title on save.',
    )
    status           = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING,
    )
    platform_fee_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=10.00,
        help_text='Percentage deducted from worker payout (e.g. 10.00 = 10%).',
    )
    created_at       = models.DateTimeField(auto_now_add=True)
    updated_at       = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Contract: {self.title} — {self.employer} ↔ {self.worker}'

    def save(self, *args, **kwargs):
        if not self.title and self.job_id:
            self.title = self.job.title
        super().save(*args, **kwargs)


# ──────────────────────────────────────────────────────────────────────────────
#  14.  MILESTONE
#       Individual payment milestones within a Contract.
# ──────────────────────────────────────────────────────────────────────────────

class Milestone(models.Model):
    """
    A single deliverable within a Contract.  Each milestone has its own
    escrowed funds, lifecycle (fund → submit → approve → release), and
    Paystack payment/transfer references.
    """

    class Status(models.TextChoices):
        UNFUNDED     = 'unfunded',     'Unfunded'
        FUNDED       = 'funded',       'Funded (In Escrow)'
        IN_REVIEW    = 'in_review',    'In Review'
        APPROVED     = 'approved',     'Approved'
        PENDING_OTP  = 'pending_otp',  'Pending OTP (Transfer Awaiting Confirmation)'
        RELEASED     = 'released',     'Released'
        DISPUTED     = 'disputed',     'Disputed'
        REFUNDED     = 'refunded',     'Refunded'

    id                   = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    contract             = models.ForeignKey(
        Contract, on_delete=models.PROTECT, related_name='milestones',
    )
    title                = models.CharField(max_length=200)
    description          = models.TextField()
    amount               = models.DecimalField(
        max_digits=12, decimal_places=2,
        help_text='Gross amount the employer pays into escrow (NGN).',
    )
    status               = models.CharField(
        max_length=20, choices=Status.choices, default=Status.UNFUNDED,
    )
    due_date             = models.DateField(null=True, blank=True)
    funded_at            = models.DateTimeField(null=True, blank=True)
    submitted_at         = models.DateTimeField(null=True, blank=True)
    approved_at          = models.DateTimeField(null=True, blank=True)
    auto_release_at      = models.DateTimeField(
        null=True, blank=True,
        help_text='Set to funded_at + 7 days when worker submits work.',
    )
    submission_note      = models.TextField(
        blank=True,
        help_text="Worker's delivery note when submitting work.",
    )
    paystack_payment_ref = models.CharField(
        max_length=100, unique=True, null=True, blank=True,
        help_text='Paystack transaction reference for the escrow charge.',
    )
    paystack_transfer_ref = models.CharField(
        max_length=100, null=True, blank=True,
        help_text='Paystack transfer reference for the worker payout.',
    )
    worker_amount        = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text='Amount after platform fee deduction, computed on release.',
    )
    display_order        = models.PositiveIntegerField(default=0)
    created_at           = models.DateTimeField(auto_now_add=True)
    updated_at           = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['contract', 'display_order', 'created_at']

    def __str__(self):
        return f'{self.title} — ₦{self.amount} [{self.status}]'


# ──────────────────────────────────────────────────────────────────────────────
#  15.  WORKER BANK ACCOUNT
#       Bank details for Paystack payouts to workers.
# ──────────────────────────────────────────────────────────────────────────────

class WorkerBankAccount(models.Model):
    """
    Stores a worker's Nigerian bank account details for receiving payouts
    via Paystack Transfers.  Card details are never stored — only the
    bank account (NUBAN) information needed for direct transfers.
    """

    id                     = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    worker                 = models.OneToOneField(
        WorkerProfile, on_delete=models.PROTECT, related_name='bank_account',
    )
    account_name           = models.CharField(max_length=200)
    account_number         = models.CharField(
        max_length=10,
        help_text='10-digit NUBAN account number.',
    )
    bank_code              = models.CharField(
        max_length=10,
        help_text='Paystack bank code (e.g. "044" for Access Bank).',
    )
    bank_name              = models.CharField(max_length=100)
    paystack_recipient_code = models.CharField(
        max_length=100, blank=True,
        help_text='Created via Paystack Transfer Recipient API.',
    )
    is_verified            = models.BooleanField(default=False)
    created_at             = models.DateTimeField(auto_now_add=True)
    updated_at             = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Worker Bank Account'
        verbose_name_plural = 'Worker Bank Accounts'

    def __str__(self):
        masked = f'****{self.account_number[-4:]}' if len(self.account_number) >= 4 else '****'
        return f'{self.worker.user.username} — {self.bank_name} {masked}'


# ──────────────────────────────────────────────────────────────────────────────
#  16.  DISPUTE
#       Raised when either party disagrees on milestone delivery.
# ──────────────────────────────────────────────────────────────────────────────

class Dispute(models.Model):
    """
    Records a dispute raised against a milestone.  Admin reviews the
    evidence and resolves by either releasing funds to the worker or
    refunding the employer.
    """

    class Resolution(models.TextChoices):
        PENDING              = 'pending',              'Pending'
        RELEASED_TO_WORKER   = 'released_to_worker',   'Released to Worker'
        REFUNDED_TO_EMPLOYER = 'refunded_to_employer',  'Refunded to Employer'
        SPLIT                = 'split',                 'Split'

    id               = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    milestone        = models.OneToOneField(
        Milestone, on_delete=models.PROTECT, related_name='dispute',
    )
    raised_by        = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='raised_disputes',
    )
    reason           = models.TextField()
    evidence         = models.FileField(
        upload_to='disputes/evidence/', null=True, blank=True,
    )
    evidence_sha256  = models.CharField(
        max_length=64, blank=True,
        help_text='SHA-256 of the evidence file at upload time (tamper detection).',
    )
    resolution       = models.CharField(
        max_length=30, choices=Resolution.choices, default=Resolution.PENDING,
    )
    resolution_note  = models.TextField(blank=True)
    split_worker_pct = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text='For SPLIT resolution: percentage (0-100) released to the worker.',
    )
    resolved_at      = models.DateTimeField(null=True, blank=True)
    resolved_by      = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='resolved_disputes',
    )

    # ── Mediation (5-day self-resolution window) ─────────────────────────
    mediation_deadline       = models.DateTimeField(
        null=True, blank=True,
        help_text='Set to created_at + 5 days. Admin cannot act until this passes.',
    )
    mediation_employer_agreed = models.CharField(
        max_length=30, blank=True,
        help_text='Resolution the employer agreed to during mediation window.',
    )
    mediation_worker_agreed   = models.CharField(
        max_length=30, blank=True,
        help_text='Resolution the worker agreed to during mediation window.',
    )

    # ── SLA / Escalation ─────────────────────────────────────────────────
    escalated        = models.BooleanField(
        default=False,
        help_text='Set True when dispute has been open 72h+ without resolution.',
    )
    auto_release_at  = models.DateTimeField(
        null=True, blank=True,
        help_text='Set to created_at + 7 days. Funds auto-release to worker if admin has not acted.',
    )

    created_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Dispute: {self.milestone.title} — {self.resolution}'


# ──────────────────────────────────────────────────────────────────────────────
#  17.  DISPUTE MESSAGE
#       Immutable evidence thread — both parties + admin post here after
#       a dispute is opened.  Provides an auditable conversation log.
# ──────────────────────────────────────────────────────────────────────────────

class DisputeMessage(models.Model):
    """
    A single message/evidence post within a Dispute thread.
    Once created it is never edited or deleted — forms the immutable audit log.
    """

    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dispute    = models.ForeignKey(
        Dispute, on_delete=models.CASCADE, related_name='messages',
    )
    author     = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='dispute_messages',
    )
    body       = models.TextField(help_text='Message body — visible to both parties and admin.')
    attachment = models.FileField(
        upload_to='disputes/messages/', null=True, blank=True,
    )
    attachment_sha256 = models.CharField(
        max_length=64, blank=True,
        help_text='SHA-256 of attachment at upload time.',
    )
    is_admin_note = models.BooleanField(
        default=False,
        help_text='If True, only admin/staff can see this message.',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'DisputeMessage by {self.author.username} on {self.created_at:%Y-%m-%d %H:%M}'