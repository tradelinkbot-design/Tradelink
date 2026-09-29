"""
jobs/service/search_service.py
================================
Semantic search service — powers the `q` field on JobListView.

How it works
────────────
  1. The user types a query — e.g. "fix my generator" or "solar wiring Lagos".
  2. We encode the query with the same sentence-transformer used for jobs.
  3. We pull all active jobs that have a text_embedding computed.
  4. Batch cosine similarity → ranked list of (job_pk, score) pairs.
  5. We re-order the Django queryset to match that ranked order.
  6. Jobs without an embedding (newly posted, worker not yet processed) fall
     to the end of the results so they're never hidden — just not ranked.

Why not icontains?
──────────────────
  icontains("generator") won't match a job titled
  "Diesel Engine & ATS Maintenance Technician" even though the job is
  directly relevant.  The sentence-transformer understands synonyms and
  semantic intent — the same model that powered the worker↔job matching.

Fallback
────────
  If the model isn't loaded yet (cold start) or the query is too short,
  we fall back to the original icontains filter so the page never breaks.

Performance
───────────
  Encoding one query:  ~30–80 ms on CPU.
  Cosine similarity against 1,000 jobs: < 5 ms (NumPy vectorised).
  Total overhead vs a plain DB query: ~35–85 ms — acceptable for a search.

  At very large scale (10,000+ jobs) consider caching embeddings in Redis
  or using pgvector for native DB similarity search.
"""

import logging
from typing import List, Tuple, Optional

import numpy as np

logger = logging.getLogger(__name__)

# Minimum query length to bother with semantic search
MIN_QUERY_LEN = 2

# Minimum semantic score to include a result (0–1).
# 0.15 is deliberately low — sentence-transformer scores for trade queries
# rarely fall below 0.2 for relevant results, but we don't want to over-filter.
MIN_SCORE_THRESHOLD = 0.15


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

        # Offload encoding to the Celery worker via RPC.
        # This completely prevents PyTorch from loading in the web server process,
        # avoiding the Windows ASGI crash. If Celery is down, it falls back after 5s.
        try:
            query_vec_list = encode_search_query_task.apply_async(
                args=[query.strip()], 
                expires=5.0
            ).get(timeout=5.0)
            query_vec = np.array(query_vec_list, dtype=np.float32)
        except Exception as exc:
            logger.warning(
                "semantic_job_search: Celery RPC failed/timed out (%s) — using keyword fallback.", exc
            )
            return None

        # Fetch jobs with embeddings
        qs = Job.objects.filter(
            status=Job.Status.ACTIVE,
            text_embedding__isnull=False,
        ).values('pk', 'text_embedding')

        if job_pks is not None:
            qs = qs.filter(pk__in=job_pks)

        rows = list(qs)
        if not rows:
            return None

        pks        = [r['pk'] for r in rows]
        embeddings = [r['text_embedding'] for r in rows]

        # Vectorised cosine similarity (one query vs N job embeddings)
        scores = text_encoder.batch_cosine_similarity(query_vec, embeddings)

        # Zip, filter below threshold, sort descending
        ranked = sorted(
            [(pk, score) for pk, score in zip(pks, scores) if score >= MIN_SCORE_THRESHOLD],
            key=lambda x: x[1],
            reverse=True,
        )[:50]

        logger.debug(
            "semantic_job_search: query=%r → %d results (from %d candidates)",
            query, len(ranked), len(rows),
        )
        return ranked

    except Exception as exc:
        # Never crash the search page — fall back gracefully
        logger.warning(
            "semantic_job_search failed for query %r — falling back to icontains. Error: %s",
            query, exc,
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