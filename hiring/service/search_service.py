"""
hiring/service/search_service.py
==================================
Semantic worker-search service — powers the `keyword` field on TalentSearchView.

Performance tiers
─────────────────
  TIER 1 — pgvector (production / NeonDB):
    Cosine similarity runs entirely inside Postgres via the `<=>` operator.
    Only (pk, score) pairs are returned — no bulk embedding transfer.

  TIER 2 — Celery RPC + NumPy (local dev / PG 12):
    Original approach — encode query via Celery, fetch all embeddings to
    Python, run NumPy matrix multiply.

Both tiers keep PyTorch off the Daphne/ASGI web-server process.
"""

import logging
from typing import List, Tuple, Optional

import numpy as np

logger = logging.getLogger(__name__)

# Minimum query length to bother with semantic search
MIN_QUERY_LEN = 2

# Minimum cosine similarity to include a result (0–1).
# 0.60 = 60% — only return workers with at least 60% semantic match.
MIN_SCORE_THRESHOLD = 0.60

# Celery RPC timeout (seconds)
CELERY_ENCODE_TIMEOUT = 5.0

# Text embedding dimension
EMBEDDING_DIM = 768


def semantic_worker_search(
    query: str,
    worker_pks: Optional[List] = None,
) -> Optional[List[Tuple]]:
    """
    Encode ``query`` and return a ranked list of (worker_pk, score) tuples,
    highest score first.

    Args:
        query:       The employer's natural-language search string.
        worker_pks:  Optional list of WorkerProfile PKs to restrict the
                     search to (those already filtered by trade/state/etc.).
                     Pass None to search all workers with embeddings.

    Returns:
        List of (pk, score) tuples sorted descending by score, or None if
        semantic search is unavailable.  Callers should fall back to an
        icontains queryset filter when None is returned.
    """
    if not query or len(query.strip()) < MIN_QUERY_LEN:
        return None

    try:
        from jobs.tasks import encode_search_query_task
        from jobs.service.text_encoder import text_encoder
        from jobs.models import WorkerProfile

        # ── Encode the query (on Celery worker to keep PyTorch off ASGI) ──────
        try:
            query_vec_list = encode_search_query_task.apply_async(
                args=[query.strip()],
                expires=CELERY_ENCODE_TIMEOUT,
            ).get(timeout=CELERY_ENCODE_TIMEOUT)
            query_vec = np.array(query_vec_list, dtype=np.float32)
        except Exception as exc:
            logger.warning(
                "semantic_worker_search: Celery RPC failed/timed out (%s) "
                "— trying in-process encoding.", exc,
            )
            try:
                query_vec = np.array(
                    text_encoder.encode(query.strip()), dtype=np.float32
                )
            except Exception as encode_exc:
                logger.warning(
                    "semantic_worker_search: in-process encoding failed: %s",
                    encode_exc,
                )
                return None

        # ── Base queryset ──────────────────────────────────────────────────────
        qs = WorkerProfile.objects.filter(text_embedding__isnull=False)
        if worker_pks is not None:
            qs = qs.filter(pk__in=worker_pks)

        # ── TIER 1: pgvector (production) ─────────────────────────────────────
        from jobs.service.pgvector_utils import pgvector_cosine_search

        ranked = pgvector_cosine_search(
            qs=qs,
            field='text_embedding',
            dim=EMBEDDING_DIM,
            query_vec=query_vec,
            threshold=MIN_SCORE_THRESHOLD,
            limit=100,            # cap at 100 to keep CASE WHEN manageable
        )

        if ranked is not None:
            logger.debug(
                "semantic_worker_search [pgvector]: query=%r → %d results",
                query, len(ranked),
            )
            return ranked or None

        # ── TIER 2: NumPy fallback ─────────────────────────────────────────────
        rows = list(qs.values('pk', 'text_embedding'))
        if not rows:
            logger.debug(
                "semantic_worker_search: no workers with embeddings "
                "(pks=%s).", len(worker_pks) if worker_pks else 'all',
            )
            return None

        pks        = [r['pk'] for r in rows]
        embeddings = [r['text_embedding'] for r in rows]

        scores = text_encoder.batch_cosine_similarity(query_vec, embeddings)

        ranked = sorted(
            [
                (pk, score)
                for pk, score in zip(pks, scores)
                if score >= MIN_SCORE_THRESHOLD
            ],
            key=lambda x: x[1],
            reverse=True,
        )[:100]

        logger.debug(
            "semantic_worker_search [numpy]: query=%r → %d results "
            "(from %d candidates)",
            query, len(ranked), len(rows),
        )
        return ranked or None

    except Exception as exc:
        logger.warning(
            "semantic_worker_search failed for query %r — "
            "falling back to icontains. Error: %s", query, exc,
        )
        return None


def reorder_workers_by_scores(queryset, ranked: List[Tuple]):
    """
    Re-order a WorkerProfile QuerySet to match the semantic ranking using
    a SQL CASE WHEN expression — exactly as done in jobs.service.search_service.

    Workers that have an embedding but scored below the threshold, and workers
    with no embedding at all, are handled by the caller (appended at the end).

    Args:
        queryset: A WorkerProfile queryset, already filtered and
                  select_related/prefetch_related.
        ranked:   List of (pk, score) tuples from semantic_worker_search().

    Returns:
        An ordered queryset containing only the ranked workers.
    """
    from django.db.models import Case, When, FloatField, Value

    if not ranked:
        return queryset.none()

    ranked_pks = [pk for pk, _ in ranked]

    ordering = Case(
        *[When(pk=pk, then=Value(float(pos))) for pos, pk in enumerate(ranked_pks)],
        default=Value(float(len(ranked_pks))),
        output_field=FloatField(),
    )

    return (
        queryset
        .filter(pk__in=ranked_pks)
        .annotate(semantic_rank=ordering)
        .order_by('semantic_rank')
    )
