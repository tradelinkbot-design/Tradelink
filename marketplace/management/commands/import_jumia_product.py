"""
marketplace/management/commands/import_jumia_products.py
========================================================
Imports Jumia Nigeria product data (scraped by Apify) into the TradeLink NG
marketplace database.

Accepts either an Apify dataset ID (fetched live) or a local JSON file.
Handles output from BOTH Jumia scrapers on Apify automatically — no config
needed, format is detected at runtime:
  • microworlds~jumia-scraper          — nested "product" key structure
  • 123webdata/jumia-nigeria-scraper   — flat structure, NGN integer prices

Usage
─────
  # Pull live from Apify (recommended)
  python manage.py import_jumia_products DATASET_ID --apify-token YOUR_TOKEN

  # Token from environment variable (put APIFY_TOKEN=... in your .env)
  python manage.py import_jumia_products DATASET_ID

  # Local JSON file exported from Apify Console
  python manage.py import_jumia_products dataset.json

  # First-time only: create the import bot seller account
  python manage.py import_jumia_products DATASET_ID --create-seller

  # Update existing products instead of skipping them
  python manage.py import_jumia_products DATASET_ID --update

  # Only import items within a price range (NGN)
  python manage.py import_jumia_products DATASET_ID --min-price 5000 --max-price 500000

  # Only import in-stock items, auto-detect their category
  python manage.py import_jumia_products DATASET_ID --in-stock-only --auto-category

  # Full example
  python manage.py import_jumia_products DATASET_ID \\
      --auto-category              \\
      --status active              \\
      --state Lagos                \\
      --lga "Lagos Island"         \\
      --max-items 200              \\
      --in-stock-only              \\
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

IMPORT_BOT_USERNAME = "jumia_import_bot"
IMPORT_BOT_EMAIL    = "jumia-import-bot@tradelink.ng"
DEFAULT_CATEGORY    = "Hand Tools"

APIFY_DATASET_URL = "https://api.apify.com/v2/datasets/{dataset_id}/items"

IMAGE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    # Jumia serves images from ng.jumia.is — this referer prevents hotlink blocks
    "Referer": "https://www.jumia.com.ng/",
}
IMAGE_MAX_RETRIES = 3
IMAGE_RETRY_DELAY = 2  # seconds between retries

# Maps lowercased Jumia category strings → our MarketplaceCategory.name.
# Used when --auto-category is passed. Partial substring matching also runs
# as a fallback, so "power tools & accessories" still maps to "Power Tools".
JUMIA_CATEGORY_MAP: dict[str, str] = {
    # Power Tools
    "power tools":             "Power Tools",
    "power & hand tools":      "Power Tools",
    "power tool sets":         "Power Tools",
    "cordless tools":          "Power Tools",
    "drills":                  "Power Tools",
    "angle grinders":          "Power Tools",
    "generators":              "Power Tools",
    "inverters":               "Power Tools",
    "generators & inverters":  "Power Tools",
    # Hand Tools
    "hand tools":              "Hand Tools",
    "tool sets":               "Hand Tools",
    "tool box":                "Hand Tools",
    "tool boxes":              "Hand Tools",
    "wrenches":                "Hand Tools",
    "spanners":                "Hand Tools",
    "screwdrivers":            "Hand Tools",
    "hammers":                 "Hand Tools",
    "pliers":                  "Hand Tools",
    "chisels":                 "Hand Tools",
    # Electrical
    "electrical":              "Electrical Equipment",
    "electrician tools":       "Electrical Equipment",
    "electrical equipment":    "Electrical Equipment",
    "cables & wires":          "Electrical Equipment",
    "circuit breakers":        "Electrical Equipment",
    # Plumbing
    "plumbing":                "Plumbing Supplies",
    "plumbing supplies":       "Plumbing Supplies",
    "pipes & fittings":        "Plumbing Supplies",
    # Safety Gear
    "safety":                  "Safety Gear",
    "safety equipment":        "Safety Gear",
    "safety helmets":          "Safety Gear",
    "safety gloves":           "Safety Gear",
    "safety boots":            "Safety Gear",
    "ppe":                     "Safety Gear",
    # Woodworking
    "woodworking":             "Woodworking Tools",
    "woodworking tools":       "Woodworking Tools",
    "saws":                    "Woodworking Tools",
    # Measuring
    "measuring tools":         "Measuring Instruments",
    "measuring instruments":   "Measuring Instruments",
    "levels":                  "Measuring Instruments",
    "tape measures":           "Measuring Instruments",
    # Materials
    "building materials":      "Materials",
    "construction materials":  "Materials",
    "nails & screws":          "Materials",
    "fasteners":               "Materials",
}


# ══════════════════════════════════════════════════════════════════════════════
# ── Pure helpers ──────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

def is_dataset_id(value: str) -> bool:
    """True if value looks like an Apify dataset ID (10–30 alphanumeric chars)."""
    return bool(re.fullmatch(r"[A-Za-z0-9]{10,30}", value))


def _parse_ngn_price(value) -> Decimal | None:
    """
    Parse a Jumia price that may arrive in several shapes:
      - Clean decimal string:    "1499.00"
      - Formatted NGN string:    "₦ 1,499" or "₦1,499.00"
      - Integer/float already in NGN: 99991
    Returns None if no valid positive value is extractable.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)) and value > 0:
        return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if isinstance(value, str):
        cleaned = re.sub(r"[₦\s,]", "", value.strip())
        try:
            val = Decimal(cleaned)
            if val > 0:
                return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except Exception:
            pass
    return None


