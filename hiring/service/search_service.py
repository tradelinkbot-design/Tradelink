"""
hiring/service/search_service.py
==================================
Semantic worker-search service — powers the `keyword` field on TalentSearchView.

Architecture (mirrors jobs/service/search_service.py exactly)
──────────────────────────────────────────────────────────────

  1. Employer types a keyword — e.g. "solar panel installer Lagos" or
     "plumber who can fix burst pipes".

  2. We collect the PKs of WorkerProfile rows that passed the hard filters
     (trade, state, experience level, open-to-work, verified, etc.).

  3. The query is encoded on the CELERY WORKER process via an RPC call
     to ``jobs.tasks.encode_search_query_task``.  This keeps PyTorch
     completely out of the Daphne/ASGI web-server process — the same
     reason the jobs and marketplace apps use this pattern.

  4. Batch cosine similarity is computed here (in the web process) using
     the pre-stored ``WorkerProfile.text_embedding`` vectors (numpy,
     fast — no model loading).

  5. Workers with a score >= MIN_SCORE_THRESHOLD are returned as a ranked
     list of (pk, score) pairs.  The caller re-orders the Django queryset
     using a CASE WHEN SQL expression so Pagination still works normally.

  6. Workers WITHOUT an embedding (profile newly updated, Celery not yet
     processed) are appended at the END so they're never hidden.

Fallback
────────
  • If Celery times out or is unavailable → fall back to icontains keyword
    search on name, trade, bio, skills.
  • If the query is shorter than 2 chars → skip semantic search entirely.

Performance
───────────
  Encoding one query via RPC:  ~30–80 ms on CPU.
  Batch cosine on 5,000 workers: < 10 ms (NumPy matrix-multiply).
  Total overhead vs a plain DB query: ~40–90 ms — acceptable.
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

# Celery RPC timeout (seconds).  If the worker doesn't respond in time we
# fall back gracefully rather than leaving the employer waiting forever.
CELERY_ENCODE_TIMEOUT = 5.0


def semantic_worker_search(
    query: str,
    worker_pks: Optional[List] = None,
) -> Optional[List[Tuple]]:
    """
    Encode ``query`` via Celery RPC (no PyTorch in the web process!) and
    return a ranked list of (worker_pk, score) tuples, highest score first.

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

        # ── Step 1: encode the query ON THE CELERY WORKER via RPC ───────────
        # apply_async().get() is a synchronous RPC — the web process blocks
        # for at most CELERY_ENCODE_TIMEOUT seconds, then falls back.
        try:
            query_vec_list = encode_search_query_task.apply_async(
                args=[query.strip()],
                expires=CELERY_ENCODE_TIMEOUT,
            ).get(timeout=CELERY_ENCODE_TIMEOUT)
            query_vec = np.array(query_vec_list, dtype=np.float32)
        except Exception as exc:
            logger.warning(
                "semantic_worker_search: Celery RPC failed/timed out (%s) "
                "— using keyword fallback.",
                exc,
            )
            return None

        # ── Step 2: fetch worker embeddings from the DB ──────────────────────
        qs = WorkerProfile.objects.filter(
            text_embedding__isnull=False,
        ).values('pk', 'text_embedding')

        if worker_pks is not None:
            qs = qs.filter(pk__in=worker_pks)

        rows = list(qs)
        if not rows:
            logger.debug(
                "semantic_worker_search: no workers with embeddings (pks=%s).",
                len(worker_pks) if worker_pks else 'all',
            )
            return None

        pks        = [r['pk'] for r in rows]
        embeddings = [r['text_embedding'] for r in rows]

        # ── Step 3: vectorised cosine similarity (one query vs N workers) ────
        # text_encoder.batch_cosine_similarity uses a single NumPy matrix-
        # multiply — O(N·D) — no PyTorch needed.
        scores = text_encoder.batch_cosine_similarity(query_vec, embeddings)

        # ── Step 4: filter & rank ────────────────────────────────────────────
        ranked = sorted(
            [
                (pk, score)
                for pk, score in zip(pks, scores)
                if score >= MIN_SCORE_THRESHOLD
            ],
            key=lambda x: x[1],
            reverse=True,
        )[:100]  # cap at 100 to keep CASE WHEN expression manageable

        logger.debug(
            "semantic_worker_search: query=%r → %d results (from %d candidates)",
            query, len(ranked), len(rows),
        )
        return ranked or None

    except Exception as exc:
        # Never crash the talent search page — fall back gracefully
        logger.warning(
            "semantic_worker_search failed for query %r — "
            "falling back to icontains. Error: %s",
            query, exc,
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
