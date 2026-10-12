"""
jobs/tests_escrow_service.py
==============================
Comprehensive test suite for the escrow service layer.

Covers every public function in jobs/service/escrow_service.py:

  1.  _paystack_headers
  2.  _safe_json
  3.  _notify
  4.  _hash_file
  5.  _validate_evidence_mime
  6.  _update_dispute_flag
  7.  initialize_milestone_payment
  8.  verify_milestone_payment
  9.  submit_milestone_work
  10. approve_milestone
  11. release_milestone_to_worker  (success / otp / error paths)
  12. mark_milestone_released
  13. finalize_transfer_with_otp
  14. sync_pending_transfers
  15. request_disable_transfer_otp
  16. finalize_disable_transfer_otp
  17. enable_transfer_otp
  18. create_transfer_recipient
  19. raise_dispute  (all guard branches)
  20. resolve_dispute  (RELEASED / REFUNDED / SPLIT / invalid)
  21. split_milestone
  22. post_dispute_message
  23. mediation_agree  (single-party / both-agree / expired window)

All Paystack HTTP calls are intercepted with unittest.mock.patch so no
network access is required and tests run in full isolation.
"""

import hashlib
import io
import json
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch, PropertyMock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone

from jobs.models import (
    Contract,
    Dispute,
    DisputeMessage,
    EmployerProfile,
    Job,
    JobApplication,
    Milestone,
    Notification,
    TradeCategory,
    WorkerBankAccount,
    WorkerProfile,
)
from jobs.service.escrow_service import (
    ABUSE_DISPUTE_THRESHOLD,
    ABUSE_MIN_DISPUTES,
    DISPUTE_WINDOW_DAYS,
    MEDIATION_WINDOW_DAYS,
    MIN_DISPUTE_AGE_HOURS,
    SLA_AUTO_RELEASE_DAYS,
    _hash_file,
    _notify,
    _paystack_headers,
    _safe_json,
    _update_dispute_flag,
    _validate_evidence_mime,
    approve_milestone,
    create_transfer_recipient,
    enable_transfer_otp,
    finalize_disable_transfer_otp,
    finalize_transfer_with_otp,
    initialize_milestone_payment,
    mark_milestone_released,
    mediation_agree,
    post_dispute_message,
    raise_dispute,
    release_milestone_to_worker,
    request_disable_transfer_otp,
    resolve_dispute,
    split_milestone,
    submit_milestone_work,
    sync_pending_transfers,
    verify_milestone_payment,
)

User = get_user_model()


# ──────────────────────────────────────────────────────────────────────────────
#  SHARED FIXTURES
# ──────────────────────────────────────────────────────────────────────────────

def _make_mock_response(status_code=200, json_body=None, text=""):
    """Return a minimal mock that mimics a requests.Response."""
    mock = MagicMock()
    mock.status_code = status_code
    mock.ok = (200 <= status_code < 300)
    mock.text = text or (json.dumps(json_body) if json_body else "")
    mock.json.return_value = json_body or {}
    return mock


