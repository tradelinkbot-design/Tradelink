"""
jobs/service/search_service.py
================================
Semantic search service — powers the `q` field on JobListView.

How it works
────────────
  1. The user types a query — e.g. "fix my generator" or "solar wiring Lagos".
  2. We encode the query with the same sentence-transformer used for jobs.
  3. We run cosine similarity against all active jobs with embeddings.
  4. Jobs that score ≥ 60% are returned ranked by score.
  5. Jobs without an embedding fall to the end of results.

Performance tiers
─────────────────
  TIER 1 — pgvector (production / NeonDB):
    • The `vector` extension is installed on Neon.
    • We annotate the queryset with a RawSQL cosine distance expression that
      runs entirely in Postgres (C / SIMD kernels).
    • Only (pk, score) pairs are transferred back — ~375× less data than
      shipping full embedding arrays to Python.

  TIER 2 — NumPy (local dev / PG 12 without pgvector):
    • Falls back to the original approach: fetch all active job embeddings
      (as JSON arrays) and compute cosine similarity in Python.
    • Overhead: ~3–5 ms for 1,000 jobs on CPU.

  Both tiers share the same Celery RPC for query encoding — PyTorch stays
  off the web-server process on Windows to avoid the ASGI crash.

Why not icontains?
──────────────────
  icontains("generator") won't match "Diesel Engine & ATS Maintenance
  Technician" even though it's directly relevant.  The sentence-transformer
  understands synonyms and semantic intent.

Fallback
────────
  Any exception drops through to None so the view falls back to icontains.
"""

import logging
from typing import List, Tuple, Optional

import numpy as np

logger = logging.getLogger(__name__)

# Minimum query length to bother with semantic search
MIN_QUERY_LEN = 2

# Minimum semantic score to include a result (0–1).
# 0.60 = 60% — only show results the AI is genuinely confident about.
MIN_SCORE_THRESHOLD = 0.60

# Text embedding dimension (must match the model used to generate embeddings)
EMBEDDING_DIM = 768


def semantic_job_search(
    query: str,
    job_pks: Optional[List] = None,
) -> Optional[List[Tuple]]:
    """
    Encode `query` with the sentence-transformer and return a ranked list
    of (job_pk, score) tuples, highest score first.

    Args:
        query:    The user's search string.
        job_pks:  Optional list of job PKs to restrict search to
                  (e.g. already filtered by trade/state). If None, searches
                  all active jobs with embeddings.

    Returns:
        List of (pk, score) tuples sorted by score descending, or None if
        semantic search is unavailable (model not loaded, query too short).
        Caller should fall back to icontains when None is returned.
    """
    if not query or len(query.strip()) < MIN_QUERY_LEN:
        return None

    try:
        from jobs.tasks import encode_search_query_task
        from jobs.service.text_encoder import text_encoder
        from jobs.models import Job

        # ── Encode query (offloaded to Celery worker to keep PyTorch off ASGI) ──
        try:
            query_vec_list = encode_search_query_task.apply_async(
                args=[query.strip()],
                expires=4.0
            ).get(timeout=4.0)
            query_vec = np.array(query_vec_list, dtype=np.float32)
        except Exception as exc:
            logger.info(
                "semantic_job_search: Celery RPC unavailable (%s) — encoding "
                "with in-process FastEmbed.", exc
            )
            try:
                query_vec = np.array(
                    text_encoder.encode(query.strip()), dtype=np.float32
                )
            except Exception as encode_exc:
                logger.warning(
                    "semantic_job_search: in-process encoding failed: %s",
                    encode_exc,
                )
                return None

        # ── Base queryset ──────────────────────────────────────────────────────
        qs = Job.objects.filter(
            status=Job.Status.ACTIVE,
            text_embedding__isnull=False,
        )
        if job_pks is not None:
            qs = qs.filter(pk__in=job_pks)

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
            # pgvector succeeded
            logger.debug(
                "semantic_job_search [pgvector]: query=%r → %d results",
                query, len(ranked),
            )
            return ranked

        # ── TIER 2: NumPy fallback (local dev / no pgvector) ──────────────────
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
            "semantic_job_search [numpy]: query=%r → %d results "
            "(from %d candidates)",
            query, len(ranked), len(rows),
        )
        return ranked

    except Exception as exc:
        logger.warning(
            "semantic_job_search failed for query %r — falling back to "
            "icontains. Error: %s", query, exc,
        )
        return None


def reorder_queryset_by_scores(queryset, ranked: List[Tuple]):
    """
    Re-order a Django QuerySet to match the semantic ranking.

    Django doesn't support arbitrary ordering from Python, so we use a
    CASE WHEN expression to preserve the ranked order in SQL.

    Jobs that have an embedding but didn't make the threshold cut are
    excluded.  Jobs with no embedding at all (not in ranked) are excluded
    too — the caller appends them at the end if needed.

    Args:
        queryset: A Job queryset, already filtered and select_related.
        ranked:   List of (pk, score) tuples from semantic_job_search().

    Returns:
        An ordered queryset.
    """
    from django.db.models import Case, When, FloatField, Value

    if not ranked:
        return queryset.none()

    ranked_pks = [pk for pk, _ in ranked]

    # Build CASE WHEN pk = X THEN position ELSE 9999 END
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