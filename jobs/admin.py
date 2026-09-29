"""
marketplace/admin.py
====================
Admin configuration for all TradeLink NG marketplace models.

Design decisions:
  - Embedding fields (clip_*_embedding) are collapsed + read-only — they are
    large JSON arrays that should never be hand-edited.
  - Inlines are used wherever a child model only makes sense in the context of
    its parent (skills inside a trade, portfolio inside a worker profile, etc.)
  - Custom actions let admins bulk-verify workers/employers and trigger
    CLIP re-computation directly from the changelist.
  - list_editable is used on quick-toggle booleans (is_active, is_verified, etc.)
    to save round-trips.
"""

from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Avg, Count
from django.utils import timezone

from .models import (
    TradeCategory,
    Skill,
    WorkerProfile,
    WorkerSkill,
    PortfolioItem,
    EmployerProfile,
    Job,
    CLIPMatch,
    JobApplication,
    SavedJob,
    Review,
    Notification,
    Contract,
    Milestone,
    WorkerBankAccount,
    Dispute,
    DisputeMessage,
)


# ──────────────────────────────────────────────────────────────────────────────
#  TRADE CATEGORY
# ──────────────────────────────────────────────────────────────────────────────

class SkillInline(admin.TabularInline):
    model  = Skill
    extra  = 2
    fields = ['name', 'slug', 'is_active']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(TradeCategory)
class TradeCategoryAdmin(admin.ModelAdmin):
    list_display    = [
        'name', 'slug', 'icon_class',
        'worker_count', 'job_count',
        'is_active', 'display_order',
    ]
    list_filter     = ['is_active']
    search_fields   = ['name', 'description', 'clip_context_text']
    prepopulated_fields = {'slug': ('name',)}
    list_editable   = ['is_active', 'display_order']
    readonly_fields = ['created']
    inlines         = [SkillInline]

    fieldsets = (
        (None, {
            'fields': ('name', 'slug', 'icon_class', 'is_active', 'display_order'),
        }),
        ('Content', {
            'fields': ('description',),
        }),
        ('CLIP Context', {
            'fields': ('clip_context_text',),
            'description': (
                'This text is sent to the CLIP text encoder as a fallback when '
                'a job in this trade has a thin description. Write it as natural '
                'language, e.g. "expert electrician wiring installation Lagos Nigeria".'
            ),
        }),
        ('Timestamps', {
            'fields': ('created',),
            'classes': ('collapse',),
        }),
    )

    # ── Annotated columns ───────────────────────────────────────────────────

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(
            _worker_count=Count('workers', distinct=True),
            _job_count=Count('jobs', distinct=True),
        )

    @admin.display(description='Workers', ordering='_worker_count')
    def worker_count(self, obj):
        return obj._worker_count

    @admin.display(description='Jobs', ordering='_job_count')
    def job_count(self, obj):
        return obj._job_count


# ──────────────────────────────────────────────────────────────────────────────
#  SKILL  (also managed as inline under TradeCategory)
# ──────────────────────────────────────────────────────────────────────────────

@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display  = ['name', 'category', 'slug', 'is_active', 'worker_count']
    list_filter   = ['category', 'is_active']
    search_fields = ['name', 'category__name']
    prepopulated_fields = {'slug': ('name',)}
    list_editable = ['is_active']

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _worker_count=Count('workers', distinct=True),
        )

    @admin.display(description='Workers', ordering='_worker_count')
    def worker_count(self, obj):
        return obj._worker_count


# ──────────────────────────────────────────────────────────────────────────────
#  WORKER PROFILE
# ──────────────────────────────────────────────────────────────────────────────

class WorkerSkillInline(admin.TabularInline):
    model  = WorkerSkill
    extra  = 1
    fields = ['skill', 'years_experience', 'proficiency']
    autocomplete_fields = ['skill']


class PortfolioItemInline(admin.StackedInline):
    model         = PortfolioItem
    extra         = 0
    fields        = ['image', 'caption', 'trade_context', 'display_order']
    readonly_fields = ['clip_image_embedding']
    show_change_link = True


