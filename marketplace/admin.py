"""
marketplace/admin.py
====================
Django admin configuration for the TradeLink NG marketplace.

Covers all eight models:
    MarketplaceCategory · Product · ProductImage · Offer
    Order · OrderDispute · ProductReview · SavedProduct
"""

from django.contrib import admin
from django.utils.html import format_html
from django.utils.timezone import now

from .models import (
    MarketplaceCategory,
    Offer,
    Order,
    OrderDispute,
    OrderDisputeMessage,
    Product,
    ProductImage,
    ProductReview,
    SavedProduct,
)


# ──────────────────────────────────────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────────────────────────────────────

def naira(value):
    """Format a Decimal as a readable ₦ amount."""
    if value is None:
        return '—'
    return f'₦{value:,.2f}'


# ──────────────────────────────────────────────────────────────────────────────
#  1.  MARKETPLACE CATEGORY
# ──────────────────────────────────────────────────────────────────────────────

@admin.register(MarketplaceCategory)
class MarketplaceCategoryAdmin(admin.ModelAdmin):
    list_display  = ('name', 'slug', 'display_order', 'is_active', 'created')
    list_editable = ('display_order', 'is_active')
    list_filter   = ('is_active',)
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('id', 'created')
    ordering = ('display_order', 'name')


# ──────────────────────────────────────────────────────────────────────────────
#  2.  PRODUCT
# ──────────────────────────────────────────────────────────────────────────────

class ProductImageInline(admin.TabularInline):
    model         = ProductImage
    extra         = 0
    fields        = ('image', 'caption', 'display_order', 'image_preview')
    readonly_fields = ('image_preview', 'created')
    ordering      = ('display_order',)

    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="height:60px; border-radius:4px;" />',
                obj.image.url,
            )
        return '—'
    image_preview.short_description = 'Preview'


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display  = (
        'title', 'seller_link', 'category', 'condition',
        'price_display', 'status', 'state', 'views_count',
        'has_embedding', 'created',
    )
    list_filter   = ('status', 'condition', 'category', 'state', 'offers_allowed', 'pickup_only')
    search_fields = ('title', 'description', 'brand', 'model_number', 'seller__user__username')
    raw_id_fields = ('seller', 'category', 'trade')
    readonly_fields = (
        'id', 'views_count', 'text_embedding', 'text_embedding_updated',
        'created', 'updated', 'seller_amount_display',
    )
    inlines    = [ProductImageInline]
    ordering   = ('-created',)
    date_hierarchy = 'created'

    fieldsets = (
        ('Listing', {
            'fields': ('id', 'seller', 'category', 'trade', 'status'),
        }),
        ('Content', {
            'fields': ('title', 'description', 'condition', 'brand', 'model_number'),
        }),
        ('Pricing', {
            'fields': (
                'price', 'min_offer', 'offers_allowed',
                'platform_fee_pct', 'seller_amount_display',
            ),
        }),
        ('Location & Pickup', {
            'fields': ('state', 'lga', 'pickup_only', 'pickup_notes'),
        }),
        ('Inventory', {
            'fields': ('slots', 'views_count'),
        }),
        ('Semantic Search', {
            'classes': ('collapse',),
            'fields': ('text_embedding', 'text_embedding_updated'),
        }),
        ('Timestamps', {
            'classes': ('collapse',),
            'fields': ('created', 'updated'),
        }),
    )

    # ── Custom columns ────────────────────────────────────────────────────────

    @admin.display(description='Seller', ordering='seller__user__username')
    def seller_link(self, obj):
        return format_html(
            '<a href="/admin/jobs/workerprofile/{}/change/">{}</a>',
            obj.seller.pk,
            obj.seller,
        )

    @admin.display(description='Price', ordering='price')
    def price_display(self, obj):
        return naira(obj.price)

    @admin.display(description='Embedding?', boolean=True)
    def has_embedding(self, obj):
        return obj.text_embedding is not None

    @admin.display(description='Seller receives')
    def seller_amount_display(self, obj):
        return naira(obj.seller_amount)