def _parse_discount(value) -> int | None:
    """Parse a discount string like '70%' → 70. Returns None if unparseable."""
    if not value:
        return None
    m = re.search(r"(\d+)", str(value))
    return int(m.group(1)) if m else None


# ── Format detection & normalisation ──────────────────────────────────────────

def normalize_item(raw: dict) -> dict:
    """
    Normalize a raw Apify item from EITHER Jumia scraper into a uniform dict.

    Format A — microworlds~jumia-scraper:
        Has a top-level "product" key; prices are nested objects; tags are
        a pipe-separated string of internal codes.

    Format B — 123webdata/jumia-nigeria-scraper:
        Flat; price is an NGN integer; images is a plain URL list;
        may include a full description string and breadcrumbs.
    """
    if "product" in raw and isinstance(raw.get("product"), dict):
        return _normalize_format_a(raw)
    return _normalize_format_b(raw)


def _normalize_format_a(raw: dict) -> dict:
    """microworlds~jumia-scraper — nested product.{} structure."""
    p      = raw["product"]
    prices = p.get("prices") or {}

    # rawPrice is a clean "1499.00" string; fall back to the display price
    price_ngn     = (_parse_ngn_price(prices.get("rawPrice"))
                     or _parse_ngn_price(prices.get("price")))
    old_price_ngn = _parse_ngn_price(prices.get("oldPrice"))
    discount_pct  = _parse_discount(prices.get("discount"))

    # Images may be under several keys depending on scraper version
    raw_imgs = (p.get("images") or p.get("imageUrls")
                or p.get("photos") or [])
    if isinstance(raw_imgs, str):
        raw_imgs = [raw_imgs] if raw_imgs else []
    image_urls: list[str] = []
    for img in raw_imgs:
        if isinstance(img, str) and img:
            image_urls.append(img)
        elif isinstance(img, dict):
            url = img.get("url") or img.get("src") or ""
            if url:
                image_urls.append(url)

    # Categories list from the product object
    categories = [str(c) for c in (p.get("categories") or []) if c]

    # Tags are pipe-separated; strip internal Jumia tracking codes (CP_*)
    tags_raw = p.get("tags") or ""
    tags = [
        t.strip() for t in tags_raw.split("|")
        if t.strip() and not t.strip().startswith("CP_")
    ]

    # Rating may be a nested object or a bare float
    rating_obj   = p.get("rating") or {}
    rating       = rating_obj.get("average")  if isinstance(rating_obj, dict) else None
    review_count = rating_obj.get("count")    if isinstance(rating_obj, dict) else None

    return {
        "product_id":    str(p.get("sku") or ""),
        "name":          str(p.get("displayName") or p.get("name") or "").strip(),
        "brand":         str(p.get("brand") or "").strip(),
        "price_ngn":     price_ngn,
        "old_price_ngn": old_price_ngn,
        "discount_pct":  discount_pct,
        "in_stock":      True,   # listing is active → safe to assume in stock
        "categories":    categories,
        "image_urls":    image_urls[:5],
        "rating":        rating,
        "review_count":  review_count,
        "seller_name":   "",     # only sellerId available in this format
        "url":           str(raw.get("url") or p.get("url") or "").split("?")[0],
        "is_express":    bool(p.get("isShopExpress")),
        "tags":          tags,
        "description":   "",     # not available at list-scrape level
        "scraped_at":    raw.get("scrapedAt") or "",
    }


