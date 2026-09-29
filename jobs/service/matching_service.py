"""
jobs/service/matching_service.py
=================================
Hybrid matching service — orchestrates text_encoder, clip_image_encoder,
and scoring_engine to compute and persist CLIPMatch rows.

This is the only file that knows about the database AND the ML services.
Neither the models, nor the encoders, nor the scoring engine import from here.

Embedding strategy
──────────────────
  Two separate encoders, two separate embedding fields per model:

  sentence-transformers (text ↔ text)
  ────────────────────────────────────
    WorkerProfile.text_embedding   768-dim  bio + trade + skills
    Job.text_embedding             768-dim  title + trade + skills + description
    → Used for 50 % text_score in hybrid engine.

  CLIP (image ↔ text, cross-modal only)
  ──────────────────────────────────────
    PortfolioItem.clip_image_embedding  512-dim  portfolio photo
    Job.clip_embedding                  512-dim  CLIP text encoding of job
    → Used for 10 % image_score: portfolio photos vs job CLIP text.
    → WorkerProfile has NO CLIP text embedding — workers are matched
      to jobs purely by sentence-transformer text similarity; CLIP is
      only used to compare a worker's VISUAL portfolio against the job.

Data flow
─────────
  compute_worker_text_embedding(id)
      └─ text_encoder.encode(worker.get_clip_input_text())
         └─ WorkerProfile.text_embedding saved

  compute_job_text_embedding(id)
      └─ text_encoder.encode(job.get_clip_input_text())
         └─ Job.text_embedding saved

  compute_job_clip_embedding(id)          ← NEW — replaces on-the-fly recompute
      └─ clip_image_encoder.encode_text_for_image_comparison(job text)
         └─ Job.clip_embedding saved (512-dim, used for portfolio comparison)

  compute_portfolio_image_embedding(id)
      └─ clip_image_encoder.encode_image_file(item.image.path)
         └─ PortfolioItem.clip_image_embedding saved

  compute_matches_for_job(job_id)
      ┌─ Fetch job.text_embedding  (sentence-transformer)
      ├─ Fetch job.clip_embedding  (CLIP text, for image cross-modal)
      ├─ Fetch all workers in same trade with text_embedding
      ├─ text_encoder.batch_cosine_similarity  → text scores (vectorised)
      ├─ _get_worker_portfolio_image_scores()  → CLIP image scores (stored)
      ├─ _get_worker_avg_ratings()             → rating scores (single query)
      ├─ scoring_engine.compute_hybrid_score() → final weighted score
      └─ CLIPMatch bulk upsert (one transaction)

  compute_matches_for_worker(worker_id)
      └─ same flow, reversed (worker's embedding vs all active job embeddings)
"""

import logging
from typing import Dict, List, Optional

import numpy as np
from django.db import transaction
from django.db.models import Avg
from django.utils import timezone

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
#  EMBEDDING COMPUTATION
# ──────────────────────────────────────────────────────────────────────────────

def compute_worker_text_embedding(worker_profile_id: str) -> bool:
    """
    Encode a WorkerProfile's text with sentence-transformers and persist it.
    Returns True on success, False on failure.
    """
    from jobs.models import WorkerProfile
    from jobs.service.text_encoder import text_encoder

    try:
        worker = (
            WorkerProfile.objects
            .select_related('trade_category')
            .prefetch_related('skills')
            .get(pk=worker_profile_id)
        )
    except WorkerProfile.DoesNotExist:
        logger.warning(
            "compute_worker_text_embedding: WorkerProfile %s not found.",
            worker_profile_id,
        )
        return False

    text = worker.get_clip_input_text()
    if not text.strip():
        logger.info(
            "compute_worker_text_embedding: Worker %s has no text — skipping.",
            worker_profile_id,
        )
        return False

    logger.info(
        "Worker %s — sentence-transformer input preview:\n  %s…",
        worker_profile_id, text[:120],
    )

    try:
        embedding = text_encoder.encode(text)
        WorkerProfile.objects.filter(pk=worker_profile_id).update(
            text_embedding=embedding,
            text_embedding_updated=timezone.now(),
        )
        logger.info(
            "Worker text embedding updated: %s  (dim=%d)",
            worker_profile_id, len(embedding),
        )
        return True
    except Exception as exc:
        logger.exception(
            "compute_worker_text_embedding failed for %s: %s",
            worker_profile_id, exc,
        )
        return False


