"""
Helper: append recommendation Celery tasks to marketplace/tasks.py
Run once from the project root: python append_tasks.py
"""

NEW_TASKS = '''

# ──────────────────────────────────────────────────────────────────────────────
#  AI RECOMMENDATION TASKS
# ──────────────────────────────────────────────────────────────────────────────

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
    ignore_result=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=120,
    retry_jitter=True,
)
def compute_personalised_feed_task(self, user_id: int) -> None:
    """
    Engine 2 — Personalised Feed.
    Builds a weighted taste-profile embedding from the user\'s interaction
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
    Writes bi-directional ProductRecommendation rows (rec_type=\'cross_sell\').

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
'''

target = 'marketplace/tasks.py'

with open(target, 'r', encoding='utf-8') as f:
    content = f.read()

if 'compute_similar_products_task' not in content:
    with open(target, 'a', encoding='utf-8') as f:
        f.write(NEW_TASKS)
    print('SUCCESS: recommendation tasks appended.')
else:
    print('SKIP: tasks already present.')
