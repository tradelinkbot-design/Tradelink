"""
marketplace/urls.py
====================
URL configuration for the TradeLink NG Tool & Equipment Marketplace.

Include in your project's root urls.py:

    urlpatterns = [
        ...
        path('marketplace/', include('marketplace.urls', namespace='mktplace')),
    ]

All view names follow the pattern: mktplace:<name>
e.g.  {% url 'mktplace:product_list' %}
      {% url 'mktplace:product_detail' pk=product.pk %}
      reverse('mktplace:order_detail', kwargs={'pk': order.pk})
"""

from django.urls import path

from .views import (
    # Public
    ProductListView,
    ProductDetailView,
    CategoryListView,
    CategoryDetailView,
    SellerPublicProfileView,

    # Seller dashboard & listings
    SellerDashboardView,
    ProductCreateView,
    ProductUpdateView,
    ProductDeleteView,
    ProductImageUploadView,
    ProductImageDeleteView,

    # Offer management (seller-side)
    RespondToOfferView,
    SellerOrderListView,

    # Buyer actions
    MakeOfferView,
    WithdrawOfferView,
    AcceptCounterOfferView,
    BuyNowView,
    ToggleSaveProductView,

    # Orders
    OrderDetailView,
    OrderListView,
    ConfirmReceiptView,

    # Dispute & review
    RaiseDisputeView,
    PostOrderDisputeMessageView,
    OrderMediationAgreeView,
    SubmitReviewView,

    # Payment callback
    PaystackCallbackView,

    # Admin
    DisputeAdminResolveView,
)

app_name = 'mktplace'

urlpatterns = [

    # ── Browse / Search ─────────────────────────────────────────────────────
    path(
        '',
        ProductListView.as_view(),
        name='product_list',
    ),
    path(
        'products/<uuid:pk>/',
        ProductDetailView.as_view(),
        name='product_detail',
    ),

    # ── Categories ───────────────────────────────────────────────────────────
    path(
        'categories/',
        CategoryListView.as_view(),
        name='category_list',
    ),
    path(
        'categories/<slug:slug>/',
        CategoryDetailView.as_view(),
        name='category_detail',
    ),

    # ── Seller Public Profile ─────────────────────────────────────────────────
    path(
        'sellers/<uuid:pk>/',
        SellerPublicProfileView.as_view(),
        name='seller_public',
    ),

    # ── Seller Dashboard ──────────────────────────────────────────────────────
    path(
        'dashboard/',
        SellerDashboardView.as_view(),
        name='seller_dashboard',
    ),

    # ── Seller — Listing CRUD ─────────────────────────────────────────────────
    path(
        'products/create/',
        ProductCreateView.as_view(),
        name='product_create',
    ),
    path(
        'products/<uuid:pk>/edit/',
        ProductUpdateView.as_view(),
        name='product_edit',
    ),
    path(
        'products/<uuid:pk>/delete/',
        ProductDeleteView.as_view(),
        name='product_delete',
    ),

    # ── Seller — Image Management ─────────────────────────────────────────────
    path(
        'products/<uuid:pk>/images/add/',
        ProductImageUploadView.as_view(),
        name='product_image_add',
    ),
    path(
        'images/<uuid:pk>/delete/',
        ProductImageDeleteView.as_view(),
        name='product_image_delete',
    ),

    # ── Seller — Offer Responses ──────────────────────────────────────────────
    path(
        'offers/<uuid:pk>/respond/',
        RespondToOfferView.as_view(),
        name='offer_respond',
    ),

    # ── Seller — Orders ───────────────────────────────────────────────────────
    path(
        'seller/orders/',
        SellerOrderListView.as_view(),
        name='seller_order_list',
    ),

    # ── Buyer — Offers ────────────────────────────────────────────────────────
    path(
        'products/<uuid:pk>/offer/',
        MakeOfferView.as_view(),
        name='make_offer',
    ),
    path(
        'offers/<uuid:pk>/withdraw/',
        WithdrawOfferView.as_view(),
        name='offer_withdraw',
    ),
    path(
        'offers/<uuid:pk>/accept-counter/',
        AcceptCounterOfferView.as_view(),
        name='offer_accept_counter',
    ),

    # ── Buyer — Buy Now ───────────────────────────────────────────────────────
    path(
        'products/<uuid:pk>/buy/',
        BuyNowView.as_view(),
        name='buy_now',
    ),

    # ── Buyer — Save / Bookmark ───────────────────────────────────────────────
    path(
        'products/<uuid:pk>/save/',
        ToggleSaveProductView.as_view(),
        name='product_save_toggle',
    ),

    # ── Orders ────────────────────────────────────────────────────────────────
    path(
        'orders/',
        OrderListView.as_view(),
        name='order_list',
    ),
    path(
        'orders/<uuid:pk>/',
        OrderDetailView.as_view(),
        name='order_detail',
    ),
    path(
        'orders/<uuid:pk>/confirm/',
        ConfirmReceiptView.as_view(),
        name='order_confirm',
    ),

    # ── Disputes ──────────────────────────────────────────────────────────────
    path(
        'orders/<uuid:pk>/dispute/',
        RaiseDisputeView.as_view(),
        name='order_dispute',
    ),
    path(
        'disputes/<uuid:pk>/messages/',
        PostOrderDisputeMessageView.as_view(),
        name='dispute_messages',
    ),
    path(
        'disputes/<uuid:pk>/mediate/',
        OrderMediationAgreeView.as_view(),
        name='dispute_mediate',
    ),
    path(
        'disputes/<uuid:pk>/resolve/',
        DisputeAdminResolveView.as_view(),
        name='dispute_resolve',
    ),

    # ── Reviews ───────────────────────────────────────────────────────────────
    path(
        'orders/<uuid:pk>/review/',
        SubmitReviewView.as_view(),
        name='order_review',
    ),

    # ── Paystack Callback ─────────────────────────────────────────────────────
    path(
        'paystack/callback/',
        PaystackCallbackView.as_view(),
        name='paystack_callback',
    ),
]