# Alias so tasks.py import stays unchanged
compute_worker_embedding = compute_worker_text_embedding


def compute_job_text_embedding(job_id: str) -> bool:
    """
    Encode a Job's text with sentence-transformers (768-dim) and persist it.
    This is the PRIMARY embedding used for text ↔ text similarity.
    Returns True on success, False on failure.
    """
    from jobs.models import Job
    from jobs.service.text_encoder import text_encoder

    try:
        job = (
            Job.objects
            .select_related('trade_category')
            .prefetch_related('required_skills')
            .get(pk=job_id)
        )
    except Job.DoesNotExist:
        logger.warning("compute_job_text_embedding: Job %s not found.", job_id)
        return False

    text = job.get_clip_input_text()
    if not text.strip():
        logger.info(
            "compute_job_text_embedding: Job %s has no text — skipping.", job_id
        )
        return False

    logger.info(
        "Job %s — sentence-transformer input preview:\n  %s…",
        job_id, text[:120],
    )

    try:
        embedding = text_encoder.encode(text)
        Job.objects.filter(pk=job_id).update(
            text_embedding=embedding,
            text_embedding_updated=timezone.now(),
        )
        logger.info(
            "Job text embedding updated: %s  (dim=%d)",
            job_id, len(embedding),
        )
        return True
    except Exception as exc:
        logger.exception(
            "compute_job_text_embedding failed for %s: %s", job_id, exc
        )
        return False


# Alias so tasks.py import stays unchanged
compute_job_embedding = compute_job_text_embedding


def compute_job_clip_embedding(job_id: str) -> bool:
    """
    Encode a Job's text with CLIP's text encoder (512-dim) and persist it
    in Job.clip_embedding.

    This is a SEPARATE embedding from text_embedding (sentence-transformer).
    Its only purpose is cross-modal comparison: job description text vs
    worker portfolio IMAGES — both must be in CLIP's shared vector space.

    Called by compute_job_embedding_task after compute_job_text_embedding.
    Returns True on success, False on failure.
    """
    from jobs.models import Job
    from jobs.service.clip_service import clip_image_encoder

    try:
        job = (
            Job.objects
            .select_related('trade_category')
            .prefetch_related('required_skills')
            .get(pk=job_id)
        )
    except Job.DoesNotExist:
        logger.warning("compute_job_clip_embedding: Job %s not found.", job_id)
        return False

    # Use the same rich text as sentence-transformer but cap at 300 chars —
    # CLIP's text encoder truncates at 77 tokens anyway.
    text = job.get_clip_input_text()[:300]
    if not text.strip():
        logger.info(
            "compute_job_clip_embedding: Job %s has no text — skipping.", job_id
        )
        return False

    logger.info(
        "Job %s — CLIP input text preview:\n  %s…",
        job_id, text[:120],
    )

    try:
        embedding = clip_image_encoder.encode_text_for_image_comparison(text)
        Job.objects.filter(pk=job_id).update(
            clip_embedding=embedding,
            clip_embedding_updated=timezone.now(),
        )
        logger.info(
            "Job CLIP embedding updated: %s  (dim=%d)",
            job_id, len(embedding),
        )
        return True
    except Exception as exc:
        logger.exception(
            "compute_job_clip_embedding failed for %s: %s", job_id, exc
        )
        return False


def compute_portfolio_image_embedding(portfolio_item_id: str) -> bool:
    """
    Encode a PortfolioItem image with CLIP's visual encoder and persist it.
    Returns True on success, False on failure.
    """
    from jobs.models import PortfolioItem
    from jobs.service.clip_service import clip_image_encoder

    try:
        item = PortfolioItem.objects.get(pk=portfolio_item_id)
    except PortfolioItem.DoesNotExist:
        logger.warning(
            "compute_portfolio_image_embedding: PortfolioItem %s not found.",
            portfolio_item_id,
        )
        return False

    if not item.image:
        logger.info(
            "compute_portfolio_image_embedding: item %s has no image.",
            portfolio_item_id,
        )
        return False

    try:
        logger.info(
            "Portfolio item %s — encoding image: %s",
            portfolio_item_id, item.image.name,
        )
        embedding = clip_image_encoder.encode_image_file(item.image.path)
        PortfolioItem.objects.filter(pk=portfolio_item_id).update(
            clip_image_embedding=embedding,
        )
        logger.info(
            "Portfolio image embedding updated: %s  (dim=%d)",
            portfolio_item_id, len(embedding),
        )
        return True
    except Exception as exc:
        logger.exception(
            "compute_portfolio_image_embedding failed for %s: %s",
            portfolio_item_id, exc,
        )
        return False


