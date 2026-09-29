"""
bot/admin.py
============
Django admin configuration for the WhatsApp bot app.
"""

from django.contrib import admin
from django.utils.html import format_html

from .models import WhatsAppMessage, WhatsAppSession


class WhatsAppMessageInline(admin.TabularInline):
    model   = WhatsAppSession.messages.field.model
    fields  = ('direction', 'content', 'message_id', 'created')
    readonly_fields = ('direction', 'content', 'message_id', 'created')
    extra   = 0
    max_num = 0
    can_delete = False
    ordering = ('-created',)


@admin.register(WhatsAppSession)
class WhatsAppSessionAdmin(admin.ModelAdmin):
    list_display  = (
        'phone_display', 'user', 'flow', 'step',
        'last_activity', 'created',
    )
    list_filter   = ('flow',)
    search_fields = ('phone_number', 'user__email', 'user__username')
    readonly_fields = ('id', 'created', 'last_activity')
    raw_id_fields  = ('user',)
    inlines        = [WhatsAppMessageInline]

    fieldsets = (
        ('Identity', {
            'fields': ('id', 'phone_number', 'user'),
        }),
        ('Conversation State', {
            'fields': ('flow', 'step', 'data'),
        }),
        ('Timestamps', {
            'fields': ('created', 'last_activity'),
        }),
    )

    @admin.display(description='Phone')
    def phone_display(self, obj):
        return format_html('<code>+{}</code>', obj.phone_number)


@admin.register(WhatsAppMessage)
class WhatsAppMessageAdmin(admin.ModelAdmin):
    list_display  = (
        'created', 'direction_badge', 'phone_display',
        'content_preview',
    )
    list_filter   = ('direction',)
    search_fields = ('session__phone_number', 'content', 'message_id')
    readonly_fields = ('id', 'session', 'direction', 'message_id', 'content', 'created')
    date_hierarchy = 'created'
    ordering       = ('-created',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description='Direction')
    def direction_badge(self, obj):
        colour = '#27ae60' if obj.direction == 'outbound' else '#2980b9'
        arrow  = '→' if obj.direction == 'outbound' else '←'
        return format_html(
            '<span style="color:{}; font-weight:bold;">{} {}</span>',
            colour, arrow, obj.direction,
        )

    @admin.display(description='Phone')
    def phone_display(self, obj):
        return format_html('<code>+{}</code>', obj.session.phone_number)

    @admin.display(description='Message')
    def content_preview(self, obj):
        return obj.content[:80] + ('…' if len(obj.content) > 80 else '')