def _normalize_format_b(raw: dict) -> dict:
    """123webdata/jumia-nigeria-scraper — flat structure."""
    price_ngn     = _parse_ngn_price(raw.get("price"))
    old_price_ngn = _parse_ngn_price(raw.get("regular_price"))

    # Compute discount ourselves if the scraper didn't provide it
    discount_pct: int | None = None
    if price_ngn and old_price_ngn and old_price_ngn > price_ngn:
        discount_pct = int((1 - price_ngn / old_price_ngn) * 100)

    # Build a deduplicated image list: main_image first, then images[]
    image_urls: list[str] = []
    main_image = raw.get("main_image") or ""
    if main_image:
        image_urls.append(main_image)
    for img in (raw.get("images") or []):
        if isinstance(img, str) and img and img not in image_urls:
            image_urls.append(img)

    # Prefer breadcrumbs (full chain) over the flat category string
    breadcrumbs  = raw.get("breadcrumbs") or []
    category_str = str(raw.get("category") or "")
    categories = (
        [str(c) for c in breadcrumbs if c]
        if breadcrumbs
        else ([category_str] if category_str else [])
    )

    return {
        "product_id":    str(raw.get("product_id") or raw.get("sku") or ""),
        "name":          str(raw.get("name") or "").strip(),
        "brand":         str(raw.get("brand") or "").strip(),
        "price_ngn":     price_ngn,
        "old_price_ngn": old_price_ngn,
        "discount_pct":  discount_pct,
        "in_stock":      bool(raw.get("in_stock", True)),
        "categories":    categories,
        "image_urls":    image_urls[:5],
        "rating":        raw.get("rating_value"),
        "review_count":  raw.get("review_count"),
        "seller_name":   str(raw.get("seller_name") or "").strip(),
        "url":           str(
            raw.get("url") or raw.get("canonical_url") or ""
        ).split("?")[0],
        "is_express":    False,
        "tags":          [],
        "description":   str(raw.get("description") or "").strip()[:3000],
        "scraped_at":    str(raw.get("scraped_at") or ""),
    }


# ── Category mapping ──────────────────────────────────────────────────────────

def resolve_category(categories: list[str], default_name: str) -> str:
    """
    Map a Jumia category breadcrumb list to our MarketplaceCategory name.
    Tries from most-specific (last) to broadest (first). Falls back to
    a partial substring match, then to default_name if nothing matches.
    """
    for cat in reversed(categories):
        key = cat.lower().strip()
        if key in JUMIA_CATEGORY_MAP:
            return JUMIA_CATEGORY_MAP[key]
        for jumia_key, our_name in JUMIA_CATEGORY_MAP.items():
            if jumia_key in key or key in jumia_key:
                return our_name
    return default_name


# ── Description builder ───────────────────────────────────────────────────────

