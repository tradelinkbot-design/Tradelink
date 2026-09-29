"""
marketplace/service/recommendation_service.py
=============================================
TradeLink NG — Marketplace AI Recommendation Engine.

Five recommendation engines, all built on the existing sentence-transformer
singleton from jobs/service/text_encoder.py. No new dependencies required.

Engine 1 — Similar Items
    Algorithm : cosine similarity between Product.text_embedding vectors.
    Trigger   : after compute_product_embedding_task completes.
    Output    : ProductRecommendation rows (rec_type='similar').

Engine 2 — Personalised Feed
    Algorithm : weighted mean embedding of user interaction history (taste
                profile), then cosine similarity against all active products.
    Trigger   : after user makes offer or completes purchase; nightly batch.
    Output    : ProductRecommendation rows (rec_type='personal', user=user).

Engine 3 — Trending
    Algorithm : time-decayed popularity score using interaction event counts
                over the last 7 days. Exponential decay rewards recent activity.
    Trigger   : hourly Celery Beat task.
    Output    : Product.trending_score field (updated in-place).

Engine 4 — Price Intelligence
    Algorithm : finds semantically similar products (score > 0.70), computes
                the median price, derives a percentile rank for this product.
    Trigger   : after product is created or price changes.
    Output    : Product.price_percentile + Product.market_median_price fields.

Engine 5 — Cross-Sell
    Algorithm : co-purchase co-occurrence graph. When user buys product A,
                increment co-occurrence counts for every other product B the
                same user has previously purchased. Score = normalised count.
    Trigger   : after an Order reaches COMPLETED status.
    Output    : ProductRecommendation rows (rec_type='cross_sell').

Design principles (mirrors jobs/service/matching_service.py):
  - Never touches the DB and ML in the same function.
  - All DB writes use bulk_create / update to minimise round-trips.
  - All functions return a count (int) for Celery task logging.
  - All functions are idempotent (safe to re-run).
"""

import logging
import math
from decimal import Decimal
from typing import List, Optional, Tuple
from datetime import timedelta

import numpy as np
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

logger = logging.getLogger(__name__)

# Similarity threshold: products below this cosine similarity are ignored
SIMILARITY_THRESHOLD = 0.45
PRICE_SIMILARITY_THRESHOLD = 0.70
TOP_K_SIMILAR = 8
TOP_K_PERSONAL = 12
TOP_K_CROSS_SELL = 6


# ──────────────────────────────────────────────────────────────────────────────
#  ENGINE 1 — SIMILAR ITEMS
# ──────────────────────────────────────────────────────────────────────────────

def compute_similar_products(product_id: str, top_k: int = TOP_K_SIMILAR) -> int:
    """
    Find the top_k most semantically similar active products to the given
    product, using cosine similarity between sentence-transformer embeddings.

    Only considers products in the same MarketplaceCategory to keep results
    relevant. Falls back to all categories if fewer than 5 candidates exist
    in the same category.

    Returns the number of ProductRecommendation rows written.
    """
    from marketplace.models import Product, ProductRecommendation
    from jobs.service.text_encoder import text_encoder

    try:
        product = Product.objects.select_related('category').get(
            pk=product_id, status=Product.Status.ACTIVE,
        )
    except Product.DoesNotExist:
        logger.warning('compute_similar_products: product %s not found or inactive.', product_id)
        return 0

    if not product.text_embedding:
        logger.warning('compute_similar_products: product %s has no embedding yet.', product_id)
        return 0

    # Build candidate queryset — same category first, expand if sparse
    base_qs = (
        Product.objects
        .filter(status=Product.Status.ACTIVE)
        .exclude(pk=product.pk)
        .exclude(text_embedding__isnull=True)
    )

    same_cat_qs = base_qs.filter(category=product.category) if product.category else base_qs
    candidates_qs = same_cat_qs if same_cat_qs.count() >= 5 else base_qs

    candidates = list(candidates_qs.values('id', 'text_embedding'))
    if not candidates:
        return 0

    # Vectorised batch cosine similarity
    query_vec = product.text_embedding
    candidate_vecs = [c['text_embedding'] for c in candidates]
    scores = text_encoder.batch_cosine_similarity(query_vec, candidate_vecs)

    # Filter + rank
    ranked: List[Tuple[str, float]] = sorted(
        [(str(c['id']), s) for c, s in zip(candidates, scores) if s >= SIMILARITY_THRESHOLD],
        key=lambda x: -x[1],
    )[:top_k]

    if not ranked:
        return 0

    # Upsert ProductRecommendation rows
    _upsert_recommendations(
        rec_type=ProductRecommendation.RecommendationType.SIMILAR,
        source_product_id=product_id,
        pairs=ranked,
        user=None,
    )

    logger.info(
        'compute_similar_products: wrote %d similar recs for product %s.',
        len(ranked), product_id,
    )
    return len(ranked)


