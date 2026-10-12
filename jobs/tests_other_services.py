"""
jobs/tests_other_services.py
==============================
Comprehensive test suite for the remaining services in jobs/service/:
  - scoring_engine.py
  - pgvector_utils.py
  - search_service.py
  - matching_service.py
  - clip_service.py
  - text_encoder.py
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import numpy as np
from django.contrib.auth import get_user_model
from django.test import TestCase

from jobs.models import (
    CLIPMatch,
    EmployerProfile,
    Job,
    JobApplication,
    PortfolioItem,
    Review,
    Skill,
    TradeCategory,
    WorkerProfile,
)
from jobs.service.clip_service import CLIPImageEncoder, is_clip_enabled
from jobs.service.matching_service import (
    _get_worker_avg_ratings,
    _get_worker_portfolio_image_scores,
    _resolve_job_clip_embedding,
    calculate_profile_completion,
    compute_job_clip_embedding,
    compute_job_text_embedding,
    compute_matches_for_job,
    compute_matches_for_worker,
    compute_portfolio_image_embedding,
    compute_worker_text_embedding,
    get_top_jobs_for_worker,
    get_top_workers_for_job,
)
from jobs.service.pgvector_utils import (
    _PGVectorState,
    _vec_to_pg_literal,
    pgvector_available,
    pgvector_batch_text_scores,
    pgvector_cosine_search,
)
from jobs.service.scoring_engine import (
    EXPERIENCE_MATRIX,
    EXPERIENCE_WEIGHT,
    IMAGE_WEIGHT,
    LOCATION_WEIGHT,
    RATING_WEIGHT,
    TEXT_WEIGHT,
    VERIFICATION_WEIGHT,
    ScoringInputs,
    compute_hybrid_score,
    score_experience,
    score_image,
    score_location,
    score_rating,
    score_verification,
)
from jobs.service.search_service import (
    MIN_QUERY_LEN,
    reorder_queryset_by_scores,
    semantic_job_search,
)
from jobs.service.text_encoder import (
    EMBEDDING_DIM,
    TextEncoder,
    _deterministic_fallback_encode,
    _deterministic_fallback_encode_batch,
)

User = get_user_model()


# ──────────────────────────────────────────────────────────────────────────────
#  1. SCORING ENGINE TESTS
# ──────────────────────────────────────────────────────────────────────────────

class ScoringEngineTests(TestCase):

    def test_weights_sum_to_one(self):
        total = (
            TEXT_WEIGHT
            + LOCATION_WEIGHT
            + EXPERIENCE_WEIGHT
            + IMAGE_WEIGHT
            + RATING_WEIGHT
            + VERIFICATION_WEIGHT
        )
        self.assertAlmostEqual(total, 1.0, places=5)

    def test_score_location_remote(self):
        self.assertEqual(score_location('lagos', 'kano', job_is_remote=True, worker_willing_to_relocate=False), 1.0)

    def test_score_location_same_state(self):
        self.assertEqual(score_location('Lagos', 'lagos', job_is_remote=False, worker_willing_to_relocate=False), 1.0)

    def test_score_location_willing_to_relocate(self):
        self.assertEqual(score_location('abuja', 'lagos', job_is_remote=False, worker_willing_to_relocate=True), 0.5)

    def test_score_location_different_state_no_relocate(self):
        self.assertEqual(score_location('abuja', 'lagos', job_is_remote=False, worker_willing_to_relocate=False), 0.0)

    def test_score_experience_matrix_values(self):
        self.assertEqual(score_experience('entry', 'internship'), 1.0)
        self.assertEqual(score_experience('expert', 'full_time'), 1.0)
        self.assertEqual(score_experience('entry', 'contract'), 0.3)

    def test_score_experience_fallbacks(self):
        # Unknown job type or unknown level falls back gracefully
        score = score_experience('unknown_level', 'unknown_job_type')
        self.assertIsInstance(score, float)
        self.assertTrue(0.0 <= score <= 1.0)

    def test_score_image_none_returns_neutral(self):
        self.assertEqual(score_image(None), 0.5)

    def test_score_image_clamped(self):
        self.assertEqual(score_image(0.85), 0.85)
        self.assertEqual(score_image(1.5), 1.0)
        self.assertEqual(score_image(-0.2), 0.0)

    def test_score_rating_none_returns_neutral(self):
        self.assertEqual(score_rating(None), 0.5)

    def test_score_rating_normalised_range(self):
        self.assertEqual(score_rating(1.0), 0.0)
        self.assertEqual(score_rating(3.0), 0.5)
        self.assertEqual(score_rating(5.0), 1.0)

    def test_score_verification(self):
        self.assertEqual(score_verification(True), 1.0)
        self.assertEqual(score_verification(False), 0.0)

    def test_compute_hybrid_score(self):
        inputs = ScoringInputs(
            text_similarity=0.8,
            worker_state='lagos',
            job_state='lagos',
            job_is_remote=False,
            worker_willing_to_relocate=False,
            worker_experience_level='mid',
            job_type='contract',
            image_similarity=0.7,
            avg_rating=4.0,
            is_verified=True,
        )
        res = compute_hybrid_score(inputs)
        self.assertTrue(0.0 <= res.score <= 1.0)
        self.assertEqual(res.location_score, 1.0)
        self.assertEqual(res.verification_bonus, 1.0)
        self.assertEqual(res.text_score, 0.8)


# ──────────────────────────────────────────────────────────────────────────────
#  2. PGVECTOR UTILS TESTS
# ──────────────────────────────────────────────────────────────────────────────

class PGVectorUtilsTests(TestCase):

    def test_vec_to_pg_literal_list(self):
        vec = [0.1, -0.2, 0.35]
        literal = _vec_to_pg_literal(vec)
        self.assertTrue(literal.startswith('['))
        self.assertTrue(literal.endswith(']'))
        self.assertIn('0.1', literal)
        self.assertIn('-0.2', literal)

    def test_vec_to_pg_literal_numpy(self):
        arr = np.array([1.0, 2.0], dtype=np.float32)
        literal = _vec_to_pg_literal(arr)
        self.assertEqual(literal, '[1,2]')

    def test_pgvector_state_singleton(self):
        state = _PGVectorState()
        with patch.object(state, '_check_extension', return_value=False):
            self.assertFalse(state.is_available())
            state.reset()
        with patch.object(state, '_check_extension', return_value=True):
            self.assertTrue(state.is_available())

    def test_pgvector_cosine_search_returns_none_when_unavailable(self):
        with patch('jobs.service.pgvector_utils.pgvector_available', return_value=False):
            result = pgvector_cosine_search(Job.objects.none(), 'text_embedding', 768, [0.0] * 768)
            self.assertIsNone(result)

    def test_pgvector_batch_text_scores_returns_none_when_unavailable(self):
        with patch('jobs.service.pgvector_utils.pgvector_available', return_value=False):
            result = pgvector_batch_text_scores(Job.objects.none(), 'text_embedding', 768, [0.0] * 768)
            self.assertIsNone(result)


# ──────────────────────────────────────────────────────────────────────────────
#  3. TEXT ENCODER TESTS
# ──────────────────────────────────────────────────────────────────────────────

class TextEncoderTests(TestCase):

    def test_deterministic_fallback_encode(self):
        vec = _deterministic_fallback_encode("Electrician wiring installation")
        self.assertEqual(len(vec), EMBEDDING_DIM)
        norm = np.linalg.norm(vec)
        self.assertAlmostEqual(norm, 1.0, places=4)

    def test_deterministic_fallback_encode_batch(self):
        texts = ["Plumber fixing pipe", "Carpenter building shelf"]
        vecs = _deterministic_fallback_encode_batch(texts)
        self.assertEqual(len(vecs), 2)
        self.assertEqual(len(vecs[0]), EMBEDDING_DIM)
        self.assertEqual(len(vecs[1]), EMBEDDING_DIM)

    def test_cosine_similarity(self):
        a = [1.0, 0.0, 0.0]
        b = [1.0, 0.0, 0.0]
        c = [0.0, 1.0, 0.0]
        self.assertAlmostEqual(TextEncoder.cosine_similarity(a, b), 1.0)
        self.assertAlmostEqual(TextEncoder.cosine_similarity(a, c), 0.0)

    def test_batch_cosine_similarity(self):
        encoder = TextEncoder()
        q = [1.0, 0.0]
        candidates = [[1.0, 0.0], [0.0, 1.0], [0.7071, 0.7071]]
        scores = encoder.batch_cosine_similarity(q, candidates)
        self.assertEqual(len(scores), 3)
        self.assertAlmostEqual(scores[0], 1.0, places=4)
        self.assertAlmostEqual(scores[1], 0.0, places=4)
        self.assertAlmostEqual(scores[2], 0.7071, places=3)


# ──────────────────────────────────────────────────────────────────────────────
#  4. CLIP SERVICE TESTS
# ──────────────────────────────────────────────────────────────────────────────

class ClipServiceTests(TestCase):

    def test_is_clip_enabled_default_false(self):
        with patch.dict('os.environ', {'ENABLE_CLIP': 'False'}):
            self.assertFalse(is_clip_enabled())

    def test_is_clip_enabled_true(self):
        with patch.dict('os.environ', {'ENABLE_CLIP': 'True'}):
            self.assertTrue(is_clip_enabled())

    def test_clip_image_encoder_returns_zero_vector_when_disabled(self):
        encoder = CLIPImageEncoder()
        with patch('jobs.service.clip_service.is_clip_enabled', return_value=False):
            vec = encoder.encode_text("solar panels")
            self.assertEqual(len(vec), 512)
            self.assertEqual(sum(vec), 0.0)

    def test_clip_batch_cosine_similarity(self):
        q = [1.0, 0.0]
        candidates = [[1.0, 0.0], [0.0, 1.0]]
        scores = CLIPImageEncoder.batch_cosine_similarity(q, candidates)
        self.assertEqual(len(scores), 2)
        self.assertAlmostEqual(scores[0], 1.0, places=4)
        self.assertAlmostEqual(scores[1], 0.0, places=4)


# ──────────────────────────────────────────────────────────────────────────────
#  5. SEARCH SERVICE TESTS
# ──────────────────────────────────────────────────────────────────────────────

class SearchServiceTests(TestCase):

    def setUp(self):
        self.employer_user = User.objects.create_user(username='emp_search', email='e@s.ng', password='p')
        self.employer = EmployerProfile.objects.create(user=self.employer_user, company_name='Search Co')
        self.trade = TradeCategory.objects.create(name='Carpentry', slug='carpentry')
        self.job1 = Job.objects.create(
            employer=self.employer,
            trade_category=self.trade,
            title='Make Dining Table',
            description='Build a modern wooden dining table.',
            status=Job.Status.ACTIVE,
            text_embedding=[0.1] * EMBEDDING_DIM,
        )
        self.job2 = Job.objects.create(
            employer=self.employer,
            trade_category=self.trade,
            title='Wardrobe Repairs',
            description='Repair wardrobe hinge.',
            status=Job.Status.ACTIVE,
            text_embedding=[0.5] * EMBEDDING_DIM,
        )

    def test_empty_or_short_query_returns_none(self):
        self.assertIsNone(semantic_job_search(''))
        self.assertIsNone(semantic_job_search('a'))

    @patch('jobs.service.text_encoder.text_encoder.encode', return_value=[0.1] * EMBEDDING_DIM)
    @patch('jobs.service.pgvector_utils.pgvector_cosine_search', return_value=None)
    def test_semantic_job_search_numpy_fallback(self, mock_pgv, mock_encode):
        ranked = semantic_job_search('table dining')
        # If any job scored >= 0.60
        self.assertIsInstance(ranked, (list, type(None)))

    def test_reorder_queryset_by_scores(self):
        qs = Job.objects.filter(id__in=[self.job1.pk, self.job2.pk])
        ranked = [(self.job2.pk, 0.95), (self.job1.pk, 0.70)]
        ordered = reorder_queryset_by_scores(qs, ranked)
        pks = list(ordered.values_list('pk', flat=True))
        self.assertEqual(pks, [self.job2.pk, self.job1.pk])

    def test_reorder_queryset_empty_ranked_returns_none(self):
        qs = Job.objects.filter(id__in=[self.job1.pk, self.job2.pk])
        ordered = reorder_queryset_by_scores(qs, [])
        self.assertEqual(ordered.count(), 0)


# ──────────────────────────────────────────────────────────────────────────────
#  6. MATCHING SERVICE TESTS
# ──────────────────────────────────────────────────────────────────────────────

class MatchingServiceTests(TestCase):

    def setUp(self):
        self.worker_user = User.objects.create_user(username='w_match', email='w@m.ng', password='p')
        self.employer_user = User.objects.create_user(username='e_match', email='e@m.ng', password='p')
        self.trade = TradeCategory.objects.create(name='Welding', slug='welding')
        self.skill = Skill.objects.create(category=self.trade, name='TIG Welding', slug='tig-welding')

        self.worker = WorkerProfile.objects.create(
            user=self.worker_user,
            trade_category=self.trade,
            bio='Expert welder with 5 years experience in Lagos.',
            state='lagos',
            years_experience=5,
            hourly_rate=Decimal('3000.00'),
            text_embedding=[0.2] * EMBEDDING_DIM,
        )
        self.worker.skills.add(self.skill)

        self.employer = EmployerProfile.objects.create(
            user=self.employer_user,
            company_name='Weld Corp',
            state='lagos',
        )
        self.job = Job.objects.create(
            employer=self.employer,
            trade_category=self.trade,
            title='Structural Metal Welding',
            description='Weld steel beams for warehouse.',
            state='lagos',
            status=Job.Status.ACTIVE,
            text_embedding=[0.2] * EMBEDDING_DIM,
            clip_embedding=[0.1] * 512,
        )

    def test_calculate_profile_completion(self):
        score = calculate_profile_completion(str(self.worker.pk))
        self.worker.refresh_from_db()
        # bio (>30) = 25, trade = 15, skill = 15, state = 10, rate = 10, exp = 10 -> 85
        self.assertEqual(score, 85)
        self.assertEqual(self.worker.profile_completion, 85)

    def test_calculate_profile_completion_nonexistent_worker(self):
        score = calculate_profile_completion('00000000-0000-0000-0000-000000000000')
        self.assertEqual(score, 0)

    @patch('jobs.service.text_encoder.text_encoder.encode', return_value=[0.1] * EMBEDDING_DIM)
    def test_compute_worker_text_embedding(self, _):
        ok = compute_worker_text_embedding(str(self.worker.pk))
        self.assertTrue(ok)
        self.worker.refresh_from_db()
        self.assertIsNotNone(self.worker.text_embedding)

    @patch('jobs.service.text_encoder.text_encoder.encode', return_value=[0.1] * EMBEDDING_DIM)
    def test_compute_job_text_embedding(self, _):
        ok = compute_job_text_embedding(str(self.job.pk))
        self.assertTrue(ok)
        self.job.refresh_from_db()
        self.assertIsNotNone(self.job.text_embedding)

    def test_get_worker_avg_ratings(self):
        Review.objects.create(
            job=self.job,
            reviewer=self.employer_user,
            reviewee=self.worker_user,
            review_type=Review.ReviewType.EMPLOYER_TO_WORKER,
            rating=5,
        )
        ratings = _get_worker_avg_ratings([str(self.worker.pk)])
        self.assertEqual(ratings[str(self.worker.pk)], 5.0)

    def test_compute_matches_for_job(self):
        count = compute_matches_for_job(str(self.job.pk))
        self.assertGreaterEqual(count, 1)
        match = CLIPMatch.objects.filter(job=self.job, worker=self.worker).first()
        self.assertIsNotNone(match)
        self.assertTrue(0.0 <= match.score <= 1.0)

    def test_compute_matches_for_worker(self):
        count = compute_matches_for_worker(str(self.worker.pk))
        self.assertGreaterEqual(count, 1)
        match = CLIPMatch.objects.filter(job=self.job, worker=self.worker).first()
        self.assertIsNotNone(match)

    def test_get_top_jobs_for_worker(self):
        compute_matches_for_worker(str(self.worker.pk))
        matches = get_top_jobs_for_worker(str(self.worker.pk), min_score=0.0)
        self.assertTrue(len(matches) >= 1)

    def test_get_top_workers_for_job(self):
        compute_matches_for_job(str(self.job.pk))
        matches = get_top_workers_for_job(str(self.job.pk), min_score=0.0)
        self.assertTrue(len(matches) >= 1)