def build_description(item: dict) -> str:
    """
    Build a structured product description from a normalised Jumia item.
    Includes the scraped description (if any), key attributes, categories,
    seller info, rating, and the source listing URL for duplicate detection.
    """
    parts: list[str] = []

    if item["description"]:
        parts.append(item["description"])

    # Key attributes on a single compact line
    attrs: list[str] = []
    if item["brand"]:
        attrs.append(f"Brand: {item['brand']}")
    if item["discount_pct"]:
        attrs.append(f"Discount: {item['discount_pct']}% off")
    if item["old_price_ngn"]:
        attrs.append(f"Original price: ₦{item['old_price_ngn']:,.2f}")
    if item["is_express"]:
        attrs.append("Delivery: Jumia Express")
    if attrs:
        parts.append(" · ".join(attrs))

    if item["categories"]:
        parts.append("Categories: " + " > ".join(item["categories"]))

    # Only include seller name if it's a real name (not a bare ID integer)
    if item["seller_name"] and not item["seller_name"].isdigit():
        parts.append(f"Sold by: {item['seller_name']}")

    if item["rating"] is not None:
        review_str = f" ({item['review_count']} reviews)" if item["review_count"] else ""
        parts.append(f"Jumia rating: {item['rating']}/5 ★{review_str}")

    # SKU line — secondary duplicate detection key (see duplicate-detection block)
    if item["product_id"]:
        parts.append(f"SKU: {item['product_id']}")

    # Always append the URL last — duplicate detection keys off it
    if item["url"]:
        parts.append(f"[Jumia listing: {item['url']}]")

    return (
        "\n\n".join(p for p in parts if p).strip()
        or "Product imported from Jumia Nigeria."
    )


# ── Apify fetcher ─────────────────────────────────────────────────────────────

