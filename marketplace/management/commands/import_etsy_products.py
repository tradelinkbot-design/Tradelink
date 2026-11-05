"""
marketplace/management/commands/import_etsy_products.py
========================================================
Imports Etsy product data (scraped by Apify) into the TradeLink NG
marketplace database.

Accepts either an Apify dataset ID (fetched live) or a local JSON file.

Usage
─────
  # Pull live from Apify (recommended)
  python manage.py import_etsy_products DATASET_ID --apify-token YOUR_TOKEN

  # Token from environment variable (put APIFY_TOKEN=... in your .env)
  python manage.py import_etsy_products DATASET_ID

  # Local JSON file exported from Apify Console
  python manage.py import_etsy_products dataset.json

  # Fetch current USD → NGN rate automatically
  python manage.py import_etsy_products DATASET_ID --live-rate

  # First-time only: create the import bot seller account
  python manage.py import_etsy_products DATASET_ID --create-seller

  # Update existing products instead of skipping them
  python manage.py import_etsy_products DATASET_ID --update

  # Only import items within a price range (USD)
  python manage.py import_etsy_products DATASET_ID --min-price 10 --max-price 500

  # Full example
  python manage.py import_etsy_products DATASET_ID \\
      --live-rate                  \\
      --category "Woodworking Tools" \\
      --status active              \\
      --state Lagos                \\
      --lga "Lagos Island"         \\
      --max-items 100              \\
      --update                     \\
      --dry-run

Finding your Apify dataset ID
─────────────────────────────
  Apify Console → your actor run → Storage → Dataset
  The ID is the alphanumeric string in the URL, e.g.:
  https://console.apify.com/storage/datasets/abc123XYZabc123
                                              ^^^^^^^^^^^^^^ this

Finding your Apify API token
────────────────────────────
  Apify Console → Settings → Integrations → API token
  Or set APIFY_TOKEN=... in your .env to avoid passing it on every run.
"""

# ── Standard library ───────────────────────────────────────────────────────────
import html as html_lib
import json
import os
import re
import sys
import time
import uuid
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from urllib.parse import urlparse

# ── Third-party ────────────────────────────────────────────────────────────────
import requests
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

# ── Internal ───────────────────────────────────────────────────────────────────
from jobs.models import WorkerProfile
from marketplace.models import MarketplaceCategory, Product, ProductImage

User = get_user_model()


# ── Constants ──────────────────────────────────────────────────────────────────

IMPORT_BOT_USERNAME = "etsy_import_bot"
IMPORT_BOT_EMAIL    = "etsy-import-bot@tradelink.ng"
DEFAULT_CATEGORY    = "Woodworking Tools"
DEFAULT_EXCHANGE    = Decimal("1380.00")   # USD → NGN; update weekly or use --live-rate

APIFY_DATASET_URL   = "https://api.apify.com/v2/datasets/{dataset_id}/items"

# Two free exchange-rate sources — tried in order, first success wins
EXCHANGE_RATE_SOURCES = [
    ("https://api.exchangerate-api.com/v4/latest/USD", lambda d: d["rates"]["NGN"]),
    ("https://open.er-api.com/v6/latest/USD",          lambda d: d["rates"]["NGN"]),
]

IMAGE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.etsy.com/",
}
IMAGE_MAX_RETRIES = 3
IMAGE_RETRY_DELAY = 2  # seconds between retries

CONDITION_MAP = {
    "new":       Product.Condition.NEW,
    "used_good": Product.Condition.USED_GOOD,
    "used_fair": Product.Condition.USED_FAIR,
    "for_parts": Product.Condition.FOR_PARTS,
}

# Fields the Apify mapper can produce; we try all of them for price
RAW_PRICE_FIELDS = (
    "price", "priceUSD", "listingPrice", "currentPrice",
    "salePrice", "formattedPrice", "priceValue", "displayPrice",
    "cost", "amount",
)

# Fields the Apify mapper can produce; we try all of them for seller name
RAW_SELLER_FIELDS = (
    "shop_name", "sellerName", "shopName", "seller", "shop",
)

