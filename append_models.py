"""
Helper: append UserProductInteraction + ProductRecommendation to marketplace/models.py
Run once from the project root: python append_models.py
"""

NEW_CODE = """

# ──────────────────────────────────────────────────────────────────────────────
#  9.  USER PRODUCT INTERACTION
#      Event log powering personalised recommendations.
# ──────────────────────────────────────────────────────────────────────────────

class UserProductInteraction(models.Model):
    \"\"\"
    An interaction event between a user and a product listing.

    Event weights used by Engine 2 (Personalised Feed):
        view     ->  1.0  (weak signal - user browsed)
        save     ->  3.0  (moderate - explicit interest)
        chat     ->  4.0  (strong - reached out to seller)
        offer    ->  5.0  (strong - purchase intent)
        purchase -> 10.0  (strongest - completed transaction)
    \"\"\"

    class EventType(models.TextChoices):
        VIEW     = 'view',     'Viewed'
        SAVE     = 'save',     'Saved / Bookmarked'
        OFFER    = 'offer',    'Made Offer'
        PURCHASE = 'purchase', 'Purchased'
        CHAT     = 'chat',     'Started Chat'

    EVENT_WEIGHTS = {
        'view':     1.0,
        'save':     3.0,
        'offer':    5.0,
        'purchase': 10.0,
        'chat':     4.0,
    }

    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user       = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='product_interactions',
    )
    product    = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='user_interactions',
    )
    event_type = models.CharField(max_length=20, choices=EventType.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes  = [
            models.Index(fields=['user', 'event_type', '-created_at']),
            models.Index(fields=['product', 'event_type']),
        ]

    def __str__(self):
        return f'{self.user.username} [{self.event_type}] {self.product.title}'


# ──────────────────────────────────────────────────────────────────────────────
#  10. PRODUCT RECOMMENDATION
#      Pre-computed recommendation cache - mirrors CLIPMatch from jobs app.
#      Populated by Celery background tasks; read instantly by views.
#
#  Query patterns:
#    Similar items:
#      ProductRecommendation.objects
#          .filter(source_product=product, rec_type='similar')
#          .select_related('recommended__seller__user')
#          .prefetch_related('recommended__images')
#          .order_by('-score')[:8]
#
#    Personalised feed:
#      ProductRecommendation.objects
#          .filter(user=request.user, rec_type='personal')
#          .order_by('-score')[:12]
#
#    Cross-sell:
#      ProductRecommendation.objects
#          .filter(source_product=product, rec_type='cross_sell')
#          .order_by('-score')[:6]
# ──────────────────────────────────────────────────────────────────────────────

class ProductRecommendation(models.Model):
    \"\"\"
    A pre-computed recommendation pairing.

    rec_type values and their engine:
        'similar'    - Engine 1: cosine similarity between product embeddings
        'personal'   - Engine 2: personalised feed based on user history
        'trending'   - Engine 3: time-decayed popularity (source_product=None)
        'cross_sell' - Engine 5: co-purchase co-occurrence graph
    \"\"\"

    class RecommendationType(models.TextChoices):
        SIMILAR    = 'similar',    'Similar Items'
        PERSONAL   = 'personal',   'Personalised For User'
        TRENDING   = 'trending',   'Trending'
        CROSS_SELL = 'cross_sell', 'Cross-Sell'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # The anchor product (None for trending - they have no single source)
    source_product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='recommendations_as_source',
    )

    # The product being recommended
    recommended = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='recommendations_as_target',
    )

    rec_type = models.CharField(
        max_length=20,
        choices=RecommendationType.choices,
        db_index=True,
    )

    # For personalised recs only - the user this rec was computed for
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='product_recommendations',
    )

    # Recommendation strength 0.0-1.0. Higher = stronger match.
    score = models.FloatField(
        default=0.0,
        help_text='Recommendation strength 0-1. Higher = stronger.',
    )

    computed_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-score']
        indexes  = [
            models.Index(fields=['source_product', 'rec_type', '-score']),
            models.Index(fields=['user', 'rec_type', '-score']),
            models.Index(fields=['rec_type', '-score']),
        ]

    def __str__(self):
        if self.user:
            return (
                f'[{self.rec_type}] For {self.user.username}: '
                f'{self.recommended.title} ({self.score:.3f})'
            )
        src = self.source_product.title[:30] if self.source_product else 'global'
        return f'[{self.rec_type}] {src} -> {self.recommended.title} ({self.score:.3f})'
"""

target = 'marketplace/models.py'

with open(target, 'r', encoding='utf-8') as f:
    content = f.read()

# Only append if not already present (idempotent)
if 'class UserProductInteraction' not in content:
    with open(target, 'a', encoding='utf-8') as f:
        f.write(NEW_CODE)
    print('SUCCESS: models appended.')
else:
    print('SKIP: models already present.')
