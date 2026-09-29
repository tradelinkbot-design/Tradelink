"""
verification/admin.py
"""

from django.contrib import admin
from django.utils.html import format_html
from .models import VerificationProfile, VerificationAttempt


@admin.register(VerificationProfile)
class VerificationProfileAdmin(admin.ModelAdmin):
    list_display  = ('user', 'level_badge', 'nin_verified', 'bvn_verified',
                     'cac_verified', 'updated')
    list_filter   = ('level', 'nin_verified', 'bvn_verified', 'cac_verified')
    search_fields = ('user__username', 'user__email', 'cac_rc_number', 'cac_company_name')
    readonly_fields = ('created', 'updated', 'nin_dojah_ref', 'bvn_dojah_ref', 'cac_dojah_ref')

    fieldsets = (
        ('User', {'fields': ('user', 'level')}),
        ('NIN (Level 1)', {'fields': ('nin_verified', 'nin_verified_at', 'nin_last4', 'nin_dojah_ref')}),
        ('BVN (Level 2)', {'fields': ('bvn_verified', 'bvn_verified_at', 'bvn_last4', 'bvn_dojah_ref')}),
        ('CAC (Level 3)', {'fields': ('cac_verified', 'cac_verified_at', 'cac_rc_number', 'cac_company_name', 'cac_dojah_ref')}),
        ('Timestamps',   {'fields': ('created', 'updated')}),
    )

    def level_badge(self, obj):
        colours = {0: '#6B7280', 1: '#3B82F6', 2: '#F59E0B', 3: '#10B981'}
        labels  = {0: '⬤ Unverified', 1: '⬤ ID Verified', 2: '⬤ Enhanced', 3: '⬤ Trusted Biz'}
        colour  = colours.get(obj.level, '#6B7280')
        label   = labels.get(obj.level, 'Unknown')
        return format_html(
            '<span style="color:{}; font-weight:600;">{}</span>', colour, label
        )
    level_badge.short_description = 'Verification Level'


@admin.register(VerificationAttempt)
class VerificationAttemptAdmin(admin.ModelAdmin):
    list_display  = ('user', 'ver_type', 'status', 'identifier_hint', 'dojah_ref', 'created')
    list_filter   = ('ver_type', 'status')
    search_fields = ('user__username', 'user__email', 'dojah_ref')
    readonly_fields = ('user', 'ver_type', 'status', 'identifier_hint',
                       'dojah_ref', 'error_message', 'created')
    ordering = ['-created']