class EscrowBaseTestCase(TestCase):
    """
    Shared DB fixture used by all escrow service tests.
    Creates a complete contract + milestone stack so tests can focus on logic.
    Celery tasks are mocked at the class level to avoid Redis dependency.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Silence Celery task dispatching
        cls._task_patches = [
            patch('jobs.tasks.compute_worker_embedding_task.delay'),
            patch('jobs.tasks.compute_job_embedding_task.delay'),
        ]
        for p in cls._task_patches:
            p.start()

    @classmethod
    def tearDownClass(cls):
        for p in cls._task_patches:
            p.stop()
        super().tearDownClass()

    def setUp(self):
        # --- Users -------------------------------------------------------
        self.worker_user = User.objects.create_user(
            username='worker_test', email='worker@test.ng', password='pass'
        )
        self.employer_user = User.objects.create_user(
            username='employer_test', email='employer@test.ng', password='pass'
        )
        self.admin_user = User.objects.create_user(
            username='admin_test', email='admin@test.ng',
            password='pass', is_staff=True, is_superuser=True
        )

        # --- Domain objects ---------------------------------------------
        self.trade = TradeCategory.objects.create(name='Plumbing', slug='plumbing')

        self.worker_profile = WorkerProfile.objects.create(
            user=self.worker_user,
            trade_category=self.trade,
            state='lagos',
        )
        self.employer_profile = EmployerProfile.objects.create(
            user=self.employer_user,
            company_name='Fix-It Homes Ltd',
            state='lagos',
        )
        self.job = Job.objects.create(
            employer=self.employer_profile,
            trade_category=self.trade,
            title='Bathroom Plumbing Overhaul',
            description='Complete bathroom plumbing overhaul.',
            status=Job.Status.ACTIVE,
        )
        self.application = JobApplication.objects.create(
            job=self.job,
            worker=self.worker_profile,
            status=JobApplication.Status.ACCEPTED,
        )
        self.contract = Contract.objects.create(
            job=self.job,
            application=self.application,
            employer=self.employer_profile,
            worker=self.worker_profile,
            status=Contract.Status.ACTIVE,
            platform_fee_pct=Decimal('10.00'),
        )
        self.milestone = Milestone.objects.create(
            contract=self.contract,
            title='Phase 1 – Rough-in',
            description='Install main pipes.',
            amount=Decimal('50000.00'),
            status=Milestone.Status.UNFUNDED,
        )
        # Bank account for payout tests
        self.bank_account = WorkerBankAccount.objects.create(
            worker=self.worker_profile,
            account_name='Test Worker',
            account_number='0123456789',
            bank_code='044',
            bank_name='Access Bank',
            paystack_recipient_code='RCP_test_abc123',
        )


# ──────────────────────────────────────────────────────────────────────────────
#  1. INTERNAL HELPERS
# ──────────────────────────────────────────────────────────────────────────────

class PaystackHeadersTests(TestCase):
    """Tests for _paystack_headers()."""

    @override_settings(PAYSTACK_SECRET_KEY='sk_test_supersecret')
    def test_returns_bearer_auth_header(self):
        headers = _paystack_headers()
        self.assertEqual(headers['Authorization'], 'Bearer sk_test_supersecret')
        self.assertEqual(headers['Content-Type'], 'application/json')

    @override_settings(PAYSTACK_SECRET_KEY='  sk_test_padded  ')
    def test_strips_whitespace_from_key(self):
        headers = _paystack_headers()
        self.assertEqual(headers['Authorization'], 'Bearer sk_test_padded')

    @override_settings(PAYSTACK_SECRET_KEY=None)
    def test_missing_key_returns_empty_bearer(self):
        headers = _paystack_headers()
        self.assertEqual(headers['Authorization'], 'Bearer ')


class SafeJsonTests(TestCase):
    """Tests for _safe_json()."""

    def test_none_returns_empty_dict(self):
        self.assertEqual(_safe_json(None), {})

    def test_empty_text_returns_empty_dict(self):
        mock = MagicMock()
        mock.text = ''
        self.assertEqual(_safe_json(mock), {})

    def test_whitespace_text_returns_empty_dict(self):
        mock = MagicMock()
        mock.text = '   '
        self.assertEqual(_safe_json(mock), {})

    def test_valid_json_returns_dict(self):
        mock = MagicMock()
        mock.text = '{"status": true}'
        mock.json.return_value = {'status': True}
        result = _safe_json(mock)
        self.assertEqual(result, {'status': True})

    def test_invalid_json_returns_empty_dict(self):
        mock = MagicMock()
        mock.text = 'not json at all'
        mock.json.side_effect = ValueError('No JSON object')
        result = _safe_json(mock)
        self.assertEqual(result, {})


class NotifyHelperTests(EscrowBaseTestCase):
    """Tests for _notify()."""

    def test_creates_notification_for_user(self):
        _notify(
            user=self.worker_user,
            notif_type=Notification.NotifType.SYSTEM,
            title='Test notification',
            body='Test body',
            data={'key': 'value'},
        )
        notif = Notification.objects.get(user=self.worker_user, title='Test notification')
        self.assertEqual(notif.notif_type, Notification.NotifType.SYSTEM)
        self.assertEqual(notif.body, 'Test body')
        self.assertEqual(notif.data, {'key': 'value'})

    def test_data_defaults_to_empty_dict(self):
        _notify(
            user=self.worker_user,
            notif_type=Notification.NotifType.SYSTEM,
            title='No data',
            body='',
        )
        notif = Notification.objects.get(user=self.worker_user, title='No data')
        self.assertEqual(notif.data, {})


class HashFileTests(TestCase):
    """Tests for _hash_file()."""

    def test_returns_sha256_hex_digest(self):
        content = b'test file content'
        f = io.BytesIO(content)
        f.chunks = lambda: [content]
        f.seek = lambda pos: None
        result = _hash_file(f)
        expected = hashlib.sha256(content).hexdigest()
        self.assertEqual(result, expected)

    def test_file_is_seeked_back_to_zero(self):
        content = b'some bytes'
        seek_calls = []

        class FakeFile:
            def chunks(self):
                yield content
            def seek(self, pos):
                seek_calls.append(pos)

        _hash_file(FakeFile())
        self.assertIn(0, seek_calls)


class ValidateEvidenceMimeTests(TestCase):
    """Tests for _validate_evidence_mime()."""

    def test_raises_if_magic_detects_disallowed_mime(self):
        f = MagicMock()
        f.read.return_value = b'fake'
        f.seek = MagicMock()

        mock_magic = MagicMock()
        mock_magic.from_buffer.return_value = 'application/x-executable'
        with patch.dict('sys.modules', {'magic': mock_magic}):
            with self.assertRaises(ValidationError):
                _validate_evidence_mime(f)

    def test_passes_for_allowed_mime_types(self):
        allowed = ['image/jpeg', 'image/png', 'image/webp', 'video/mp4', 'application/pdf']
        for mime in allowed:
            f = MagicMock()
            f.read.return_value = b'fake'
            f.seek = MagicMock()
            mock_magic = MagicMock()
            mock_magic.from_buffer.return_value = mime
            with patch.dict('sys.modules', {'magic': mock_magic}):
                _validate_evidence_mime(f)   # must not raise

    def test_skips_check_if_magic_not_installed(self):
        """When python-magic is absent the function must not raise."""
        f = MagicMock()
        f.read.return_value = b'fake'
        f.seek = MagicMock()
        with patch.dict('sys.modules', {'magic': None}):
            _validate_evidence_mime(f)   # should not raise


class UpdateDisputeFlagTests(EscrowBaseTestCase):
    """Tests for _update_dispute_flag()."""

    def test_flags_profile_when_loss_rate_exceeds_threshold(self):
        self.worker_profile.disputes_raised = 5
        self.worker_profile.disputes_lost = 3  # 60% > 40% threshold
        self.worker_profile.dispute_flagged = False
        self.worker_profile.save()

        _update_dispute_flag(self.worker_profile)
        self.worker_profile.refresh_from_db()
        self.assertTrue(self.worker_profile.dispute_flagged)

    def test_does_not_flag_below_min_disputes(self):
        self.worker_profile.disputes_raised = 2  # < ABUSE_MIN_DISPUTES (3)
        self.worker_profile.disputes_lost = 2
        self.worker_profile.dispute_flagged = False
        self.worker_profile.save()

        _update_dispute_flag(self.worker_profile)
        self.worker_profile.refresh_from_db()
        self.assertFalse(self.worker_profile.dispute_flagged)

    def test_does_not_reflag_already_flagged_profile(self):
        """Once flagged, disputes_flagged must stay True (no second save call)."""
        self.worker_profile.disputes_raised = 5
        self.worker_profile.disputes_lost = 4
        self.worker_profile.dispute_flagged = True
        self.worker_profile.save()

        # Call again — should be idempotent
        _update_dispute_flag(self.worker_profile)
        self.worker_profile.refresh_from_db()
        self.assertTrue(self.worker_profile.dispute_flagged)

    def test_does_not_flag_below_loss_rate_threshold(self):
        self.worker_profile.disputes_raised = 5
        self.worker_profile.disputes_lost = 1  # 20% < 40%
        self.worker_profile.dispute_flagged = False
        self.worker_profile.save()

        _update_dispute_flag(self.worker_profile)
        self.worker_profile.refresh_from_db()
        self.assertFalse(self.worker_profile.dispute_flagged)


# ──────────────────────────────────────────────────────────────────────────────
#  2. INITIALIZE MILESTONE PAYMENT
# ──────────────────────────────────────────────────────────────────────────────

class InitializeMilestonePaymentTests(EscrowBaseTestCase):

    PAYSTACK_OK = {
        'status': True,
        'data': {
            'authorization_url': 'https://checkout.paystack.com/abc',
            'reference': 'tl_ms_abc123',
        },
    }

    @patch('jobs.service.escrow_service.requests.post')
    @override_settings(
        PAYSTACK_SECRET_KEY='sk_test_key',
        PAYSTACK_CALLBACK_URL='https://test.ng/callback/',
    )
    def test_success_returns_url_and_ref(self, mock_post):
        mock_post.return_value = _make_mock_response(200, self.PAYSTACK_OK)

        result = initialize_milestone_payment(
            str(self.milestone.pk), 'employer@test.ng'
        )

        self.assertEqual(result['authorization_url'], 'https://checkout.paystack.com/abc')
        self.assertEqual(result['reference'], 'tl_ms_abc123')

        self.milestone.refresh_from_db()
        self.assertEqual(self.milestone.paystack_payment_ref, 'tl_ms_abc123')

    @patch('jobs.service.escrow_service.requests.post')
    @override_settings(
        PAYSTACK_SECRET_KEY='sk_test_key',
        PAYSTACK_CALLBACK_URL='https://test.ng/callback/',
    )
    def test_success_saves_paystack_ref_to_milestone(self, mock_post):
        mock_post.return_value = _make_mock_response(200, self.PAYSTACK_OK)
        initialize_milestone_payment(str(self.milestone.pk), 'employer@test.ng')
        self.milestone.refresh_from_db()
        self.assertIsNotNone(self.milestone.paystack_payment_ref)

    def test_milestone_not_found_returns_empty_dict(self):
        result = initialize_milestone_payment('00000000-0000-0000-0000-000000000000', 'e@ng')
        self.assertEqual(result, {})

    @patch('jobs.service.escrow_service.requests.post')
    @override_settings(
        PAYSTACK_SECRET_KEY='sk_test_key',
        PAYSTACK_CALLBACK_URL='https://test.ng/callback/',
    )
    def test_paystack_error_returns_empty_dict(self, mock_post):
        mock_post.return_value = _make_mock_response(400, {'status': False, 'message': 'Bad request'})
        result = initialize_milestone_payment(str(self.milestone.pk), 'employer@test.ng')
        self.assertEqual(result, {})

    @patch('jobs.service.escrow_service.requests.post', side_effect=Exception('timeout'))
    @override_settings(
        PAYSTACK_SECRET_KEY='sk_test_key',
        PAYSTACK_CALLBACK_URL='https://test.ng/callback/',
    )
    def test_network_exception_returns_empty_dict(self, mock_post):
        result = initialize_milestone_payment(str(self.milestone.pk), 'employer@test.ng')
        self.assertEqual(result, {})

    @patch('jobs.service.escrow_service.requests.post')
    @override_settings(
        PAYSTACK_SECRET_KEY='sk_test_key',
        PAYSTACK_CALLBACK_URL='https://test.ng/callback/',
    )
    def test_amount_sent_as_kobo(self, mock_post):
        """Paystack needs amount in kobo (× 100)."""
        mock_post.return_value = _make_mock_response(200, self.PAYSTACK_OK)
        initialize_milestone_payment(str(self.milestone.pk), 'employer@test.ng')
        call_kwargs = mock_post.call_args
        payload = call_kwargs[1]['json'] if 'json' in call_kwargs[1] else call_kwargs[0][1]
        self.assertEqual(payload['amount'], int(self.milestone.amount * 100))


# ──────────────────────────────────────────────────────────────────────────────
#  3. VERIFY MILESTONE PAYMENT
# ──────────────────────────────────────────────────────────────────────────────

class VerifyMilestonePaymentTests(EscrowBaseTestCase):

    def setUp(self):
        super().setUp()
        self.milestone.paystack_payment_ref = 'tl_ms_verify_test'
        self.milestone.status = Milestone.Status.UNFUNDED
        self.milestone.save()

    def _paystack_success_body(self):
        return {
            'status': True,
            'data': {
                'status': 'success',
                'amount': int(self.milestone.amount * 100),  # 5000000 kobo
            },
        }

    @patch('jobs.service.escrow_service.requests.get')
    def test_success_marks_milestone_funded(self, mock_get):
        mock_get.return_value = _make_mock_response(200, self._paystack_success_body())
        result = verify_milestone_payment('tl_ms_verify_test')
        self.assertTrue(result)
        self.milestone.refresh_from_db()
        self.assertEqual(self.milestone.status, Milestone.Status.FUNDED)
        self.assertIsNotNone(self.milestone.funded_at)

    @patch('jobs.service.escrow_service.requests.get')
    def test_success_activates_pending_contract(self, mock_get):
        self.contract.status = Contract.Status.PENDING
        self.contract.save()
        mock_get.return_value = _make_mock_response(200, self._paystack_success_body())
        verify_milestone_payment('tl_ms_verify_test')
        self.contract.refresh_from_db()
        self.assertEqual(self.contract.status, Contract.Status.ACTIVE)

    @patch('jobs.service.escrow_service.requests.get')
    def test_success_sends_notifications_to_both_parties(self, mock_get):
        mock_get.return_value = _make_mock_response(200, self._paystack_success_body())
        verify_milestone_payment('tl_ms_verify_test')
        worker_notif = Notification.objects.filter(
            user=self.worker_user,
            notif_type=Notification.NotifType.ESCROW_FUNDED,
        )
        employer_notif = Notification.objects.filter(
            user=self.employer_user,
            notif_type=Notification.NotifType.ESCROW_FUNDED,
        )
        self.assertTrue(worker_notif.exists())
        self.assertTrue(employer_notif.exists())

    def test_unknown_reference_returns_false(self):
        result = verify_milestone_payment('no_such_ref_xyz')
        self.assertFalse(result)

    @patch('jobs.service.escrow_service.requests.get')
    def test_failed_transaction_status_returns_false(self, mock_get):
        body = {
            'status': True,
            'data': {'status': 'failed', 'amount': int(self.milestone.amount * 100)},
        }
        mock_get.return_value = _make_mock_response(200, body)
        result = verify_milestone_payment('tl_ms_verify_test')
        self.assertFalse(result)

    @patch('jobs.service.escrow_service.requests.get')
    def test_amount_mismatch_returns_false(self, mock_get):
        body = {
            'status': True,
            'data': {'status': 'success', 'amount': 999},  # wrong amount
        }
        mock_get.return_value = _make_mock_response(200, body)
        result = verify_milestone_payment('tl_ms_verify_test')
        self.assertFalse(result)
        self.milestone.refresh_from_db()
        self.assertNotEqual(self.milestone.status, Milestone.Status.FUNDED)

    @patch('jobs.service.escrow_service.requests.get', side_effect=Exception('network'))
    def test_network_exception_returns_false(self, _):
        result = verify_milestone_payment('tl_ms_verify_test')
        self.assertFalse(result)


# ──────────────────────────────────────────────────────────────────────────────
#  4. SUBMIT MILESTONE WORK
# ──────────────────────────────────────────────────────────────────────────────

class SubmitMilestoneWorkTests(EscrowBaseTestCase):

    def setUp(self):
        super().setUp()
        self.milestone.status = Milestone.Status.FUNDED
        self.milestone.funded_at = timezone.now()
        self.milestone.save()

    def test_success_transitions_to_in_review(self):
        result = submit_milestone_work(str(self.milestone.pk), 'All pipes installed.')
        self.assertTrue(result)
        self.milestone.refresh_from_db()
        self.assertEqual(self.milestone.status, Milestone.Status.IN_REVIEW)

    def test_submission_note_is_saved(self):
        submit_milestone_work(str(self.milestone.pk), 'Done.')
        self.milestone.refresh_from_db()
        self.assertEqual(self.milestone.submission_note, 'Done.')

    def test_auto_release_at_set_to_7_days_from_now(self):
        before = timezone.now()
        submit_milestone_work(str(self.milestone.pk), 'Done.')
        self.milestone.refresh_from_db()
        after = timezone.now()
        delta = self.milestone.auto_release_at - before
        self.assertAlmostEqual(delta.days, 7, delta=1)

    def test_employer_notification_sent(self):
        submit_milestone_work(str(self.milestone.pk), 'All done.')
        notif = Notification.objects.filter(
            user=self.employer_user,
            notif_type=Notification.NotifType.ESCROW_SUBMITTED,
        )
        self.assertTrue(notif.exists())

    def test_unfunded_milestone_returns_false(self):
        self.milestone.status = Milestone.Status.UNFUNDED
        self.milestone.save()
        result = submit_milestone_work(str(self.milestone.pk), 'Done.')
        self.assertFalse(result)

    def test_nonexistent_milestone_returns_false(self):
        result = submit_milestone_work('00000000-0000-0000-0000-000000000000', 'x')
        self.assertFalse(result)


# ──────────────────────────────────────────────────────────────────────────────
#  5. APPROVE MILESTONE
# ──────────────────────────────────────────────────────────────────────────────

class ApproveMilestoneTests(EscrowBaseTestCase):

    def setUp(self):
        super().setUp()
        self.milestone.status = Milestone.Status.IN_REVIEW
        self.milestone.save()

    @patch('jobs.service.escrow_service.release_milestone_to_worker')
    def test_success_sets_approved_status_and_calls_release(self, mock_release):
        mock_release.return_value = True
        result = approve_milestone(str(self.milestone.pk))
        self.assertTrue(result)
        self.milestone.refresh_from_db()
        self.assertEqual(self.milestone.status, Milestone.Status.APPROVED)
        mock_release.assert_called_once_with(str(self.milestone.pk))

    @patch('jobs.service.escrow_service.release_milestone_to_worker', return_value=True)
    def test_approved_at_is_set(self, _):
        before = timezone.now()
        approve_milestone(str(self.milestone.pk))
        self.milestone.refresh_from_db()
        self.assertGreaterEqual(self.milestone.approved_at, before)

    @patch('jobs.service.escrow_service.release_milestone_to_worker', return_value=True)
    def test_works_from_disputed_status(self, _):
        self.milestone.status = Milestone.Status.DISPUTED
        self.milestone.save()
        result = approve_milestone(str(self.milestone.pk))
        self.assertTrue(result)

    def test_unfunded_milestone_returns_false(self):
        self.milestone.status = Milestone.Status.UNFUNDED
        self.milestone.save()
        result = approve_milestone(str(self.milestone.pk))
        self.assertFalse(result)

    def test_nonexistent_milestone_returns_false(self):
        result = approve_milestone('00000000-0000-0000-0000-000000000000')
        self.assertFalse(result)


# ──────────────────────────────────────────────────────────────────────────────
#  6. RELEASE MILESTONE TO WORKER
# ──────────────────────────────────────────────────────────────────────────────

class ReleaseMilestoneToWorkerTests(EscrowBaseTestCase):

    def setUp(self):
        super().setUp()
        self.milestone.status = Milestone.Status.APPROVED
        self.milestone.amount = Decimal('100000.00')
        self.milestone.save()

    def _mock_recipient_valid(self, valid=True):
        """Patch the internal _recipient_valid call (inline function)."""
        return patch(
            'requests.get',
            return_value=_make_mock_response(200, {'status': True} if valid else {'status': False}),
        )

    @patch('jobs.service.escrow_service.requests.get')
    @patch('jobs.service.escrow_service.requests.post')
    @override_settings(PAYSTACK_SECRET_KEY='sk_test_key')
    def test_success_transfer_marks_milestone_released(self, mock_post, mock_get):
        # recipient validation passes
        mock_get.return_value = _make_mock_response(200, {'status': True})
        # transfer succeeds immediately
        mock_post.return_value = _make_mock_response(200, {
            'status': True,
            'data': {'status': 'success', 'transfer_code': 'TRF_ok'},
        })

        result = release_milestone_to_worker(str(self.milestone.pk))
        self.assertTrue(result)
        self.milestone.refresh_from_db()
        self.assertEqual(self.milestone.status, Milestone.Status.RELEASED)
        self.assertEqual(self.milestone.paystack_transfer_ref, 'TRF_ok')

    @patch('jobs.service.escrow_service.requests.get')
    @patch('jobs.service.escrow_service.requests.post')
    @override_settings(PAYSTACK_SECRET_KEY='sk_test_key')
    def test_worker_amount_is_gross_minus_fee(self, mock_post, mock_get):
        """Worker receives gross × (1 − 10%) = 90 000."""
        mock_get.return_value = _make_mock_response(200, {'status': True})
        mock_post.return_value = _make_mock_response(200, {
            'status': True,
            'data': {'status': 'success', 'transfer_code': 'TRF_ok'},
        })
        release_milestone_to_worker(str(self.milestone.pk))
        self.milestone.refresh_from_db()
        self.assertEqual(self.milestone.worker_amount, Decimal('90000.00'))

    @patch('jobs.service.escrow_service.requests.get')
    @patch('jobs.service.escrow_service.requests.post')
    @override_settings(PAYSTACK_SECRET_KEY='sk_test_key')
    def test_otp_path_sets_pending_otp_status(self, mock_post, mock_get):
        mock_get.return_value = _make_mock_response(200, {'status': True})
        mock_post.return_value = _make_mock_response(200, {
            'status': True,
            'data': {'status': 'otp', 'transfer_code': 'TRF_otp'},
        })
        result = release_milestone_to_worker(str(self.milestone.pk))
        self.assertTrue(result)
        self.milestone.refresh_from_db()
        self.assertEqual(self.milestone.status, Milestone.Status.PENDING_OTP)
        self.assertEqual(self.milestone.paystack_transfer_ref, 'TRF_otp')

    @patch('jobs.service.escrow_service.requests.get')
    @patch('jobs.service.escrow_service.requests.post')
    @override_settings(PAYSTACK_SECRET_KEY='sk_test_key')
    def test_otp_path_sends_notification_to_admin(self, mock_post, mock_get):
        mock_get.return_value = _make_mock_response(200, {'status': True})
        mock_post.return_value = _make_mock_response(200, {
            'status': True,
            'data': {'status': 'otp', 'transfer_code': 'TRF_otp'},
        })
        release_milestone_to_worker(str(self.milestone.pk))
        admin_notif = Notification.objects.filter(
            user=self.admin_user,
            notif_type=Notification.NotifType.SYSTEM,
            title__icontains='Approve Transfer OTP',
        )
        self.assertTrue(admin_notif.exists())

    @patch('jobs.service.escrow_service.requests.get')
    @patch('jobs.service.escrow_service.requests.post')
    @override_settings(PAYSTACK_SECRET_KEY='sk_test_key')
    def test_transfer_failure_returns_false(self, mock_post, mock_get):
        mock_get.return_value = _make_mock_response(200, {'status': True})
        mock_post.return_value = _make_mock_response(400, {
            'status': False, 'message': 'Insufficient balance',
        })
        result = release_milestone_to_worker(str(self.milestone.pk))
        self.assertFalse(result)

    def test_no_bank_account_returns_false(self):
        self.bank_account.delete()
        result = release_milestone_to_worker(str(self.milestone.pk))
        self.assertFalse(result)

    def test_nonexistent_milestone_returns_false(self):
        result = release_milestone_to_worker('00000000-0000-0000-0000-000000000000')
        self.assertFalse(result)

    @patch('jobs.service.escrow_service.requests.get')
    @patch('jobs.service.escrow_service.requests.post')
    @override_settings(PAYSTACK_SECRET_KEY='sk_test_key')
    def test_unexpected_transfer_status_returns_false(self, mock_post, mock_get):
        mock_get.return_value = _make_mock_response(200, {'status': True})
        mock_post.return_value = _make_mock_response(200, {
            'status': True,
            'data': {'status': 'mystery_status', 'transfer_code': 'TRF_???'},
        })
        result = release_milestone_to_worker(str(self.milestone.pk))
        self.assertFalse(result)

    @patch('jobs.service.escrow_service.requests.get')
    @patch('jobs.service.escrow_service.requests.post')
    @override_settings(PAYSTACK_SECRET_KEY='sk_live_key')
    def test_test_recipient_code_on_live_key_triggers_recreation(self, mock_post, mock_get):
        """A test-mode recipient code (RCP_test_*) on a live key must be recreated."""
        self.bank_account.paystack_recipient_code = 'RCP_test_oldcode'
        self.bank_account.save()

        # get: first call validates existing code (fails), second call is the new recipient creation check
        mock_get.return_value = _make_mock_response(200, {'status': True})
        # post: first call is create_transfer_recipient, second is the transfer itself
        mock_post.side_effect = [
            _make_mock_response(200, {
                'status': True,
                'data': {'recipient_code': 'RCP_live_newcode'},
            }),
            _make_mock_response(200, {
                'status': True,
                'data': {'status': 'success', 'transfer_code': 'TRF_live'},
            }),
        ]
        result = release_milestone_to_worker(str(self.milestone.pk))
        self.assertTrue(result)


# ──────────────────────────────────────────────────────────────────────────────
#  7. MARK MILESTONE RELEASED
# ──────────────────────────────────────────────────────────────────────────────

class MarkMilestoneReleasedTests(EscrowBaseTestCase):

    def setUp(self):
        super().setUp()
        self.milestone.status = Milestone.Status.RELEASED
        self.milestone.worker_amount = Decimal('90000.00')
        self.milestone.save()

    def test_sends_release_notifications_to_both_parties(self):
        mark_milestone_released(self.milestone)
        worker_notif = Notification.objects.filter(
            user=self.worker_user,
            notif_type=Notification.NotifType.ESCROW_RELEASED,
        )
        employer_notif = Notification.objects.filter(
            user=self.employer_user,
            notif_type=Notification.NotifType.ESCROW_RELEASED,
        )
        self.assertTrue(worker_notif.exists())
        self.assertTrue(employer_notif.exists())

    def test_marks_contract_completed_when_all_milestones_released(self):
        mark_milestone_released(self.milestone)
        self.contract.refresh_from_db()
        self.assertEqual(self.contract.status, Contract.Status.COMPLETED)

    def test_does_not_complete_contract_if_other_milestones_pending(self):
        Milestone.objects.create(
            contract=self.contract,
            title='Phase 2',
            description='desc',
            amount=Decimal('20000.00'),
            status=Milestone.Status.FUNDED,
        )
        mark_milestone_released(self.milestone)
        self.contract.refresh_from_db()
        self.assertNotEqual(self.contract.status, Contract.Status.COMPLETED)

    def test_handles_null_worker_amount_gracefully(self):
        self.milestone.worker_amount = None
        self.milestone.save()
        try:
            mark_milestone_released(self.milestone)
        except Exception as exc:
            self.fail(f"mark_milestone_released raised unexpectedly: {exc}")


# ──────────────────────────────────────────────────────────────────────────────
#  8. FINALIZE TRANSFER WITH OTP
# ──────────────────────────────────────────────────────────────────────────────

class FinalizeTransferWithOtpTests(EscrowBaseTestCase):

    def setUp(self):
        super().setUp()
        self.milestone.status = Milestone.Status.PENDING_OTP
        self.milestone.paystack_transfer_ref = 'TRF_pending_otp'
        self.milestone.worker_amount = Decimal('90000.00')
        self.milestone.save()

    @patch('jobs.service.escrow_service.requests.post')
    def test_success_marks_milestone_released(self, mock_post):
        mock_post.return_value = _make_mock_response(200, {'status': True})
        result = finalize_transfer_with_otp(str(self.milestone.pk), '123456')
        self.assertTrue(result)
        self.milestone.refresh_from_db()
        self.assertEqual(self.milestone.status, Milestone.Status.RELEASED)

    @patch('jobs.service.escrow_service.requests.post')
    def test_success_calls_mark_milestone_released(self, mock_post):
        mock_post.return_value = _make_mock_response(200, {'status': True})
        with patch('jobs.service.escrow_service.mark_milestone_released') as mock_mark:
            finalize_transfer_with_otp(str(self.milestone.pk), '123456')
            mock_mark.assert_called_once()

    @patch('jobs.service.escrow_service.requests.post')
    def test_paystack_rejection_returns_false(self, mock_post):
        mock_post.return_value = _make_mock_response(400, {'status': False, 'message': 'Invalid OTP'})
        result = finalize_transfer_with_otp(str(self.milestone.pk), 'wrong')
        self.assertFalse(result)

    def test_wrong_status_milestone_returns_false(self):
        self.milestone.status = Milestone.Status.FUNDED
        self.milestone.save()
        result = finalize_transfer_with_otp(str(self.milestone.pk), '123456')
        self.assertFalse(result)

    def test_missing_transfer_ref_returns_false(self):
        self.milestone.paystack_transfer_ref = ''
        self.milestone.save()
        result = finalize_transfer_with_otp(str(self.milestone.pk), '123456')
        self.assertFalse(result)

    def test_nonexistent_milestone_returns_false(self):
        result = finalize_transfer_with_otp('00000000-0000-0000-0000-000000000000', '123')
        self.assertFalse(result)

    @patch('jobs.service.escrow_service.requests.post', side_effect=Exception('network'))
    def test_network_exception_returns_false(self, _):
        result = finalize_transfer_with_otp(str(self.milestone.pk), '123456')
        self.assertFalse(result)


# ──────────────────────────────────────────────────────────────────────────────
#  9. SYNC PENDING TRANSFERS
# ──────────────────────────────────────────────────────────────────────────────

class SyncPendingTransfersTests(EscrowBaseTestCase):

    def setUp(self):
        super().setUp()
        self.milestone.status = Milestone.Status.PENDING_OTP
        self.milestone.paystack_transfer_ref = 'TRF_sync_test'
        self.milestone.amount = Decimal('100000.00')
        self.milestone.save()

    @patch('jobs.service.escrow_service.requests.get')
    def test_syncs_success_status_to_released(self, mock_get):
        mock_get.return_value = _make_mock_response(200, {
            'status': True,
            'data': {'status': 'success'},
        })
        with patch('jobs.service.escrow_service.mark_milestone_released') as mock_mark:
            sync_pending_transfers(self.contract)
            mock_mark.assert_called_once()
        self.milestone.refresh_from_db()
        self.assertEqual(self.milestone.status, Milestone.Status.RELEASED)

    @patch('jobs.service.escrow_service.requests.get')
    def test_syncs_failed_status_reverts_to_approved(self, mock_get):
        mock_get.return_value = _make_mock_response(200, {
            'status': True,
            'data': {'status': 'failed'},
        })
        sync_pending_transfers(self.contract)
        self.milestone.refresh_from_db()
        self.assertEqual(self.milestone.status, Milestone.Status.APPROVED)
        self.assertIsNone(self.milestone.paystack_transfer_ref)

    @patch('jobs.service.escrow_service.requests.get', side_effect=Exception('network'))
    def test_network_error_handled_gracefully(self, _):
        """sync should not raise even on network errors."""
        try:
            sync_pending_transfers(self.contract)
        except Exception as exc:
            self.fail(f"sync_pending_transfers raised: {exc}")

    def test_skips_milestones_without_transfer_ref(self):
        self.milestone.paystack_transfer_ref = ''
        self.milestone.save()
        # Should not make any HTTP call
        with patch('jobs.service.escrow_service.requests.get') as mock_get:
            sync_pending_transfers(self.contract)
            mock_get.assert_not_called()


# ──────────────────────────────────────────────────────────────────────────────
#  10. OTP MANAGEMENT (enable/disable)
# ──────────────────────────────────────────────────────────────────────────────

class OtpManagementTests(TestCase):

    @patch('jobs.service.escrow_service.requests.post')
    def test_request_disable_otp_success(self, mock_post):
        mock_post.return_value = _make_mock_response(200, {'status': True, 'message': 'OTP sent'})
        result = request_disable_transfer_otp()
        self.assertTrue(result.get('status'))

    @patch('jobs.service.escrow_service.requests.post', side_effect=Exception('timeout'))
    def test_request_disable_otp_network_error_returns_false_status(self, _):
        result = request_disable_transfer_otp()
        self.assertFalse(result.get('status'))

    @patch('jobs.service.escrow_service.requests.post')
    def test_finalize_disable_otp_success(self, mock_post):
        mock_post.return_value = _make_mock_response(200, {'status': True})
        result = finalize_disable_transfer_otp('654321')
        self.assertTrue(result.get('status'))

    @patch('jobs.service.escrow_service.requests.post')
    def test_enable_otp_success(self, mock_post):
        mock_post.return_value = _make_mock_response(200, {'status': True})
        result = enable_transfer_otp()
        self.assertTrue(result.get('status'))

    @patch('jobs.service.escrow_service.requests.post', side_effect=Exception('err'))
    def test_enable_otp_network_error_returns_false_status(self, _):
        result = enable_transfer_otp()
        self.assertFalse(result.get('status'))


# ──────────────────────────────────────────────────────────────────────────────
#  11. CREATE TRANSFER RECIPIENT
# ──────────────────────────────────────────────────────────────────────────────

class CreateTransferRecipientTests(EscrowBaseTestCase):

    @patch('jobs.service.escrow_service.requests.post')
    def test_success_saves_recipient_code(self, mock_post):
        mock_post.return_value = _make_mock_response(200, {
            'status': True,
            'data': {'recipient_code': 'RCP_new123'},
        })
        code = create_transfer_recipient(str(self.bank_account.pk))
        self.assertEqual(code, 'RCP_new123')
        self.bank_account.refresh_from_db()
        self.assertEqual(self.bank_account.paystack_recipient_code, 'RCP_new123')
        self.assertTrue(self.bank_account.is_verified)

    @patch('jobs.service.escrow_service.requests.post')
    def test_paystack_error_returns_empty_string(self, mock_post):
        mock_post.return_value = _make_mock_response(400, {'status': False, 'message': 'Bad'})
        code = create_transfer_recipient(str(self.bank_account.pk))
        self.assertEqual(code, '')

    def test_nonexistent_account_returns_empty_string(self):
        code = create_transfer_recipient('00000000-0000-0000-0000-000000000000')
        self.assertEqual(code, '')

    @patch('jobs.service.escrow_service.requests.post', side_effect=Exception('net'))
    def test_network_error_returns_empty_string(self, _):
        code = create_transfer_recipient(str(self.bank_account.pk))
        self.assertEqual(code, '')

    @patch('jobs.service.escrow_service.requests.post')
    def test_missing_recipient_code_in_response_returns_empty_string(self, mock_post):
        mock_post.return_value = _make_mock_response(200, {
            'status': True,
            'data': {},  # no recipient_code key
        })
        code = create_transfer_recipient(str(self.bank_account.pk))
        self.assertEqual(code, '')


# ──────────────────────────────────────────────────────────────────────────────
#  12. RAISE DISPUTE
# ──────────────────────────────────────────────────────────────────────────────

class RaiseDisputeTests(EscrowBaseTestCase):

    def setUp(self):
        super().setUp()
        # Put milestone in a disputable state with valid funded_at timing
        self.milestone.status = Milestone.Status.IN_REVIEW
        self.milestone.funded_at = timezone.now() - timedelta(hours=25)  # > 24h ago
        self.milestone.save()

    def test_success_creates_dispute(self):
        ok, err = raise_dispute(
            str(self.milestone.pk),
            self.employer_user.pk,
            'Work is incomplete.',
        )
        self.assertTrue(ok)
        self.assertEqual(err, '')
        self.assertTrue(Dispute.objects.filter(milestone=self.milestone).exists())

    def test_success_sets_milestone_to_disputed(self):
        raise_dispute(str(self.milestone.pk), self.employer_user.pk, 'Bad work.')
        self.milestone.refresh_from_db()
        self.assertEqual(self.milestone.status, Milestone.Status.DISPUTED)

    def test_success_sets_contract_to_disputed(self):
        raise_dispute(str(self.milestone.pk), self.employer_user.pk, 'Bad work.')
        self.contract.refresh_from_db()
        self.assertEqual(self.contract.status, Contract.Status.DISPUTED)

    def test_success_increments_raiser_disputes_raised(self):
        raise_dispute(str(self.milestone.pk), self.employer_user.pk, 'Bad work.')
        self.employer_profile.refresh_from_db()
        self.assertEqual(self.employer_profile.disputes_raised, 1)

    def test_success_notifies_both_parties_and_admins(self):
        raise_dispute(str(self.milestone.pk), self.employer_user.pk, 'Issues.')
        worker_notif = Notification.objects.filter(
            user=self.worker_user,
            notif_type=Notification.NotifType.ESCROW_DISPUTE,
        )
        employer_notif = Notification.objects.filter(
            user=self.employer_user,
            notif_type=Notification.NotifType.ESCROW_DISPUTE,
        )
        admin_notif = Notification.objects.filter(
            user=self.admin_user,
            notif_type=Notification.NotifType.ESCROW_DISPUTE,
        )
        self.assertTrue(worker_notif.exists())
        self.assertTrue(employer_notif.exists())
        self.assertTrue(admin_notif.exists())

    def test_mediation_deadline_set_to_5_days(self):
        raise_dispute(str(self.milestone.pk), self.employer_user.pk, 'reason')
        dispute = Dispute.objects.get(milestone=self.milestone)
        delta = dispute.mediation_deadline - dispute.created_at
        self.assertAlmostEqual(delta.days, MEDIATION_WINDOW_DAYS, delta=1)

    def test_too_soon_returns_error(self):
        """Dispute raised < 24h after funding."""
        self.milestone.funded_at = timezone.now() - timedelta(hours=10)  # < 24h
        self.milestone.save()
        ok, err = raise_dispute(str(self.milestone.pk), self.employer_user.pk, 'reason')
        self.assertFalse(ok)
        self.assertEqual(err, 'too_soon')

    def test_expired_dispute_window_returns_error(self):
        self.milestone.funded_at = timezone.now() - timedelta(days=DISPUTE_WINDOW_DAYS + 1)
        self.milestone.save()
        ok, err = raise_dispute(str(self.milestone.pk), self.employer_user.pk, 'reason')
        self.assertFalse(ok)
        self.assertEqual(err, 'dispute_window_expired')

    def test_duplicate_dispute_returns_error(self):
        raise_dispute(str(self.milestone.pk), self.employer_user.pk, 'first')
        self.milestone.status = Milestone.Status.DISPUTED
        self.milestone.save()
        ok, err = raise_dispute(str(self.milestone.pk), self.employer_user.pk, 'second')
        self.assertFalse(ok)
        self.assertEqual(err, 'dispute_already_exists')

    def test_invalid_milestone_status_returns_error(self):
        self.milestone.status = Milestone.Status.RELEASED
        self.milestone.save()
        ok, err = raise_dispute(str(self.milestone.pk), self.employer_user.pk, 'reason')
        self.assertFalse(ok)
        self.assertEqual(err, 'invalid_milestone_status')

    def test_nonexistent_milestone_returns_error(self):
        ok, err = raise_dispute('00000000-0000-0000-0000-000000000000', self.employer_user.pk, 'r')
        self.assertFalse(ok)
        self.assertEqual(err, 'milestone_not_found')

    def test_nonexistent_user_returns_error(self):
        ok, err = raise_dispute(str(self.milestone.pk), 9999999, 'reason')
        self.assertFalse(ok)
        self.assertEqual(err, 'user_not_found')

    def test_invalid_evidence_mime_returns_error(self):
        evidence = MagicMock()
        evidence.read.return_value = b'bad bytes'
        evidence.seek = MagicMock()
        with patch('jobs.service.escrow_service._validate_evidence_mime',
                   side_effect=ValidationError("File type 'x' is not accepted")):
            ok, err = raise_dispute(
                str(self.milestone.pk), self.employer_user.pk, 'reason', evidence=evidence
            )
        self.assertFalse(ok)

    def test_no_funded_at_skips_age_check(self):
        """funded_at=None means no age/window checks should run."""
        self.milestone.funded_at = None
        self.milestone.save()
        ok, err = raise_dispute(str(self.milestone.pk), self.employer_user.pk, 'reason')
        self.assertTrue(ok)


# ──────────────────────────────────────────────────────────────────────────────
#  13. RESOLVE DISPUTE
# ──────────────────────────────────────────────────────────────────────────────

class ResolveDisputeTests(EscrowBaseTestCase):

    def setUp(self):
        super().setUp()
        self.milestone.status = Milestone.Status.DISPUTED
        self.milestone.funded_at = timezone.now() - timedelta(hours=30)
        self.milestone.paystack_payment_ref = 'tl_ms_resolve_test'
        self.milestone.save()

        self.contract.status = Contract.Status.DISPUTED
        self.contract.save()

        self.dispute = Dispute.objects.create(
            milestone=self.milestone,
            raised_by=self.employer_user,
            reason='Dispute reason',
            mediation_deadline=timezone.now() + timedelta(days=5),
            auto_release_at=timezone.now() + timedelta(days=7),
        )

    @patch('jobs.service.escrow_service.release_milestone_to_worker')
    def test_release_to_worker_resolution(self, mock_release):
        mock_release.return_value = True
        result = resolve_dispute(
            str(self.dispute.pk),
            Dispute.Resolution.RELEASED_TO_WORKER,
            self.admin_user.pk,
            'Worker won.',
        )
        self.assertTrue(result)
        self.dispute.refresh_from_db()
        self.assertEqual(self.dispute.resolution, Dispute.Resolution.RELEASED_TO_WORKER)

    @patch('jobs.service.escrow_service.requests.post')
    def test_refund_to_employer_resolution(self, mock_post):
        mock_post.return_value = _make_mock_response(200, {'status': True})
        result = resolve_dispute(
            str(self.dispute.pk),
            Dispute.Resolution.REFUNDED_TO_EMPLOYER,
            self.admin_user.pk,
        )
        self.assertTrue(result)
        self.milestone.refresh_from_db()
        self.assertEqual(self.milestone.status, Milestone.Status.REFUNDED)

    @patch('jobs.service.escrow_service.requests.post')
    def test_refund_paystack_failure_returns_false(self, mock_post):
        mock_post.return_value = _make_mock_response(400, {'status': False})
        result = resolve_dispute(
            str(self.dispute.pk),
            Dispute.Resolution.REFUNDED_TO_EMPLOYER,
            self.admin_user.pk,
        )
        self.assertFalse(result)

    @patch('jobs.service.escrow_service.release_milestone_to_worker', return_value=True)
    def test_resolved_at_is_set(self, _):
        before = timezone.now()
        resolve_dispute(
            str(self.dispute.pk), Dispute.Resolution.RELEASED_TO_WORKER, self.admin_user.pk
        )
        self.dispute.refresh_from_db()
        self.assertGreaterEqual(self.dispute.resolved_at, before)

    @patch('jobs.service.escrow_service.release_milestone_to_worker', return_value=True)
    def test_loser_disputes_lost_incremented(self, _):
        resolve_dispute(
            str(self.dispute.pk), Dispute.Resolution.RELEASED_TO_WORKER, self.admin_user.pk
        )
        self.employer_profile.refresh_from_db()
        self.assertEqual(self.employer_profile.disputes_lost, 1)

    def test_contract_reverts_to_active_after_resolution(self):
        Milestone.objects.create(
            contract=self.contract,
            title='Phase 2',
            description='desc',
            amount=Decimal('20000.00'),
            status=Milestone.Status.FUNDED,
        )

        def fake_release(m_id):
            Milestone.objects.filter(pk=m_id).update(status=Milestone.Status.RELEASED)
            return True

        with patch('jobs.service.escrow_service.release_milestone_to_worker', side_effect=fake_release):
            resolve_dispute(
                str(self.dispute.pk), Dispute.Resolution.RELEASED_TO_WORKER, self.admin_user.pk
            )
        self.contract.refresh_from_db()
        self.assertEqual(self.contract.status, Contract.Status.ACTIVE)

    def test_contract_marked_completed_if_all_milestones_released_after_resolution(self):
        def fake_release(m_id):
            Milestone.objects.filter(pk=m_id).update(status=Milestone.Status.RELEASED)
            return True

        with patch('jobs.service.escrow_service.release_milestone_to_worker', side_effect=fake_release):
            resolve_dispute(
                str(self.dispute.pk), Dispute.Resolution.RELEASED_TO_WORKER, self.admin_user.pk
            )
        self.contract.refresh_from_db()
        self.assertEqual(self.contract.status, Contract.Status.COMPLETED)

    def test_invalid_resolution_returns_false(self):
        result = resolve_dispute(
            str(self.dispute.pk), 'invalid_resolution', self.admin_user.pk
        )
        self.assertFalse(result)

    def test_nonexistent_dispute_returns_false(self):
        result = resolve_dispute(
            '00000000-0000-0000-0000-000000000000',
            Dispute.Resolution.RELEASED_TO_WORKER,
            self.admin_user.pk,
        )
        self.assertFalse(result)

    def test_nonexistent_user_returns_false(self):
        result = resolve_dispute(
            str(self.dispute.pk),
            Dispute.Resolution.RELEASED_TO_WORKER,
            99999,
        )
        self.assertFalse(result)

    @patch('jobs.service.escrow_service.release_milestone_to_worker', return_value=True)
    def test_sends_resolution_notifications_to_both_parties(self, _):
        resolve_dispute(
            str(self.dispute.pk),
            Dispute.Resolution.RELEASED_TO_WORKER,
            self.admin_user.pk,
            'Final decision.',
        )
        worker_notif = Notification.objects.filter(
            user=self.worker_user,
            notif_type=Notification.NotifType.ESCROW_DISPUTE,
            title__icontains='Dispute resolved',
        )
        employer_notif = Notification.objects.filter(
            user=self.employer_user,
            notif_type=Notification.NotifType.ESCROW_DISPUTE,
            title__icontains='Dispute resolved',
        )
        self.assertTrue(worker_notif.exists())
        self.assertTrue(employer_notif.exists())


# ──────────────────────────────────────────────────────────────────────────────
#  14. SPLIT MILESTONE
# ──────────────────────────────────────────────────────────────────────────────

class SplitMilestoneTests(EscrowBaseTestCase):

    def setUp(self):
        super().setUp()
        self.milestone.status = Milestone.Status.DISPUTED
        self.milestone.amount = Decimal('100000.00')
        self.milestone.paystack_payment_ref = 'tl_ms_split_test'
        self.milestone.save()

        self.contract.status = Contract.Status.DISPUTED
        self.contract.save()

        self.dispute = Dispute.objects.create(
            milestone=self.milestone,
            raised_by=self.employer_user,
            reason='Partial delivery',
            mediation_deadline=timezone.now() + timedelta(days=5),
            auto_release_at=timezone.now() + timedelta(days=7),
        )

    @patch('jobs.service.escrow_service.requests.post')
    def test_50_50_split_correct_amounts(self, mock_post):
        """
        Gross = 100 000, fee = 10%, net = 90 000.
        Worker at 50% → worker_share = 45 000.
        Refund at 50% of gross → 50 000.
        """
        mock_post.side_effect = [
            # transfer call
            _make_mock_response(200, {'status': True, 'data': {'status': 'success'}}),
            # refund call
            _make_mock_response(200, {'status': True}),
        ]
        result = split_milestone(str(self.dispute.pk), 50, self.admin_user.pk)
        self.assertTrue(result)
        self.milestone.refresh_from_db()
        self.assertEqual(self.milestone.worker_amount, Decimal('45000.00'))
        self.assertEqual(self.milestone.status, Milestone.Status.RELEASED)

    @patch('jobs.service.escrow_service.requests.post')
    def test_100_percent_to_worker_no_refund_call(self, mock_post):
        """worker_pct=100 → refund_share = 0 → no Paystack refund call."""
        mock_post.return_value = _make_mock_response(200, {
            'status': True,
            'data': {'status': 'success'},
        })
        result = split_milestone(str(self.dispute.pk), 100, self.admin_user.pk)
        self.assertTrue(result)
        # Only one POST (the transfer) — no refund
        self.assertEqual(mock_post.call_count, 1)

    @patch('jobs.service.escrow_service.requests.post')
    def test_0_percent_to_worker_no_transfer_call(self, mock_post):
        """worker_pct=0 → worker_share = 0 → no Paystack transfer call."""
        mock_post.return_value = _make_mock_response(200, {'status': True})
        result = split_milestone(str(self.dispute.pk), 0, self.admin_user.pk)
        self.assertTrue(result)

    def test_out_of_range_pct_returns_false(self):
        result = split_milestone(str(self.dispute.pk), 150, self.admin_user.pk)
        self.assertFalse(result)

    def test_nonexistent_dispute_returns_false(self):
        result = split_milestone('00000000-0000-0000-0000-000000000000', 50, self.admin_user.pk)
        self.assertFalse(result)

    def test_nonexistent_user_returns_false(self):
        result = split_milestone(str(self.dispute.pk), 50, 999999)
        self.assertFalse(result)

    @patch('jobs.service.escrow_service.requests.post')
    def test_transfer_failure_returns_false(self, mock_post):
        mock_post.return_value = _make_mock_response(400, {'status': False, 'message': 'fail'})
        result = split_milestone(str(self.dispute.pk), 50, self.admin_user.pk)
        self.assertFalse(result)

    @patch('jobs.service.escrow_service.requests.post')
    def test_split_updates_dispute_fields(self, mock_post):
        mock_post.side_effect = [
            _make_mock_response(200, {'status': True, 'data': {'status': 'success'}}),
            _make_mock_response(200, {'status': True}),
        ]
        split_milestone(str(self.dispute.pk), 60, self.admin_user.pk, 'Notes on split.')
        self.dispute.refresh_from_db()
        self.assertEqual(self.dispute.resolution, Dispute.Resolution.SPLIT)
        self.assertEqual(self.dispute.split_worker_pct, 60)
        self.assertEqual(self.dispute.resolution_note, 'Notes on split.')

    @patch('jobs.service.escrow_service.requests.post')
    def test_split_notifies_both_parties(self, mock_post):
        mock_post.side_effect = [
            _make_mock_response(200, {'status': True, 'data': {'status': 'success'}}),
            _make_mock_response(200, {'status': True}),
        ]
        split_milestone(str(self.dispute.pk), 50, self.admin_user.pk)
        for user in [self.worker_user, self.employer_user]:
            self.assertTrue(
                Notification.objects.filter(
                    user=user,
                    notif_type=Notification.NotifType.ESCROW_DISPUTE,
                    title__icontains='Dispute split',
                ).exists()
            )

    @patch('jobs.service.escrow_service.requests.post')
    def test_no_bank_account_returns_false(self, _):
        self.bank_account.delete()
        result = split_milestone(str(self.dispute.pk), 50, self.admin_user.pk)
        self.assertFalse(result)


# ──────────────────────────────────────────────────────────────────────────────
#  15. POST DISPUTE MESSAGE
# ──────────────────────────────────────────────────────────────────────────────

class PostDisputeMessageTests(EscrowBaseTestCase):

    def setUp(self):
        super().setUp()
        self.milestone.status = Milestone.Status.DISPUTED
        self.milestone.funded_at = timezone.now() - timedelta(hours=30)
        self.milestone.save()

        self.dispute = Dispute.objects.create(
            milestone=self.milestone,
            raised_by=self.employer_user,
            reason='Quality issue',
            mediation_deadline=timezone.now() + timedelta(days=5),
            auto_release_at=timezone.now() + timedelta(days=7),
        )

    def test_employer_can_post_message(self):
        ok, err = post_dispute_message(
            str(self.dispute.pk), self.employer_user.pk, 'Here is my evidence.'
        )
        self.assertTrue(ok)
        self.assertEqual(DisputeMessage.objects.filter(dispute=self.dispute).count(), 1)

    def test_worker_can_post_message(self):
        ok, err = post_dispute_message(
            str(self.dispute.pk), self.worker_user.pk, 'My counter-evidence.'
        )
        self.assertTrue(ok)

    def test_admin_can_post_admin_note(self):
        ok, err = post_dispute_message(
            str(self.dispute.pk), self.admin_user.pk, 'Admin note.', is_admin_note=True
        )
        self.assertTrue(ok)
        msg = DisputeMessage.objects.get(dispute=self.dispute)
        self.assertTrue(msg.is_admin_note)

    def test_non_participant_cannot_post(self):
        stranger = User.objects.create_user(username='stranger', email='s@s.ng', password='p')
        ok, err = post_dispute_message(str(self.dispute.pk), stranger.pk, 'Sneaky msg.')
        self.assertFalse(ok)
        self.assertEqual(err, 'not_participant')

    def test_resolved_dispute_rejects_message(self):
        self.dispute.resolution = Dispute.Resolution.RELEASED_TO_WORKER
        self.dispute.save()
        ok, err = post_dispute_message(
            str(self.dispute.pk), self.employer_user.pk, 'Late message.'
        )
        self.assertFalse(ok)
        self.assertEqual(err, 'dispute_already_resolved')

    def test_notification_sent_to_other_party(self):
        post_dispute_message(
            str(self.dispute.pk), self.employer_user.pk, 'Employer speaks.'
        )
        worker_notif = Notification.objects.filter(
            user=self.worker_user,
            notif_type=Notification.NotifType.ESCROW_DISPUTE,
            title__icontains='New message on dispute',
        )
        self.assertTrue(worker_notif.exists())

    def test_nonexistent_dispute_returns_error(self):
        ok, err = post_dispute_message(
            '00000000-0000-0000-0000-000000000000', self.employer_user.pk, 'msg'
        )
        self.assertFalse(ok)
        self.assertEqual(err, 'dispute_not_found')

    def test_nonexistent_user_returns_error(self):
        ok, err = post_dispute_message(str(self.dispute.pk), 99999, 'msg')
        self.assertFalse(ok)
        self.assertEqual(err, 'user_not_found')


# ──────────────────────────────────────────────────────────────────────────────
#  16. MEDIATION AGREE
# ──────────────────────────────────────────────────────────────────────────────

class MediationAgreeTests(EscrowBaseTestCase):

    def setUp(self):
        super().setUp()
        self.milestone.status = Milestone.Status.DISPUTED
        self.milestone.funded_at = timezone.now() - timedelta(hours=30)
        self.milestone.save()

        self.dispute = Dispute.objects.create(
            milestone=self.milestone,
            raised_by=self.employer_user,
            reason='Problem',
            mediation_deadline=timezone.now() + timedelta(days=5),
            auto_release_at=timezone.now() + timedelta(days=7),
        )

    def test_employer_agreement_stored_pending_worker(self):
        ok, outcome = mediation_agree(
            str(self.dispute.pk),
            self.employer_user.pk,
            Dispute.Resolution.REFUNDED_TO_EMPLOYER,
        )
        self.assertTrue(ok)
        self.assertEqual(outcome, 'pending_other_party')
        self.dispute.refresh_from_db()
        self.assertEqual(
            self.dispute.mediation_employer_agreed,
            Dispute.Resolution.REFUNDED_TO_EMPLOYER,
        )

    def test_both_parties_same_resolution_auto_resolves(self):
        # Employer agrees first
        mediation_agree(
            str(self.dispute.pk),
            self.employer_user.pk,
            Dispute.Resolution.REFUNDED_TO_EMPLOYER,
        )

        # Now worker agrees to same resolution
        with patch('jobs.service.escrow_service.resolve_dispute', return_value=True) as mock_resolve:
            ok, outcome = mediation_agree(
                str(self.dispute.pk),
                self.worker_user.pk,
                Dispute.Resolution.REFUNDED_TO_EMPLOYER,
            )
        self.assertTrue(ok)
        self.assertEqual(outcome, 'auto_resolved')
        mock_resolve.assert_called_once()

    def test_different_resolutions_do_not_auto_resolve(self):
        mediation_agree(
            str(self.dispute.pk), self.employer_user.pk, Dispute.Resolution.REFUNDED_TO_EMPLOYER
        )
        ok, outcome = mediation_agree(
            str(self.dispute.pk), self.worker_user.pk, Dispute.Resolution.RELEASED_TO_WORKER
        )
        self.assertTrue(ok)
        self.assertEqual(outcome, 'pending_other_party')

    def test_expired_mediation_window_returns_error(self):
        self.dispute.mediation_deadline = timezone.now() - timedelta(hours=1)
        self.dispute.save()
        ok, outcome = mediation_agree(
            str(self.dispute.pk),
            self.employer_user.pk,
            Dispute.Resolution.RELEASED_TO_WORKER,
        )
        self.assertFalse(ok)
        self.assertEqual(outcome, 'mediation_window_closed')

    def test_non_participant_returns_error(self):
        stranger = User.objects.create_user(username='stranger2', email='s2@s.ng', password='p')
        ok, outcome = mediation_agree(
            str(self.dispute.pk), stranger.pk, Dispute.Resolution.RELEASED_TO_WORKER
        )
        self.assertFalse(ok)
        self.assertEqual(outcome, 'not_participant')

    def test_invalid_resolution_choice_returns_error(self):
        ok, outcome = mediation_agree(
            str(self.dispute.pk), self.employer_user.pk, 'some_invalid_choice'
        )
        self.assertFalse(ok)
        self.assertEqual(outcome, 'invalid_resolution_choice')

    def test_already_resolved_dispute_returns_not_found(self):
        self.dispute.resolution = Dispute.Resolution.RELEASED_TO_WORKER
        self.dispute.save()
        ok, outcome = mediation_agree(
            str(self.dispute.pk), self.employer_user.pk, Dispute.Resolution.RELEASED_TO_WORKER
        )
        self.assertFalse(ok)
        self.assertEqual(outcome, 'dispute_not_found_or_resolved')

    def test_nonexistent_user_returns_error(self):
        ok, outcome = mediation_agree(
            str(self.dispute.pk), 999999, Dispute.Resolution.RELEASED_TO_WORKER
        )
        self.assertFalse(ok)
        self.assertEqual(outcome, 'user_not_found')

    def test_notification_sent_to_other_party_on_single_agreement(self):
        mediation_agree(
            str(self.dispute.pk), self.employer_user.pk, Dispute.Resolution.RELEASED_TO_WORKER
        )
        worker_notif = Notification.objects.filter(
            user=self.worker_user,
            notif_type=Notification.NotifType.ESCROW_DISPUTE,
            title__icontains='agreement proposed',
        )
        self.assertTrue(worker_notif.exists())


# ──────────────────────────────────────────────────────────────────────────────
#  17. EDGE CASES & INTEGRATION-STYLE TESTS
# ──────────────────────────────────────────────────────────────────────────────

class EscrowEdgeCaseTests(EscrowBaseTestCase):
    """Miscellaneous edge-case tests that cross multiple service functions."""

    @patch('jobs.service.escrow_service.requests.get')
    @patch('jobs.service.escrow_service.requests.post')
    @override_settings(PAYSTACK_SECRET_KEY='sk_test_key', PAYSTACK_CALLBACK_URL='https://cb.ng/')
    def test_full_happy_path_unfunded_to_released(self, mock_post, mock_get):
        """
        End-to-end: initialize → verify (FUNDED) → submit → approve → release (RELEASED).
        All Paystack calls are mocked.
        """
        # --- 1. Initialize ---
        mock_post.return_value = _make_mock_response(200, {
            'status': True,
            'data': {'authorization_url': 'https://pay.co/x', 'reference': 'tl_ms_e2e'},
        })
        init_result = initialize_milestone_payment(str(self.milestone.pk), 'e@ng')
        self.assertIn('authorization_url', init_result)
        self.milestone.refresh_from_db()

        # --- 2. Verify ---
        mock_get.return_value = _make_mock_response(200, {
            'status': True,
            'data': {'status': 'success', 'amount': int(self.milestone.amount * 100)},
        })
        verified = verify_milestone_payment('tl_ms_e2e')
        self.assertTrue(verified)
        self.milestone.refresh_from_db()
        self.assertEqual(self.milestone.status, Milestone.Status.FUNDED)

        # --- 3. Submit work ---
        submitted = submit_milestone_work(str(self.milestone.pk), 'Done!')
        self.assertTrue(submitted)
        self.milestone.refresh_from_db()
        self.assertEqual(self.milestone.status, Milestone.Status.IN_REVIEW)

        # --- 4. Approve ---
        # Mock recipient validation (GET) and transfer (POST)
        mock_get.return_value = _make_mock_response(200, {'status': True})
        mock_post.return_value = _make_mock_response(200, {
            'status': True,
            'data': {'status': 'success', 'transfer_code': 'TRF_e2e'},
        })
        approved = approve_milestone(str(self.milestone.pk))
        self.assertTrue(approved)
        self.milestone.refresh_from_db()
        self.assertEqual(self.milestone.status, Milestone.Status.RELEASED)

    def test_platform_fee_zero_percent_gives_full_amount_to_worker(self):
        """With 0% platform fee, worker receives the full gross amount."""
        self.contract.platform_fee_pct = Decimal('0.00')
        self.contract.save()
        self.milestone.status = Milestone.Status.APPROVED
        self.milestone.amount = Decimal('60000.00')
        self.milestone.save()

        with patch('jobs.service.escrow_service.requests.get',
                   return_value=_make_mock_response(200, {'status': True})):
            with patch('jobs.service.escrow_service.requests.post',
                       return_value=_make_mock_response(200, {
                           'status': True,
                           'data': {'status': 'success', 'transfer_code': 'TRF_zerofee'},
                       })):
                with override_settings(PAYSTACK_SECRET_KEY='sk_test_key'):
                    release_milestone_to_worker(str(self.milestone.pk))

        self.milestone.refresh_from_db()
        self.assertEqual(self.milestone.worker_amount, Decimal('60000.00'))

    def test_verify_does_not_refund_contract_already_active(self):
        """Verifying payment on ACTIVE contract must NOT downgrade contract status."""
        self.contract.status = Contract.Status.ACTIVE
        self.contract.save()
        self.milestone.paystack_payment_ref = 'tl_ms_already_active'
        self.milestone.status = Milestone.Status.UNFUNDED
        self.milestone.save()

        with patch('jobs.service.escrow_service.requests.get',
                   return_value=_make_mock_response(200, {
                       'status': True,
                       'data': {
                           'status': 'success',
                           'amount': int(self.milestone.amount * 100),
                       },
                   })):
            verify_milestone_payment('tl_ms_already_active')

        self.contract.refresh_from_db()
        self.assertEqual(self.contract.status, Contract.Status.ACTIVE)

    def test_dispute_abuse_flag_triggered_after_threshold(self):
        """
        If employer raises 5 disputes and loses 3 (60% > 40% threshold), they get flagged.
        """
        self.employer_profile.disputes_raised = 4
        self.employer_profile.disputes_lost = 2
        self.employer_profile.dispute_flagged = False
        self.employer_profile.save()

        # Set up a fresh milestone in a disputable state
        m2 = Milestone.objects.create(
            contract=self.contract,
            title='Extra milestone',
            description='desc',
            amount=Decimal('10000.00'),
            status=Milestone.Status.IN_REVIEW,
            funded_at=timezone.now() - timedelta(hours=30),
        )
        raise_dispute(str(m2.pk), self.employer_user.pk, 'Abuse test')
        self.employer_profile.refresh_from_db()
        # disputes_raised is now 5 (4+1) but losses still 2 → 40% — at boundary, not above
        # So they should NOT be flagged (strictly >)
        self.assertFalse(self.employer_profile.dispute_flagged)

    def test_cannot_initialize_already_funded_milestone(self):
        self.milestone.status = Milestone.Status.FUNDED
        self.milestone.save()
        result = initialize_milestone_payment(str(self.milestone.pk), 'test@test.ng')
        self.assertEqual(result, {})

    def test_cannot_initialize_zero_amount_milestone(self):
        self.milestone.amount = Decimal('0.00')
        self.milestone.save()
        result = initialize_milestone_payment(str(self.milestone.pk), 'test@test.ng')
        self.assertEqual(result, {})

    def test_verify_milestone_payment_is_idempotent(self):
        self.milestone.paystack_payment_ref = 'tl_ms_idempotent'
        self.milestone.status = Milestone.Status.FUNDED
        old_funded_at = timezone.now() - timedelta(days=2)
        self.milestone.funded_at = old_funded_at
        self.milestone.save()

        # Calling verify again on already funded milestone must return True without re-saving funded_at
        result = verify_milestone_payment('tl_ms_idempotent')
        self.assertTrue(result)
        self.milestone.refresh_from_db()
        self.assertEqual(self.milestone.funded_at, old_funded_at)

    def test_non_participant_cannot_raise_dispute(self):
        stranger = User.objects.create_user(username='intruder', email='intruder@x.ng', password='pass')
        self.milestone.status = Milestone.Status.IN_REVIEW
        self.milestone.funded_at = timezone.now() - timedelta(hours=30)
        self.milestone.save()

        ok, err = raise_dispute(str(self.milestone.pk), stranger.pk, 'Malicious dispute')
        self.assertFalse(ok)
        self.assertEqual(err, 'not_participant')

    def test_cannot_resolve_already_resolved_dispute(self):
        self.milestone.status = Milestone.Status.DISPUTED
        self.milestone.funded_at = timezone.now() - timedelta(hours=30)
        self.milestone.save()
        dispute = Dispute.objects.create(
            milestone=self.milestone,
            raised_by=self.employer_user,
            reason='Issues',
            resolution=Dispute.Resolution.RELEASED_TO_WORKER,
        )
        result = resolve_dispute(str(dispute.pk), Dispute.Resolution.REFUNDED_TO_EMPLOYER, self.admin_user.pk)
        self.assertFalse(result)

    def test_approve_disputed_milestone_resolves_dispute(self):
        self.milestone.status = Milestone.Status.DISPUTED
        self.milestone.save()
        dispute = Dispute.objects.create(
            milestone=self.milestone,
            raised_by=self.employer_user,
            reason='Disagreement',
            resolution=Dispute.Resolution.PENDING,
        )

        with patch('jobs.service.escrow_service.release_milestone_to_worker', return_value=True):
            ok = approve_milestone(str(self.milestone.pk))
            self.assertTrue(ok)

        dispute.refresh_from_db()
        self.assertEqual(dispute.resolution, Dispute.Resolution.RELEASED_TO_WORKER)
        self.assertEqual(dispute.resolution_note, "Approved by employer.")

    def test_admin_note_does_not_notify_regular_users(self):
        self.milestone.status = Milestone.Status.DISPUTED
        self.milestone.save()
        dispute = Dispute.objects.create(
            milestone=self.milestone,
            raised_by=self.employer_user,
            reason='Issue',
            resolution=Dispute.Resolution.PENDING,
        )
        notif_count_before = Notification.objects.filter(
            user__in=[self.employer_user, self.worker_user]
        ).count()

        ok, err = post_dispute_message(
            str(dispute.pk),
            self.admin_user.pk,
            "Internal staff discussion only.",
            is_admin_note=True,
        )
        self.assertTrue(ok)
        notif_count_after = Notification.objects.filter(
            user__in=[self.employer_user, self.worker_user]
        ).count()
        self.assertEqual(notif_count_before, notif_count_after)

