import datetime
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.utils import timezone

from jobs.models import (
    TradeCategory, Skill, WorkerProfile, EmployerProfile,
    Job, JobApplication, SavedJob, Contract, Milestone,
    Review, Notification
)
from jobs.forms import JobForm

User = get_user_model()


class BaseJobsTestCase(TestCase):
    """Base test case that mocks Celery background tasks so tests run instantly without Redis."""
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.patcher_worker = patch('jobs.tasks.compute_worker_embedding_task.delay')
        cls.patcher_job = patch('jobs.tasks.compute_job_embedding_task.delay')
        cls.mock_worker = cls.patcher_worker.start()
        cls.mock_job = cls.patcher_job.start()

    @classmethod
    def tearDownClass(cls):
        cls.patcher_worker.stop()
        cls.patcher_job.stop()
        super().tearDownClass()


class JobDomainModelTests(BaseJobsTestCase):
    def setUp(self):
        self.worker_user = User.objects.create_user(
            username='worker_bob', email='bob@trades.ng', password='password123'
        )
        self.employer_user = User.objects.create_user(
            username='employer_alice', email='alice@apex.ng', password='password123'
        )
        self.trade = TradeCategory.objects.create(name='Carpentry', slug='carpentry')
        self.skill_wood = Skill.objects.create(name='Wood Carving', slug='wood-carving', category=self.trade)
        self.skill_joinery = Skill.objects.create(name='Joinery', slug='joinery', category=self.trade)

        self.worker = WorkerProfile.objects.create(
            user=self.worker_user,
            trade_category=self.trade,
            years_experience=4,
            hourly_rate=Decimal('2500.00'),
            daily_rate=Decimal('18000.00'),
            state='lagos',
            availability=WorkerProfile.Availability.AVAILABLE
        )
        self.employer = EmployerProfile.objects.create(
            user=self.employer_user,
            company_name='Apex Interior Ltd',
            company_type=EmployerProfile.CompanyType.SME,
            state='lagos'
        )

    def test_trade_category_and_skills(self):
        self.assertEqual(str(self.trade), 'Carpentry')
        self.assertEqual(self.trade.skills.count(), 2)
        self.assertIn(self.skill_wood, self.trade.skills.all())

    def test_worker_profile_attributes(self):
        self.assertEqual(self.worker.availability, WorkerProfile.Availability.AVAILABLE)
        self.assertEqual(self.worker.hourly_rate, Decimal('2500.00'))
        self.assertFalse(self.worker.is_verified)
        self.assertIn('worker_bob', str(self.worker))

    def test_employer_profile_attributes(self):
        self.assertEqual(self.employer.company_type, EmployerProfile.CompanyType.SME)
        self.assertEqual(str(self.employer), 'Apex Interior Ltd')
        self.assertFalse(self.employer.is_verified)

    def test_job_creation_and_clean_validation(self):
        job = Job.objects.create(
            employer=self.employer,
            trade_category=self.trade,
            title='Custom Kitchen Cabinets',
            description='Build 12 custom wooden kitchen cabinets.',
            job_type=Job.JobType.ONCE_OFF,
            pay_type=Job.PayType.FIXED,
            pay_min=Decimal('150000.00'),
            pay_max=Decimal('200000.00'),
            state='lagos',
            status=Job.Status.ACTIVE,
            deadline=timezone.now().date() + datetime.timedelta(days=14)
        )
        job.required_skills.add(self.skill_wood, self.skill_joinery)
        self.assertEqual(job.required_skills.count(), 2)
        self.assertIn('Custom Kitchen Cabinets', str(job))

        # Test JobForm clean validation for pay_min > pay_max
        form_data = {
            'trade_category': self.trade.id,
            'title': 'Invalid Pay Job',
            'description': 'Valid description with wrong pay range.',
            'job_type': 'once_off',
            'pay_type': 'fixed',
            'pay_min': '300000.00',
            'pay_max': '150000.00',  # Min is greater than Max
            'slots': 1,
            'state': 'lagos'
        }
        form = JobForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('Minimum pay cannot be greater than maximum pay.', form.non_field_errors())

    def test_job_application_lifecycle_and_uniqueness(self):
        job = Job.objects.create(
            employer=self.employer,
            trade_category=self.trade,
            title='Office Desks',
            description='Build 4 large office desks.',
            status=Job.Status.ACTIVE,
            deadline=timezone.now().date() + datetime.timedelta(days=14)
        )

        app = JobApplication.objects.create(
            job=job,
            worker=self.worker,
            cover_note='I have built desks for multiple corporate offices.'
        )
        self.assertEqual(app.status, JobApplication.Status.PENDING)
        self.assertIn('worker_bob', str(app))

        # Duplicate application must raise IntegrityError
        with self.assertRaises(IntegrityError):
            JobApplication.objects.create(
                job=job,
                worker=self.worker,
                cover_note='Duplicate application'
            )

    def test_contract_and_milestones(self):
        job = Job.objects.create(
            employer=self.employer,
            trade_category=self.trade,
            title='Wardrobe Fitting',
            description='Fit 3 built-in wardrobes.',
            status=Job.Status.ACTIVE,
            deadline=timezone.now().date() + datetime.timedelta(days=14)
        )
        app = JobApplication.objects.create(job=job, worker=self.worker)

        contract = Contract.objects.create(
            job=job,
            application=app,
            employer=self.employer,
            worker=self.worker
        )
        # Contract title auto-populates from job title on save
        self.assertEqual(contract.title, 'Wardrobe Fitting')
        self.assertEqual(contract.status, Contract.Status.PENDING)
        self.assertEqual(contract.platform_fee_pct, Decimal('10.00'))

        milestone = Milestone.objects.create(
            contract=contract,
            title='Milestone 1: Cutting and Sanding',
            description='Source wood, cut panels, and sand all surfaces.',
            amount=Decimal('50000.00')
        )
        self.assertEqual(milestone.status, Milestone.Status.UNFUNDED)
        self.assertEqual(contract.milestones.count(), 1)

    def test_review_creation(self):
        job = Job.objects.create(
            employer=self.employer,
            trade_category=self.trade,
            title='Reviewed Job',
            description='Test review job',
            status=Job.Status.FILLED
        )
        review = Review.objects.create(
            job=job,
            reviewer=self.employer_user,
            reviewee=self.worker_user,
            rating=5,
            comment='Outstanding craftsmanship and finished on time.'
        )
        self.assertEqual(review.rating, 5)
        self.assertTrue(review.is_visible)

    def test_notification_routing(self):
        notif = Notification.objects.create(
            user=self.worker_user,
            notif_type=Notification.NotifType.APPLICATION_UPDATE,
            title='Application Accepted',
            body='Your application was accepted.'
        )
        url = notif.get_absolute_url()
        self.assertEqual(url, reverse('marketplace:worker_applications'))


