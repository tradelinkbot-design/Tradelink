"""
digital_skills/admin.py
=======================
Django Admin registration for the digital_skills app.
"""

from django.contrib import admin
from .models import (
    DigitalSkillCategory,
    DigitalSubSkill,
    DigitalWorkerProfile,
    DigitalWorkerSubSkill,
    DigitalPortfolioItem,
    DigitalGig,
    DigitalApplication,
    SavedDigitalGig,
    DigitalWorkerReview,
)


# ── Inlines ──────────────────────────────────────────────────────────────────

class DigitalSubSkillInline(admin.TabularInline):
    model  = DigitalSubSkill
    extra  = 2
    fields = ('name', 'slug', 'is_active')
    prepopulated_fields = {'slug': ('name',)}


class DigitalWorkerSubSkillInline(admin.TabularInline):
    model  = DigitalWorkerSubSkill
    extra  = 1
    fields = ('sub_skill', 'years_exp')


class DigitalPortfolioItemInline(admin.TabularInline):
    model  = DigitalPortfolioItem
    extra  = 0
    fields = ('item_type', 'title', 'image', 'external_url', 'display_order')


# ── Category ─────────────────────────────────────────────────────────────────

@admin.register(DigitalSkillCategory)
class DigitalSkillCategoryAdmin(admin.ModelAdmin):
    list_display   = ('name', 'slug', 'icon_class', 'display_order', 'is_active')
    list_editable  = ('display_order', 'is_active')
    prepopulated_fields = {'slug': ('name',)}
    search_fields  = ('name',)
    inlines        = [DigitalSubSkillInline]


@admin.register(DigitalSubSkill)
class DigitalSubSkillAdmin(admin.ModelAdmin):
    list_display   = ('name', 'category', 'slug', 'is_active')
    list_filter    = ('category', 'is_active')
    search_fields  = ('name', 'category__name')
    prepopulated_fields = {'slug': ('name',)}


# ── Worker Profile ────────────────────────────────────────────────────────────

@admin.register(DigitalWorkerProfile)
class DigitalWorkerProfileAdmin(admin.ModelAdmin):
    list_display   = ('user', 'primary_category', 'experience_level', 'availability',
                       'profile_completion', 'is_verified', 'is_featured', 'created')
    list_filter    = ('primary_category', 'experience_level', 'availability',
                       'is_verified', 'is_featured', 'remote_ok')
    search_fields  = ('user__username', 'user__email', 'headline', 'bio')
    list_editable  = ('is_verified', 'is_featured')
    readonly_fields = ('profile_completion', 'text_embedding_updated', 'created', 'updated')
    inlines        = [DigitalWorkerSubSkillInline, DigitalPortfolioItemInline]

    fieldsets = (
        ('User', {'fields': ('user',)}),
        ('Skills', {'fields': ('primary_category', 'experience_level', 'years_experience')}),
        ('Bio', {'fields': ('headline', 'bio')}),
        ('Rates', {'fields': ('hourly_rate', 'project_rate')}),
        ('Location', {'fields': ('state', 'lga', 'remote_ok')}),
        ('Employment', {'fields': ('availability', 'employment_preference', 'open_to_employment',
                                    'expected_monthly_salary', 'notice_period')}),
        ('Contact', {'fields': ('whatsapp_number', 'portfolio_url', 'linkedin_url', 'twitter_url')}),
        ('Status', {'fields': ('is_verified', 'is_featured', 'profile_completion')}),
        ('AI Embedding', {'fields': ('text_embedding_updated',), 'classes': ('collapse',)}),
        ('Timestamps', {'fields': ('created', 'updated'), 'classes': ('collapse',)}),
    )


# ── Digital Gig ───────────────────────────────────────────────────────────────

@admin.register(DigitalGig)
class DigitalGigAdmin(admin.ModelAdmin):
    list_display   = ('title', 'employer', 'category', 'status', 'budget_type',
                       'budget_min', 'budget_max', 'work_type', 'created')
    list_filter    = ('status', 'budget_type', 'work_type', 'category')
    search_fields  = ('title', 'description', 'employer__company_name')
    list_editable  = ('status',)
    readonly_fields = ('views_count', 'applications_count', 'created', 'updated')


# ── Application ───────────────────────────────────────────────────────────────

@admin.register(DigitalApplication)
class DigitalApplicationAdmin(admin.ModelAdmin):
    list_display   = ('worker', 'gig', 'status', 'proposed_rate', 'created')
    list_filter    = ('status',)
    search_fields  = ('worker__user__username', 'gig__title')
    list_editable  = ('status',)


# ── Review ────────────────────────────────────────────────────────────────────

@admin.register(DigitalWorkerReview)
class DigitalWorkerReviewAdmin(admin.ModelAdmin):
    list_display = ('worker', 'reviewer', 'rating', 'is_public', 'created')
    list_filter  = ('rating', 'is_public')
    search_fields = ('worker__user__username', 'reviewer__username')
