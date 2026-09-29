"""
jobs/service/scoring_engine.py
================================
Pure hybrid scoring engine — no I/O, no database, no ML models.

This module takes pre-computed component values and returns a final
weighted score.  Keeping it I/O-free means:
  • It's trivially unit-testable (no mocks needed).
  • Weights can be tuned without touching the embedding or DB code.
  • The scoring logic is readable in one place.

Hybrid scoring formula
──────────────────────

  final_score = clamp(
      TEXT_WEIGHT        × text_score
    + LOCATION_WEIGHT    × location_score
    + EXPERIENCE_WEIGHT  × experience_score
    + IMAGE_WEIGHT       × image_score
    + RATING_WEIGHT      × rating_score
    + VERIFICATION_WEIGHT × verification_bonus
  , 0.0, 1.0)

  Weights sum to 1.0.  They are intentionally configurable — you can tune
  them once you have real application/hire data.

Component signal guide
──────────────────────
  text_score (0–1)
      Cosine similarity between sentence-transformer embeddings of the worker's
      bio+skills and the job's title+description+skills.  This is the dominant
      signal.  A score of 0.75+ is a strong semantic match.

  location_score (0.0 / 0.5 / 1.0)
      1.0  — Worker's state == Job's state (or job is remote)
      0.5  — Worker is willing to relocate
      0.0  — Different state and not willing to relocate

  experience_score (0–1)
      Measures how well the worker's experience level fits the job type.
      Internship jobs prefer entry-level.  Full-time contracts prefer
      experienced/expert workers.  See EXPERIENCE_MATRIX below.

  image_score (0–1)
      Average CLIP cosine similarity between the worker's portfolio images and
      the CLIP text encoding of the job description.  Defaults to 0.5 (neutral)
      if the worker has no portfolio — this avoids penalising workers who
      haven't uploaded photos yet.

  rating_score (0–1)
      (average_star_rating - 1) / 4, normalised to [0, 1].
      Defaults to 0.5 for workers with no reviews yet (neutral, not punishing).

  verification_bonus (0.0 / 1.0)
      1.0 if the worker's account is admin-verified, 0.0 otherwise.
      This is a trust signal, not a quality signal — it nudges verified workers
      higher in rankings to incentivise verification.
"""

from dataclasses import dataclass
from typing import Optional


# ──────────────────────────────────────────────────────────────────────────────
#  WEIGHTS  (must sum to 1.0)
# ──────────────────────────────────────────────────────────────────────────────

TEXT_WEIGHT         = 0.50
LOCATION_WEIGHT     = 0.15
EXPERIENCE_WEIGHT   = 0.15
IMAGE_WEIGHT        = 0.10
RATING_WEIGHT       = 0.05
VERIFICATION_WEIGHT = 0.05

assert abs(
    TEXT_WEIGHT + LOCATION_WEIGHT + EXPERIENCE_WEIGHT +
    IMAGE_WEIGHT + RATING_WEIGHT + VERIFICATION_WEIGHT - 1.0
) < 1e-9, "Weights must sum to 1.0"


# ──────────────────────────────────────────────────────────────────────────────
#  EXPERIENCE MATRIX
#  Maps (job_type, worker_experience_level) → score ∈ [0.0, 1.0]
# ──────────────────────────────────────────────────────────────────────────────
#
#  Worker levels:  entry | mid | experienced | expert
#  Job types:      internship | once_off | part_time | contract | full_time
#

EXPERIENCE_MATRIX = {
    #              entry  mid   experienced  expert
    'internship': {
        'entry':       1.0,
        'mid':         0.8,
        'experienced': 0.5,
        'expert':      0.3,
    },
    'once_off': {
        # One-off gigs can use anyone — neutral across all levels
        'entry':       0.7,
        'mid':         0.8,
        'experienced': 0.9,
        'expert':      0.8,
    },
    'part_time': {
        'entry':       0.6,
        'mid':         1.0,
        'experienced': 0.9,
        'expert':      0.7,
    },
    'contract': {
        'entry':       0.3,
        'mid':         0.7,
        'experienced': 1.0,
        'expert':      1.0,
    },
    'full_time': {
        'entry':       0.3,
        'mid':         0.7,
        'experienced': 1.0,
        'expert':      1.0,
    },
}

# Fallback row used when job_type is unknown
_NEUTRAL_EXPERIENCE = {
    'entry': 0.6, 'mid': 0.75, 'experienced': 0.9, 'expert': 0.9,
}