def fetch_apify_dataset(dataset_id: str, token: str | None) -> list:
    """
    Fetch ALL items from an Apify dataset, automatically paginating
    for datasets larger than 1 000 items.
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
            raise CommandError(f"Apify API error {resp.status_code}: {resp.text[:200]}")

        data  = resp.json()
        batch = (
            data if isinstance(data, list)
            else data.get("items") or data.get("data") or []
        )
        if not isinstance(batch, list):
            raise CommandError("Unexpected response format from Apify API.")

        items.extend(batch)
        print(f"    …{len(items)} item(s) fetched")

        if len(batch) < limit:
            break   # last (or only) page
        offset += limit

    return items


# ── Image utilities ───────────────────────────────────────────────────────────

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


# ── Stats ─────────────────────────────────────────────────────────────────────

def _fresh_stats() -> dict:
    return {
        "created": 0, "updated": 0, "skipped": 0, "errors": 0,
        # Detailed skip reasons
        "no_title": 0, "no_price": 0, "price_filtered": 0,
        "out_of_stock": 0, "duplicate": 0,
        # Images
        "images_saved": 0, "images_failed": 0,
    }


# ══════════════════════════════════════════════════════════════════════════════
# ── Management command ────────────────────────────────════════════════════════
# ══════════════════════════════════════════════════════════════════════════════

class Command(BaseCommand):
    help = (
        "Import Jumia Nigeria product listings (from Apify) into the TradeLink marketplace. "
        "Pass an Apify dataset ID or a local JSON file path. "
        "Handles both microworlds~jumia-scraper and 123webdata/jumia-nigeria-scraper output."
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
            help=(
                f"MarketplaceCategory name applied to all imports. "
                f"Used as fallback when --auto-category finds no match. "
                f"Default: '{DEFAULT_CATEGORY}'"
            ),
        )
        parser.add_argument(
            "--auto-category",
            action="store_true",
            help=(
                "Detect each product's category from its Jumia category data. "
                "--category is used as the fallback when no mapping is found."
            ),
        )

        # ── Product defaults ────────────────────────────────────────────────
        parser.add_argument(
            "--condition",
            choices=[c.value for c in Product.Condition],
            default=Product.Condition.NEW,
            help="Condition for all imported products. Default: new",
        )
        parser.add_argument(
            "--status",
            choices=[s.value for s in Product.Status],
            default=Product.Status.ACTIVE,
            help="Product status after import. Default: active",
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
            metavar="NGN",
            help="Skip products cheaper than this amount in NGN.",
        )
        parser.add_argument(
            "--max-price",
            type=float,
            default=None,
            metavar="NGN",
            help="Skip products more expensive than this amount in NGN.",
        )
        parser.add_argument(
            "--in-stock-only",
            action="store_true",
            help=(
                "Skip products reported as out of stock by the scraper. "
                "Only effective with 123webdata scraper output (has in_stock field)."
            ),
        )

        # ── Behaviour flags ─────────────────────────────────────────────────
        parser.add_argument(
            "--update",
            action="store_true",
            help=(
                "Update price, title, description, and brand of already-imported "
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
        self._opts  = options
        source      = options["source"]
        apify_token = options["apify_token"] or os.environ.get("APIFY_TOKEN")
        dry_run     = options["dry_run"]

        if dry_run:
            self.stdout.write(self.style.WARNING(
                "⚠  DRY RUN — nothing will be written to the database.\n"
            ))

        # 1. Load data ──────────────────────────────────────────────────────────
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

        # 2. Seller + default category ──────────────────────────────────────────
        seller           = self._get_or_create_seller(dry_run)
        default_category = self._get_or_create_category(options["category"], dry_run)

        # 3. Import loop ────────────────────────────────────────────────────────
        stats = _fresh_stats()

        for idx, raw_item in enumerate(data, 1):
            self._log_progress(idx, len(data), stats)
            try:
                item = normalize_item(raw_item)
                self._import_item(item, seller, default_category, stats, dry_run)
            except Exception as exc:
                stats["errors"] += 1
                # Safely extract a name from either raw format
                p    = raw_item.get("product", {}) if isinstance(raw_item.get("product"), dict) else {}
                name = str(p.get("name") or raw_item.get("name") or "<unknown>")[:60]
                self.stderr.write(self.style.ERROR(f"\n  ✗ ERROR — '{name}': {exc}"))

        # 4. Summary ────────────────────────────────────────────────────────────
        self._print_summary(stats, dry_run)

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
                f"  python manage.py import_jumia_products {sys.argv[-1]} --create-seller\n"
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
                "first_name": "Jumia",
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

    def _get_or_create_category(self, name: str, dry_run: bool):
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
                "description":   f"Tools and equipment — {name.lower()}.",
                "icon_class":    "fas fa-tools",
                "is_active":     True,
                "display_order": 10,
            },
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f'  Created category: "{name}"'))
        return cat

    # ── Single item import ─────────────────────────────────────────────────────

    def _import_item(
        self,
        item: dict,
        seller,
        default_category,
        stats: dict,
        dry_run: bool,
    ) -> None:
        opts = self._opts

        # ── Title ──────────────────────────────────────────────────────────────
        title = item["name"][:200]
        if not title:
            stats["no_title"] += 1
            stats["skipped"]  += 1
            self.stdout.write(f"  [SKIP] No title — {item['url'][:80]}")
            return

        # ── Stock filter ───────────────────────────────────────────────────────
        if opts["in_stock_only"] and not item["in_stock"]:
            stats["out_of_stock"] += 1
            stats["skipped"]      += 1
            self.stdout.write(f"  [SKIP] Out of stock — {title[:60]}")
            return

        # ── Price ──────────────────────────────────────────────────────────────
        price_ngn = item["price_ngn"]
        if not price_ngn or price_ngn <= 0:
            stats["no_price"] += 1
            stats["skipped"]  += 1
            self.stdout.write(f"  [SKIP] No price — {title[:60]}")
            return

        if price_ngn < Decimal(str(opts["min_price"])):
            stats["price_filtered"] += 1
            stats["skipped"]        += 1
            return
        if opts["max_price"] is not None and price_ngn > Decimal(str(opts["max_price"])):
            stats["price_filtered"] += 1
            stats["skipped"]        += 1
            return

        # ── Category ───────────────────────────────────────────────────────────
        # With --auto-category: resolve per product and create if needed.
        # Without: all products go into the single default category.
        if opts["auto_category"] and item["categories"]:
            cat_name = resolve_category(item["categories"], opts["category"])
            # Avoid a DB hit for the category we already resolved last call
            category = self._get_or_create_category(cat_name, dry_run)
        else:
            category = default_category

        # ── Description ────────────────────────────────────────────────────────
        description = build_description(item)

        # ── Duplicate detection ────────────────────────────────────────────────
        # Key on the Jumia product URL (always appended to description) and
        # the product_id/SKU as a secondary check.
        existing = None
        if item["url"]:
            # Match the full bracketed marker so a bare URL substring cannot
            # false-positive against unrelated text in other descriptions.
            existing = Product.objects.filter(
                description__contains=f"[Jumia listing: {item['url']}]"
            ).first()
        if existing is None and item["product_id"] and len(item["product_id"]) >= 6:
            # Require the "SKU: " prefix so short SKUs like "123" never match
            # random words elsewhere in a product description.
            existing = Product.objects.filter(
                description__contains=f"SKU: {item['product_id']}"
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
                    f"               ₦{price_ngn:,.2f}"
                )
                stats["updated"] += 1
                return

            existing.title       = title
            existing.description = description
            existing.price       = price_ngn
            existing.brand       = item["brand"][:100] if item["brand"] else ""
            existing.status      = opts["status"]
            existing.save(update_fields=["title", "description", "price", "brand", "status"])
            # Download images only if this product currently has none
            img_saved = img_failed = 0
            if (
                not opts["skip_images"]
                and item["image_urls"]
                and not existing.images.exists()
            ):
                img_saved, img_failed = self._save_images(
                    existing, item["image_urls"], item["product_id"]
                )
                stats["images_saved"]  += img_saved
                stats["images_failed"] += img_failed

            self.stdout.write(
                f"  [UPDATED] {existing.title[:55]} - ?{price_ngn:,.2f}"
                + (f" | {img_saved} img(s)" if img_saved else "")
            )
            stats["updated"] += 1

            return

        # ── DRY RUN preview ────────────────────────────────────────────────────
        if dry_run:
            cat_name = (category.name if category else opts["category"])
            self.stdout.write(
                f"  [DRY-CREATE] {title[:60]}\n"
                f"               ₦{price_ngn:,.2f} | "
                f"brand={item['brand'] or 'N/A'} | "
                f"cat={cat_name} | "
                f"imgs={len(item['image_urls'])} | "
                f"stock={'✓' if item['in_stock'] else '✗'}"
            )
            stats["created"] += 1
            return

        # ── CREATE new product ─────────────────────────────────────────────────
        with transaction.atomic():
            product = Product.objects.create(
                seller          = seller,
                category        = category,
                title           = title,
                description     = description,
                condition       = opts["condition"],
                brand           = item["brand"][:100] if item["brand"] else "",
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
            if not opts["skip_images"] and item["image_urls"]:
                img_saved, img_failed = self._save_images(
                    product, item["image_urls"], item["product_id"]
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
        self, product, image_urls: list, product_id: str
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
            filename = f"jumia_{product_id or uuid.uuid4().hex[:8]}_{order}.{ext}"
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

    def _print_summary(self, stats: dict, dry_run: bool) -> None:
        verb = "Would create" if dry_run else "Created"
        w    = self.stdout.write
        sep  = "─" * 60

        w("\n" + sep)
        w(self.style.SUCCESS(f"  {verb}:              {stats['created']}"))
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
            if stats["out_of_stock"]:
                w(f"    └ out of stock:     {stats['out_of_stock']}")

        if stats["errors"]:
            w(self.style.ERROR(f"  Errors:               {stats['errors']}"))

        total_imgs = stats["images_saved"] + stats["images_failed"]
        if total_imgs:
            w(
                f"  Images:               "
                f"{stats['images_saved']} saved, "
                f"{stats['images_failed']} failed"
            )

        w(sep + "\n")