# ──────────────────────────────────────────────────────────────────────────────
#  ENGINE 2 — PERSONALISED FEED
# ──────────────────────────────────────────────────────────────────────────────

def compute_personalised_feed(user_id: int, top_k: int = TOP_K_PERSONAL) -> int:
    """
    Build a personalised product feed for a user by:
      1. Fetching the user's last 50 interactions (weighted by event type).
      2. Loading the embeddings of interacted products.
      3. Computing a weighted mean embedding (the user's "taste profile").
      4. Running batch cosine similarity against all active products the user
         has NOT already interacted with.
      5. Storing top_k results as PersonalRecommendation rows.

    Returns the number of ProductRecommendation rows written.
    """
    from marketplace.models import Product, ProductRecommendation, UserProductInteraction
    from jobs.service.text_encoder import text_encoder

    # Fetch recent interactions (last 90 days, max 50 events)
    cutoff = timezone.now() - timedelta(days=90)
    interactions = (
        UserProductInteraction.objects
        .filter(user_id=user_id, created_at__gte=cutoff)
        .select_related('product')
        .order_by('-created_at')[:50]
    )

    if not interactions:
        logger.debug('compute_personalised_feed: no interactions for user %s.', user_id)
        return 0

    # Build weighted sum of embeddings
    weighted_sum = None
    total_weight = 0.0
    interacted_ids = set()

    for interaction in interactions:
        product = interaction.product
        interacted_ids.add(str(product.pk))

        if not product.text_embedding:
            continue

        weight = UserProductInteraction.EVENT_WEIGHTS.get(interaction.event_type, 1.0)
        vec = np.array(product.text_embedding, dtype=np.float32)

        if weighted_sum is None:
            weighted_sum = vec * weight
        else:
            weighted_sum += vec * weight
        total_weight += weight

    if weighted_sum is None or total_weight == 0:
        return 0

    # Normalise to get unit taste vector
    taste_profile = weighted_sum / total_weight
    norm = np.linalg.norm(taste_profile)
    if norm > 0:
        taste_profile = taste_profile / norm

    # Candidates: active products NOT already interacted with
    candidates = list(
        Product.objects
        .filter(status=Product.Status.ACTIVE)
        .exclude(pk__in=interacted_ids)
        .exclude(text_embedding__isnull=True)
        .values('id', 'text_embedding')
    )

    if not candidates:
        return 0

    candidate_vecs = [c['text_embedding'] for c in candidates]
    scores = text_encoder.batch_cosine_similarity(taste_profile.tolist(), candidate_vecs)

    ranked: List[Tuple[str, float]] = sorted(
        [(str(c['id']), s) for c, s in zip(candidates, scores) if s >= SIMILARITY_THRESHOLD],
        key=lambda x: -x[1],
    )[:top_k]

    if not ranked:
        return 0

    # Add trade category affinity boost for worker users
    ranked = _apply_trade_affinity_boost(user_id, ranked)

    _upsert_recommendations(
        rec_type=ProductRecommendation.RecommendationType.PERSONAL,
        source_product_id=None,
        pairs=ranked,
        user_id=user_id,
    )

    logger.info(
        'compute_personalised_feed: wrote %d personal recs for user %s.',
        len(ranked), user_id,
    )
    return len(ranked)


