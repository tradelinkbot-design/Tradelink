"""
hiring/admin.py
===============
Django admin registrations for the hiring app.
"""

from django.contrib import admin
from django.utils.html import format_html

from .models import (
    WorkHistory,
    Certification,
    SkillEndorsement,
    SavedWorker,
    HiringInterest,
    SubscriptionPlan,
    EmployerSubscription,
)


@admin.register(WorkHistory)
class WorkHistoryAdmin(admin.ModelAdmin):
    list_display  = ('worker_username', 'role_title', 'employer_name', 'start_date', 'is_current')
    list_filter   = ('is_current', 'location_state', 'trade_category')
    search_fields = ('worker__user__username', 'employer_name', 'role_title')
    raw_id_fields = ('worker',)

    def worker_username(self, obj):
        return obj.worker.user.username
    worker_username.short_description = 'Worker'


@admin.register(Certification)
class CertificationAdmin(admin.ModelAdmin):
    list_display  = ('worker_username', 'name', 'issuing_body', 'year_obtained', 'is_verified', 'cert_preview')
    list_filter   = ('is_verified', 'issuing_body')
    search_fields = ('worker__user__username', 'name', 'issuing_body')
    raw_id_fields = ('worker',)
    actions       = ['verify_certifications']

    def worker_username(self, obj):
        return obj.worker.user.username
    worker_username.short_description = 'Worker'

    def cert_preview(self, obj):
        if obj.certificate_image:
            return format_html(
                '<a href="{}" target="_blank">View Certificate</a>',
                obj.certificate_image.url,
            )
        return '—'
    cert_preview.short_description = 'Certificate'

    def verify_certifications(self, request, queryset):
        updated = queryset.update(is_verified=True)
        self.message_user(request, f'{updated} certification(s) marked as verified.')
    verify_certifications.short_description = 'Mark selected certifications as Verified'


@admin.register(SkillEndorsement)
class SkillEndorsementAdmin(admin.ModelAdmin):
    list_display  = ('endorsed_by_username', 'skill', 'worker_username', 'created_at')
    list_filter   = ('skill__category',)
    search_fields = ('worker__user__username', 'endorsed_by__username', 'skill__name')
    raw_id_fields = ('worker', 'endorsed_by', 'skill')

    def worker_username(self, obj):
        return obj.worker.user.username
    worker_username.short_description = 'Worker'

    def endorsed_by_username(self, obj):
        return obj.endorsed_by.username
    endorsed_by_username.short_description = 'Endorsed By'


@admin.register(SavedWorker)
class SavedWorkerAdmin(admin.ModelAdmin):
    list_display  = ('employer', 'worker_username', 'saved_at')
    search_fields = ('employer__company_name', 'worker__user__username')
    raw_id_fields = ('employer', 'worker')

    def worker_username(self, obj):
        return obj.worker.user.username
    worker_username.short_description = 'Worker'


@admin.register(HiringInterest)
class HiringInterestAdmin(admin.ModelAdmin):
    list_display  = ('employer', 'worker_username', 'job', 'status', 'sent_at', 'responded_at')
    list_filter   = ('status',)
    search_fields = ('employer__company_name', 'worker__user__username')
    raw_id_fields = ('employer', 'worker', 'job')
    readonly_fields = ('sent_at', 'viewed_at', 'responded_at')

    def worker_username(self, obj):
        return obj.worker.user.username
    worker_username.short_description = 'Worker'


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'price_monthly_ngn', 'talent_searches_per_month',
                    'direct_outreach_per_month', 'job_posts_per_month', 'is_active')
    list_editable = ('is_active',)


@admin.register(EmployerSubscription)
class EmployerSubscriptionAdmin(admin.ModelAdmin):
    list_display  = ('employer', 'plan', 'is_active', 'started_at', 'expires_at',
                     'searches_used', 'outreach_used', 'posts_used')
    list_filter   = ('is_active', 'plan')
    search_fields = ('employer__company_name',)
    raw_id_fields = ('employer',)
    readonly_fields = ('started_at', 'usage_reset_at')