# Fields the mapper can produce; we try all of them for image lists
RAW_IMAGE_FIELDS = (
    "images", "imageUrls", "photos", "imagesList",
)


# ══════════════════════════════════════════════════════════════════════════════
# ── Pure helpers ──────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

def is_dataset_id(value: str) -> bool:
    """True if value is an Apify dataset ID (10–30 alphanumeric characters)."""
    return bool(re.fullmatch(r"[A-Za-z0-9]{10,30}", value))


def fetch_apify_dataset(dataset_id: str, token: str | None) -> list:
    """
    Fetch ALL items from an Apify dataset, automatically paginating
    for datasets with more than 1 000 items.
    """
    base_url = APIFY_DATASET_URL.format(dataset_id=dataset_id)
    items, offset, limit = [], 0, 1000

    print(f"  Fetching Apify dataset: {dataset_id}")
    while True:
        params = {"format": "json", "clean": "true",
                  "limit": str(limit), "offset": str(offset)}
        if token:
            params["token"] = token

        try:
            resp = requests.get(base_url, params=params, timeout=60)
        except requests.exceptions.RequestException as exc:
            raise CommandError(f"Network error fetching Apify dataset: {exc}")

        if resp.status_code == 401:
            raise CommandError(
                "Apify returned 401 Unauthorized.\n"
                "Pass --apify-token or set APIFY_TOKEN in your .env file."
            )
        if resp.status_code == 404:
            raise CommandError(
                f"Dataset '{dataset_id}' not found.\n"
                "Check the ID in Apify Console → Storage → Datasets."
            )
        if not resp.ok:
            raise CommandError(
                f"Apify API error {resp.status_code}: {resp.text[:200]}"
            )

        data  = resp.json()
        batch = (data if isinstance(data, list)
                 else data.get("items") or data.get("data") or [])

        if not isinstance(batch, list):
            raise CommandError("Unexpected response format from Apify API.")

        items.extend(batch)
        print(f"    …{len(items)} item(s) fetched")

        if len(batch) < limit:
            break   # last (or only) page
        offset += limit

    return items


def fetch_live_exchange_rate() -> Decimal:
    """
    Fetch the current USD → NGN rate from public free APIs.
    Tries two sources in order and falls back to DEFAULT_EXCHANGE on failure.
    """
    for url, getter in EXCHANGE_RATE_SOURCES:
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            rate = getter(resp.json())
            if rate and float(rate) > 0:
                return Decimal(str(rate)).quantize(Decimal("0.01"))
        except Exception:
            continue
    return DEFAULT_EXCHANGE


def to_ngn(usd_amount: float, rate: Decimal) -> Decimal:
    """Convert a USD float to NGN Decimal, rounded to 2 decimal places."""
    return (Decimal(str(usd_amount)) * rate).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def strip_html(text: str) -> str:
    """
    Convert an HTML description to clean plain text.
    Replaces block-level elements with newlines, strips all remaining tags,
    and decodes HTML entities (&amp; → &, &lt; → <, etc.).
    """
    if not text:
        return ""
    text = re.sub(r"<br\s*/?>",  "\n",   text, flags=re.IGNORECASE)
    text = re.sub(r"</p>",       "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</li>",      "\n",   text, flags=re.IGNORECASE)
    text = re.sub(r"</h[1-6]>",  "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>",    "",     text)
    text = html_lib.unescape(text)
    text = re.sub(r" {2,}",      " ",    text)
    text = re.sub(r"\n{3,}",     "\n\n", text)
    return text.strip()