def _apply_trade_affinity_boost(user_id: int, ranked: List[Tuple[str, float]]) -> List[Tuple[str, float]]:
    """
    If the user is a WorkerProfile, boost products in their trade's related
    marketplace categories by 15%. Electricians see electrical equipment higher.
    """
    try:
        from jobs.models import WorkerProfile
        from marketplace.models import Product
        worker = WorkerProfile.objects.select_related('trade_category').get(user_id=user_id)
        trade_name = worker.trade_category.name.lower() if worker.trade_category else ''
    except Exception:
        return ranked

    if not trade_name:
        return ranked

    # Fetch recommended product categories
    product_ids = [pid for pid, _ in ranked]
    category_map = dict(
        Product.objects.filter(pk__in=product_ids)
        .values_list('id', 'category__name')
    )

    boosted = []
    for pid, score in ranked:
        cat_name = (category_map.get(pid) or '').lower()
        # Simple heuristic: if category name overlaps with trade name words
        trade_words = set(trade_name.split())
        cat_words = set(cat_name.split())
        if trade_words & cat_words:
            score = min(1.0, score * 1.15)  # 15% boost, capped at 1.0
        boosted.append((pid, score))

    # Re-sort after boosting
    return sorted(boosted, key=lambda x: -x[1])


# ──────────────────────────────────────────────────────────────────────────────
#  ENGINE 3 — TRENDING
# ──────────────────────────────────────────────────────────────────────────────

def compute_trending_scores() -> int:
    """
    Compute and update trending_score for all active products.

    trending_score = time-decayed interaction-weighted popularity.

    Interaction weights (last 7 days):
        view     * 0.4
        save     * 1.5
        chat     * 2.0
        offer    * 3.0
        purchase * 5.0

    Recency decay: events from N days ago contribute score * exp(-0.2 * N).
    This means yesterday's events count ~82% of today's; last week ~25%.

    Returns the number of products updated.
    """
    from marketplace.models import Product, UserProductInteraction

    now = timezone.now()
    cutoff = now - timedelta(days=7)

    # Weight configuration
    INTERACTION_WEIGHT = {
        'view':     0.4,
        'save':     1.5,
        'chat':     2.0,
        'offer':    3.0,
        'purchase': 5.0,
    }
    DECAY_RATE = 0.2  # lambda for exp(-decay * days_ago)

    active_product_ids = list(
        Product.objects.filter(status=Product.Status.ACTIVE).values_list('id', flat=True)
    )

    if not active_product_ids:
        return 0

    # Fetch all interactions in the last 7 days in one query
    interactions = (
        UserProductInteraction.objects
        .filter(product__in=active_product_ids, created_at__gte=cutoff)
        .values('product_id', 'event_type', 'created_at')
    )

    # Accumulate scores per product
    scores: dict = {str(pid): 0.0 for pid in active_product_ids}

    for interaction in interactions:
        pid = str(interaction['product_id'])
        event_w = INTERACTION_WEIGHT.get(interaction['event_type'], 0.4)
        days_ago = (now - interaction['created_at']).total_seconds() / 86400
        decay = math.exp(-DECAY_RATE * days_ago)
        scores[pid] = scores.get(pid, 0.0) + event_w * decay

    # Normalise scores to [0, 1] range
    max_score = max(scores.values()) if scores else 1.0
    if max_score > 0:
        scores = {pid: s / max_score for pid, s in scores.items()}

    # Bulk update Product.trending_score
    updated = 0
    with transaction.atomic():
        for pid, score in scores.items():
            updated += Product.objects.filter(pk=pid).update(trending_score=score)

    logger.info('compute_trending_scores: updated trending_score for %d products.', updated)
    return updated


