"""
Script to manually populate the AI Recommendation Engine for local testing.
Run with: py manage.py shell < populate_recs.py  (or python manage.py shell < populate_recs.py)
"""
import sys
from django.utils import timezone
from marketplace.models import Product, ProductRecommendation, UserProductInteraction
from marketplace.service.recommendation_service import (
    compute_similar_products,
    compute_trending_scores,
    compute_price_intelligence,
    compute_personalised_feed
)
from jobs.service.text_encoder import text_encoder

print("=== TradeLink AI Recommendation Backfill ===")

active_products = Product.objects.filter(status=Product.Status.ACTIVE)
count = active_products.count()
print(f"Found {count} active products.")

if count == 0:
    print("No active products found. Please create some products first.")
    sys.exit(0)

# 1. Generate Embeddings for all products
print("\n[1/4] Generating product text embeddings...")
updated = 0
for product in active_products:
    text = product.get_embedding_text()
    if text.strip():
        emb = text_encoder.encode(text)
        product.text_embedding = emb
        product.text_embedding_updated = timezone.now()
        product.save(update_fields=['text_embedding', 'text_embedding_updated'])
        updated += 1
print(f"✅ Generated embeddings for {updated} products.")

# 2. Compute Similar Items (Engine 1)
print("\n[2/4] Computing Similar Items (Engine 1)...")
sim_count = 0
for product in active_products:
    sim_count += compute_similar_products(str(product.id))
print(f"✅ Created {sim_count} similar item pairings.")

# 3. Compute Price Intelligence (Engine 4)
print("\n[3/4] Computing Price Intelligence (Engine 4)...")
price_count = 0
for product in active_products:
    if compute_price_intelligence(str(product.id)):
        price_count += 1
print(f"✅ Computed price intelligence for {price_count} products.")

# 4. Compute Trending Scores (Engine 3)
# To make things trend, we need some fake interactions.
print("\n[4/4] Computing Trending Scores (Engine 3)...")
from django.contrib.auth import get_user_model
User = get_user_model()
first_user = User.objects.first()

if first_user and active_products.exists():
    print("Creating some dummy interactions to populate trending/personal feeds...")
    for product in active_products[:5]:
        UserProductInteraction.objects.create(
            user=first_user,
            product=product,
            event_type=UserProductInteraction.EventType.VIEW
        )
        UserProductInteraction.objects.create(
            user=first_user,
            product=product,
            event_type=UserProductInteraction.EventType.SAVE
        )

trending_updated = compute_trending_scores()
print(f"✅ Updated trending scores for {trending_updated} products.")

if first_user:
    personal_count = compute_personalised_feed(first_user.id)
    print(f"✅ Computed {personal_count} personalised recommendations for user {first_user.username}.")

print("\n=== Backfill Complete ===")
print("Refresh your browser to see the AI recommendations!")
