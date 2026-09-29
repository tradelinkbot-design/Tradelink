"""
chats/admin.py
===============
Django admin configuration for the TradeLink NG chat system.

Registered models
──────────────────
  Conversation       — searchable by participant username, product title
  Message            — filterable by type / deleted / edited
  MessageAttachment  — filterable by file type, orphan status
  UserOnlineStatus   — at-a-glance online presence board
"""

from django.contrib import admin
from django.utils.html import format_html

from .models import (
    Conversation,
    Message,
    MessageAttachment,
    MessageReadReceipt,
    UserOnlineStatus,
)


# ──────────────────────────────────────────────────────────────────────────────
#  INLINES
# ──────────────────────────────────────────────────────────────────────────────

class MessageInline(admin.TabularInline):
    model         = Message
    extra         = 0
    fields        = ('sender', 'body_excerpt_col', 'message_type', 'is_deleted', 'created_at')
    readonly_fields = ('body_excerpt_col', 'created_at')
    ordering      = ('-created_at',)
    max_num       = 20
    can_delete    = False

    def body_excerpt_col(self, obj):
        if obj.is_deleted:
            return format_html('<em style="color:#999">[deleted]</em>')
        return (obj.body[:60] + '…') if len(obj.body) > 60 else obj.body or '—'
    body_excerpt_col.short_description = 'Body'


class MessageAttachmentInline(admin.TabularInline):
    model         = MessageAttachment
    extra         = 0
    fields        = ('file_preview', 'file_type', 'original_name', 'file_size', 'created_at')
    readonly_fields = ('file_preview', 'created_at')
    ordering      = ('created_at',)

    def file_preview(self, obj):
        if obj.file and obj.file_type == MessageAttachment.FileType.IMAGE:
            return format_html(
                '<img src="{}" style="height:50px; border-radius:4px;" />',
                obj.file.url,
            )
        return obj.original_name or '—'
    file_preview.short_description = 'Preview'


# ──────────────────────────────────────────────────────────────────────────────
#  1. CONVERSATION
# ──────────────────────────────────────────────────────────────────────────────

@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display    = (
        'short_id', 'participant_names', 'product_link',
        'message_count', 'last_message_at', 'created_at',
    )
    search_fields   = ('participants__username', 'product__title')
    raw_id_fields   = ('product', 'order')
    readonly_fields = ('id', 'created_at', 'last_message_at')
    ordering        = ('-last_message_at', '-created_at')
    date_hierarchy  = 'created_at'
    inlines         = [MessageInline]

    @admin.display(description='ID')
    def short_id(self, obj):
        return str(obj.pk)[:8].upper()

    @admin.display(description='Participants')
    def participant_names(self, obj):
        return ', '.join(u.username for u in obj.participants.all())

    @admin.display(description='Product')
    def product_link(self, obj):
        if obj.product:
            return format_html(
                '<a href="/admin/marketplace/product/{}/change/">{}</a>',
                obj.product.pk, obj.product.title[:50],
            )
        return '—'

    @admin.display(description='Messages')
    def message_count(self, obj):
        return obj.messages.count()


# ──────────────────────────────────────────────────────────────────────────────
#  2. MESSAGE
# ──────────────────────────────────────────────────────────────────────────────

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display    = (
        'short_id', 'conversation', 'sender',
        'body_col', 'message_type', 'is_edited', 'is_deleted', 'created_at',
    )
    list_filter     = ('message_type', 'is_edited', 'is_deleted')
    search_fields   = ('sender__username', 'body', 'conversation__id')
    raw_id_fields   = ('conversation', 'sender')
    readonly_fields = ('id', 'created_at', 'updated_at', 'edited_at', 'deleted_at')
    ordering        = ('-created_at',)
    date_hierarchy  = 'created_at'
    inlines         = [MessageAttachmentInline]

    fieldsets = (
        ('Message', {
            'fields': ('id', 'conversation', 'sender', 'body', 'message_type'),
        }),
        ('State', {
            'fields': (
                'is_edited', 'edited_at',
                'is_deleted', 'deleted_at',
            ),
        }),
        ('Timestamps', {
            'classes': ('collapse',),
            'fields': ('created_at', 'updated_at'),
        }),
    )

    @admin.display(description='ID')
    def short_id(self, obj):
        return str(obj.pk)[:8].upper()

    @admin.display(description='Body')
    def body_col(self, obj):
        if obj.is_deleted:
            return format_html('<em style="color:#c00">[deleted]</em>')
        text = (obj.body[:70] + '…') if len(obj.body) > 70 else obj.body
        return text or format_html('<em style="color:#999">[image only]</em>')


# ──────────────────────────────────────────────────────────────────────────────
#  3. MESSAGE ATTACHMENT
# ──────────────────────────────────────────────────────────────────────────────

@admin.register(MessageAttachment)
class MessageAttachmentAdmin(admin.ModelAdmin):
    list_display    = (
        'short_id', 'message', 'uploaded_by',
        'file_preview', 'file_type', 'original_name',
        'file_size_kb', 'is_orphan', 'created_at',
    )
    list_filter     = ('file_type',)
    search_fields   = ('original_name', 'uploaded_by__username')
    raw_id_fields   = ('message', 'uploaded_by')
    readonly_fields = ('id', 'created_at', 'file_preview')
    ordering        = ('-created_at',)
    date_hierarchy  = 'created_at'

    @admin.display(description='ID')
    def short_id(self, obj):
        return str(obj.pk)[:8].upper()

    @admin.display(description='Preview')
    def file_preview(self, obj):
        if obj.file and obj.file_type == MessageAttachment.FileType.IMAGE:
            return format_html(
                '<img src="{}" style="height:60px; border-radius:4px;" />',
                obj.file.url,
            )
        return obj.original_name or '—'

    @admin.display(description='Size')
    def file_size_kb(self, obj):
        if obj.file_size:
            return f'{obj.file_size / 1024:.1f} KB'
        return '—'

    @admin.display(description='Orphan?', boolean=True)
    def is_orphan(self, obj):
        return obj.message_id is None


# ──────────────────────────────────────────────────────────────────────────────
#  4. MESSAGE READ RECEIPT (lightweight — no inline, just searchable)
# ──────────────────────────────────────────────────────────────────────────────

@admin.register(MessageReadReceipt)
class MessageReadReceiptAdmin(admin.ModelAdmin):
    list_display    = ('message', 'user', 'read_at')
    search_fields   = ('user__username',)
    raw_id_fields   = ('message', 'user')
    readonly_fields = ('id', 'read_at')
    ordering        = ('-read_at',)
    date_hierarchy  = 'read_at'


# ──────────────────────────────────────────────────────────────────────────────
#  5. USER ONLINE STATUS
# ──────────────────────────────────────────────────────────────────────────────

@admin.register(UserOnlineStatus)
class UserOnlineStatusAdmin(admin.ModelAdmin):
    list_display  = ('user', 'status_badge', 'last_seen')
    list_filter   = ('is_online',)
    search_fields = ('user__username',)
    raw_id_fields = ('user',)
    readonly_fields = ('last_seen',)
    ordering      = ('-last_seen',)

    @admin.display(description='Status')
    def status_badge(self, obj):
        if obj.is_online:
            return format_html(
                '<span style="color:#22c55e; font-weight:600;">● Online</span>'
            )
        return format_html('<span style="color:#9ca3af;">○ Offline</span>')