def get_trending_products(category_id=None, limit: int = 8):
    """
    Returns trending active products, optionally filtered by category.
    Reads directly from Product.trending_score — zero extra queries beyond
    what the view already makes.
    """
    from marketplace.models import Product
    qs = Product.objects.filter(status=Product.Status.ACTIVE, trending_score__gt=0)
    if category_id:
        qs = qs.filter(category_id=category_id)
    return (
        qs.select_related('category', 'seller__user')
        .prefetch_related('images')
        .order_by('-trending_score')[:limit]
    )


# ──────────────────────────────────────────────────────────────────────────────
#  ENGINE 4 — PRICE INTELLIGENCE
# ──────────────────────────────────────────────────────────────────────────────

def compute_price_intelligence(product_id: str) -> bool:
    """
    For a given product, find semantically similar products (score >= 0.70),
    compute the market median price, and derive this product's price percentile.

    Updates Product.price_percentile and Product.market_median_price in-place.

    Returns True on success, False if insufficient data.
    """
    from marketplace.models import Product
    from jobs.service.text_encoder import text_encoder

    try:
        product = Product.objects.get(pk=product_id, status=Product.Status.ACTIVE)
    except Product.DoesNotExist:
        return False

    if not product.text_embedding:
        return False

    # Fetch similar active products (same category preferred)
    base_qs = (
        Product.objects
        .filter(status=Product.Status.ACTIVE)
        .exclude(pk=product.pk)
        .exclude(text_embedding__isnull=True)
    )
    if product.category:
        base_qs = base_qs.filter(category=product.category)

    candidates = list(base_qs.values('id', 'text_embedding', 'price'))
    if len(candidates) < 3:
        # Too few data points for meaningful intelligence
        return False

    candidate_vecs = [c['text_embedding'] for c in candidates]
    scores = text_encoder.batch_cosine_similarity(product.text_embedding, candidate_vecs)

    # Only include products with high similarity (tight comparison group)
    similar_prices = [
        float(c['price'])
        for c, s in zip(candidates, scores)
        if s >= PRICE_SIMILARITY_THRESHOLD
    ]

    if len(similar_prices) < 3:
        return False

    similar_prices.sort()
    market_median = _median(similar_prices)
    this_price = float(product.price)

    # Percentile rank: how many similar products are cheaper than this one?
    cheaper_count = sum(1 for p in similar_prices if p < this_price)
    percentile = (cheaper_count / len(similar_prices)) * 100

    Product.objects.filter(pk=product_id).update(
        price_percentile=round(percentile, 1),
        market_median_price=Decimal(str(round(market_median, 2))),
    )

    logger.info(
        'compute_price_intelligence: product %s — ₦%.0f vs median ₦%.0f (%.0f percentile).',
        product_id, this_price, market_median, percentile,
    )
    return True


def get_price_label(product) -> Optional[str]:
    """
    Returns a human-readable price intelligence label for display in templates.

    Usage in template:
        {% with label=product|price_label %}
          {% if label %}<span class="price-badge">{{ label }}</span>{% endif %}
        {% endwith %}

    Or call from view:
        context['price_label'] = get_price_label(product)
    """
    if product.price_percentile is None or product.market_median_price is None:
        return None

    p = product.price_percentile
    if p <= 20:
        return '🔥 Exceptional Deal'
    elif p <= 35:
        return '✅ Great Value'
    elif p <= 55:
        return '💰 Fair Price'
    elif p <= 75:
        return '⚠️ Slightly Above Average'
    else:
        return '📈 Premium Priced'


def _median(values: List[float]) -> float:
    n = len(values)
    if n == 0:
        return 0.0
    mid = n // 2
    if n % 2 == 0:
        return (values[mid - 1] + values[mid]) / 2
    return values[mid]