# ──────────────────────────────────────────────────────────────────────────────
#  3.  OFFER
# ──────────────────────────────────────────────────────────────────────────────

@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):
    list_display  = (
        'product', 'buyer', 'offered_price_display',
        'counter_price_display', 'status', 'expires_at', 'created_at',
    )
    list_filter   = ('status',)
    search_fields = ('product__title', 'buyer__username')
    raw_id_fields = ('product', 'buyer')
    readonly_fields = ('id', 'created_at', 'updated_at')
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'

    @admin.display(description='Offered', ordering='offered_price')
    def offered_price_display(self, obj):
        return naira(obj.offered_price)

    @admin.display(description='Counter', ordering='counter_price')
    def counter_price_display(self, obj):
        return naira(obj.counter_price)


# ──────────────────────────────────────────────────────────────────────────────
#  4.  ORDER
# ──────────────────────────────────────────────────────────────────────────────

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display  = (
        'short_id', 'product', 'buyer', 'seller',
        'agreed_price_display', 'platform_fee_display', 'seller_payout_display',
        'status', 'paid_at', 'completed_at', 'created_at',
    )
    list_filter   = ('status',)
    search_fields = (
        'product__title',
        'buyer__username',
        'seller__user__username',
        'paystack_payment_ref',
        'paystack_transfer_ref',
    )
    raw_id_fields = ('product', 'buyer', 'seller', 'offer')
    readonly_fields = (
        'id', 'platform_fee_amount', 'seller_payout_amount',
        'paid_at', 'confirmed_at', 'completed_at',
        'created_at', 'updated_at',
    )
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Order', {
            'fields': ('id', 'product', 'buyer', 'seller', 'offer', 'status'),
        }),
        ('Financials', {
            'fields': (
                'agreed_price', 'platform_fee_pct',
                'platform_fee_amount', 'seller_payout_amount',
            ),
        }),
        ('Paystack', {
            'fields': ('paystack_payment_ref', 'paystack_transfer_ref'),
        }),
        ('Meetup', {
            'fields': ('meetup_notes', 'auto_complete_at'),
        }),
        ('Timestamps', {
            'classes': ('collapse',),
            'fields': ('paid_at', 'confirmed_at', 'completed_at', 'created_at', 'updated_at'),
        }),
    )

    actions = ['mark_completed', 'mark_cancelled']

    @admin.display(description='Order ID')
    def short_id(self, obj):
        return str(obj.pk)[:8].upper()

    @admin.display(description='Agreed', ordering='agreed_price')
    def agreed_price_display(self, obj):
        return naira(obj.agreed_price)

    @admin.display(description='Fee', ordering='platform_fee_amount')
    def platform_fee_display(self, obj):
        return naira(obj.platform_fee_amount)

    @admin.display(description='Payout', ordering='seller_payout_amount')
    def seller_payout_display(self, obj):
        return naira(obj.seller_payout_amount)

    @admin.action(description='Mark selected orders as Completed')
    def mark_completed(self, request, queryset):
        updated = queryset.filter(
            status=Order.Status.CONFIRMED
        ).update(status=Order.Status.COMPLETED, completed_at=now())
        self.message_user(request, f'{updated} order(s) marked as completed.')

    @admin.action(description='Mark selected orders as Cancelled')
    def mark_cancelled(self, request, queryset):
        updated = queryset.exclude(
            status__in=[Order.Status.COMPLETED, Order.Status.REFUNDED]
        ).update(status=Order.Status.CANCELLED)
        self.message_user(request, f'{updated} order(s) cancelled.')


# ──────────────────────────────────────────────────────────────────────────────
#  5.  ORDER DISPUTE
# ──────────────────────────────────────────────────────────────────────────────