@admin.register(WorkerProfile)
class WorkerProfileAdmin(admin.ModelAdmin):
    list_display  = [
        'username', 'trade_category', 'experience_level', 'state',
        'availability', 'is_verified', 'is_featured', 'profile_completion_bar',
        'clip_status',
    ]
    list_filter   = [
        'trade_category', 'state', 'availability',
        'is_verified', 'is_featured', 'experience_level',
    ]
    search_fields = ['user__username', 'user__email', 'user__first_name', 'bio']
    list_editable = ['is_verified', 'is_featured']
    inlines       = [WorkerSkillInline, PortfolioItemInline]
    actions       = ['action_verify', 'action_feature', 'action_unfeature']
    autocomplete_fields = ['user', 'trade_category']

    readonly_fields = [
        'text_embedding', 'text_embedding_updated',        # hybrid (sentence-transformers)
        'clip_text_embedding', 'clip_embedding_updated',  # legacy CLIP text encoder
        'created', 'updated', 'clip_input_preview',
    ]

    fieldsets = (
        ('Account', {
            'fields': ('user',),
        }),
        ('Trade & Experience', {
            'fields': (
                'trade_category', 'experience_level',
                'years_experience', 'bio',
            ),
        }),
        ('Location', {
            'fields': ('state', 'lga', 'is_willing_to_relocate'),
        }),
        ('Rates & Availability', {
            'fields': ('hourly_rate', 'daily_rate', 'availability'),
        }),
        ('Platform Status', {
            'fields': ('is_verified', 'is_featured', 'profile_completion'),
        }),
        ('AI Embeddings (read-only)', {
            'fields': (
                'clip_input_preview',
                'text_embedding_updated', 'text_embedding',
                'clip_embedding_updated', 'clip_text_embedding',
            ),
            'classes': ('collapse',),
            'description': (
                'text_embedding — sentence-transformer 768-dim (primary signal, written by the hybrid engine). '
                'clip_text_embedding — legacy 512-dim CLIP text encoder (kept for backward compat). '
                'Do not edit either field manually.'
            ),
        }),
        ('Timestamps', {
            'fields': ('created', 'updated'),
            'classes': ('collapse',),
        }),
    )

    # ── Computed columns ────────────────────────────────────────────────────

    @admin.display(description='Username', ordering='user__username')
    def username(self, obj):
        return obj.user.username

    @admin.display(description='Profile %')
    def profile_completion_bar(self, obj):
        pct   = obj.profile_completion
        color = '#10B981' if pct >= 80 else '#F59E0B' if pct >= 40 else '#EF4444'
        return format_html(
            '<div style="width:80px;background:#333;border-radius:4px;">'
            '<div style="width:{pct}%;background:{color};height:8px;border-radius:4px;"></div>'
            '</div> {pct}%',
            pct=pct, color=color,
        )

    @admin.display(description='AI Embed')
    def clip_status(self, obj):
        # Prefer the new sentence-transformer embedding; fall back to legacy CLIP
        if obj.text_embedding:
            updated = obj.text_embedding_updated
            return format_html(
                '<span style="color:#10B981;">✓ ST</span> <span style="font-size:0.8em;color:#888;">{}</span>',
                updated.strftime('%d %b %Y') if updated else '—',
            )
        if obj.clip_text_embedding:
            updated = obj.clip_embedding_updated
            return format_html(
                '<span style="color:#F59E0B;">✓ CLIP</span> <span style="font-size:0.8em;color:#888;">{}</span>',
                updated.strftime('%d %b %Y') if updated else '—',
            )
        return format_html('<span style="color:#EF4444;">✗ Not computed</span>')

    @admin.display(description='CLIP Input Text Preview')
    def clip_input_preview(self, obj):
        text = obj.get_clip_input_text()
        return text[:300] + '…' if len(text) > 300 else text

    # ── Bulk actions ────────────────────────────────────────────────────────

    @admin.action(description='✅ Mark selected workers as Verified')
    def action_verify(self, request, queryset):
        updated = queryset.update(is_verified=True)
        self.message_user(request, f'{updated} worker(s) marked as verified.')

    @admin.action(description='⭐ Mark selected workers as Featured')
    def action_feature(self, request, queryset):
        updated = queryset.update(is_featured=True)
        self.message_user(request, f'{updated} worker(s) marked as featured.')

    @admin.action(description='Remove Featured from selected workers')
    def action_unfeature(self, request, queryset):
        updated = queryset.update(is_featured=False)
        self.message_user(request, f'{updated} worker(s) removed from featured.')


