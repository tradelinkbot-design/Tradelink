"""
marketplace/tasks.py
=====================
Celery tasks for the TradeLink NG marketplace app.

Tasks
──────
  compute_product_embedding_task
      Encodes product text with the SAME sentence-transformer used by the
      jobs app (all-mpnet-base-v2, 768-dim). Reuses text_encoder singleton —
      the model is already loaded in memory, so this costs only ~30 ms.

  process_order_payout_task
      Releases seller funds via Paystack Transfer API after buyer confirms.

  auto_complete_orders_task
      Periodic task — auto-completes orders 7 days after buyer confirmation
      if no dispute is raised.

  expire_offers_task
      Periodic task — expires pending offers after 48 hours.
"""

import logging
from celery import shared_task

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
#  EMBEDDING
# ──────────────────────────────────────────────────────────────────────────────

@shared_task(
    bind=True,
    max_retries=3,
    acks_late=True,
    time_limit=120,
    soft_time_limit=90,
    ignore_result=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=120,
    retry_jitter=True,
)
def compute_product_embedding_task(self, product_id: str) -> None:
    """
    Encodes a Product's text with the sentence-transformer (768-dim)
    and saves it to Product.text_embedding.

    Uses the SAME text_encoder singleton as the jobs app —
    no second model load, no extra memory.

    Input text format:
        "{category} {condition}. {brand}. {title}. {description}"
    """
    from django.utils import timezone
    from marketplace.models import Product
    from jobs.service.text_encoder import text_encoder

    logger.info("Task: compute_product_embedding for %s", product_id)

    try:
        product = Product.objects.select_related('category').get(pk=product_id)
    except Product.DoesNotExist:
        logger.warning("compute_product_embedding: product %s not found.", product_id)
        return

    input_text = product.get_embedding_text()
    if not input_text.strip():
        logger.warning(
            "compute_product_embedding: product %s has no text to encode.", product_id
        )
        return

    logger.info(
        "Product %s — embedding input: %s…", product_id, input_text[:120]
    )

    embedding = text_encoder.encode(input_text)
    Product.objects.filter(pk=product_id).update(
        text_embedding=embedding,
        text_embedding_updated=timezone.now(),
    )
    logger.info("compute_product_embedding: saved embedding for %s.", product_id)

    # Chain: trigger recommendation engines now that embedding exists
    # Engine 1: find similar products (cosine similarity)
    compute_similar_products_task.delay(product_id)
    # Engine 4: compute price intelligence (market comparison)
    compute_price_intelligence_task.delay(product_id)


@shared_task(
    bind=True,
    max_retries=1,
    acks_late=False,
    ignore_result=False,
)
def encode_product_search_query_task(self, query: str) -> list[float]:
    """
    RPC task used by marketplace/service/search_service.py to offload
    PyTorch query encoding to the Celery worker process.

    This prevents the Daphne ASGI server from crashing on Windows due to
    PyTorch thread interactions — the exact same pattern used by the jobs
    app's encode_search_query_task.

    Returns a plain list of floats so Celery can serialise it as JSON.
    The caller converts it back to a numpy array for cosine similarity.
    """
    from jobs.service.text_encoder import text_encoder
    return text_encoder.encode(query.strip())


# ──────────────────────────────────────────────────────────────────────────────
#  PAYOUT
# ──────────────────────────────────────────────────────────────────────────────

@shared_task(
    bind=True,
    max_retries=3,
    acks_late=True,
    time_limit=60,
    soft_time_limit=45,
    ignore_result=True,
    retry_backoff=True,
    retry_backoff_max=120,
    retry_jitter=True,
)
def process_order_payout_task(self, order_id: str) -> None:
    """
    Async wrapper around release_order_to_seller().
    Called after buyer confirms receipt so payout doesn't block the HTTP request.
    """
    from marketplace.service.market_place_service_escrow import release_order_to_seller

    logger.info("Task: process_order_payout for %s", order_id)
    try:
        success = release_order_to_seller(order_id)
        if not success:
            raise RuntimeError(f"release_order_to_seller returned False for order {order_id}")
    except Exception as exc:
        logger.exception("Task: process_order_payout failed for %s", order_id)
        raise self.retry(exc=exc)


# ──────────────────────────────────────────────────────────────────────────────
#  PERIODIC TASKS
# ──────────────────────────────────────────────────────────────────────────────

@shared_task(ignore_result=True)
def auto_complete_orders_task() -> None:
    """
    Runs every hour via Celery Beat.
    Auto-completes orders where buyer confirmed receipt 7+ days ago
    and no dispute has been raised.

    Add to settings.py CELERY_BEAT_SCHEDULE:
        'auto-complete-orders': {
            'task': 'marketplace.tasks.auto_complete_orders_task',
            'schedule': crontab(minute=0),
        },
    """
    from django.utils import timezone
    from marketplace.models import Order
    from marketplace.service.market_place_service_escrow import release_order_to_seller

    now = timezone.now()
    orders = Order.objects.filter(
        status=Order.Status.CONFIRMED,
        auto_complete_at__lte=now,
    ).exclude(dispute__isnull=False)

    count = 0
    for order in orders:
        try:
            release_order_to_seller(str(order.pk))
            count += 1
        except Exception:
            logger.exception(
                "auto_complete_orders_task: failed for order %s", order.pk
            )

    logger.info("auto_complete_orders_task: auto-completed %d orders.", count)