class OrderDisputeMessageInline(admin.TabularInline):
    model = OrderDisputeMessage
    extra = 0
    readonly_fields = ('author', 'body', 'attachment', 'attachment_sha256', 'is_admin_note', 'created_at')
    can_delete = False


@admin.register(OrderDispute)
class OrderDisputeAdmin(admin.ModelAdmin):
    list_display  = (
        'order', 'raised_by', 'resolution', 'split_seller_pct', 'escalated',
        'mediation_deadline', 'resolved_by', 'resolved_at', 'created_at',
    )
    list_filter   = ('resolution', 'escalated')
    search_fields = (
        'order__paystack_payment_ref',
        'raised_by__username',
        'reason',
        'evidence_sha256',
    )
    raw_id_fields = ('order', 'raised_by', 'resolved_by')
    readonly_fields = (
        'id', 'created_at', 'resolved_at', 'evidence_sha256',
        'mediation_deadline', 'mediation_buyer_agreed', 'mediation_seller_agreed',
        'auto_release_at', 'escalated',
    )
    inlines = [OrderDisputeMessageInline]
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Dispute', {
            'fields': ('id', 'order', 'raised_by', 'reason', 'evidence', 'evidence_sha256'),
        }),
        ('Mediation & SLA', {
            'fields': (
                'mediation_deadline', 'mediation_buyer_agreed', 'mediation_seller_agreed',
                'auto_release_at', 'escalated',
            ),
        }),
        ('Resolution', {
            'fields': ('resolution', 'split_seller_pct', 'resolution_note', 'resolved_by', 'resolved_at'),
        }),
        ('Timestamps', {
            'classes': ('collapse',),
            'fields': ('created_at',),
        }),
    )

    actions = ['resolve_release_to_seller', 'resolve_refund_to_buyer']

    @admin.action(description='Resolve: Release funds to Seller')
    def resolve_release_to_seller(self, request, queryset):
        updated = queryset.filter(resolution=OrderDispute.Resolution.PENDING).update(
            resolution=OrderDispute.Resolution.RELEASED_TO_SELLER,
            resolved_by=request.user,
            resolved_at=now(),
        )
        self.message_user(request, f'{updated} dispute(s) resolved — funds released to seller.')

    @admin.action(description='Resolve: Refund Buyer')
    def resolve_refund_to_buyer(self, request, queryset):
        updated = queryset.filter(resolution=OrderDispute.Resolution.PENDING).update(
            resolution=OrderDispute.Resolution.REFUNDED_TO_BUYER,
            resolved_by=request.user,
            resolved_at=now(),
        )
        self.message_user(request, f'{updated} dispute(s) resolved — buyer refunded.')


# ──────────────────────────────────────────────────────────────────────────────
#  6.  PRODUCT REVIEW
# ──────────────────────────────────────────────────────────────────────────────

@admin.register(ProductReview)
class ProductReviewAdmin(admin.ModelAdmin):
    list_display  = ('product', 'reviewer', 'seller', 'stars', 'comment_excerpt', 'created_at')
    list_filter   = ('rating',)
    search_fields = ('product__title', 'reviewer__username', 'seller__user__username', 'comment')
    raw_id_fields = ('order', 'reviewer', 'seller', 'product')
    readonly_fields = ('id', 'created_at')
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'

    @admin.display(description='Rating', ordering='rating')
    def stars(self, obj):
        return '★' * obj.rating + '☆' * (5 - obj.rating)

    @admin.display(description='Comment')
    def comment_excerpt(self, obj):
        return obj.comment[:80] + '…' if len(obj.comment) > 80 else obj.comment


# ──────────────────────────────────────────────────────────────────────────────
#  7.  SAVED PRODUCT
# ──────────────────────────────────────────────────────────────────────────────

@admin.register(SavedProduct)
class SavedProductAdmin(admin.ModelAdmin):
    list_display  = ('user', 'product', 'created_at')
    search_fields = ('user__username', 'product__title')
    raw_id_fields = ('user', 'product')
    readonly_fields = ('id', 'created_at')
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'