"""
marketplace/service/search_service.py
======================================
Semantic search service — powers the `q` field on ProductListView.

Performance tiers
─────────────────
  TIER 1 — pgvector (production / NeonDB):
    Cosine similarity computed entirely in Postgres via the `<=>` operator.
    Only (pk, score) pairs transferred — ~375× less data than NumPy path.

  TIER 2 — NumPy (local dev / PG 12):
    Falls back to the original approach: fetch all embeddings to Python.

Query encoding uses the Celery worker RPC (encode_product_search_query_task)
to keep heavy model loading out of the web-server process on Windows.
"""

import logging
from typing import List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Minimum query length to bother with semantic search
MIN_QUERY_LEN = 2

# Minimum semantic score to include a result (0–1).
# 0.60 = 60% — only return products with at least 60% semantic similarity.
MIN_SCORE_THRESHOLD = 0.60

# Text embedding dimension
EMBEDDING_DIM = 768


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
        semantic search is unavailable.  Caller should fall back to icontains.
    """
    if not query or len(query.strip()) < MIN_QUERY_LEN:
        return None

    try:
        from marketplace.tasks import encode_product_search_query_task
        from jobs.service.text_encoder import text_encoder
        from marketplace.models import Product

        # ── Offload encoding to Celery worker via RPC ─────────────────────────
        try:
            query_vec_list = encode_product_search_query_task.apply_async(
                args=[query.strip()],
                expires=4.0,
            ).get(timeout=4.0)
            query_vec = np.array(query_vec_list, dtype=np.float32)
        except Exception as exc:
            logger.info(
                "semantic_product_search: Celery RPC unavailable (%s) — "
                "encoding with in-process FastEmbed.", exc,
            )
            try:
                query_vec = np.array(
                    text_encoder.encode(query.strip()), dtype=np.float32
                )
            except Exception as encode_exc:
                logger.warning(
                    "semantic_product_search: in-process encoding failed: %s",
                    encode_exc,
                )
                return None

        # ── Base queryset ──────────────────────────────────────────────────────
        qs = Product.objects.filter(
            status=Product.Status.ACTIVE,
            text_embedding__isnull=False,
        )
        if product_pks is not None:
            qs = qs.filter(pk__in=product_pks)

        # ── TIER 1: pgvector (production) ─────────────────────────────────────
        from jobs.service.pgvector_utils import pgvector_cosine_search

        ranked = pgvector_cosine_search(
            qs=qs,
            field='text_embedding',
            dim=EMBEDDING_DIM,
            query_vec=query_vec,
            threshold=MIN_SCORE_THRESHOLD,
            limit=50,
        )

        if ranked is not None:
            logger.debug(
                "semantic_product_search [pgvector]: query=%r → %d results",
                query, len(ranked),
            )
            return ranked or None

        # ── TIER 2: NumPy fallback ─────────────────────────────────────────────
        rows = list(qs.values('pk', 'text_embedding'))
        if not rows:
            return None

        pks        = [r['pk'] for r in rows]
        embeddings = [r['text_embedding'] for r in rows]

        scores = text_encoder.batch_cosine_similarity(query_vec, embeddings)

        ranked = sorted(
            [(pk, score) for pk, score in zip(pks, scores)
             if score >= MIN_SCORE_THRESHOLD],
            key=lambda x: x[1],
            reverse=True,
        )[:50]

        logger.debug(
            "semantic_product_search [numpy]: query=%r → %d results "
            "(from %d candidates)",
            query, len(ranked), len(rows),
        )
        return ranked or None

    except Exception as exc:
        logger.warning(
            "semantic_product_search failed for query %r — falling back to "
            "icontains. Error: %s", query, exc,
        )
        return None