# ──────────────────────────────────────────────────────────────────────────────
#  INTERNAL HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def _get_worker_avg_ratings(worker_ids: List[str]) -> Dict[str, Optional[float]]:
    """
    Returns {worker_id: avg_rating} for all given worker IDs.
    Workers with no reviews get None.
    Single DB query using aggregate — does not N+1.
    """
    from jobs.models import Review

    rows = (
        Review.objects
        .filter(
            reviewee__worker_profile__id__in=worker_ids,
            review_type=Review.ReviewType.EMPLOYER_TO_WORKER,
            is_visible=True,
        )
        .values('reviewee__worker_profile__id')
        .annotate(avg=Avg('rating'))
    )

    result = {wid: None for wid in worker_ids}
    for row in rows:
        wid = str(row['reviewee__worker_profile__id'])
        result[wid] = row['avg']
    return result


def _get_worker_portfolio_image_scores(
    worker_ids: List[str],
    job_clip_embedding: Optional[List[float]],
) -> Dict[str, Optional[float]]:
    """
    For each worker, compute the average CLIP cosine similarity between their
    portfolio images and the job's stored CLIP text embedding.

    This is the cross-modal signal: job description text ↔ worker portfolio image.
    Both vectors live in CLIP's 512-dim space — cosine similarity is meaningful.

    If the job has no CLIP embedding, or a worker has no portfolio images with
    embeddings, returns None for that worker.  scoring_engine treats None as 0.5
    (neutral) so workers without portfolios are not penalised.
    """
    from jobs.models import PortfolioItem
    from jobs.service.clip_service import clip_image_encoder

    result: Dict[str, Optional[float]] = {wid: None for wid in worker_ids}

    if not job_clip_embedding:
        return result

    portfolio_rows = list(
        PortfolioItem.objects
        .filter(
            worker_id__in=worker_ids,
            clip_image_embedding__isnull=False,
        )
        .values('worker_id', 'clip_image_embedding')
    )

    if not portfolio_rows:
        return result

    # Group by worker
    worker_images: Dict[str, List[List[float]]] = {}
    for row in portfolio_rows:
        wid = str(row['worker_id'])
        worker_images.setdefault(wid, []).append(row['clip_image_embedding'])

    for wid, image_embeddings in worker_images.items():
        scores = clip_image_encoder.batch_cosine_similarity(
            job_clip_embedding, image_embeddings
        )
        result[wid] = float(np.mean(scores))

    return result


def _resolve_job_clip_embedding(
    job_id: str,
    stored_embedding: Optional[List[float]],
) -> Optional[List[float]]:
    """
    Returns the CLIP text embedding for a job used in cross-modal comparison.

    Prefers the stored Job.clip_embedding (fast, no inference).
    Falls back to on-the-fly CLIP encoding only if the stored value is missing
    (e.g. the CLIP embedding task hasn't run yet for this job).

    The fallback result is NOT persisted here — compute_job_clip_embedding()
    should be called to store it properly.
    """
    if stored_embedding:
        return stored_embedding

    # Fallback: compute on-the-fly (slower — model inference)
    from jobs.models import Job
    from jobs.service.clip_service import clip_image_encoder

    logger.warning(
        "Job %s has no stored CLIP embedding — computing on-the-fly. "
        "Run compute_job_clip_embedding() to cache it.",
        job_id,
    )
    job = Job.objects.filter(pk=job_id).values('title', 'description').first()
    if not job:
        return None
    text = f"{job['title']}. {job['description']}"[:300]
    try:
        return clip_image_encoder.encode_text_for_image_comparison(text)
    except Exception as exc:
        logger.warning(
            "Fallback CLIP encoding failed for job %s: %s", job_id, exc
        )
        return None


# ──────────────────────────────────────────────────────────────────────────────
#  MATCH COMPUTATION  (the core of the hybrid engine)
# ──────────────────────────────────────────────────────────────────────────────

