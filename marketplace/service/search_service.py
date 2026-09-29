"""
marketplace/service/search_service.py
======================================
Semantic search service — powers the `q` field on ProductListView.

How it works
────────────
  1. The user types a query — e.g. "angle grinder" or "used generator Lagos".
  2. We offload encoding to the Celery worker via RPC (encode_product_search_query_task).
     This completely prevents PyTorch from loading in the web server process,
     avoiding the Windows ASGI crash — identical to the pattern used by the
     jobs app's search_service.py.
  3. We pull all active products that have a text_embedding computed.
  4. Batch cosine similarity → ranked list of (product_pk, score) pairs.
  5. We return the ranked list; the view re-orders the queryset accordingly.
  6. Products without an embedding (newly listed, worker not yet processed)
     fall back to icontains so they're never hidden — just not ranked.

Why not icontains?
──────────────────
  icontains("grinder") won't match a product titled
  "Angle Tool & Disc Polisher" even though it's directly relevant.
  The sentence-transformer understands synonyms and semantic intent.

Fallback
────────
  If Celery is down or times out (5 s), we return None and the view
  falls back to icontains transparently — the page never breaks.

Performance
───────────
  Encoding one query:  ~30–80 ms on CPU (in the worker).
  Cosine similarity against 1,000 products: < 5 ms (NumPy vectorised).
  Total overhead vs a plain DB query: ~35–85 ms — acceptable for a search.
"""

import logging
from typing import List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Minimum query length to bother with semantic search
MIN_QUERY_LEN = 2

# Minimum semantic score to include a result (0–1).
# 0.15 is deliberately low — sentence-transformer scores for trade queries
# rarely fall below 0.2 for relevant results, but we don't want to over-filter.
MIN_SCORE_THRESHOLD = 0.15


def semantic_product_search(
    query: str,
    product_pks: Optional[List] = None,
) -> Optional[List[Tuple]]:
    """
    Encode `query` via the Celery worker RPC and return a ranked list
    of (product_pk, score) tuples, highest score first.

    Args:
        query:       The buyer's search string.
        product_pks: Optional list of product PKs to restrict search to
                     (e.g. already filtered by category/state). If None,
                     searches all active products with embeddings.

    Returns:
        List of (pk, score) tuples sorted by score descending, or None if
        semantic search is unavailable (Celery down, query too short, no
        embeddings).  Caller should fall back to icontains when None is returned.
    """
    if not query or len(query.strip()) < MIN_QUERY_LEN:
        return None

    try:
        from marketplace.tasks import encode_product_search_query_task
        from jobs.service.text_encoder import text_encoder
        from marketplace.models import Product

        # ── Offload encoding to the Celery worker via RPC ────────────────
        # Keeps PyTorch out of the web-server process (same pattern as jobs app).
        try:
            query_vec_list = encode_product_search_query_task.apply_async(
                args=[query.strip()],
                expires=5.0,
            ).get(timeout=5.0)
            query_vec = np.array(query_vec_list, dtype=np.float32)
        except Exception as exc:
            logger.warning(
                "semantic_product_search: Celery RPC failed/timed out (%s) "
                "— using keyword fallback.",
                exc,
            )
            return None

        # ── Fetch products with embeddings ───────────────────────────────
        qs = Product.objects.filter(
            status=Product.Status.ACTIVE,
            text_embedding__isnull=False,
        ).values('pk', 'text_embedding')

        if product_pks is not None:
            qs = qs.filter(pk__in=product_pks)

        rows = list(qs)
        if not rows:
            return None

        pks        = [r['pk'] for r in rows]
        embeddings = [r['text_embedding'] for r in rows]

        # ── Vectorised cosine similarity (one query vs N product embeddings) ──
        scores = text_encoder.batch_cosine_similarity(query_vec, embeddings)

        # ── Zip, filter below threshold, sort descending ─────────────────
        ranked = sorted(
            [(pk, score) for pk, score in zip(pks, scores) if score >= MIN_SCORE_THRESHOLD],
            key=lambda x: x[1],
            reverse=True,
        )[:50]

        logger.debug(
            "semantic_product_search: query=%r → %d results (from %d candidates)",
            query, len(ranked), len(rows),
        )
        return ranked or None

    except Exception as exc:
        # Never crash the search page — fall back gracefully
        logger.warning(
            "semantic_product_search failed for query %r — falling back to icontains. "
            "Error: %s",
            query, exc,
        )
        return None
