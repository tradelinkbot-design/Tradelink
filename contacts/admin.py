from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from .models import ContactInquiry


@admin.register(ContactInquiry)
class ContactInquiryAdmin(admin.ModelAdmin):
    list_display = (
        "reference_id",
        "name",
        "email",
        "category_badge",
        "subject",
        "status_badge",
        "created_at",
    )
    list_filter = ("status", "category", "created_at")
    search_fields = ("name", "email", "phone", "subject", "message", "admin_notes")
    readonly_fields = ("created_at", "updated_at", "ip_address")
    list_per_page = 25
    actions = ["mark_in_progress", "mark_resolved", "mark_closed"]

    fieldsets = (
        ("Inquiry Details", {
            "fields": (
                "user",
                "name",
                "email",
                "phone",
                "category",
                "subject",
                "message",
                "ip_address",
            )
        }),
        ("Support Management", {
            "fields": (
                "status",
                "admin_notes",
                "replied_at",
                "created_at",
                "updated_at",
            )
        }),
    )

    def reference_id(self, obj):
        return f"#TL-{obj.id:05d}"
    reference_id.short_description = "Ref ID"

    def category_badge(self, obj):
        colors = {
            "general": "#F59E0B",
            "verification": "#3B82F6",
            "hiring": "#10B981",
            "billing": "#EC4899",
            "dispute": "#EF4444",
            "partnership": "#8B5CF6",
            "technical": "#6B7280",
        }
        color = colors.get(obj.category, "#F59E0B")
        return format_html(
            '<span style="background:{}; color:#fff; padding:3px 8px; border-radius:12px; font-size:11px; font-weight:600;">{}</span>',
            color,
            obj.get_category_display(),
        )
    category_badge.short_description = "Topic"

    def status_badge(self, obj):
        styles = {
            "new": "background:#EF4444; color:#fff;",
            "in_progress": "background:#F59E0B; color:#000;",
            "resolved": "background:#10B981; color:#fff;",
            "closed": "background:#6B7280; color:#fff;",
        }
        style = styles.get(obj.status, "background:#6B7280; color:#fff;")
        return format_html(
            '<span style="{}; padding:3px 8px; border-radius:12px; font-size:11px; font-weight:600;">{}</span>',
            style,
            obj.get_status_display(),
        )
    status_badge.short_description = "Status"

    @admin.action(description="Mark selected inquiries as In Progress")
    def mark_in_progress(self, request, queryset):
        queryset.update(status="in_progress")

    @admin.action(description="Mark selected inquiries as Resolved")
    def mark_resolved(self, request, queryset):
        queryset.update(status="resolved", replied_at=timezone.now())

    @admin.action(description="Mark selected inquiries as Closed")
    def mark_closed(self, request, queryset):
        queryset.update(status="closed")