def compute_matches_for_job(job_id: str) -> int:
    """
    Compute hybrid CLIPMatch rows for all workers in the same trade as a job.

    Steps:
      1.  Load job — both text_embedding (768-dim) and clip_embedding (512-dim).
      2.  Load all workers in same trade with text_embedding.
      3.  Vectorised text cosine similarity (one matrix multiply).
      4.  Get CLIP cross-modal image scores per worker (uses stored clip_embedding).
      5.  Get avg ratings per worker (one DB query).
      6.  For each worker: call scoring_engine.compute_hybrid_score().
      7.  Bulk upsert all CLIPMatch rows in one transaction.

    Returns number of CLIPMatch rows written.
    """
    from jobs.models import Job, WorkerProfile, CLIPMatch
    from jobs.service.text_encoder import text_encoder
    from jobs.service.scoring_engine import ScoringInputs, compute_hybrid_score

    # ── 1. Load job ──────────────────────────────────────────────────────────
    try:
        job = (
            Job.objects
            .select_related('trade_category', 'employer')
            .get(pk=job_id)
        )
    except Job.DoesNotExist:
        logger.warning("compute_matches_for_job: Job %s not found.", job_id)
        return 0

    if not job.text_embedding:
        logger.warning(
            "compute_matches_for_job: Job %s has no text_embedding — "
            "run compute_job_text_embedding() first.", job_id
        )
        return 0

    # Resolve CLIP embedding (stored preferred, on-the-fly fallback)
    job_clip_emb = _resolve_job_clip_embedding(job_id, job.clip_embedding)

    # ── 2. Load workers ──────────────────────────────────────────────────────
    workers = list(
        WorkerProfile.objects
        .filter(
            trade_category=job.trade_category,
            text_embedding__isnull=False,
        )
        .values(
            'id', 'text_embedding', 'state', 'is_willing_to_relocate',
            'experience_level', 'is_verified',
        )
    )

    if not workers:
        logger.info(
            "compute_matches_for_job: no embedded workers for trade %s.",
            job.trade_category,
        )
        return 0

    worker_ids = [str(w['id']) for w in workers]
    embeddings = [w['text_embedding'] for w in workers]

    # ── 3. Vectorised text similarity (sentence-transformers) ────────────────
    text_scores = text_encoder.batch_cosine_similarity(job.text_embedding, embeddings)

    # ── 4. Portfolio image scores (CLIP cross-modal) ─────────────────────────
    image_scores_map = _get_worker_portfolio_image_scores(worker_ids, job_clip_emb)

    # ── 5. Avg ratings ───────────────────────────────────────────────────────
    rating_map = _get_worker_avg_ratings(worker_ids)

    # ── 6. Compute hybrid scores ─────────────────────────────────────────────
    now           = timezone.now()
    score_results = []

    for worker, text_score in zip(workers, text_scores):
        wid = str(worker['id'])
        inputs = ScoringInputs(
            text_similarity=float(text_score),
            worker_state=worker['state'] or '',
            job_state=job.state or '',
            job_is_remote=job.is_remote,
            worker_willing_to_relocate=worker['is_willing_to_relocate'],
            worker_experience_level=worker['experience_level'] or 'mid',
            job_type=job.job_type or 'once_off',
            image_similarity=image_scores_map.get(wid),
            avg_rating=rating_map.get(wid),
            is_verified=worker['is_verified'],
        )
        result = compute_hybrid_score(inputs)
        score_results.append((wid, result))

    # ── 7. Bulk upsert ───────────────────────────────────────────────────────
    created = 0
    with transaction.atomic():
        existing = {
            str(m.worker_id): m
            for m in CLIPMatch.objects.filter(job_id=job_id, worker_id__in=worker_ids)
        }

        to_create, to_update = [], []

        for wid, res in score_results:
            if wid in existing:
                m = existing[wid]
                m.score              = res.score
                m.text_score         = res.text_score
                m.image_score        = res.image_score
                m.location_score     = res.location_score
                m.experience_score   = res.experience_score
                m.rating_score       = res.rating_score
                m.verification_bonus = res.verification_bonus
                m.computed_at        = now
                to_update.append(m)
            else:
                to_create.append(CLIPMatch(
                    worker_id=wid, job_id=job_id,
                    score=res.score,
                    text_score=res.text_score,
                    image_score=res.image_score,
                    location_score=res.location_score,
                    experience_score=res.experience_score,
                    rating_score=res.rating_score,
                    verification_bonus=res.verification_bonus,
                    computed_at=now,
                ))

        if to_create:
            CLIPMatch.objects.bulk_create(to_create, ignore_conflicts=True)
            created = len(to_create)
        if to_update:
            CLIPMatch.objects.bulk_update(to_update, [
                'score', 'text_score', 'image_score', 'location_score',
                'experience_score', 'rating_score', 'verification_bonus', 'computed_at',
            ])

    total = created + len(to_update)
    logger.info(
        "compute_matches_for_job: %d rows written for job %s (%d new, %d updated).",
        total, job_id, created, len(to_update),
    )
    return total


