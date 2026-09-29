"""
marketplace/views.py
=====================
TradeLink NG — Tool & Equipment Marketplace views.

URL namespace: 'mktplace'  (add to root urls.py as namespace='mktplace')

View map
────────
  Public
    ProductListView              GET  /marketplace/
    ProductDetailView            GET  /marketplace/products/<uuid:pk>/
    CategoryListView             GET  /marketplace/categories/
    CategoryDetailView           GET  /marketplace/categories/<slug:slug>/
    SellerPublicProfileView      GET  /marketplace/sellers/<uuid:pk>/

  Auth — any logged-in user (buyer actions)
    MakeOfferView                POST /marketplace/products/<uuid:pk>/offer/
    WithdrawOfferView            POST /marketplace/offers/<uuid:pk>/withdraw/
    AcceptCounterOfferView       POST /marketplace/offers/<uuid:pk>/accept-counter/
    BuyNowView                   POST /marketplace/products/<uuid:pk>/buy/
    OrderDetailView              GET  /marketplace/orders/<uuid:pk>/
    OrderListView                GET  /marketplace/orders/
    ConfirmReceiptView           POST /marketplace/orders/<uuid:pk>/confirm/
    RaiseDisputeView             POST /marketplace/orders/<uuid:pk>/dispute/
    SubmitReviewView             POST /marketplace/orders/<uuid:pk>/review/
    ToggleSaveProductView        POST /marketplace/products/<uuid:pk>/save/
    PaystackCallbackView         GET  /marketplace/paystack/callback/

  Auth — WorkerProfile required (seller actions)
    SellerDashboardView          GET  /marketplace/dashboard/
    ProductCreateView            GET/POST /marketplace/products/create/
    ProductUpdateView            GET/POST /marketplace/products/<uuid:pk>/edit/
    ProductDeleteView            POST /marketplace/products/<uuid:pk>/delete/
    ProductImageUploadView       POST /marketplace/products/<uuid:pk>/images/add/
    ProductImageDeleteView       POST /marketplace/images/<uuid:pk>/delete/
    RespondToOfferView           POST /marketplace/offers/<uuid:pk>/respond/
    SellerOrderListView          GET  /marketplace/seller/orders/

  Admin
    DisputeAdminResolveView      POST /marketplace/disputes/<uuid:pk>/resolve/

Design notes
────────────
  • Sellers must be WorkerProfile users — enforced by SellerRequiredMixin.
  • Buyers can be any authenticated user (employers, workers, staff).
  • All Paystack calls are delegated to marketplace_escrow_service — views
    only redirect and set messages.
  • Semantic search (sentence-transformer) is attempted first; on failure
    the view falls back to icontains keyword search transparently.
  • views_count is incremented on ProductDetailView using F() to avoid
    race conditions.
"""

import hashlib
import logging
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Avg, Count, F, Q
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import ListView

from .models import (
    MarketplaceCategory,
    Product,
    ProductImage,
    Offer,
    Order,
    OrderDispute,
    OrderDisputeMessage,
    ProductReview,
    SavedProduct,
    UserProductInteraction,
    ProductRecommendation,
)
from jobs.models import WorkerProfile, Notification
from jobs.service.escrow_service import _hash_file, _validate_evidence_mime
from core.ratelimit import rate_limit

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
#  MIXINS & HELPERS
# ──────────────────────────────────────────────────────────────────────────────