class JobWorkflowViewTests(BaseJobsTestCase):
    def setUp(self):
        self.client = Client()

        self.worker_user = User.objects.create_user(
            username='worker_sam', email='sam@trades.ng', password='password123'
        )
        self.employer_user = User.objects.create_user(
            username='employer_kemi', email='kemi@corp.ng', password='password123'
        )
        self.trade = TradeCategory.objects.create(name='Welding', slug='welding')
        self.skill = Skill.objects.create(name='Arc Welding', slug='arc-welding', category=self.trade)

        self.worker = WorkerProfile.objects.create(
            user=self.worker_user,
            trade_category=self.trade,
            state='lagos'
        )
        self.employer = EmployerProfile.objects.create(
            user=self.employer_user,
            company_name='Kemi Fabrications',
            state='lagos'
        )

        self.active_job = Job.objects.create(
            employer=self.employer,
            trade_category=self.trade,
            title='Gate Fabrication',
            description='Fabricate a wrought iron security gate for estate residence.',
            job_type=Job.JobType.CONTRACT,
            pay_type=Job.PayType.FIXED,
            pay_min=Decimal('80000.00'),
            pay_max=Decimal('100000.00'),
            state='lagos',
            status=Job.Status.ACTIVE,
            deadline=timezone.now().date() + datetime.timedelta(days=20)
        )

    def test_job_list_public_view_and_filtering(self):
        url = reverse('marketplace:job_list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Gate Fabrication')

        # Filter by trade
        response_filtered = self.client.get(url, {'trade': self.trade.id})
        self.assertEqual(response_filtered.status_code, 200)
        self.assertContains(response_filtered, 'Gate Fabrication')

    def test_job_detail_public_view(self):
        url = reverse('marketplace:job_detail', kwargs={'pk': self.active_job.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Gate Fabrication')
        self.assertContains(response, 'Kemi Fabrications')

    def test_job_create_view_employer(self):
        self.client.force_login(self.employer_user)
        create_url = reverse('marketplace:job_create')
        response = self.client.get(create_url)
        self.assertEqual(response.status_code, 200)

        post_data = {
            'trade_category': self.trade.id,
            'title': 'Staircase Railing Installation',
            'description': 'Install steel railings across 3 flights of stairs.',
            'job_type': 'contract',
            'pay_type': 'fixed',
            'pay_min': '120000.00',
            'pay_max': '150000.00',
            'slots': 1,
            'state': 'lagos',
            'deadline': (timezone.now().date() + datetime.timedelta(days=30)).strftime('%Y-%m-%d'),
            'required_skills': [self.skill.id]
        }
        post_response = self.client.post(create_url, post_data)
        self.assertEqual(post_response.status_code, 302)
        self.assertTrue(Job.objects.filter(title='Staircase Railing Installation').exists())

    def test_job_apply_view_worker(self):
        self.client.force_login(self.worker_user)
        apply_url = reverse('marketplace:job_apply', kwargs={'pk': self.active_job.pk})

        response = self.client.get(apply_url)
        self.assertEqual(response.status_code, 200)

        post_data = {'cover_note': 'I have 7 years experience fabricating estate gates.'}
        post_response = self.client.post(apply_url, post_data)
        self.assertRedirects(post_response, reverse('marketplace:worker_dashboard'))

        # Check application created
        app = JobApplication.objects.filter(job=self.active_job, worker=self.worker).first()
        self.assertIsNotNone(app)
        self.assertEqual(app.status, JobApplication.Status.PENDING)

        # Check employer received notification
        notif = Notification.objects.filter(user=self.employer_user, notif_type=Notification.NotifType.NEW_APPLICATION).first()
        self.assertIsNotNone(notif)

    def test_withdraw_application(self):
        app = JobApplication.objects.create(job=self.active_job, worker=self.worker)
        self.client.force_login(self.worker_user)

        withdraw_url = reverse('marketplace:application_withdraw', kwargs={'pk': app.pk})
        response = self.client.post(withdraw_url)
        self.assertRedirects(response, reverse('marketplace:worker_applications'))

        app.refresh_from_db()
        self.assertEqual(app.status, JobApplication.Status.WITHDRAWN)

    def test_toggle_save_job(self):
        self.client.force_login(self.worker_user)
        save_url = reverse('marketplace:job_save_toggle', kwargs={'pk': self.active_job.pk})

        # Save job
        response_save = self.client.post(save_url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response_save.status_code, 200)
        self.assertTrue(SavedJob.objects.filter(job=self.active_job, worker=self.worker).exists())

        # Unsave job
        response_unsave = self.client.post(save_url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response_unsave.status_code, 200)
        self.assertFalse(SavedJob.objects.filter(job=self.active_job, worker=self.worker).exists())

    def test_accept_application_creates_contract(self):
        app = JobApplication.objects.create(job=self.active_job, worker=self.worker)
        self.client.force_login(self.employer_user)

        update_url = reverse('marketplace:application_update', kwargs={'pk': app.pk})
        post_data = {'status': 'accepted', 'employer_note': 'Welcome aboard.'}
        response = self.client.post(update_url, post_data)
        self.assertEqual(response.status_code, 302)

        app.refresh_from_db()
        self.assertEqual(app.status, JobApplication.Status.ACCEPTED)

        # Verify Contract was automatically created for this accepted application
        contract = Contract.objects.filter(application=app).first()
        self.assertIsNotNone(contract)
        self.assertEqual(contract.worker, self.worker)
        self.assertEqual(contract.employer, self.employer)
        self.assertEqual(contract.job, self.active_job)
