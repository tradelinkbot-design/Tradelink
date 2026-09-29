"""
Helper: patch views.py to inject recommendation context into ProductDetailView
and ProductListView. Also adds a view-interaction log to ProductDetailView.
Run once: python patch_views.py
"""

target = 'marketplace/views.py'

with open(target, 'r', encoding='utf-8') as f:
    content = f.read()

# ── Patch 1: Expand the models import to include new recommendation models ──
OLD_IMPORT = """from .models import (
    MarketplaceCategory,
    Product,
    ProductImage,
    Offer,
    Order,
    OrderDispute,
    ProductReview,
    SavedProduct,
)"""

NEW_IMPORT = """from .models import (
    MarketplaceCategory,
    Product,
    ProductImage,
    Offer,
    Order,
    OrderDispute,
    ProductReview,
    SavedProduct,
    UserProductInteraction,
    ProductRecommendation,
)"""

if 'UserProductInteraction' not in content:
    content = content.replace(OLD_IMPORT, NEW_IMPORT, 1)
    print('Patch 1 applied: expanded imports.')
else:
    print('Patch 1 SKIP: UserProductInteraction already imported.')


# ── Patch 2: ProductDetailView — inject similar/cross-sell recs + log view ──
OLD_DETAIL_RETURN = """        return render(request, self.template_name, {
            'product':       product,
            'is_seller':     is_seller,
            'pending_offers': pending_offers,
            'buyer_offer':   buyer_offer,
            'active_order':  active_order,
            'is_saved':      _is_saved(request.user, product),
            'avg_rating':    round(avg_rating, 1) if avg_rating else None,
            'reviews':       product.reviews.all()[:10],
            'unread_count':  _unread_count(request.user),
        })"""

NEW_DETAIL_RETURN = """        # ── AI Recommendations ───────────────────────────────────────────
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
        })"""

if 'similar_products' not in content:
    content = content.replace(OLD_DETAIL_RETURN, NEW_DETAIL_RETURN, 1)
    print('Patch 2 applied: ProductDetailView recs injected.')
else:
    print('Patch 2 SKIP: already patched.')


# ── Patch 3: ProductListView — inject personalised feed + trending ───────────
OLD_LIST_CATEGORIES = "        categories = MarketplaceCategory.objects.filter(is_active=True)"

NEW_LIST_CATEGORIES = """        categories = MarketplaceCategory.objects.filter(is_active=True)

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
        )"""

if 'personalised_products' not in content:
    content = content.replace(OLD_LIST_CATEGORIES, NEW_LIST_CATEGORIES, 1)
    print('Patch 3 applied: ProductListView personalised+trending injected.')
else:
    print('Patch 3 SKIP: already patched.')


# ── Patch 4: ProductListView context — add new template vars ────────────────
OLD_LIST_CONTEXT = """        return render(request, self.template_name, {
            'products':        products,
            'page_obj':        page_obj,
            'categories':      categories,
            'category':        category,
            'q':               q,
            'condition':       condition,
            'state':           state,
            'min_price':       min_price,
            'max_price':       max_price,
            'sort':            sort,
            'semantic_active': semantic_active,
            'conditions':      Product.Condition.choices,
            'unread_count':    _unread_count(request.user),
        })"""

NEW_LIST_CONTEXT = """        return render(request, self.template_name, {
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
        })"""

if "'trending_products'" not in content:
    content = content.replace(OLD_LIST_CONTEXT, NEW_LIST_CONTEXT, 1)
    print('Patch 4 applied: ProductListView context expanded.')
else:
    print('Patch 4 SKIP: already patched.')


with open(target, 'w', encoding='utf-8') as f:
    f.write(content)

print('DONE: all patches applied to views.py')