@shared_task(ignore_result=True)
def expire_offers_task() -> None:
    """
    Runs every hour via Celery Beat.
    Expires pending offers older than 48 hours.

    Add to settings.py CELERY_BEAT_SCHEDULE:
        'expire-offers': {
            'task': 'marketplace.tasks.expire_offers_task',
            'schedule': crontab(minute=30),
        },
    """
    from django.utils import timezone
    from marketplace.models import Offer

    updated = Offer.objects.filter(
        status=Offer.Status.PENDING,
        expires_at__lt=timezone.now(),
    ).update(status=Offer.Status.EXPIRED)

    logger.info("expire_offers_task: expired %d offers.", updated)


@shared_task(ignore_result=True)
def recompute_all_product_embeddings_task() -> None:
    """
    Periodic maintenance task — re-encodes every active product.
    Run nightly via Celery Beat after a model upgrade.

    Add to settings.py CELERY_BEAT_SCHEDULE:
        'recompute-product-embeddings': {
            'task': 'marketplace.tasks.recompute_all_product_embeddings_task',
            'schedule': crontab(hour=3, minute=0),
        },
    """
    from marketplace.models import Product

    product_ids = list(
        Product.objects.filter(status=Product.Status.ACTIVE)
        .values_list('id', flat=True)
    )
    for pid in product_ids:
        compute_product_embedding_task.delay(str(pid))

    logger.info(
        "recompute_all_product_embeddings_task: queued %d tasks.", len(product_ids)
    )

# ──────────────────────────────────────────────────────────────────────────────
#  AI RECOMMENDATION TASKS
# ──────────────────────────────────────────────────────────────────────────────

@shared_task(
    bind=True,
    max_retries=3,
    acks_late=True,
    time_limit=120,
    soft_time_limit=90,
    ignore_result=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=120,
    retry_jitter=True,
)
def compute_similar_products_task(self, product_id: str) -> None:
    """
    Engine 1 — Similar Items.
    Computes cosine similarity between this product and all active products
    in the same category. Writes top-8 results to ProductRecommendation.

    Chained from compute_product_embedding_task on success.
    """
    from marketplace.service.recommendation_service import compute_similar_products

    logger.info('Task: compute_similar_products for %s', product_id)
    count = compute_similar_products(product_id)
    logger.info('Task: compute_similar_products wrote %d recs for %s', count, product_id)


@shared_task(
    bind=True,
    max_retries=3,
    acks_late=True,
    time_limit=120,
    soft_time_limit=90,
    ignore_result=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=120,
    retry_jitter=True,
)
def compute_personalised_feed_task(self, user_id: int) -> None:
    """
    Engine 2 — Personalised Feed.
    Builds a weighted taste-profile embedding from the user's interaction
    history and finds the top-12 most similar active products.

    Triggered by: offer created, order completed, nightly batch.
    """
    from marketplace.service.recommendation_service import compute_personalised_feed

    logger.info('Task: compute_personalised_feed for user %s', user_id)
    count = compute_personalised_feed(user_id)
    logger.info(
        'Task: compute_personalised_feed wrote %d recs for user %s', count, user_id
    )


@shared_task(ignore_result=True)
def compute_trending_task() -> None:
    """
    Engine 3 — Trending.
    Updates Product.trending_score for all active products using time-decayed
    interaction event weights over the last 7 days.

    Schedule: crontab(minute=0)  — every hour.
    """
    from marketplace.service.recommendation_service import compute_trending_scores

    logger.info('Task: compute_trending_scores starting.')
    updated = compute_trending_scores()
    logger.info('Task: compute_trending_scores updated %d products.', updated)


@shared_task(
    bind=True,
    max_retries=3,
    acks_late=True,
    ignore_result=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
)
def compute_price_intelligence_task(self, product_id: str) -> None:
    """
    Engine 4 — Price Intelligence.
    Computes price_percentile and market_median_price for a product by
    comparing its price to semantically similar products.

    Triggered by: product create, product price change.
    """
    from marketplace.service.recommendation_service import compute_price_intelligence

    logger.info('Task: compute_price_intelligence for %s', product_id)
    success = compute_price_intelligence(product_id)
    if success:
        logger.info('Task: compute_price_intelligence succeeded for %s', product_id)
    else:
        logger.debug(
            'Task: compute_price_intelligence skipped %s (no embedding or too few comparisons).',
            product_id,
        )


@shared_task(
    bind=True,
    max_retries=3,
    acks_late=True,
    ignore_result=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=120,
    retry_jitter=True,
)
def compute_cross_sell_task(self, order_id: str) -> None:
    """
    Engine 5 — Cross-Sell.
    Updates the co-purchase recommendation graph when an order completes.
    Writes bi-directional ProductRecommendation rows (rec_type='cross_sell').

    Triggered by: Order status -> COMPLETED (via signal).
    """
    from marketplace.service.recommendation_service import update_cross_sell

    logger.info('Task: compute_cross_sell for order %s', order_id)
    count = update_cross_sell(order_id)
    logger.info('Task: compute_cross_sell wrote %d recs for order %s', count, order_id)


@shared_task(ignore_result=True)
def recompute_all_personalised_feeds_task() -> None:
    """
    Nightly batch: refreshes personalised recommendations for every user who
    has interacted with a product in the last 30 days.

    Schedule: crontab(hour=1, minute=30)  — 1:30 AM daily.
    """
    from django.utils import timezone
    from datetime import timedelta
    from marketplace.models import UserProductInteraction

    cutoff = timezone.now() - timedelta(days=30)
    user_ids = list(
        UserProductInteraction.objects
        .filter(created_at__gte=cutoff)
        .values_list('user_id', flat=True)
        .distinct()
    )

    logger.info(
        'recompute_all_personalised_feeds_task: queuing %d user feed tasks.', len(user_ids)
    )
    for uid in user_ids:
        compute_personalised_feed_task.delay(uid)