def compute_matches_for_worker(worker_profile_id: str) -> int:
    """
    Compute hybrid CLIPMatch rows for all active jobs in the worker's trade.
    Mirror of compute_matches_for_job with worker as the anchor.

    Steps:
      1.  Load worker — text_embedding (768-dim) and portfolio image embeddings.
      2.  Load all active jobs in same trade with text_embedding + clip_embedding.
      3.  Vectorised text cosine similarity (sentence-transformers).
      4.  Per job: CLIP cross-modal score using stored job.clip_embedding.
      5.  Worker's single avg rating (reused across all jobs).
      6.  compute_hybrid_score() for each job.
      7.  Bulk upsert CLIPMatch rows.

    Returns number of CLIPMatch rows written.
    """
    from jobs.models import WorkerProfile, Job, CLIPMatch, Review
    from jobs.service.text_encoder import text_encoder
    from jobs.service.clip_service import clip_image_encoder
    from jobs.service.scoring_engine import ScoringInputs, compute_hybrid_score

    # ── 1. Load worker ───────────────────────────────────────────────────────
    try:
        worker = (
            WorkerProfile.objects
            .select_related('trade_category')
            .get(pk=worker_profile_id)
        )
    except WorkerProfile.DoesNotExist:
        logger.warning(
            "compute_matches_for_worker: WorkerProfile %s not found.",
            worker_profile_id,
        )
        return 0

    if not worker.text_embedding:
        logger.warning(
            "compute_matches_for_worker: Worker %s has no text_embedding — "
            "run compute_worker_text_embedding() first.", worker_profile_id
        )
        return 0

    # ── 2. Load active jobs — include clip_embedding ─────────────────────────
    jobs = list(
        Job.objects
        .filter(
            trade_category=worker.trade_category,
            status=Job.Status.ACTIVE,
            text_embedding__isnull=False,
        )
        .values(
            'id', 'text_embedding', 'clip_embedding',
            'state', 'is_remote', 'job_type', 'title', 'description',
        )
    )

    if not jobs:
        logger.info(
            "compute_matches_for_worker: no active embedded jobs for trade %s.",
            worker.trade_category,
        )
        return 0

    job_ids    = [str(j['id']) for j in jobs]
    embeddings = [j['text_embedding'] for j in jobs]

    # ── 3. Vectorised text similarity (sentence-transformers) ────────────────
    text_scores = text_encoder.batch_cosine_similarity(worker.text_embedding, embeddings)

    # ── 4. Worker avg rating (single value — reused across all jobs) ─────────
    avg_rating_row = (
        Review.objects
        .filter(
            reviewee=worker.user,
            review_type=Review.ReviewType.EMPLOYER_TO_WORKER,
            is_visible=True,
        )
        .aggregate(avg=Avg('rating'))
    )
    avg_rating = avg_rating_row.get('avg')

    # ── 5. Worker portfolio image embeddings (for CLIP cross-modal) ──────────
    portfolio_items = list(
        worker.portfolio
        .filter(clip_image_embedding__isnull=False)
        .values_list('clip_image_embedding', flat=True)
    )

    # ── 6. Compute hybrid scores ─────────────────────────────────────────────
    now           = timezone.now()
    score_results = []

    for job_data, text_score in zip(jobs, text_scores):
        jid = str(job_data['id'])

        # Cross-modal image score: worker portfolio images vs this job's CLIP text.
        # Use stored clip_embedding (fast). Fall back to on-the-fly only if missing.
        image_similarity = None
        if portfolio_items:
            job_clip_emb = _resolve_job_clip_embedding(
                jid, job_data.get('clip_embedding')
            )
            if job_clip_emb:
                try:
                    scores = clip_image_encoder.batch_cosine_similarity(
                        job_clip_emb, portfolio_items
                    )
                    image_similarity = float(np.mean(scores))
                except Exception as exc:
                    logger.warning(
                        "Image score failed for job %s / worker %s: %s",
                        jid, worker_profile_id, exc,
                    )

        inputs = ScoringInputs(
            text_similarity=float(text_score),
            worker_state=worker.state or '',
            job_state=job_data['state'] or '',
            job_is_remote=job_data['is_remote'],
            worker_willing_to_relocate=worker.is_willing_to_relocate,
            worker_experience_level=worker.experience_level or 'mid',
            job_type=job_data['job_type'] or 'once_off',
            image_similarity=image_similarity,
            avg_rating=avg_rating,
            is_verified=worker.is_verified,
        )
        result = compute_hybrid_score(inputs)
        score_results.append((jid, result))

    # ── 7. Bulk upsert ───────────────────────────────────────────────────────
    created = 0
    with transaction.atomic():
        existing = {
            str(m.job_id): m
            for m in CLIPMatch.objects.filter(
                worker_id=worker_profile_id, job_id__in=job_ids
            )
        }

        to_create, to_update = [], []

        for jid, res in score_results:
            if jid in existing:
                m = existing[jid]
                m.score              = res.score
                m.text_score         = res.text_score
                m.image_score        = res.image_score
                m.location_score     = res.location_score
                m.experience_score   = res.experience_score
                m.rating_score       = res.rating_score
                m.verification_bonus = res.verification_bonus
                m.computed_at        = now
                to_update.append(m)
            else:
                to_create.append(CLIPMatch(
                    worker_id=worker_profile_id, job_id=jid,
                    score=res.score,
                    text_score=res.text_score,
                    image_score=res.image_score,
                    location_score=res.location_score,
                    experience_score=res.experience_score,
                    rating_score=res.rating_score,
                    verification_bonus=res.verification_bonus,
                    computed_at=now,
                ))

        if to_create:
            CLIPMatch.objects.bulk_create(to_create, ignore_conflicts=True)
            created = len(to_create)
        if to_update:
            CLIPMatch.objects.bulk_update(to_update, [
                'score', 'text_score', 'image_score', 'location_score',
                'experience_score', 'rating_score', 'verification_bonus', 'computed_at',
            ])

    total = created + len(to_update)
    logger.info(
        "compute_matches_for_worker: %d rows written for worker %s (%d new, %d updated).",
        total, worker_profile_id, created, len(to_update),
    )
    return total