# ──────────────────────────────────────────────────────────────────────────────
#  WORKER SKILL  (also managed as inline under WorkerProfile)
# ──────────────────────────────────────────────────────────────────────────────

@admin.register(WorkerSkill)
class WorkerSkillAdmin(admin.ModelAdmin):
    list_display  = ['worker', 'skill', 'proficiency', 'years_experience']
    list_filter   = ['proficiency', 'skill__category']
    search_fields = ['worker__user__username', 'skill__name']
    autocomplete_fields = ['worker', 'skill']


# ──────────────────────────────────────────────────────────────────────────────
#  PORTFOLIO ITEM
# ──────────────────────────────────────────────────────────────────────────────

@admin.register(PortfolioItem)
class PortfolioItemAdmin(admin.ModelAdmin):
    list_display    = ['worker', 'caption_preview', 'trade_context', 'clip_status', 'created', 'youtube_url']
    list_filter     = ['trade_context']
    search_fields   = ['worker__user__username', 'caption']
    readonly_fields = ['clip_image_embedding', 'created', 'image_preview']
    autocomplete_fields = ['worker', 'trade_context']

    fieldsets = (
        (None, {
            'fields': ('worker', 'trade_context', 'image', 'image_preview', 'caption', 'display_order'),
        }),
        ('CLIP Embedding (read-only)', {
            'fields': ('clip_image_embedding',),
            'classes': ('collapse',),
        }),
        ('Timestamps', {
            'fields': ('created',),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='Caption')
    def caption_preview(self, obj):
        return obj.caption[:60] + '…' if len(obj.caption) > 60 else obj.caption or '—'

    @admin.display(description='Image Preview')
    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="max-height:120px;border-radius:8px;" />',
                obj.image.url,
            )
        return '—'

    @admin.display(description='CLIP')
    def clip_status(self, obj):
        if obj.clip_image_embedding:
            return format_html('<span style="color:#10B981;">✓ Encoded</span>')
        return format_html('<span style="color:#EF4444;">✗ Not encoded</span>')


# ──────────────────────────────────────────────────────────────────────────────
#  EMPLOYER PROFILE
# ──────────────────────────────────────────────────────────────────────────────

@admin.register(EmployerProfile)
class EmployerProfileAdmin(admin.ModelAdmin):
    list_display  = [
        'display_name', 'company_type', 'state',
        'is_verified', 'jobs_posted', 'created',
    ]
    list_filter   = ['company_type', 'state', 'is_verified']
    search_fields = ['company_name', 'user__username', 'user__email', 'industry']
    list_editable = ['is_verified']
    readonly_fields = ['created', 'updated']
    actions       = ['action_verify']
    autocomplete_fields = ['user']

    fieldsets = (
        ('Account', {
            'fields': ('user',),
        }),
        ('Company Info', {
            'fields': ('company_name', 'company_type', 'website'),
        }),
        ('Location', {
            'fields': ('state', 'lga'),
        }),
        ('Platform Status', {
            'fields': ('is_verified',),
        }),
        ('Timestamps', {
            'fields': ('created', 'updated'),
            'classes': ('collapse',),
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _jobs_count=Count('jobs', distinct=True),
        )

    @admin.display(description='Name', ordering='company_name')
    def display_name(self, obj):
        return obj.company_name or obj.user.username

    @admin.display(description='Jobs Posted', ordering='_jobs_count')
    def jobs_posted(self, obj):
        return obj._jobs_count

    @admin.action(description='✅ Mark selected employers as Verified')
    def action_verify(self, request, queryset):
        updated = queryset.update(is_verified=True)
        self.message_user(request, f'{updated} employer(s) marked as verified.')


# ──────────────────────────────────────────────────────────────────────────────
#  JOB
# ──────────────────────────────────────────────────────────────────────────────

class JobApplicationInline(admin.TabularInline):
    model   = JobApplication
    extra   = 0
    fields  = ['worker', 'status', 'clip_match_score', 'applied_at']
    readonly_fields = ['worker', 'clip_match_score', 'applied_at']
    can_delete = False
    show_change_link = True


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display  = [
        'title', 'employer', 'trade_category', 'job_type',
        'state', 'status', 'applications_count',
        'clip_status', 'created',
    ]
    list_filter   = ['status', 'job_type', 'pay_type', 'trade_category', 'state', 'is_remote']
    search_fields = ['title', 'description', 'employer__company_name', 'employer__user__username']
    list_editable = ['status']
    readonly_fields = [
        'text_embedding', 'text_embedding_updated',        # hybrid (sentence-transformers)
        'clip_embedding', 'clip_embedding_updated',        # legacy CLIP text encoder
        'applications_count', 'views_count',
        'created', 'updated', 'clip_input_preview',
    ]
    filter_horizontal = ['required_skills']
    inlines   = [JobApplicationInline]
    date_hierarchy = 'created'
    actions   = ['action_activate', 'action_close']
    autocomplete_fields = ['employer', 'trade_category']

    fieldsets = (
        ('Basic Info', {
            'fields': ('employer', 'trade_category', 'required_skills', 'title', 'description'),
        }),
        ('Type & Pay', {
            'fields': ('job_type', 'pay_type', 'pay_min', 'pay_max', 'slots'),
        }),
        ('Location', {
            'fields': ('state', 'lga', 'is_remote'),
        }),
        ('Status & Lifecycle', {
            'fields': ('status', 'deadline'),
        }),
        ('Stats', {
            'fields': ('applications_count', 'views_count'),
            'classes': ('collapse',),
        }),
        ('AI Embeddings (read-only)', {
            'fields': (
                'clip_input_preview',
                'text_embedding_updated', 'text_embedding',
                'clip_embedding_updated', 'clip_embedding',
            ),
            'classes': ('collapse',),
            'description': (
                'text_embedding — sentence-transformer 768-dim. '
                'clip_embedding — legacy 512-dim CLIP text encoder.'
            ),
        }),
        ('Timestamps', {
            'fields': ('created', 'updated'),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='AI Embed')
    def clip_status(self, obj):
        if obj.text_embedding:
            updated = obj.text_embedding_updated
            return format_html(
                '<span style="color:#10B981;">✓ ST</span> <span style="font-size:0.8em;color:#888;">{}</span>',
                updated.strftime('%d %b %Y') if updated else '—',
            )
        if obj.clip_embedding:
            updated = obj.clip_embedding_updated
            return format_html(
                '<span style="color:#F59E0B;">✓ CLIP</span> <span style="font-size:0.8em;color:#888;">{}</span>',
                updated.strftime('%d %b %Y') if updated else '—',
            )
        return format_html('<span style="color:#EF4444;">✗ Not computed</span>')

    @admin.display(description='CLIP Input Text Preview')
    def clip_input_preview(self, obj):
        text = obj.get_clip_input_text()
        return text[:300] + '…' if len(text) > 300 else text

    @admin.action(description='▶ Activate selected jobs')
    def action_activate(self, request, queryset):
        updated = queryset.update(status=Job.Status.ACTIVE)
        self.message_user(request, f'{updated} job(s) set to Active.')

    @admin.action(description='✕ Close selected jobs')
    def action_close(self, request, queryset):
        updated = queryset.update(status=Job.Status.CLOSED)
        self.message_user(request, f'{updated} job(s) closed.')


# ──────────────────────────────────────────────────────────────────────────────
#  CLIP MATCH
# ──────────────────────────────────────────────────────────────────────────────

@admin.register(CLIPMatch)
class CLIPMatchAdmin(admin.ModelAdmin):
    list_display  = ['worker', 'job', 'score_bar', 'is_applied', 'computed_at']
    list_filter   = ['is_applied', 'job__trade_category', 'job__status']
    search_fields = ['worker__user__username', 'job__title']
    readonly_fields = ['worker', 'job', 'score', 'is_applied', 'computed_at']
    ordering      = ['-score']

    # Prevent manual creation — rows are managed by the background task
    def has_add_permission(self, request):
        return False

    @admin.display(description='Score')
    def score_bar(self, obj):
        pct   = int(obj.score * 100)
        color = '#10B981' if pct >= 80 else '#F59E0B' if pct >= 60 else '#EF4444'
        return format_html(
            '<div style="width:80px;background:#333;border-radius:4px;display:inline-block;">'
            '<div style="width:{pct}%;background:{color};height:8px;border-radius:4px;"></div>'
            '</div> {pct}%',
            pct=pct, color=color,
        )


# ──────────────────────────────────────────────────────────────────────────────
#  JOB APPLICATION
# ──────────────────────────────────────────────────────────────────────────────

@admin.register(JobApplication)
class JobApplicationAdmin(admin.ModelAdmin):
    list_display  = [
        'worker', 'job', 'status', 'clip_match_score',
        'applied_at', 'updated_at',
    ]
    list_filter   = ['status', 'job__trade_category', 'job__state']
    search_fields = [
        'worker__user__username', 'worker__user__email',
        'job__title', 'job__employer__company_name',
    ]
    list_editable = ['status']
    readonly_fields = ['worker', 'job', 'clip_match_score', 'applied_at', 'updated_at']
    date_hierarchy = 'applied_at'

    fieldsets = (
        ('Application', {
            'fields': ('worker', 'job', 'cover_note', 'clip_match_score'),
        }),
        ('Status', {
            'fields': ('status', 'employer_note'),
        }),
        ('Timestamps', {
            'fields': ('applied_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )


# ──────────────────────────────────────────────────────────────────────────────
#  SAVED JOB
# ──────────────────────────────────────────────────────────────────────────────

@admin.register(SavedJob)
class SavedJobAdmin(admin.ModelAdmin):
    list_display  = ['worker', 'job', 'saved_at']
    list_filter   = ['job__trade_category', 'job__state']
    search_fields = ['worker__user__username', 'job__title']
    readonly_fields = ['saved_at']


# ──────────────────────────────────────────────────────────────────────────────
#  REVIEW
# ──────────────────────────────────────────────────────────────────────────────

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display  = [
        'reviewer', 'reviewee', 'job',
        'review_type', 'rating', 'is_visible', 'created_at',
    ]
    list_filter   = ['review_type', 'rating', 'is_visible']
    search_fields = ['reviewer__username', 'reviewee__username', 'job__title', 'comment']
    list_editable = ['is_visible']
    readonly_fields = ['reviewer', 'reviewee', 'job', 'review_type', 'rating', 'created_at']
    date_hierarchy = 'created_at'

    actions = ['action_hide']

    @admin.action(description='Hide selected reviews')
    def action_hide(self, request, queryset):
        updated = queryset.update(is_visible=False)
        self.message_user(request, f'{updated} review(s) hidden.')


# ──────────────────────────────────────────────────────────────────────────────
#  NOTIFICATION
# ──────────────────────────────────────────────────────────────────────────────

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display  = ['user', 'notif_type', 'title', 'is_read', 'is_deleted', 'created_at']
    list_filter   = ['notif_type', 'is_read', 'is_deleted']
    search_fields = ['user__username', 'title', 'body']
    list_editable = ['is_read', 'is_deleted']
    readonly_fields = ['user', 'notif_type', 'title', 'body', 'data', 'created_at']
    date_hierarchy = 'created_at'
    ordering      = ['-created_at']


# ──────────────────────────────────────────────────────────────────────────────
#  CONTRACT
# ──────────────────────────────────────────────────────────────────────────────

class MilestoneInline(admin.TabularInline):
    model = Milestone
    extra = 0
    fields = ['title', 'amount', 'status', 'due_date', 'funded_at', 'approved_at', 'display_order']
    readonly_fields = ['funded_at', 'approved_at']
    ordering = ['display_order', 'created_at']


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display  = ['title', 'employer', 'worker', 'status', 'platform_fee_pct', 'created_at']
    list_filter   = ['status']
    search_fields = ['title', 'employer__company_name', 'worker__user__username', 'job__title']
    readonly_fields = ['id', 'job', 'application', 'employer', 'worker', 'created_at', 'updated_at']
    date_hierarchy = 'created_at'
    inlines = [MilestoneInline]


# ──────────────────────────────────────────────────────────────────────────────
#  MILESTONE
# ──────────────────────────────────────────────────────────────────────────────

@admin.register(Milestone)
class MilestoneAdmin(admin.ModelAdmin):
    list_display  = [
        'title', 'contract', 'amount', 'worker_amount',
        'status', 'funded_at', 'auto_release_at',
    ]
    list_filter   = ['status']
    search_fields = ['title', 'contract__title', 'paystack_payment_ref']
    readonly_fields = [
        'id', 'contract', 'paystack_payment_ref', 'paystack_transfer_ref',
        'funded_at', 'submitted_at', 'approved_at', 'auto_release_at',
        'worker_amount', 'created_at', 'updated_at',
    ]
    date_hierarchy = 'created_at'

    actions = ['action_force_release']

    @admin.action(description='Force release selected milestones to worker')
    def action_force_release(self, request, queryset):
        from jobs.service.escrow_service import release_milestone_to_worker
        released = 0
        for milestone in queryset.filter(status__in=[
            Milestone.Status.IN_REVIEW,
            Milestone.Status.APPROVED,
        ]):
            try:
                if release_milestone_to_worker(str(milestone.pk)):
                    released += 1
            except Exception:
                pass
        self.message_user(request, f'{released} milestone(s) released.')


# ──────────────────────────────────────────────────────────────────────────────
#  DISPUTE
# ──────────────────────────────────────────────────────────────────────────────

class DisputeMessageInline(admin.TabularInline):
    model = DisputeMessage
    extra = 0
    readonly_fields = ['author', 'body', 'attachment', 'attachment_sha256', 'is_admin_note', 'created_at']
    can_delete = False


@admin.register(Dispute)
class DisputeAdmin(admin.ModelAdmin):
    list_display  = [
        'milestone', 'raised_by', 'resolution', 'split_worker_pct',
        'escalated', 'mediation_deadline', 'resolved_at', 'created_at',
    ]
    list_filter   = ['resolution', 'escalated']
    search_fields = ['milestone__title', 'raised_by__username', 'reason', 'evidence_sha256']
    readonly_fields = [
        'id', 'milestone', 'raised_by', 'evidence', 'evidence_sha256',
        'mediation_deadline', 'mediation_employer_agreed', 'mediation_worker_agreed',
        'auto_release_at', 'escalated', 'resolved_at', 'resolved_by', 'created_at',
    ]
    inlines = [DisputeMessageInline]
    date_hierarchy = 'created_at'


# ──────────────────────────────────────────────────────────────────────────────
#  WORKER BANK ACCOUNT
# ──────────────────────────────────────────────────────────────────────────────

@admin.register(WorkerBankAccount)
class WorkerBankAccountAdmin(admin.ModelAdmin):
    list_display  = ['worker', 'bank_name', 'account_number', 'is_verified', 'created_at']
    list_filter   = ['is_verified', 'bank_name']
    search_fields = ['worker__user__username', 'account_name', 'bank_name', 'account_number']
    readonly_fields = ['id', 'paystack_recipient_code', 'created_at', 'updated_at']