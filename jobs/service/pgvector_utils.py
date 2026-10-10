"""
jobs/service/pgvector_utils.py
================================
Utility for pgvector-accelerated cosine similarity in PostgreSQL.

This module provides a transparent performance layer that:
  • Detects whether the pgvector extension is installed in the current DB.
  • Exposes a single helper — pgvector_cosine_search() — that runs cosine
    similarity entirely in Postgres using the native `<=>` operator.
  • Falls back gracefully to NumPy when pgvector is not available (e.g. local
    PG 12 without the extension) so local development is never broken.

Why pgvector?
─────────────
  Old path  : Fetch ALL embedding rows (768 floats × 4 bytes × N rows) to
              Python, then run NumPy matrix multiply.
              → For N=1,000 workers this is ~3 MB transferred, 5-10 ms compute.
              → For N=10,000 workers this is ~30 MB transferred, 50-100 ms.

  New path  : DB computes 1.0 - (vec <=> query) in C (pgvector SIMD kernels).
              Only (pk, float) pairs are returned — ~8 bytes × N rows.
              → 375× less data over the wire; computation is faster in C.
              → With an HNSW index (vector type column) it becomes O(log N).

Architecture
────────────
  • We keep JSONField on the Django models for schema-compatibility across
    environments that lack pgvector.
  • We use RawSQL annotations to cast jsonb → text → vector(dim) on-the-fly
    inside a single SQL query — no column migration required.
  • A lazy singleton (_PGVectorState) checks once per process whether the
    extension is available and caches the result permanently.

Usage
─────
    from jobs.service.pgvector_utils import pgvector_cosine_search

    ranked = pgvector_cosine_search(
        qs=Job.objects.filter(status='active'),
        field='text_embedding',
        dim=768,
        query_vec=query_vec,          # list[float] or np.ndarray
        threshold=0.60,
        limit=50,
    )
    # ranked is list[(pk, float)] sorted by score DESC, or None if pgvector
    # is not available (caller should fall back to NumPy).
"""

import logging
import threading
from typing import List, Optional, Tuple, Union

logger = logging.getLogger(__name__)


# ── Lazy singleton ──────────────────────────────────────────────────────────

class _PGVectorState:
    """Thread-safe lazy check for pgvector extension availability."""

    def __init__(self):
        self._lock       = threading.Lock()
        self._checked    = False
        self._available  = False

    def is_available(self) -> bool:
        if self._checked:
            return self._available
        with self._lock:
            if self._checked:           # double-checked locking
                return self._available
            self._available = self._check_extension()
            self._checked   = True
        return self._available

    def reset(self):
        """Call this in tests or after a migration to re-check."""
        with self._lock:
            self._checked = False

    @staticmethod
    def _check_extension() -> bool:
        try:
            from django.db import connection
            with connection.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM pg_extension WHERE extname = 'vector'"
                )
                available = bool(cur.fetchone())
            if available:
                logger.info(
                    "pgvector_utils: pgvector extension detected — "
                    "using native DB cosine similarity."
                )
            else:
                logger.info(
                    "pgvector_utils: pgvector extension NOT found — "
                    "falling back to NumPy cosine similarity."
                )
            return available
        except Exception as exc:
            logger.warning(
                "pgvector_utils: could not check for pgvector extension (%s) "
                "— assuming unavailable.", exc,
            )
            return False


_state = _PGVectorState()


def pgvector_available() -> bool:
    """Return True if the pgvector PostgreSQL extension is installed."""
    return _state.is_available()


# ── Core helper ─────────────────────────────────────────────────────────────

def _vec_to_pg_literal(vec) -> str:
    """
    Convert a Python list/ndarray to a pgvector literal string.
    e.g.  [0.1, -0.2, 0.3]  →  '[0.1,-0.2,0.3]'
    """
    try:
        import numpy as np
        if isinstance(vec, np.ndarray):
            vec = vec.tolist()
    except ImportError:
        pass
    return '[' + ','.join(f'{v:.8g}' for v in vec) + ']'


def pgvector_cosine_search(
    qs,
    field: str,
    dim: int,
    query_vec,
    threshold: float = 0.60,
    limit: int = 50,
) -> Optional[List[Tuple]]:
    """
    Run cosine similarity search entirely in Postgres using pgvector.

    Annotates `qs` with a `similarity` column (1 - cosine_distance), filters
    by threshold, orders descending, and returns (pk, score) tuples.

    The field must be a JSONField storing a flat float list — it is cast to
    vector(dim) inside the SQL via  field::text::vector(dim).

    Args:
        qs        : Base Django QuerySet (not yet evaluated).
        field     : Name of the JSONField holding the embedding.
        dim       : Embedding dimension (768 for text, 512 for CLIP).
        query_vec : Query embedding — list[float] or np.ndarray.
        threshold : Minimum similarity score to include (default 0.60 = 60%).
        limit     : Maximum number of results to return.

    Returns:
        List of (pk, float) tuples sorted by score DESC, or None if pgvector
        is not available (caller should use NumPy fallback).
    """
    if not pgvector_available():
        return None

    try:
        from django.db.models.expressions import RawSQL

        literal = _vec_to_pg_literal(query_vec)
        # SQL: 1.0 - cosine_distance = cosine_similarity
        # The cast chain jsonb → text → vector(dim) works because
        # PostgreSQL's jsonb array serialises as '[a,b,c]' which is exactly
        # what pgvector's input parser expects.
        similarity_sql = (
            f"1.0 - ({field}::text::vector({dim}) "
            f"<=> %s::vector({dim}))"
        )

        ranked_qs = (
            qs
            .filter(**{f'{field}__isnull': False})
            .annotate(
                _pgv_sim=RawSQL(similarity_sql, (literal,))
            )
            .order_by('-_pgv_sim')
            .values_list('pk', '_pgv_sim')
            [:limit * 2]           # over-fetch slightly to cover threshold filter
        )

        results = [
            (pk, float(sim))
            for pk, sim in ranked_qs
            if float(sim) >= threshold
        ][:limit]

        logger.debug(
            "pgvector_cosine_search: field=%s dim=%d → %d results",
            field, dim, len(results),
        )
        return results

    except Exception as exc:
        logger.warning(
            "pgvector_cosine_search failed (%s) — caller should use NumPy "
            "fallback.", exc,
        )
        return None


def pgvector_batch_text_scores(
    qs,
    field: str,
    dim: int,
    query_vec,
    pk_field: str = 'id',
) -> Optional[dict]:
    """
    Return a dict mapping pk → cosine_similarity for ALL rows in `qs`.

    This is used by the matching service to replace the NumPy matrix multiply:
    instead of fetching all embeddings to Python, the DB computes the scores
    and we only receive (pk, score) pairs.

    Returns None if pgvector is unavailable.
    """
    if not pgvector_available():
        return None

    try:
        from django.db.models.expressions import RawSQL

        literal = _vec_to_pg_literal(query_vec)
        similarity_sql = (
            f"1.0 - ({field}::text::vector({dim}) "
            f"<=> %s::vector({dim}))"
        )

        rows = (
            qs
            .filter(**{f'{field}__isnull': False})
            .annotate(
                _pgv_sim=RawSQL(similarity_sql, (literal,))
            )
            .values_list(pk_field, '_pgv_sim')
        )

        return {str(pk): float(sim) for pk, sim in rows}

    except Exception as exc:
        logger.warning(
            "pgvector_batch_text_scores failed (%s) — caller should use "
            "NumPy fallback.", exc,
        )
        return None