# ──────────────────────────────────────────────────────────────────────────────
#  ENGINE 5 — CROSS-SELL (Co-Purchase Graph)
# ──────────────────────────────────────────────────────────────────────────────

def update_cross_sell(order_id: str) -> int:
    """
    Called when an Order is COMPLETED.

    Algorithm:
      1. Find the purchased product A (from this order).
      2. Find all OTHER products the same buyer has previously purchased (B, C, D…).
      3. Increment co_occurrence for pairs (A,B), (A,C), (A,D) and vice-versa
         (bi-directional: if you bought A then B, next time you buy B you see A).
      4. Normalise co-occurrence counts to [0,1] and upsert ProductRecommendation
         rows with rec_type='cross_sell'.

    Returns the number of recommendation rows written/updated.
    """
    from marketplace.models import Order, ProductRecommendation

    try:
        order = Order.objects.select_related('buyer', 'product').get(pk=order_id)
    except Order.DoesNotExist:
        logger.warning('update_cross_sell: order %s not found.', order_id)
        return 0

    buyer = order.buyer
    product_a = order.product

    # All OTHER products this buyer has completed orders for (excluding current)
    co_bought_ids = list(
        Order.objects.filter(
            buyer=buyer,
            status=Order.Status.COMPLETED,
        )
        .exclude(pk=order_id)
        .values_list('product_id', flat=True)
        .distinct()
    )

    if not co_bought_ids:
        return 0

    # For each co-bought product B, count how many buyers purchased both A and B
    written = 0
    for product_b_id in co_bought_ids:
        # How many distinct users bought both A and B?
        co_count = (
            Order.objects.filter(product=product_a, status=Order.Status.COMPLETED)
            .filter(buyer__in=Order.objects.filter(
                product_id=product_b_id, status=Order.Status.COMPLETED
            ).values('buyer'))
            .values('buyer')
            .distinct()
            .count()
        )

        if co_count < 1:
            continue

        # Normalise: cap at 20 co-purchases for a score of 1.0
        score = min(1.0, co_count / 20.0)

        # Write A -> B
        _upsert_single_recommendation(
            rec_type='cross_sell',
            source_product_id=str(product_a.pk),
            recommended_id=str(product_b_id),
            score=score,
        )
        # Write B -> A (bi-directional)
        _upsert_single_recommendation(
            rec_type='cross_sell',
            source_product_id=str(product_b_id),
            recommended_id=str(product_a.pk),
            score=score,
        )
        written += 2

    logger.info(
        'update_cross_sell: wrote %d cross-sell recs for order %s.', written, order_id,
    )
    return written


# ──────────────────────────────────────────────────────────────────────────────
#  SHARED UPSERT HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def _upsert_recommendations(
    rec_type: str,
    source_product_id: Optional[str],
    pairs: List[Tuple[str, float]],
    user=None,
    user_id: Optional[int] = None,
) -> None:
    """
    Bulk-upsert ProductRecommendation rows for a list of (product_id, score) pairs.
    Uses update_or_create per row — acceptable for small top_k lists (8–12 rows).
    """
    from marketplace.models import ProductRecommendation

    effective_user_id = user_id or (user.pk if user else None)

    with transaction.atomic():
        for recommended_id, score in pairs:
            ProductRecommendation.objects.update_or_create(
                source_product_id=source_product_id,
                recommended_id=recommended_id,
                rec_type=rec_type,
                user_id=effective_user_id,
                defaults={'score': score},
            )


def _upsert_single_recommendation(
    rec_type: str,
    source_product_id: str,
    recommended_id: str,
    score: float,
    user_id: Optional[int] = None,
) -> None:
    """Single-row upsert for cross-sell engine."""
    from marketplace.models import ProductRecommendation

    ProductRecommendation.objects.update_or_create(
        source_product_id=source_product_id,
        recommended_id=recommended_id,
        rec_type=rec_type,
        user_id=user_id,
        defaults={'score': score},
    )