# ──────────────────────────────────────────────────────────────────────────────
#  QUERY HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def get_top_jobs_for_worker(
    worker_profile_id: str,
    limit: int = 20,
    min_score: float = 0.45,
) -> list:
    from jobs.models import CLIPMatch, Job
    return (
        CLIPMatch.objects
        .filter(
            worker_id=worker_profile_id,
            job__status=Job.Status.ACTIVE,
            score__gte=min_score,
            is_applied=False,
        )
        .select_related('job__employer', 'job__trade_category')
        .order_by('-score')[:limit]
    )


def get_top_workers_for_job(
    job_id: str,
    limit: int = 20,
    min_score: float = 0.45,
) -> list:
    from jobs.models import CLIPMatch
    return (
        CLIPMatch.objects
        .filter(job_id=job_id, score__gte=min_score)
        .select_related('worker__user', 'worker__trade_category')
        .prefetch_related('worker__skills')
        .order_by('-score')[:limit]
    )


# ──────────────────────────────────────────────────────────────────────────────
#  PROFILE COMPLETION
# ──────────────────────────────────────────────────────────────────────────────

def calculate_profile_completion(worker_profile_id: str) -> int:
    """
    Calculates and saves WorkerProfile.profile_completion (0–100).

    Scoring:
        bio (>30 chars)           25 pts
        trade_category set        15 pts
        at least 1 skill          15 pts
        state set                 10 pts
        hourly or daily rate set  10 pts
        at least 1 portfolio item 15 pts
        years_experience > 0      10 pts
    """
    from jobs.models import WorkerProfile

    try:
        worker = WorkerProfile.objects.get(pk=worker_profile_id)
    except WorkerProfile.DoesNotExist:
        return 0

    score = 0
    if worker.bio and len(worker.bio.strip()) > 30:               score += 25
    if worker.trade_category_id:                                   score += 15
    if worker.skills.exists():                                     score += 15
    if worker.state:                                               score += 10
    if worker.hourly_rate or worker.daily_rate:                    score += 10
    if worker.portfolio.exists():                                  score += 15
    if worker.years_experience and worker.years_experience > 0:   score += 10

    WorkerProfile.objects.filter(pk=worker_profile_id).update(
        profile_completion=score
    )
    return score