class SellerRequiredMixin(LoginRequiredMixin):
    """
    Ensures the logged-in user has a WorkerProfile (seller identity).
    Only workers can list products on the marketplace.
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not hasattr(request.user, 'worker_profile'):
            messages.warning(
                request,
                'Only worker accounts can list products. '
                'Complete your worker profile first.',
            )
            return redirect('jobs:worker_profile_edit')
        return super().dispatch(request, *args, **kwargs)

    @property
    def seller_profile(self) -> WorkerProfile:
        return self.request.user.worker_profile


def _unread_count(user) -> int:
    """Unread notification count for nav badge."""
    if user.is_authenticated:
        return Notification.objects.filter(user=user, is_read=False).count()
    return 0


def _is_saved(user, product) -> bool:
    """Returns True if the user has saved this product."""
    if not user.is_authenticated:
        return False
    return SavedProduct.objects.filter(user=user, product=product).exists()


def _seller_profile_or_none(user):
    return getattr(user, 'worker_profile', None)


# ──────────────────────────────────────────────────────────────────────────────
#  PUBLIC — PRODUCT LIST  (browse / search)
# ──────────────────────────────────────────────────────────────────────────────

class ProductListView(View):
    """
    GET /marketplace/

    Supports:
      ?q=<query>          — semantic search (falls back to icontains)
      ?category=<slug>    — filter by MarketplaceCategory slug
      ?condition=<value>  — filter by Product.Condition
      ?state=<value>      — filter by Nigerian state
      ?min_price=<n>      — minimum price filter
      ?max_price=<n>      — maximum price filter
      ?sort=newest|price_asc|price_desc|popular
    """

    template_name = 'marketplace/product_list.html'
    PAGE_SIZE = 20

    def get(self, request):
        q          = request.GET.get('q', '').strip()
        cat_slug   = request.GET.get('category', '')
        condition  = request.GET.get('condition', '')
        state      = request.GET.get('state', '')
        min_price  = request.GET.get('min_price', '')
        max_price  = request.GET.get('max_price', '')
        sort       = request.GET.get('sort', 'newest')

        qs = (
            Product.objects.filter(status=Product.Status.ACTIVE)
            .select_related('category', 'seller__user', 'trade')
            .prefetch_related('images')
        )

        # ── Category filter ──────────────────────────────────────────────
        category = None
        if cat_slug:
            category = MarketplaceCategory.objects.filter(
                slug=cat_slug, is_active=True
            ).first()
            if category:
                qs = qs.filter(category=category)

        # ── Field filters ────────────────────────────────────────────────
        if condition:
            qs = qs.filter(condition=condition)
        if state:
            qs = qs.filter(state=state)
        try:
            if min_price:
                qs = qs.filter(price__gte=float(min_price))
            if max_price:
                qs = qs.filter(price__lte=float(max_price))
        except (ValueError, TypeError):
            pass

        # ── Semantic / keyword search ────────────────────────────────────
        # Encoding is offloaded to the Celery worker via RPC — PyTorch never
        # runs in the ASGI web-server process (mirrors the jobs app pattern).
        semantic_active = False
        if q:
            from marketplace.service.search_service import (
                semantic_product_search,
            )
            ranked = semantic_product_search(q, product_pks=list(qs.values_list('pk', flat=True)))

            if ranked:
                semantic_active = True
                pk_order = {str(pk): idx for idx, (pk, _) in enumerate(ranked)}
                qs = qs.filter(pk__in=[pk for pk, _ in ranked])
                # Python-sort by semantic rank (preserves queryset filtering)
                products_list = sorted(
                    list(qs),
                    key=lambda p: pk_order.get(str(p.pk), 9999),
                )
            else:
                # Fallback: keyword icontains
                qs = qs.filter(
                    Q(title__icontains=q) |
                    Q(description__icontains=q) |
                    Q(brand__icontains=q)
                )
                products_list = None  # will paginate qs directly
        else:
            products_list = None

        # ── Sort (only if not using semantic ranking) ────────────────────
        if not semantic_active:
            if sort == 'price_asc':
                qs = qs.order_by('price')
            elif sort == 'price_desc':
                qs = qs.order_by('-price')
            elif sort == 'popular':
                qs = qs.order_by('-views_count')
            else:
                qs = qs.order_by('-created')

        # ── Pagination ───────────────────────────────────────────────────
        page_obj = None
        if products_list is not None:
            # Semantic results — paginate the list
            paginator    = Paginator(products_list, self.PAGE_SIZE)
            page_obj     = paginator.get_page(request.GET.get('page'))
            products      = page_obj.object_list
        else:
            paginator    = Paginator(qs, self.PAGE_SIZE)
            page_obj     = paginator.get_page(request.GET.get('page'))
            products      = page_obj.object_list

        categories = MarketplaceCategory.objects.filter(is_active=True)

        # ── AI: Personalised feed (Engine 2) — only for authenticated users ──
        personalised_products = []
        if request.user.is_authenticated and not q:
            # Read pre-computed personal recs (zero extra ML work at page load)
            personalised_products = list(
                ProductRecommendation.objects
                .filter(user=request.user, rec_type='personal')
                .select_related('recommended__seller__user', 'recommended__category')
                .prefetch_related('recommended__images')
                .order_by('-score')[:12]
            )

        # ── AI: Trending products (Engine 3) — top 8 by trending_score ──────
        from marketplace.service.recommendation_service import get_trending_products
        trending_products = get_trending_products(
            category_id=(category.pk if category else None),
            limit=8,
        )

        return render(request, self.template_name, {
            'products':             products,
            'page_obj':             page_obj,
            'categories':           categories,
            'category':             category,
            'q':                    q,
            'condition':            condition,
            'state':                state,
            'min_price':            min_price,
            'max_price':            max_price,
            'sort':                 sort,
            'semantic_active':      semantic_active,
            'conditions':           Product.Condition.choices,
            'unread_count':         _unread_count(request.user),
            # AI recommendation context
            'personalised_products': personalised_products,
            'trending_products':     trending_products,
        })


# ──────────────────────────────────────────────────────────────────────────────
#  PUBLIC — PRODUCT DETAIL
# ──────────────────────────────────────────────────────────────────────────────

class ProductDetailView(View):
    """
    GET /marketplace/products/<uuid:pk>/

    Shows the listing, images, seller info, existing offers (seller only),
    and reviews. Increments views_count atomically.
    """

    template_name = 'marketplace/product_detail.html'

    def get(self, request, pk):
        product = get_object_or_404(
            Product.objects.select_related(
                'seller__user', 'category', 'trade'
            ).prefetch_related('images', 'reviews__reviewer'),
            pk=pk,
            status__in=[
                Product.Status.ACTIVE,
                Product.Status.RESERVED,
                Product.Status.SOLD,
            ],
        )

        # Atomic view count increment (only for ACTIVE listings)
        if product.status == Product.Status.ACTIVE:
            Product.objects.filter(pk=pk).update(views_count=F('views_count') + 1)

        # Seller can see pending offers on their own listing
        pending_offers = []
        is_seller = (
            request.user.is_authenticated
            and _seller_profile_or_none(request.user) == product.seller
        )
        if is_seller:
            pending_offers = (
                Offer.objects.filter(
                    product=product,
                    status=Offer.Status.PENDING,
                )
                .select_related('buyer')
                .order_by('-created_at')
            )

        # Buyer's own pending offer, if any
        buyer_offer = None
        if request.user.is_authenticated and not is_seller:
            buyer_offer = (
                Offer.objects.filter(
                    product=product,
                    buyer=request.user,
                    status__in=[Offer.Status.PENDING, Offer.Status.COUNTERED],
                )
                .order_by('-created_at')
                .first()
            )

        # Active order for this buyer+product (for "already ordered" state)
        active_order = None
        if request.user.is_authenticated and not is_seller:
            active_order = Order.objects.filter(
                product=product,
                buyer=request.user,
                status__in=[
                    Order.Status.PENDING,
                    Order.Status.PAID,
                    Order.Status.MEETUP_SCHEDULED,
                    Order.Status.CONFIRMED,
                ],
            ).first()

        avg_rating = (
            ProductReview.objects.filter(seller=product.seller)
            .aggregate(avg=Avg('rating'))['avg']
        )

        # ── AI Recommendations ───────────────────────────────────────────
        # Engine 1: similar products (cosine similarity, pre-computed)
        similar_products = list(
            ProductRecommendation.objects
            .filter(source_product=product, rec_type='similar')
            .select_related('recommended__seller__user', 'recommended__category')
            .prefetch_related('recommended__images')
            .order_by('-score')[:8]
        )

        # Engine 5: cross-sell recommendations
        cross_sell_products = list(
            ProductRecommendation.objects
            .filter(source_product=product, rec_type='cross_sell')
            .select_related('recommended__seller__user')
            .prefetch_related('recommended__images')
            .order_by('-score')[:6]
        )

        # Engine 4: price intelligence label
        from marketplace.service.recommendation_service import get_price_label
        price_label = get_price_label(product)

        # Log view interaction for authenticated buyers (Engine 2 signal)
        if request.user.is_authenticated and not is_seller:
            UserProductInteraction.objects.create(
                user=request.user,
                product=product,
                event_type=UserProductInteraction.EventType.VIEW,
            )
            # Periodically refresh personal feed on view (every 5th view only,
            # to avoid overloading Celery — check via modular arithmetic on pk)
            if int(product.views_count) % 5 == 0:
                from marketplace.tasks import compute_personalised_feed_task
                compute_personalised_feed_task.delay(request.user.pk)

        return render(request, self.template_name, {
            'product':           product,
            'is_seller':         is_seller,
            'pending_offers':    pending_offers,
            'buyer_offer':       buyer_offer,
            'active_order':      active_order,
            'is_saved':          _is_saved(request.user, product),
            'avg_rating':        round(avg_rating, 1) if avg_rating else None,
            'reviews':           product.reviews.all()[:10],
            'unread_count':      _unread_count(request.user),
            # AI recommendation context
            'similar_products':   similar_products,
            'cross_sell_products': cross_sell_products,
            'price_label':        price_label,
        })


# ──────────────────────────────────────────────────────────────────────────────
#  PUBLIC — CATEGORIES
# ──────────────────────────────────────────────────────────────────────────────

class CategoryListView(View):
    """GET /marketplace/categories/"""

    template_name = 'marketplace/category_list.html'
    PAGE_SIZE = 12

    def get(self, request):
        q = request.GET.get('q', '').strip()
        qs = (
            MarketplaceCategory.objects.filter(is_active=True)
            .annotate(product_count=Count(
                'products', filter=Q(products__status=Product.Status.ACTIVE)
            ))
            .order_by('display_order', 'name')
        )
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q))

        paginator = Paginator(qs, self.PAGE_SIZE)
        page_obj = paginator.get_page(request.GET.get('page'))

        return render(request, self.template_name, {
            'categories':   page_obj.object_list,
            'page_obj':     page_obj,
            'q':            q,
            'total_count':  paginator.count,
            'unread_count': _unread_count(request.user),
        })


class CategoryDetailView(View):
    """GET /marketplace/categories/<slug:slug>/"""

    template_name = 'marketplace/category_detail.html'
    PAGE_SIZE = 20

    def get(self, request, slug):
        category = get_object_or_404(MarketplaceCategory, slug=slug, is_active=True)
        qs = (
            Product.objects.filter(
                category=category,
                status=Product.Status.ACTIVE,
            )
            .select_related('seller__user')
            .prefetch_related('images')
            .order_by('-created')
        )

        paginator = Paginator(qs, self.PAGE_SIZE)
        page_obj  = paginator.get_page(request.GET.get('page'))

        return render(request, self.template_name, {
            'category':     category,
            'page_obj':     page_obj,
            'products':     page_obj.object_list,
            'unread_count': _unread_count(request.user),
        })


# ──────────────────────────────────────────────────────────────────────────────
#  PUBLIC — SELLER PROFILE
# ──────────────────────────────────────────────────────────────────────────────

class SellerPublicProfileView(View):
    """GET /marketplace/sellers/<uuid:pk>/"""

    template_name = 'marketplace/seller_profile.html'

    def get(self, request, pk):
        seller = get_object_or_404(
            WorkerProfile.objects.select_related('user', 'trade_category'),
            pk=pk,
        )
        listings = (
            Product.objects.filter(
                seller=seller,
                status=Product.Status.ACTIVE,
            )
            .prefetch_related('images')
            .order_by('-created')[:12]
        )
        reviews = (
            ProductReview.objects.filter(seller=seller)
            .select_related('reviewer', 'product')
            .order_by('-created_at')[:10]
        )
        avg_rating = (
            ProductReview.objects.filter(seller=seller)
            .aggregate(avg=Avg('rating'))['avg']
        )
        return render(request, self.template_name, {
            'seller':       seller,
            'listings':     listings,
            'reviews':      reviews,
            'avg_rating':   round(avg_rating, 1) if avg_rating else None,
            'unread_count': _unread_count(request.user),
        })


# ──────────────────────────────────────────────────────────────────────────────
#  SELLER — DASHBOARD
# ──────────────────────────────────────────────────────────────────────────────

class SellerDashboardView(SellerRequiredMixin, View):
    """
    GET /marketplace/dashboard/

    Context
    ────────
      listings         — seller's own products, all statuses
      pending_offers   — offers waiting for a response (across all listings)
      active_orders    — orders currently in progress (PAID / MEETUP_SCHEDULED)
      recent_sales     — completed orders, last 5
      pending_orders   — orders in PENDING_PAYMENT state (buyer hasn't paid yet)
      avg_rating       — seller's average marketplace rating
      total_earned     — sum of seller_payout_amount on COMPLETED orders
    """

    template_name = 'marketplace/seller_dashboard.html'

    def get(self, request):
        seller = self.seller_profile

        listings = (
            Product.objects.filter(seller=seller)
            .prefetch_related('images')
            .annotate(offer_count=Count('offers', filter=Q(offers__status=Offer.Status.PENDING)))
            .order_by('-created')
        )

        pending_offers = (
            Offer.objects.filter(
                product__seller=seller,
                status=Offer.Status.PENDING,
            )
            .select_related('product', 'buyer')
            .order_by('-created_at')[:10]
        )

        active_orders = (
            Order.objects.filter(
                seller=seller,
                status__in=[Order.Status.PAID, Order.Status.MEETUP_SCHEDULED],
            )
            .select_related('product', 'buyer')
            .order_by('-paid_at')
        )

        pending_orders = (
            Order.objects.filter(
                seller=seller,
                status=Order.Status.PENDING,
            )
            .select_related('product', 'buyer')
            .order_by('-created_at')[:5]
        )

        recent_sales = (
            Order.objects.filter(
                seller=seller,
                status=Order.Status.COMPLETED,
            )
            .select_related('product', 'buyer')
            .order_by('-completed_at')[:5]
        )

        avg_rating = (
            ProductReview.objects.filter(seller=seller)
            .aggregate(avg=Avg('rating'))['avg']
        )

        total_earned = (
            Order.objects.filter(
                seller=seller,
                status=Order.Status.COMPLETED,
            )
            .aggregate(total=models_Sum('seller_payout_amount'))['total']
        ) or 0

        return render(request, self.template_name, {
            'seller':          seller,
            'listings':        listings,
            'pending_offers':  pending_offers,
            'active_orders':   active_orders,
            'pending_orders':  pending_orders,
            'recent_sales':    recent_sales,
            'avg_rating':      round(avg_rating, 1) if avg_rating else None,
            'total_earned':    total_earned,
            'unread_count':    _unread_count(request.user),
        })


# ──────────────────────────────────────────────────────────────────────────────
#  SELLER — PRODUCT CREATE / UPDATE / DELETE
# ──────────────────────────────────────────────────────────────────────────────

class ProductCreateView(SellerRequiredMixin, View):
    """
    GET/POST /marketplace/products/create/

    Handles the main product form + inline image uploads.
    Images are submitted as multiple file inputs (name="images").
    """

    template_name = 'marketplace/product_form.html'

    def get(self, request):
        categories = MarketplaceCategory.objects.filter(is_active=True)
        return render(request, self.template_name, {
            'product':           None,
            'categories':        categories,
            'conditions':        Product.Condition.choices,
            'action':            'create',
            'selected_state':    '',
            'selected_category': '',
            'form_data': {
                'title': '', 'description': '', 'condition': 'used_good',
                'brand': '', 'model_number': '', 'price': '', 'min_offer': '',
                'offers_allowed': '1', 'lga': '', 'pickup_notes': '', 'slots': '1',
            },
            'unread_count': _unread_count(request.user),
        })

    def post(self, request):
        seller     = self.seller_profile
        categories = MarketplaceCategory.objects.filter(is_active=True)

        # ── Collect and validate fields ──────────────────────────────────
        title       = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        condition   = request.POST.get('condition', '')
        brand       = request.POST.get('brand', '').strip()
        model_no    = request.POST.get('model_number', '').strip()
        state       = request.POST.get('state', '')
        lga         = request.POST.get('lga', '').strip()
        pickup_notes = request.POST.get('pickup_notes', '').strip()
        cat_id      = request.POST.get('category', '')
        publish     = request.POST.get('publish') == 'publish'
        print("This is publish", publish)
        if publish == "publish":
            print("yes")

        errors = {}
        if not title:
            errors['title'] = 'Title is required.'
        if not description:
            errors['description'] = 'Description is required.'
        if not condition or condition not in dict(Product.Condition.choices):
            errors['condition'] = 'Please select a condition.'

        try:
            price = float(request.POST.get('price', ''))
            if price <= 0:
                errors['price'] = 'Price must be greater than zero.'
        except (ValueError, TypeError):
            errors['price'] = 'Enter a valid price.'
            price = None

        min_offer = None
        if request.POST.get('min_offer'):
            try:
                min_offer = float(request.POST.get('min_offer'))
            except (ValueError, TypeError):
                errors['min_offer'] = 'Enter a valid minimum offer price.'

        try:
            slots = int(request.POST.get('slots', 1))
            if slots < 1:
                slots = 1
        except (ValueError, TypeError):
            slots = 1

        category = None
        if cat_id:
            category = MarketplaceCategory.objects.filter(pk=cat_id).first()

        if errors:
            return render(request, self.template_name, {
                'product':           None,
                'categories':        categories,
                'conditions':        Product.Condition.choices,
                'action':            'create',
                'errors':            errors,
                'selected_state':    request.POST.get('state', ''),
                'selected_category': request.POST.get('category', ''),
                'form_data':         request.POST,
                'unread_count':      _unread_count(request.user),
            })

        product = Product.objects.create(
            seller          = seller,
            category        = category,
            title           = title,
            description     = description,
            condition       = condition,
            brand           = brand,
            model_number    = model_no,
            price           = price,
            min_offer       = min_offer,
            offers_allowed  = request.POST.get('offers_allowed') == '1',
            state           = state,
            lga             = lga,
            pickup_notes    = pickup_notes,
            slots           = slots,
            status          = Product.Status.ACTIVE if publish else Product.Status.DRAFT,
        )

        # ── Handle uploaded images ───────────────────────────────────────
        images = request.FILES.getlist('images')
        for order_idx, img_file in enumerate(images[:8]):   # cap at 8
            ProductImage.objects.create(
                product       = product,
                image         = img_file,
                display_order = order_idx,
            )

        messages.success(
            request,
            f'"{product.title}" has been '
            f'{"published" if publish else "saved as draft"}.',
        )
        return redirect('mktplace:product_detail', pk=product.pk)


class ProductUpdateView(SellerRequiredMixin, View):
    """GET/POST /marketplace/products/<uuid:pk>/edit/"""

    template_name = 'marketplace/product_form.html'

    def _get_product(self, pk, seller):
        return get_object_or_404(
            Product,
            pk=pk,
            seller=seller,
            status__in=[
                Product.Status.DRAFT,
                Product.Status.ACTIVE,
                Product.Status.INACTIVE,
            ],
        )

    def get(self, request, pk):
        product    = self._get_product(pk, self.seller_profile)
        categories = MarketplaceCategory.objects.filter(is_active=True)
        return render(request, self.template_name, {
            'product':           product,
            'categories':        categories,
            'conditions':        Product.Condition.choices,
            'action':            'update',
            'selected_state':    product.state or '',
            'selected_category': str(product.category_id) if product.category_id else '',
            'form_data': {
                'title':          product.title,
                'description':    product.description,
                'condition':      product.condition,
                'brand':          product.brand or '',
                'model_number':   product.model_number or '',
                'price':          product.price,
                'min_offer':      product.min_offer or '',
                'offers_allowed': '1' if product.offers_allowed else '',
                'lga':            product.lga or '',
                'pickup_notes':   product.pickup_notes or '',
                'slots':          product.slots,
            },
            'unread_count': _unread_count(request.user),
        })

    def post(self, request, pk):
        product    = self._get_product(pk, self.seller_profile)
        categories = MarketplaceCategory.objects.filter(is_active=True)

        title       = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        condition   = request.POST.get('condition', '')
        brand       = request.POST.get('brand', '').strip()
        model_no    = request.POST.get('model_number', '').strip()
        state       = request.POST.get('state', '')
        lga         = request.POST.get('lga', '').strip()
        pickup_notes = request.POST.get('pickup_notes', '').strip()
        cat_id      = request.POST.get('category', '')
        new_status  = request.POST.get('status', product.status)

        errors = {}
        if not title:
            errors['title'] = 'Title is required.'
        if not description:
            errors['description'] = 'Description is required.'
        if not condition or condition not in dict(Product.Condition.choices):
            errors['condition'] = 'Please select a condition.'

        try:
            price = float(request.POST.get('price', ''))
            if price <= 0:
                errors['price'] = 'Price must be greater than zero.'
        except (ValueError, TypeError):
            errors['price'] = 'Enter a valid price.'
            price = None

        min_offer = None
        if request.POST.get('min_offer'):
            try:
                min_offer = float(request.POST.get('min_offer'))
            except (ValueError, TypeError):
                errors['min_offer'] = 'Enter a valid minimum offer price.'

        try:
            slots = int(request.POST.get('slots', 1))
            if slots < 1:
                slots = 1
        except (ValueError, TypeError):
            slots = product.slots

        category = None
        if cat_id:
            category = MarketplaceCategory.objects.filter(pk=cat_id).first()

        if errors:
            return render(request, self.template_name, {
                'product':           product,
                'categories':        categories,
                'conditions':        Product.Condition.choices,
                'action':            'update',
                'errors':            errors,
                'selected_state':    request.POST.get('state', ''),
                'selected_category': request.POST.get('category', ''),
                'form_data':         request.POST,
                'unread_count':      _unread_count(request.user),
            })

        # Only allow valid status transitions
        allowed_statuses = {
            Product.Status.DRAFT,
            Product.Status.ACTIVE,
            Product.Status.INACTIVE,
        }
        if new_status not in allowed_statuses:
            new_status = product.status

        product.title         = title
        product.description   = description
        product.condition     = condition
        product.brand         = brand
        product.model_number  = model_no
        product.price         = price
        product.min_offer     = min_offer
        product.offers_allowed = request.POST.get('offers_allowed') == '1'
        product.state         = state
        product.lga           = lga
        product.pickup_notes  = pickup_notes
        product.slots         = slots
        product.category      = category
        product.status        = new_status
        product.save()

        # New images
        images = request.FILES.getlist('images')
        existing_count = product.images.count()
        for order_idx, img_file in enumerate(images[:max(0, 8 - existing_count)]):
            ProductImage.objects.create(
                product       = product,
                image         = img_file,
                display_order = existing_count + order_idx,
            )

        messages.success(request, f'"{product.title}" has been updated.')
        return redirect('mktplace:product_detail', pk=product.pk)


class ProductDeleteView(SellerRequiredMixin, View):
    """POST /marketplace/products/<uuid:pk>/delete/"""

    def post(self, request, pk):
        product = get_object_or_404(
            Product,
            pk=pk,
            seller=self.seller_profile,
        )
        # Only allow deletion of draft/inactive listings (not active or reserved)
        if product.status in [Product.Status.ACTIVE, Product.Status.RESERVED]:
            messages.error(
                request,
                'Active or reserved listings cannot be deleted. '
                'Set the listing to Inactive first.',
            )
            return redirect('mktplace:product_detail', pk=pk)

        title = product.title
        product.delete()
        messages.success(request, f'"{title}" has been deleted.')
        return redirect('mktplace:seller_dashboard')


# ──────────────────────────────────────────────────────────────────────────────
#  SELLER — IMAGE MANAGEMENT
# ──────────────────────────────────────────────────────────────────────────────

class ProductImageUploadView(SellerRequiredMixin, View):
    """POST /marketplace/products/<uuid:pk>/images/add/"""

    @rate_limit(key='img_upload:{user}', limit=40, window=3600, message='Image upload limit reached. Please wait a while.')
    def post(self, request, pk):
        product = get_object_or_404(Product, pk=pk, seller=self.seller_profile)

        if product.images.count() >= 8:
            messages.error(request, 'Maximum 8 images per listing.')
            return redirect('mktplace:product_edit', pk=pk)

        img_file = request.FILES.get('image')
        if not img_file:
            messages.error(request, 'No image file received.')
            return redirect('mktplace:product_edit', pk=pk)

        ProductImage.objects.create(
            product       = product,
            image         = img_file,
            caption       = request.POST.get('caption', '').strip(),
            display_order = product.images.count(),
        )
        messages.success(request, 'Image added.')
        return redirect('mktplace:product_edit', pk=pk)


class ProductImageDeleteView(SellerRequiredMixin, View):
    """POST /marketplace/images/<uuid:pk>/delete/"""

    def post(self, request, pk):
        img = get_object_or_404(
            ProductImage,
            pk=pk,
            product__seller=self.seller_profile,
        )
        product_pk = img.product.pk
        img.delete()
        messages.success(request, 'Image removed.')
        return redirect('mktplace:product_edit', pk=product_pk)


# ──────────────────────────────────────────────────────────────────────────────
#  BUYER — MAKE OFFER
# ──────────────────────────────────────────────────────────────────────────────

class MakeOfferView(LoginRequiredMixin, View):
    """
    POST /marketplace/products/<uuid:pk>/offer/

    Creates an Offer. Business rules enforced here:
      - Can't offer on your own listing.
      - Can't offer on a SOLD/INACTIVE/RESERVED listing.
      - Can't make a second active offer on the same product.
      - Offered price must be > 0.
      - If min_offer is set (seller private), enforce silently
        (don't reveal min_offer to buyer — just tell them their
        offer was below the minimum).
    """

    @rate_limit(key='make_offer:{user}', limit=20, window=3600, message='You have submitted too many offers recently. Please wait a bit.')
    def post(self, request, pk):
        product = get_object_or_404(Product, pk=pk)

        # Access checks
        if product.status != Product.Status.ACTIVE:
            messages.error(request, 'This listing is no longer available.')
            return redirect('mktplace:product_detail', pk=pk)

        seller_profile = _seller_profile_or_none(request.user)
        if seller_profile and seller_profile == product.seller:
            messages.error(request, "You can't make an offer on your own listing.")
            return redirect('mktplace:product_detail', pk=pk)

        if not product.offers_allowed:
            messages.error(request, 'This seller is not accepting offers.')
            return redirect('mktplace:product_detail', pk=pk)

        # One active offer per buyer per product
        existing = Offer.objects.filter(
            product=product,
            buyer=request.user,
            status__in=[Offer.Status.PENDING, Offer.Status.COUNTERED],
        ).exists()
        if existing:
            messages.warning(
                request,
                'You already have an active offer on this listing. '
                'Withdraw it before making a new one.',
            )
            return redirect('mktplace:product_detail', pk=pk)

        # Parse price
        try:
            offered_price = float(request.POST.get('offered_price', ''))
            if offered_price <= 0:
                raise ValueError
        except (ValueError, TypeError):
            messages.error(request, 'Please enter a valid offer price.')
            return redirect('mktplace:product_detail', pk=pk)

        # Enforce min_offer (private — don't reveal the exact floor)
        if product.min_offer and offered_price < float(product.min_offer):
            messages.error(
                request,
                'Your offer is below the minimum this seller will consider. '
                'Please offer a higher amount.',
            )
            return redirect('mktplace:product_detail', pk=pk)

        from datetime import timedelta
        Offer.objects.create(
            product       = product,
            buyer         = request.user,
            offered_price = offered_price,
            message       = request.POST.get('message', '').strip()[:500],
            expires_at    = timezone.now() + timedelta(hours=48),
        )

        messages.success(
            request,
            f'Your offer of ₦{offered_price:,.0f} has been sent to the seller.',
        )
        return redirect('mktplace:product_detail', pk=pk)


# ──────────────────────────────────────────────────────────────────────────────
#  SELLER — RESPOND TO OFFER  (accept / decline / counter)
# ──────────────────────────────────────────────────────────────────────────────

class RespondToOfferView(SellerRequiredMixin, View):
    """
    POST /marketplace/offers/<uuid:pk>/respond/

    request.POST['action'] = 'accept' | 'decline' | 'counter'
    request.POST['counter_price'] = <decimal>  (only for 'counter')
    request.POST['counter_message'] = <text>   (only for 'counter')

    On 'accept': creates an Order automatically and marks product as RESERVED.
    """

    def post(self, request, pk):
        offer = get_object_or_404(
            Offer.objects.select_related('product__seller', 'buyer'),
            pk=pk,
            product__seller=self.seller_profile,
            status=Offer.Status.PENDING,
        )
        action = request.POST.get('action', '')

        if action == 'accept':
            offer.status = Offer.Status.ACCEPTED
            offer.save(update_fields=['status', 'updated_at'])

            # Create order at the offered price
            order = Order.objects.create(
                product      = offer.product,
                buyer        = offer.buyer,
                seller       = self.seller_profile,
                offer        = offer,
                agreed_price = offer.offered_price,
                status       = Order.Status.PENDING,
            )
            # Mark product reserved
            Product.objects.filter(pk=offer.product_id).update(
                status=Product.Status.RESERVED
            )
            messages.success(
                request,
                f'Offer accepted. An order has been created — '
                f'awaiting payment from {offer.buyer.get_full_name() or offer.buyer.username}.',
            )
            return redirect('mktplace:order_detail', pk=order.pk)

        elif action == 'decline':
            offer.status = Offer.Status.DECLINED
            offer.save(update_fields=['status', 'updated_at'])
            messages.success(request, 'Offer declined.')
            return redirect('mktplace:seller_dashboard')

        elif action == 'counter':
            try:
                counter_price = float(request.POST.get('counter_price', ''))
                if counter_price <= 0:
                    raise ValueError
            except (ValueError, TypeError):
                messages.error(request, 'Enter a valid counter price.')
                return redirect('mktplace:product_detail', pk=offer.product_id)

            offer.status          = Offer.Status.COUNTERED
            offer.counter_price   = counter_price
            offer.counter_message = request.POST.get('counter_message', '').strip()[:500]
            offer.save(update_fields=['status', 'counter_price', 'counter_message', 'updated_at'])
            messages.success(
                request,
                f'Counter-offer of ₦{counter_price:,.0f} sent to buyer.',
            )
            return redirect('mktplace:seller_dashboard')

        messages.error(request, 'Unknown action.')
        return redirect('mktplace:seller_dashboard')


# ──────────────────────────────────────────────────────────────────────────────
#  BUYER — WITHDRAW OFFER
# ──────────────────────────────────────────────────────────────────────────────

class WithdrawOfferView(LoginRequiredMixin, View):
    """POST /marketplace/offers/<uuid:pk>/withdraw/"""

    def post(self, request, pk):
        offer = get_object_or_404(
            Offer,
            pk=pk,
            buyer=request.user,
            status__in=[Offer.Status.PENDING, Offer.Status.COUNTERED],
        )
        offer.status = Offer.Status.WITHDRAWN
        offer.save(update_fields=['status', 'updated_at'])
        messages.success(request, 'Your offer has been withdrawn.')
        return redirect('mktplace:product_detail', pk=offer.product_id)


# ──────────────────────────────────────────────────────────────────────────────
#  BUYER — ACCEPT COUNTER-OFFER
# ──────────────────────────────────────────────────────────────────────────────

class AcceptCounterOfferView(LoginRequiredMixin, View):
    """
    POST /marketplace/offers/<uuid:pk>/accept-counter/

    Buyer accepts the seller's counter-offer → creates an Order at counter_price.
    """

    def post(self, request, pk):
        offer = get_object_or_404(
            Offer.objects.select_related('product__seller'),
            pk=pk,
            buyer=request.user,
            status=Offer.Status.COUNTERED,
        )

        if not offer.counter_price:
            messages.error(request, 'No counter-offer price found.')
            return redirect('mktplace:product_detail', pk=offer.product_id)

        offer.status = Offer.Status.ACCEPTED
        offer.save(update_fields=['status', 'updated_at'])

        order = Order.objects.create(
            product      = offer.product,
            buyer        = request.user,
            seller       = offer.product.seller,
            offer        = offer,
            agreed_price = offer.counter_price,
            status       = Order.Status.PENDING,
        )
        Product.objects.filter(pk=offer.product_id).update(
            status=Product.Status.RESERVED
        )
        messages.success(
            request,
            f'Counter-offer accepted at ₦{offer.counter_price:,.0f}. '
            f'Proceed to payment.',
        )
        return redirect('mktplace:order_detail', pk=order.pk)


# ──────────────────────────────────────────────────────────────────────────────
#  BUYER — BUY NOW  (skip offer, pay listed price)
# ──────────────────────────────────────────────────────────────────────────────

class BuyNowView(LoginRequiredMixin, View):
    """
    POST /marketplace/products/<uuid:pk>/buy/

    Creates an Order at full listed price and redirects to payment.
    """

    @rate_limit(key='buy_now:{user}', limit=10, window=600, message='Too many order attempts. Please wait a few minutes.')
    def post(self, request, pk):
        product = get_object_or_404(Product, pk=pk, status=Product.Status.ACTIVE)

        seller_profile = _seller_profile_or_none(request.user)
        if seller_profile and seller_profile == product.seller:
            messages.error(request, "You can't buy your own listing.")
            return redirect('mktplace:product_detail', pk=pk)

        # Prevent duplicate pending orders from the same buyer
        if Order.objects.filter(
            product=product,
            buyer=request.user,
            status__in=[
                Order.Status.PENDING,
                Order.Status.PAID,
                Order.Status.MEETUP_SCHEDULED,
            ],
        ).exists():
            messages.warning(request, 'You already have an active order for this item.')
            return redirect('mktplace:order_list')

        order = Order.objects.create(
            product      = product,
            buyer        = request.user,
            seller       = product.seller,
            agreed_price = product.price,
            status       = Order.Status.PENDING,
        )

        # Initialize Paystack payment
        from marketplace.service.market_place_service_escrow import initialize_order_payment
        result = initialize_order_payment(str(order.pk), request.user.email)

        if 'error' in result:
            # Roll back order on payment init failure
            order.delete()
            messages.error(
                request,
                f'Could not initialize payment: {result["error"]}. Please try again.',
            )
            return redirect('mktplace:product_detail', pk=pk)

        return redirect(result['authorization_url'])


# ──────────────────────────────────────────────────────────────────────────────
#  ORDER — DETAIL & LIST
# ──────────────────────────────────────────────────────────────────────────────

class OrderDetailView(LoginRequiredMixin, View):
    """
    GET /marketplace/orders/<uuid:pk>/

    Accessible by the buyer OR the seller of the order.
    """

    template_name = 'marketplace/order_detail.html'

    def get(self, request, pk):
        order = get_object_or_404(
            Order.objects.select_related(
                'product', 'buyer', 'seller__user', 'offer',
            ).prefetch_related('product__images'),
            pk=pk,
        )

        # Access: buyer or seller only
        seller_profile = _seller_profile_or_none(request.user)
        is_buyer  = order.buyer == request.user
        is_seller = seller_profile == order.seller

        if not (is_buyer or is_seller or request.user.is_staff):
            return HttpResponseForbidden()

        # Fetch dispute and review if any
        dispute = getattr(order, 'dispute', None)
        review  = getattr(order, 'review', None)

        return render(request, self.template_name, {
            'order':            order,
            'is_buyer':         is_buyer,
            'is_seller':        is_seller,
            'dispute':          dispute,
            'review':           review,
            'can_confirm':      is_buyer and order.status in [
                                    Order.Status.PAID,
                                    Order.Status.MEETUP_SCHEDULED,
                                ],
            'can_retry_payout': (
                (is_buyer or is_seller or request.user.is_staff)
                and order.status == Order.Status.CONFIRMED
                and not order.completed_at
            ),
            'can_dispute':      is_buyer and order.status in [
                                    Order.Status.PAID,
                                    Order.Status.MEETUP_SCHEDULED,
                                    Order.Status.CONFIRMED,
                                ],
            'can_review':       (
                is_buyer
                and order.status == Order.Status.COMPLETED
                and review is None
            ),
            'unread_count':     _unread_count(request.user),
        })


class OrderListView(LoginRequiredMixin, View):
    """
    GET /marketplace/orders/

    Shows the logged-in user's purchase history (as buyer).
    """

    template_name = 'marketplace/order_list.html'

    def get(self, request):
        orders = (
            Order.objects.filter(buyer=request.user)
            .select_related('product', 'seller__user')
            .prefetch_related('product__images')
            .order_by('-created_at')
        )
        paginator = Paginator(orders, 15)
        page_obj  = paginator.get_page(request.GET.get('page'))

        return render(request, self.template_name, {
            'page_obj':     page_obj,
            'orders':       page_obj.object_list,
            'unread_count': _unread_count(request.user),
        })


class SellerOrderListView(SellerRequiredMixin, View):
    """
    GET /marketplace/seller/orders/

    Shows all orders where user is the seller, with status filter support.
    """

    template_name = 'marketplace/seller_order_list.html'

    def get(self, request):
        status_filter = request.GET.get('status', '')
        qs = (
            Order.objects.filter(seller=self.seller_profile)
            .select_related('product', 'buyer')
            .prefetch_related('product__images')
            .order_by('-created_at')
        )
        if status_filter and status_filter in dict(Order.Status.choices):
            qs = qs.filter(status=status_filter)

        paginator = Paginator(qs, 15)
        page_obj  = paginator.get_page(request.GET.get('page'))

        return render(request, self.template_name, {
            'page_obj':      page_obj,
            'orders':        page_obj.object_list,
            'status_filter': status_filter,
            'statuses':      Order.Status.choices,
            'unread_count':  _unread_count(request.user),
        })


# ──────────────────────────────────────────────────────────────────────────────
#  BUYER — CONFIRM RECEIPT
# ──────────────────────────────────────────────────────────────────────────────

class ConfirmReceiptView(LoginRequiredMixin, View):
    """
    POST /marketplace/orders/<uuid:pk>/confirm/

    Buyer confirms they received the item, or buyer/seller retries payout if
    the background transfer previously failed.
    Triggers payout to seller via Celery task.
    """

    def post(self, request, pk):
        order = get_object_or_404(
            Order,
            pk=pk,
            status__in=[
                Order.Status.PAID,
                Order.Status.MEETUP_SCHEDULED,
                Order.Status.CONFIRMED,
            ],
        )

        seller_profile = _seller_profile_or_none(request.user)
        is_buyer = order.buyer == request.user
        is_seller = seller_profile == order.seller

        if not (is_buyer or is_seller or request.user.is_staff):
            return HttpResponseForbidden()

        from marketplace.service.market_place_service_escrow import confirm_order_receipt
        success = confirm_order_receipt(str(order.pk))

        if success:
            if order.status == Order.Status.CONFIRMED:
                messages.success(
                    request,
                    'Payout transfer process initiated for this order.',
                )
            else:
                messages.success(
                    request,
                    'Receipt confirmed — the seller will receive their payment shortly. '
                    'Please leave a review.',
                )
        else:
            messages.error(request, 'Could not process receipt/payout. Please try again.')

        return redirect('mktplace:order_detail', pk=pk)


# ──────────────────────────────────────────────────────────────────────────────
#  BUYER — PAYSTACK CALLBACK
# ──────────────────────────────────────────────────────────────────────────────

class PaystackCallbackView(View):
    """
    GET /marketplace/paystack/callback/

    Paystack redirects here after the buyer completes payment on their
    hosted checkout page.

    We do NOT verify payment here — that is done by the webhook
    (charge.success → verify_order_payment). This view just finds
    the order from the reference and shows the right message.
    """

    @rate_limit(key='mkt_paystack_cb:{ip}', limit=30, window=60, message='Too many requests.')
    def get(self, request):
        reference = request.GET.get('reference', '')

        if not reference:
            messages.error(request, 'No payment reference found.')
            return redirect('mktplace:order_list')

        order = Order.objects.filter(
            paystack_payment_ref=reference,
        ).first()

        if order and request.user.is_authenticated and order.buyer != request.user:
            messages.error(request, 'You do not have permission to view this order.')
            return redirect('mktplace:order_list')

        if not order:
            messages.warning(
                request,
                'We received your payment — it is being verified. '
                'Check your orders shortly.',
            )
            return redirect('mktplace:order_list')

        if order.status in [
            Order.Status.PAID,
            Order.Status.MEETUP_SCHEDULED,
            Order.Status.CONFIRMED,
            Order.Status.COMPLETED,
        ]:
            messages.success(
                request,
                'Payment confirmed! The seller has been notified and will '
                'contact you to arrange handover.',
            )
        else:
            messages.info(
                request,
                'Your payment is being verified — this usually takes a few '
                'seconds. Refresh this page shortly.',
            )

        return redirect('mktplace:order_detail', pk=order.pk)


# ──────────────────────────────────────────────────────────────────────────────
#  BUYER — RAISE DISPUTE
# ──────────────────────────────────────────────────────────────────────────────

class RaiseDisputeView(LoginRequiredMixin, View):
    """
    POST /marketplace/orders/<uuid:pk>/dispute/

    Buyer raises a dispute on a PAID or CONFIRMED order.
    Enforces:
      - 24h minimum age after payment (prevents premature dispute)
      - 14-day maximum dispute window
      - Single active dispute per order
      - MIME whitelist + SHA-256 evidence hashing
      - 5-day mediation window + 7-day auto-release SLA
    """

    def post(self, request, pk):
        order = get_object_or_404(
            Order,
            pk=pk,
            buyer=request.user,
            status__in=[
                Order.Status.PAID,
                Order.Status.MEETUP_SCHEDULED,
                Order.Status.CONFIRMED,
            ],
        )

        # Can't raise a second dispute
        if hasattr(order, 'dispute'):
            messages.warning(request, 'A dispute already exists for this order.')
            return redirect('mktplace:order_detail', pk=pk)

        # 24h minimum age
        now = timezone.now()
        if order.paid_at:
            age_hours = (now - order.paid_at).total_seconds() / 3600
            if age_hours < 24:
                messages.error(
                    request,
                    'A dispute cannot be raised within 24 hours of payment. Please allow time for meetup/handover.',
                )
                return redirect('mktplace:order_detail', pk=pk)

            # 14-day window
            age_days = (now - order.paid_at).days
            if age_days > 14:
                messages.error(
                    request,
                    'The 14-day dispute window for this order has expired.',
                )
                return redirect('mktplace:order_detail', pk=pk)

        reason = request.POST.get('reason', '').strip()
        if not reason:
            messages.error(request, 'Please describe the problem.')
            return redirect('mktplace:order_detail', pk=pk)

        evidence = request.FILES.get('evidence')
        evidence_sha256 = ""
        if evidence:
            try:
                _validate_evidence_mime(evidence)
            except ValidationError as exc:
                messages.error(request, str(exc))
                return redirect('mktplace:order_detail', pk=pk)
            evidence_sha256 = _hash_file(evidence)

        OrderDispute.objects.create(
            order           = order,
            raised_by       = request.user,
            reason          = reason,
            evidence        = evidence,
            evidence_sha256 = evidence_sha256,
            mediation_deadline = now + timedelta(days=5),
            auto_release_at = now + timedelta(days=7),
        )
        order.status = Order.Status.DISPUTED
        order.save(update_fields=['status', 'updated_at'])

        # Notify seller
        Notification.objects.create(
            user=order.seller.user,
            notif_type=Notification.NotifType.SYSTEM,
            title='Dispute raised on order',
            body=(
                f'Buyer has raised a dispute on "{order.product.title}". '
                f'You have 5 days to resolve this via the dispute thread.'
            ),
            data={'order_id': str(order.pk)},
        )

        messages.warning(
            request,
            'Your dispute has been raised. You and the seller have 5 days for mediation before admin review.',
        )
        return redirect('mktplace:order_detail', pk=pk)


# ──────────────────────────────────────────────────────────────────────────────
#  MARKETPLACE DISPUTE MESSAGES (EVIDENCE THREAD)
# ──────────────────────────────────────────────────────────────────────────────

class PostOrderDisputeMessageView(LoginRequiredMixin, View):
    """
    POST /marketplace/disputes/<uuid:pk>/messages/
    Buyer, seller, or staff posts an immutable message or evidence to the thread.
    """

    def post(self, request, pk):
        dispute = get_object_or_404(
            OrderDispute.objects.select_related('order__seller__user', 'order__buyer'),
            pk=pk,
        )

        is_buyer = dispute.order.buyer_id == request.user.pk
        is_seller = dispute.order.seller.user_id == request.user.pk
        if not (is_buyer or is_seller or request.user.is_staff):
            return HttpResponseForbidden()

        body = request.POST.get('body', '').strip()
        attachment = request.FILES.get('attachment')
        is_admin_note = request.POST.get('is_admin_note') in ('true', '1', 'on') and request.user.is_staff

        if not body and not attachment:
            messages.error(request, 'Please provide a message or attach evidence.')
            return redirect('mktplace:order_detail', pk=dispute.order.pk)

        sha256 = ""
        if attachment:
            try:
                _validate_evidence_mime(attachment)
            except ValidationError as exc:
                messages.error(request, str(exc))
                return redirect('mktplace:order_detail', pk=dispute.order.pk)
            sha256 = _hash_file(attachment)

        OrderDisputeMessage.objects.create(
            dispute=dispute,
            author=request.user,
            body=body,
            attachment=attachment,
            attachment_sha256=sha256,
            is_admin_note=is_admin_note,
        )

        # Notify the counterparty
        recipient = dispute.order.seller.user if is_buyer else dispute.order.buyer
        Notification.objects.create(
            user=recipient,
            notif_type=Notification.NotifType.SYSTEM,
            title='New message on dispute',
            body=f'{request.user.get_full_name() or request.user.username} posted on order #{str(dispute.order.pk)[:8]}.',
            data={'order_id': str(dispute.order.pk)},
        )

        messages.success(request, 'Message / evidence posted to dispute thread.')
        return redirect('mktplace:order_detail', pk=dispute.order.pk)


# ──────────────────────────────────────────────────────────────────────────────
#  MARKETPLACE MEDIATION AGREE (5-DAY WINDOW)
# ──────────────────────────────────────────────────────────────────────────────

class OrderMediationAgreeView(LoginRequiredMixin, View):
    """
    POST /marketplace/disputes/<uuid:pk>/mediate/
    Buyer or seller agrees to a mutual resolution during the 5-day mediation window.
    """

    def post(self, request, pk):
        dispute = get_object_or_404(
            OrderDispute.objects.select_related('order__seller__user', 'order__buyer'),
            pk=pk,
            resolution=OrderDispute.Resolution.PENDING,
        )

        is_buyer = dispute.order.buyer_id == request.user.pk
        is_seller = dispute.order.seller.user_id == request.user.pk
        if not (is_buyer or is_seller):
            return HttpResponseForbidden()

        agreed = request.POST.get('agreed_resolution', '').strip()
        valid = {OrderDispute.Resolution.RELEASED_TO_SELLER, OrderDispute.Resolution.REFUNDED_TO_BUYER}
        if agreed not in valid:
            messages.error(request, 'Invalid resolution choice.')
            return redirect('mktplace:order_detail', pk=dispute.order.pk)

        now = timezone.now()
        if dispute.mediation_deadline and now > dispute.mediation_deadline:
            messages.error(request, 'The 5-day mediation window has closed. An admin will review this dispute.')
            return redirect('mktplace:order_detail', pk=dispute.order.pk)

        if is_buyer:
            dispute.mediation_buyer_agreed = agreed
            dispute.save(update_fields=['mediation_buyer_agreed'])
        else:
            dispute.mediation_seller_agreed = agreed
            dispute.save(update_fields=['mediation_seller_agreed'])

        # Check if both agree
        if dispute.mediation_buyer_agreed and dispute.mediation_seller_agreed and dispute.mediation_buyer_agreed == dispute.mediation_seller_agreed:
            from marketplace.service.market_place_service_escrow import release_order_to_seller, refund_order_to_buyer
            if agreed == OrderDispute.Resolution.RELEASED_TO_SELLER:
                release_order_to_seller(str(dispute.order.pk))
            else:
                refund_order_to_buyer(str(dispute.order.pk))

            dispute.resolution = agreed
            dispute.resolution_note = "Resolved by mutual agreement during mediation window."
            dispute.resolved_at = now
            dispute.resolved_by = request.user
            dispute.save(update_fields=['resolution', 'resolution_note', 'resolved_at', 'resolved_by'])

            messages.success(request, 'Both parties agreed! The dispute has been automatically resolved.')
        else:
            messages.success(request, 'Your agreement has been recorded. Waiting for the other party to confirm.')

        return redirect('mktplace:order_detail', pk=dispute.order.pk)



# ──────────────────────────────────────────────────────────────────────────────
#  BUYER — SUBMIT PRODUCT REVIEW
# ──────────────────────────────────────────────────────────────────────────────

class SubmitReviewView(LoginRequiredMixin, View):
    """
    POST /marketplace/orders/<uuid:pk>/review/

    Buyer submits a rating + comment after a COMPLETED order.
    Enforced: one review per order (OneToOneField on model).
    """

    def post(self, request, pk):
        order = get_object_or_404(
            Order.objects.select_related('product', 'seller'),
            pk=pk,
            buyer=request.user,
            status=Order.Status.COMPLETED,
        )

        if hasattr(order, 'review'):
            messages.warning(request, "You've already reviewed this order.")
            return redirect('mktplace:order_detail', pk=pk)

        try:
            rating = int(request.POST.get('rating', ''))
            if not (1 <= rating <= 5):
                raise ValueError
        except (ValueError, TypeError):
            messages.error(request, 'Please select a rating between 1 and 5.')
            return redirect('mktplace:order_detail', pk=pk)

        comment = request.POST.get('comment', '').strip()

        ProductReview.objects.create(
            order    = order,
            reviewer = request.user,
            seller   = order.seller,
            product  = order.product,
            rating   = rating,
            comment  = comment,
        )
        messages.success(request, 'Thank you for your review!')
        return redirect('mktplace:order_detail', pk=pk)


# ──────────────────────────────────────────────────────────────────────────────
#  BUYER — TOGGLE SAVE PRODUCT
# ──────────────────────────────────────────────────────────────────────────────

class ToggleSaveProductView(LoginRequiredMixin, View):
    """
    POST /marketplace/products/<uuid:pk>/save/

    Toggles SavedProduct for the logged-in user.
    Returns JSON {'saved': true/false} for AJAX calls,
    or redirects for plain form posts.
    """

    def post(self, request, pk):
        product = get_object_or_404(Product, pk=pk)
        saved, created = SavedProduct.objects.get_or_create(
            user=request.user, product=product
        )
        if not created:
            saved.delete()
            is_saved = False
        else:
            is_saved = True

        # Honour AJAX requests
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'saved': is_saved})

        if is_saved:
            messages.success(request, f'"{product.title}" saved.')
        else:
            messages.info(request, f'"{product.title}" removed from saved items.')

        return redirect('mktplace:product_detail', pk=pk)


# ──────────────────────────────────────────────────────────────────────────────
#  ADMIN — RESOLVE DISPUTE
# ──────────────────────────────────────────────────────────────────────────────

class DisputeAdminResolveView(LoginRequiredMixin, View):
    """
    POST /marketplace/disputes/<uuid:pk>/resolve/

    Staff-only. Resolves an OrderDispute.

    request.POST['resolution'] = 'released_to_seller' | 'refunded_to_buyer' | 'split'
    request.POST['resolution_note'] = <text>
    request.POST['split_seller_pct'] = <0-100>  (only for 'split')

    On released_to_seller → release_order_to_seller()
    On refunded_to_buyer  → Paystack Refund API (phase 2 — stub for now)
    On split              → partial transfer (phase 2 — stub)
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_staff:
            return HttpResponseForbidden()
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, pk):
        dispute = get_object_or_404(
            OrderDispute.objects.select_related(
                'order__product', 'order__seller', 'order__buyer',
            ),
            pk=pk,
            resolution=OrderDispute.Resolution.PENDING,
        )

        resolution = request.POST.get('resolution', '')
        valid = {
            OrderDispute.Resolution.RELEASED_TO_SELLER,
            OrderDispute.Resolution.REFUNDED_TO_BUYER,
            OrderDispute.Resolution.SPLIT,
        }
        if resolution not in valid:
            messages.error(request, 'Invalid resolution choice.')
            return redirect('admin:marketplace_orderdispute_change', pk)

        note = request.POST.get('resolution_note', '').strip()
        now  = timezone.now()

        split_seller_pct = None
        if resolution == OrderDispute.Resolution.SPLIT:
            try:
                split_seller_pct = int(request.POST.get('split_seller_pct', 50))
            except (ValueError, TypeError):
                split_seller_pct = 50

        dispute.resolution       = resolution
        dispute.resolution_note  = note
        dispute.split_seller_pct = split_seller_pct
        dispute.resolved_at      = now
        dispute.resolved_by      = request.user
        dispute.save(update_fields=[
            'resolution', 'resolution_note', 'split_seller_pct', 'resolved_at', 'resolved_by',
        ])

        order = dispute.order
        from marketplace.service.market_place_service_escrow import (
            release_order_to_seller,
            refund_order_to_buyer,
            split_order,
        )

        if resolution == OrderDispute.Resolution.RELEASED_TO_SELLER:
            success = release_order_to_seller(str(order.pk))
            if success:
                messages.success(request, 'Funds released to seller via Paystack Transfer.')
            else:
                messages.error(request, 'Transfer failed — check logs.')

        elif resolution == OrderDispute.Resolution.REFUNDED_TO_BUYER:
            success = refund_order_to_buyer(str(order.pk))
            if success:
                messages.success(request, 'Order refunded to buyer via Paystack Refund API.')
            else:
                messages.error(request, 'Refund failed — check logs.')

        elif resolution == OrderDispute.Resolution.SPLIT:
            success = split_order(str(order.pk), split_seller_pct)
            if success:
                messages.success(
                    request,
                    f'Dispute resolved with split: seller received {split_seller_pct}%, buyer refunded {100 - split_seller_pct}%.',
                )
            else:
                messages.error(request, 'Split payout failed — check logs.')

        # Notify both parties
        Notification.objects.create(
            user=order.buyer,
            notif_type=Notification.NotifType.SYSTEM,
            title='Dispute resolved',
            body=(
                f'Your dispute on "{order.product.title}" has been resolved: '
                f'{dispute.get_resolution_display()}. {note}'
            ),
            data={'order_id': str(order.pk)},
        )
        Notification.objects.create(
            user=order.seller.user,
            notif_type=Notification.NotifType.SYSTEM,
            title='Dispute resolved',
            body=(
                f'The dispute on "{order.product.title}" has been resolved: '
                f'{dispute.get_resolution_display()}. {note}'
            ),
            data={'order_id': str(order.pk)},
        )

        return redirect('mktplace:order_detail', pk=order.pk)



from django.db.models import Sum as models_Sum