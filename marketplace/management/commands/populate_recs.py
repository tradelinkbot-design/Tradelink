import sys
from django.core.management.base import BaseCommand
from django.utils import timezone
from marketplace.models import Product, ProductRecommendation, UserProductInteraction
from marketplace.service.recommendation_service import (
    compute_similar_products,
    compute_trending_scores,
    compute_price_intelligence,
    compute_personalised_feed
)
from jobs.service.text_encoder import text_encoder
from django.contrib.auth import get_user_model

class Command(BaseCommand):
    help = 'Populates the AI Recommendation Engine with initial data for local testing.'

    def handle(self, *args, **options):
        self.stdout.write("=== TradeLink AI Recommendation Backfill ===")

        active_products = Product.objects.filter(status=Product.Status.ACTIVE)
        count = active_products.count()
        self.stdout.write(f"Found {count} active products.")

        if count == 0:
            self.stdout.write("No active products found. Please create some products first.")
            return

        # 1. Generate Embeddings for all products
        self.stdout.write("\n[1/4] Generating product text embeddings...")
        updated = 0
        for product in active_products:
            text = product.get_embedding_text()
            if text.strip():
                emb = text_encoder.encode(text)
                product.text_embedding = emb
                product.text_embedding_updated = timezone.now()
                product.save(update_fields=['text_embedding', 'text_embedding_updated'])
                updated += 1
        self.stdout.write(self.style.SUCCESS(f"Generated embeddings for {updated} products."))

        # 2. Compute Similar Items (Engine 1)
        self.stdout.write("\n[2/4] Computing Similar Items (Engine 1)...")
        sim_count = 0
        for product in active_products:
            sim_count += compute_similar_products(str(product.id))
        self.stdout.write(self.style.SUCCESS(f"Created {sim_count} similar item pairings."))

        # 3. Compute Price Intelligence (Engine 4)
        self.stdout.write("\n[3/4] Computing Price Intelligence (Engine 4)...")
        price_count = 0
        for product in active_products:
            if compute_price_intelligence(str(product.id)):
                price_count += 1
        self.stdout.write(self.style.SUCCESS(f"Computed price intelligence for {price_count} products."))

        # 4. Compute Trending Scores (Engine 3)
        self.stdout.write("\n[4/4] Computing Trending Scores (Engine 3)...")
        User = get_user_model()
        first_user = User.objects.first()

        if first_user and active_products.exists():
            self.stdout.write("Creating some dummy interactions to populate trending/personal feeds...")
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
        self.stdout.write(self.style.SUCCESS(f"Updated trending scores for {trending_updated} products."))

        if first_user:
            personal_count = compute_personalised_feed(first_user.id)
            self.stdout.write(self.style.SUCCESS(f"Computed {personal_count} personalised recommendations for user {first_user.username}."))

        self.stdout.write("\n=== Backfill Complete ===")
        self.stdout.write("Refresh your browser to see the AI recommendations!")