# ──────────────────────────────────────────────────────────────────────────────
#  DATA CLASS — holds all component inputs
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class ScoringInputs:
    """
    All inputs needed to compute one (worker, job) hybrid score.

    Passed from matching_service.py into compute_hybrid_score().
    """
    # ── Text similarity ──────────────────────────────────────────────────────
    text_similarity: float           # cosine sim from sentence-transformers (0–1)

    # ── Location ────────────────────────────────────────────────────────────
    worker_state: str                # e.g. 'lagos'
    job_state: str                   # e.g. 'lagos'
    job_is_remote: bool
    worker_willing_to_relocate: bool

    # ── Experience ──────────────────────────────────────────────────────────
    worker_experience_level: str     # 'entry' | 'mid' | 'experienced' | 'expert'
    job_type: str                    # 'full_time' | 'once_off' | etc.

    # ── Image ───────────────────────────────────────────────────────────────
    image_similarity: Optional[float] = None   # None = no portfolio

    # ── Rating ──────────────────────────────────────────────────────────────
    avg_rating: Optional[float] = None         # None = no reviews yet

    # ── Verification ────────────────────────────────────────────────────────
    is_verified: bool = False


# ──────────────────────────────────────────────────────────────────────────────
#  COMPONENT CALCULATORS  (pure functions, easily unit-testable)
# ──────────────────────────────────────────────────────────────────────────────

def score_location(
    worker_state: str,
    job_state: str,
    job_is_remote: bool,
    worker_willing_to_relocate: bool,
) -> float:
    """
    Returns a location compatibility score.

    Rules (applied in order):
      1. Remote job → 1.0 (location irrelevant)
      2. Same state → 1.0 (perfect local match)
      3. Worker willing to relocate → 0.5 (possible but not ideal)
      4. Different state, not willing → 0.0 (unlikely hire)
    """
    if job_is_remote:
        return 1.0
    if worker_state and job_state and worker_state.lower() == job_state.lower():
        return 1.0
    if worker_willing_to_relocate:
        return 0.5
    return 0.0


def score_experience(worker_experience_level: str, job_type: str) -> float:
    """
    Returns an experience compatibility score using EXPERIENCE_MATRIX.
    Falls back to neutral scores for unknown job types or experience levels.
    """
    level = (worker_experience_level or 'mid').lower()
    jtype = (job_type or 'once_off').lower()

    row = EXPERIENCE_MATRIX.get(jtype, _NEUTRAL_EXPERIENCE)
    return row.get(level, 0.6)


def score_image(image_similarity: Optional[float]) -> float:
    """
    Returns the image signal score.

    If image_similarity is None (worker has no portfolio), return 0.5 —
    a neutral score that neither rewards nor punishes the worker.
    """
    if image_similarity is None:
        return 0.5
    return max(0.0, min(1.0, float(image_similarity)))


def score_rating(avg_rating: Optional[float]) -> float:
    """
    Normalises a 1–5 star rating to [0.0, 1.0].

    Formula: (avg - 1) / 4
      1★ → 0.00   (terrible)
      3★ → 0.50   (average)
      5★ → 1.00   (excellent)

    If avg_rating is None (no reviews yet), return 0.50 — neutral.
    """
    if avg_rating is None:
        return 0.5
    avg_rating = max(1.0, min(5.0, float(avg_rating)))
    return (avg_rating - 1.0) / 4.0


def score_verification(is_verified: bool) -> float:
    """Returns 1.0 for verified workers, 0.0 otherwise."""
    return 1.0 if is_verified else 0.0


# ──────────────────────────────────────────────────────────────────────────────
#  MAIN ENTRY POINT
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class HybridScoreResult:
    """
    Returned by compute_hybrid_score().
    Contains both the final score and every component for storage/explainability.
    """
    score:              float    # final weighted hybrid score (0–1)
    text_score:         float
    location_score:     float
    experience_score:   float
    image_score:        float
    rating_score:       float
    verification_bonus: float


def compute_hybrid_score(inputs: ScoringInputs) -> HybridScoreResult:
    """
    Combines all six signals into one hybrid score.

    Args:
        inputs: A ScoringInputs dataclass with all pre-computed values.

    Returns:
        HybridScoreResult with the final score and all component values.
    """
    text_s    = max(0.0, min(1.0, float(inputs.text_similarity)))
    loc_s     = score_location(
                    inputs.worker_state,
                    inputs.job_state,
                    inputs.job_is_remote,
                    inputs.worker_willing_to_relocate,
                )
    exp_s     = score_experience(inputs.worker_experience_level, inputs.job_type)
    img_s     = score_image(inputs.image_similarity)
    rat_s     = score_rating(inputs.avg_rating)
    ver_s     = score_verification(inputs.is_verified)

    final = (
        TEXT_WEIGHT         * text_s
        + LOCATION_WEIGHT   * loc_s
        + EXPERIENCE_WEIGHT * exp_s
        + IMAGE_WEIGHT      * img_s
        + RATING_WEIGHT     * rat_s
        + VERIFICATION_WEIGHT * ver_s
    )
    final = round(max(0.0, min(1.0, final)), 6)

    return HybridScoreResult(
        score=final,
        text_score=round(text_s, 6),
        location_score=round(loc_s, 6),
        experience_score=round(exp_s, 6),
        image_score=round(img_s, 6),
        rating_score=round(rat_s, 6),
        verification_bonus=round(ver_s, 6),
    )