def extract_price_usd(item: dict) -> float:
    """
    Multi-strategy extraction of a USD price from a raw Apify item dict.

    Strategy 1 — mapped output: uses price_usd our Apify mapper already
                  computed (fastest path; this works once the mapper is fixed).
    Strategy 2 — raw API fields: tries every known Etsy API field name,
                  handling plain numbers, cents integers, nested price objects,
                  and price strings like "$1,250.00" or "US$45".
    Strategy 3 — price_ngn fallback: if all else fails and price_ngn is
                  present, the caller derives price_usd from it using the rate.
    Strategy 4 — full scan: scans every string value in the item for a
                  "$X.XX"-style pattern.

    Returns 0.0 if no price can be found.
    """
    # Strategy 1: use already-mapped price_usd
    mapped = item.get("price_usd")
    if mapped is not None:
        try:
            val = float(mapped)
            if val > 0:
                return val
        except (TypeError, ValueError):
            pass

    # Strategy 2: raw Etsy API field names
    for key in RAW_PRICE_FIELDS:
        raw = item.get(key)
        if raw is None:
            continue

        # Plain number (possibly cents)
        if isinstance(raw, (int, float)) and raw > 0:
            return float(raw) / 100 if raw > 10_000 else float(raw)

        # Nested price object: { amount: 4500, divisor: 100, currency_code: "USD" }
        if isinstance(raw, dict):
            amt = raw.get("amount") or raw.get("value") or 0
            div = raw.get("divisor") or raw.get("divider") or 100
            try:
                val = float(amt) / float(div)
                if val > 0:
                    return val
            except (TypeError, ValueError):
                pass

        # Price string: "$45.00", "US$1,250", "From $29.99"
        if isinstance(raw, str):
            cleaned = re.sub(r"[^\d.]", "", raw)
            try:
                val = float(cleaned)
                if val > 0:
                    return val
            except ValueError:
                pass

    # Strategy 4: scan all string values for a "$X" pattern
    for val in item.values():
        if isinstance(val, str):
            m = re.search(r"\$\s*([\d,]+\.?\d*)", val)
            if m:
                try:
                    return float(m.group(1).replace(",", ""))
                except ValueError:
                    pass

    return 0.0


def extract_shop_name(item: dict) -> str:
    """
    Extract the shop/seller name, safely handling nested seller objects
    (some Apify actors return the seller as a dict instead of a string).
    """
    for key in RAW_SELLER_FIELDS:
        raw = item.get(key)
        if not raw:
            continue
        if isinstance(raw, dict):
            name = (raw.get("shopName") or raw.get("name") or
                    raw.get("login") or raw.get("id") or "")
            return str(name).strip()[:100]
        result = str(raw).strip()
        if result and result.lower() not in {"none", "null", "[object object]"}:
            return result[:100]
    return ""


def extract_images(item: dict) -> list[str]:
    """
    Return up to 5 image URLs, handling arrays of plain strings or
    image-info objects (various Apify actor output formats).
    """
    for key in RAW_IMAGE_FIELDS:
        raw = item.get(key)
        if not raw or not isinstance(raw, list):
            continue
        urls = []
        for img in raw:
            if isinstance(img, str) and img:
                urls.append(img)
            elif isinstance(img, dict):
                url = (
                    img.get("url_fullxfull") or img.get("url_570xN") or
                    img.get("url") or img.get("src") or img.get("href") or ""
                )
                if url:
                    urls.append(url)
        if urls:
            return urls[:5]
    return []


def extract_tags(item: dict) -> list[str]:
    """Extract tags, handling both list and CSV-string formats."""
    raw = item.get("tags") or item.get("keywords") or []
    if isinstance(raw, list):
        return [str(t).strip() for t in raw if t]
    if isinstance(raw, str) and raw:
        return [t.strip() for t in raw.split(",") if t.strip()]
    return []


def download_image(url: str) -> ContentFile | None:
    """Download an image with exponential back-off on failure."""
    for attempt in range(1, IMAGE_MAX_RETRIES + 1):
        try:
            resp = requests.get(url, headers=IMAGE_HEADERS, timeout=20)
            resp.raise_for_status()
            if not resp.headers.get("content-type", "").startswith("image/"):
                return None
            return ContentFile(resp.content)
        except Exception:
            if attempt < IMAGE_MAX_RETRIES:
                time.sleep(IMAGE_RETRY_DELAY * attempt)
    return None


def image_ext_from_url(url: str) -> str:
    """Derive a safe file extension from an image URL."""
    ext = os.path.splitext(urlparse(url).path)[-1].lstrip(".").lower()
    return ext if ext in {"jpg", "jpeg", "png", "webp", "gif"} else "jpg"


def _fresh_stats() -> dict:
    return {
        "created": 0, "updated": 0, "skipped": 0, "errors": 0,
        # Detailed skip reasons
        "no_title": 0, "no_price": 0, "price_filtered": 0, "duplicate": 0,
        # Images
        "images_saved": 0, "images_failed": 0,
    }


# ══════════════════════════════════════════════════════════════════════════════
# ── Management command ────────────────────────════════════════════════════════
# ══════════════════════════════════════════════════════════════════════════════

class Command(BaseCommand):
    help = (
        "Import Etsy product listings (from Apify) into the TradeLink marketplace. "
        "Pass an Apify dataset ID or a local JSON file path."
    )

    # ── Arguments ──────────────────────────────────────────────────────────────

    def add_arguments(self, parser):
        parser.add_argument(
            "source",
            help=(
                "Apify dataset ID (10–30 alphanumeric chars) "
                "OR path to a local JSON file exported from Apify Console."
            ),
        )
        parser.add_argument(
            "--apify-token",
            default=None,
            metavar="TOKEN",
            help=(
                "Apify API token. Falls back to the APIFY_TOKEN "
                "environment variable if omitted."
            ),
        )

        # ── Exchange rate ───────────────────────────────────────────────────
        rate_group = parser.add_mutually_exclusive_group()
        rate_group.add_argument(
            "--live-rate",
            action="store_true",
            help="Fetch the current USD → NGN rate automatically (recommended).",
        )
        rate_group.add_argument(
            "--exchange-rate",
            type=float,
            default=float(DEFAULT_EXCHANGE),
            metavar="RATE",
            help=f"Manual USD → NGN rate. Default: {DEFAULT_EXCHANGE}",
        )

        # ── Seller / category ───────────────────────────────────────────────
        parser.add_argument(
            "--seller-username",
            default=IMPORT_BOT_USERNAME,
            metavar="USERNAME",
            help=f"WorkerProfile username to list products under. Default: {IMPORT_BOT_USERNAME}",
        )
        parser.add_argument(
            "--create-seller",
            action="store_true",
            help="Create the import bot User + WorkerProfile if missing. Run once.",
        )
        parser.add_argument(
            "--category",
            default=DEFAULT_CATEGORY,
            metavar="NAME",
            help=f"MarketplaceCategory name. Default: '{DEFAULT_CATEGORY}'",
        )

        # ── Product defaults ────────────────────────────────────────────────
        parser.add_argument(
            "--status",
            choices=[s.value for s in Product.Status],
            default=Product.Status.DRAFT,
            help="Product status after import. Default: draft",
        )
        parser.add_argument(
            "--state",
            default="",
            metavar="STATE",
            help="Nigerian state for all imported products (e.g. 'Lagos').",
        )
        parser.add_argument(
            "--lga",
            default="",
            metavar="LGA",
            help="LGA within the state (e.g. 'Lagos Island').",
        )
        parser.add_argument(
            "--pickup-notes",
            default="Pickup location TBC — seller will confirm.",
            metavar="TEXT",
            help="Pickup notes shown to buyers.",
        )

        # ── Filtering ───────────────────────────────────────────────────────
        parser.add_argument(
            "--max-items",
            type=int,
            default=None,
            metavar="N",
            help="Maximum number of items to process (useful for testing).",
        )
        parser.add_argument(
            "--min-price",
            type=float,
            default=0.0,
            metavar="USD",
            help="Skip items cheaper than this USD amount.",
        )
        parser.add_argument(
            "--max-price",
            type=float,
            default=None,
            metavar="USD",
            help="Skip items more expensive than this USD amount.",
        )

        # ── Behaviour flags ─────────────────────────────────────────────────
        parser.add_argument(
            "--update",
            action="store_true",
            help=(
                "Update price, title, and description of already-imported "
                "products instead of skipping them."
            ),
        )
        parser.add_argument(
            "--skip-images",
            action="store_true",
            help="Skip all image downloads.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview all changes without writing anything to the database.",
        )

    # ── Entry point ────────────────────────────────────────────────────────────

    def handle(self, *args, **options):
        self._opts = options
        source      = options["source"]
        apify_token = options["apify_token"] or os.environ.get("APIFY_TOKEN")
        dry_run     = options["dry_run"]

        if dry_run:
            self.stdout.write(self.style.WARNING(
                "⚠  DRY RUN — nothing will be written to the database.\n"
            ))

        # 1. Exchange rate ──────────────────────────────────────────────────────
        if options["live_rate"]:
            exchange_rate = fetch_live_exchange_rate()
            self.stdout.write(
                self.style.SUCCESS(f"  Live USD → NGN rate: ₦{exchange_rate:,.2f}")
            )
        else:
            exchange_rate = Decimal(str(options["exchange_rate"]))
            self.stdout.write(f"  USD → NGN rate: ₦{exchange_rate:,.2f} (manual)")

        # 2. Load data ──────────────────────────────────────────────────────────
        if is_dataset_id(source):
            self.stdout.write(f"  Source: Apify dataset → {source}")
            data = fetch_apify_dataset(source, apify_token)
        else:
            path = Path(source)
            if not path.exists():
                raise CommandError(
                    f"'{source}' is not a valid Apify dataset ID "
                    f"and no file was found at that path."
                )
            self.stdout.write(f"  Source: local file → {path.name}")
            with path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, list):
                raise CommandError("JSON file must contain a top-level array.")

        total_raw = len(data)
        if options["max_items"]:
            data = data[: options["max_items"]]
        self.stdout.write(
            f"  Loaded {total_raw} item(s) — processing {len(data)}\n"
        )

        # 3. Seller + category ─────────────────────────────────────────────────
        seller   = self._get_or_create_seller(dry_run)
        category = self._get_or_create_category(dry_run)

        # 4. Import loop ────────────────────────────────────────────────────────
        stats = _fresh_stats()

        for idx, item in enumerate(data, 1):
            self._log_progress(idx, len(data), stats)
            try:
                self._import_item(item, seller, category, exchange_rate, stats, dry_run)
            except Exception as exc:
                stats["errors"] += 1
                title = str(item.get("title") or item.get("name") or "<no title>")[:60]
                self.stderr.write(
                    self.style.ERROR(f"\n  ✗ ERROR — '{title}': {exc}")
                )

        # 5. Summary ───────────────────────────────────────────────────────────
        self._print_summary(stats, exchange_rate, dry_run)

    # ── Seller resolution ──────────────────────────────────────────────────────

    def _get_or_create_seller(self, dry_run: bool):
        username = self._opts["seller_username"]
        create   = self._opts["create_seller"]

        try:
            return WorkerProfile.objects.select_related("user").get(
                user__username=username
            )
        except WorkerProfile.DoesNotExist:
            pass

        if not create:
            raise CommandError(
                f'\nWorkerProfile for "{username}" does not exist.\n'
                f"Run once with --create-seller to create the import-bot account:\n\n"
                f"  python manage.py import_etsy_products {sys.argv[-1]} --create-seller\n"
            )

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f"[DRY RUN] Would create import-bot seller: {username}"
            ))
            return None

        user, user_created = User.objects.get_or_create(
            username=username,
            defaults={
                "email":      IMPORT_BOT_EMAIL,
                "first_name": "Etsy",
                "last_name":  "Import Bot",
                "is_active":  True,
            },
        )
        if user_created:
            user.set_unusable_password()
            user.save()
            self.stdout.write(f"  Created User: {username}")

        worker, wp_created = WorkerProfile.objects.get_or_create(
            user=user, defaults={}
        )
        if wp_created:
            self.stdout.write(
                self.style.SUCCESS(f"  Created WorkerProfile: {username}")
            )
        return worker

    # ── Category resolution ────────────────────────────────────────────────────

    def _get_or_create_category(self, dry_run: bool):
        name = self._opts["category"]

        if dry_run:
            cat = MarketplaceCategory.objects.filter(name=name).first()
            if not cat:
                self.stdout.write(self.style.WARNING(
                    f'[DRY RUN] Would create category: "{name}"'
                ))
            return cat

        cat, created = MarketplaceCategory.objects.get_or_create(
            name=name,
            defaults={
                "slug":          slugify(name),
                "description":   f"Tools and equipment for {name.lower()}.",
                "icon_class":    "fas fa-hammer",
                "is_active":     True,
                "display_order": 10,
            },
        )
        if created:
            self.stdout.write(
                self.style.SUCCESS(f'  Created category: "{name}"')
            )
        return cat

    # ── Single item import ─────────────────────────────────────────────────────

    def _import_item(
        self, item: dict, seller, category, exchange_rate: Decimal,
        stats: dict, dry_run: bool,
    ) -> None:
        opts = self._opts

        # ── Title ──────────────────────────────────────────────────────────────
        title = strip_html(
            str(item.get("title") or item.get("name") or "").strip()
        )
        if not title:
            stats["no_title"] += 1
            stats["skipped"]  += 1
            self.stdout.write(
                f"  [SKIP] No title — {str(item.get('etsy_url', ''))[:80]}"
            )
            return

        # ── Price ──────────────────────────────────────────────────────────────
        price_usd = extract_price_usd(item)

        # Last-resort: derive from price_ngn if the mapper stored it
        if price_usd <= 0:
            raw_ngn = item.get("price_ngn")
            if raw_ngn:
                try:
                    ngn_val = float(raw_ngn)
                    if ngn_val > 0:
                        price_usd = ngn_val / float(exchange_rate)
                except (TypeError, ValueError):
                    pass

        if price_usd <= 0:
            stats["no_price"] += 1
            stats["skipped"]  += 1
            self.stdout.write(f"  [SKIP] No price — {title[:60]}")
            return

        # Price range filter
        if price_usd < opts["min_price"]:
            stats["price_filtered"] += 1
            stats["skipped"]        += 1
            return
        if opts["max_price"] is not None and price_usd > opts["max_price"]:
            stats["price_filtered"] += 1
            stats["skipped"]        += 1
            return

        # ── Other fields ───────────────────────────────────────────────────────
        etsy_url   = str(item.get("etsy_url") or "").split("?")[0]
        listing_id = str(item.get("etsy_listing_id") or "")
        shop_name  = extract_shop_name(item)
        condition  = CONDITION_MAP.get(
            item.get("condition", "new"), Product.Condition.NEW
        )
        images = extract_images(item)
        tags   = extract_tags(item)
        rating = item.get("rating") or item.get("stars")

        # Build a clean, structured description
        raw_desc   = str(item.get("description") or "").strip()
        clean_desc = strip_html(raw_desc)

        parts = [clean_desc]
        if shop_name:
            parts.append(f"Sold by: {shop_name}")
        if tags:
            parts.append("Tags: " + ", ".join(tags))
        if rating:
            parts.append(f"Rating: {rating}/5 ★")
        if etsy_url:
            parts.append(f"[Etsy listing: {etsy_url}]")

        full_description = "\n\n".join(p for p in parts if p).strip()
        if not full_description:
            full_description = (
                f"Handcrafted woodworking tool — imported from Etsy."
                + (f"\n\n[Etsy listing: {etsy_url}]" if etsy_url else "")
            )

        price_ngn = to_ngn(price_usd, exchange_rate)

        # ── Duplicate detection ────────────────────────────────────────────────
        existing = None
        if etsy_url:
            existing = Product.objects.filter(
                description__contains=etsy_url
            ).first()
        if existing is None and listing_id:
            existing = Product.objects.filter(
                description__contains=listing_id
            ).first()

        # ── UPDATE existing product ────────────────────────────────────────────
        if existing:
            if not opts["update"]:
                stats["duplicate"] += 1
                stats["skipped"]   += 1
                self.stdout.write(f"  [DUP]  {title[:60]}")
                return

            if dry_run:
                self.stdout.write(
                    f"  [DRY-UPDATE] {title[:60]}\n"
                    f"               ${price_usd:.2f} → ₦{price_ngn:,.2f}"
                )
                stats["updated"] += 1
                return

            existing.title       = title[:200]
            existing.description = full_description
            existing.price       = price_ngn
            existing.brand       = shop_name
            existing.condition   = condition
            existing.save(update_fields=[
                "title", "description", "price", "brand", "condition"
            ])
            self.stdout.write(
                f"  [UPDATED] {existing.title[:55]} — ₦{price_ngn:,.2f}"
            )
            stats["updated"] += 1
            return

        # ── DRY RUN preview ────────────────────────────────────────────────────
        if dry_run:
            self.stdout.write(
                f"  [DRY-CREATE] {title[:60]}\n"
                f"               ${price_usd:.2f} → ₦{price_ngn:,.2f} | "
                f"shop={shop_name or 'N/A'} | "
                f"cond={condition} | imgs={len(images)} | tags={len(tags)}"
            )
            stats["created"] += 1
            return

        # ── CREATE new product ─────────────────────────────────────────────────
        with transaction.atomic():
            product = Product.objects.create(
                seller          = seller,
                category        = category,
                title           = title[:200],
                description     = full_description,
                condition       = condition,
                brand           = shop_name,
                price           = price_ngn,
                offers_allowed  = True,
                state           = opts["state"],
                lga             = opts["lga"],
                pickup_only     = True,
                pickup_notes    = opts["pickup_notes"],
                status          = opts["status"],
                slots           = 1,
            )

            img_saved = img_failed = 0
            if not opts["skip_images"] and images:
                img_saved, img_failed = self._save_images(
                    product, images, listing_id
                )
            stats["images_saved"]  += img_saved
            stats["images_failed"] += img_failed

        self.stdout.write(
            f"  [OK]  {product.title[:55]} — ₦{price_ngn:,.2f}"
            + (f" | {img_saved} img(s)" if img_saved else "")
        )
        stats["created"] += 1

    # ── Image downloader ───────────────────────────────────────────────────────

    def _save_images(
        self, product, image_urls: list, listing_id: str
    ) -> tuple[int, int]:
        saved = failed = 0
        for order, url in enumerate(image_urls):
            if not url:
                continue
            content = download_image(url)
            if not content:
                self.stderr.write(f"    [IMG-FAIL] {url[:80]}")
                failed += 1
                continue
            ext      = image_ext_from_url(url)
            filename = f"etsy_{listing_id or uuid.uuid4().hex[:8]}_{order}.{ext}"
            pi = ProductImage(
                product       = product,
                caption       = f"{product.title[:80]} — image {order + 1}",
                display_order = order,
            )
            pi.image.save(filename, content, save=True)
            saved += 1
        return saved, failed

    # ── Progress ticker ────────────────────────────────────────────────────────

    def _log_progress(self, idx: int, total: int, stats: dict) -> None:
        if idx % 10 == 0 or idx == total:
            self.stdout.write(
                f"  Progress [{idx}/{total}]  "
                f"✓{stats['created']}  ↺{stats['updated']}  "
                f"–{stats['skipped']}  ✗{stats['errors']}"
            )

    # ── Summary report ─────────────────────────────────────────────────────────

    def _print_summary(
        self, stats: dict, exchange_rate: Decimal, dry_run: bool
    ) -> None:
        verb = "Would create" if dry_run else "Created"
        w    = self.stdout.write
        sep  = "─" * 60

        w("\n" + sep)
        w(self.style.SUCCESS(
            f"  {verb}:              {stats['created']}"
        ))
        if stats["updated"]:
            w(self.style.SUCCESS(f"  Updated:              {stats['updated']}"))

        total_skipped = stats["skipped"]
        if total_skipped:
            w(f"  Skipped:              {total_skipped}")
            if stats["duplicate"]:
                w(f"    └ duplicates:       {stats['duplicate']}")
            if stats["no_price"]:
                w(f"    └ no price found:   {stats['no_price']}")
            if stats["no_title"]:
                w(f"    └ no title:         {stats['no_title']}")
            if stats["price_filtered"]:
                w(f"    └ price filter:     {stats['price_filtered']}")

        if stats["errors"]:
            w(self.style.ERROR(f"  Errors:               {stats['errors']}"))

        total_imgs = stats["images_saved"] + stats["images_failed"]
        if total_imgs:
            w(
                f"  Images:               "
                f"{stats['images_saved']} saved, "
                f"{stats['images_failed']} failed"
            )

        w(f"  Exchange rate used:   ₦{exchange_rate:,.2f} / USD")
        w(sep + "\n")