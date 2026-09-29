import datetime
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.core.exceptions import ValidationError

from jobs.models import TradeCategory, Skill, WorkerProfile, EmployerProfile, Job
from hiring.models import (
    WorkHistory, Certification, SkillEndorsement,
    SavedWorker, HiringInterest, SubscriptionPlan
)

User = get_user_model()


class HiringModelTests(TestCase):
    def setUp(self):
        self.worker_user = User.objects.create_user(
            username='techworker', email='worker@test.com', password='password123'
        )
        self.employer_user = User.objects.create_user(
            username='companyadmin', email='employer@test.com', password='password123'
        )
        self.trade = TradeCategory.objects.create(name='Electrical', slug='electrical')
        self.skill = Skill.objects.create(name='Wiring', category=self.trade)

        self.worker = WorkerProfile.objects.create(
            user=self.worker_user,
            trade_category=self.trade,
            years_experience=5,
            state='lagos',
            open_to_employment=True,
            expected_monthly_salary=180000.00
        )
        self.employer = EmployerProfile.objects.create(
            user=self.employer_user,
            company_name='Apex Engineering',
            state='lagos'
        )

    def test_work_history_creation_and_clean(self):
        history = WorkHistory(
            worker=self.worker,
            employer_name='Julius Berger',
            role_title='Senior Electrician',
            start_date=datetime.date(2020, 1, 1),
            is_current=True,
            location_state='lagos'
        )
        history.save()
        self.assertEqual(history.worker.user.username, 'techworker')
        self.assertTrue(history.is_current)

        # A current role cannot have an end date
        history.end_date = datetime.date(2023, 1, 1)
        with self.assertRaises(ValidationError):
            history.clean()

    def test_certification_creation(self):
        cert = Certification.objects.create(
            worker=self.worker,
            name='NABTEB Electrical Level 2',
            issuing_body='NABTEB',
            year_obtained=2021
        )
        self.assertFalse(cert.is_verified)
        self.assertIn('NABTEB', str(cert))

    def test_skill_endorsement_rules(self):
        # Employer endorses worker skill
        endorsement = SkillEndorsement.objects.create(
            worker=self.worker,
            skill=self.skill,
            endorsed_by=self.employer_user
        )
        self.assertEqual(SkillEndorsement.objects.count(), 1)

        # Worker cannot endorse own skill
        self_endorsement = SkillEndorsement(
            worker=self.worker,
            skill=self.skill,
            endorsed_by=self.worker_user
        )
        with self.assertRaises(ValidationError):
            self_endorsement.clean()

    def test_saved_worker_toggle(self):
        saved = SavedWorker.objects.create(
            employer=self.employer,
            worker=self.worker,
            note='Top candidate for Ikeja site'
        )
        self.assertEqual(SavedWorker.objects.count(), 1)
        self.assertIn('Top candidate', saved.note)

    def test_hiring_interest_flow(self):
        outreach = HiringInterest.objects.create(
            employer=self.employer,
            worker=self.worker,
            message='We would like to hire you full-time for our Lagos project.',
            salary_offer=200000.00
        )
        self.assertEqual(outreach.status, HiringInterest.Status.SENT)

        # Worker replies interested
        outreach.status = HiringInterest.Status.INTERESTED
        outreach.worker_reply = 'I am available starting next week.'
        outreach.save()
        self.assertEqual(outreach.status, HiringInterest.Status.INTERESTED)


class HiringViewTests(TestCase):
    def setUp(self):
        self.client = Client()

        self.worker_user = User.objects.create_user(
            username='worker1', email='worker1@test.com', password='password123'
        )
        self.employer_user = User.objects.create_user(
            username='emp1', email='emp1@test.com', password='password123'
        )

        self.trade = TradeCategory.objects.create(name='Plumbing', slug='plumbing')
        self.worker = WorkerProfile.objects.create(
            user=self.worker_user,
            trade_category=self.trade,
            state='lagos',
            open_to_employment=True
        )
        self.employer = EmployerProfile.objects.create(
            user=self.employer_user,
            company_name='BuildCraft Ltd',
            state='lagos'
        )

    def test_talent_search_view_employer_access(self):
        self.client.force_login(self.employer_user)
        url = reverse('hiring:talent_search')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Talent Search')
        self.assertContains(response, 'worker1')

    def test_send_hiring_interest(self):
        self.client.force_login(self.employer_user)
        url = reverse('hiring:send_interest', kwargs={'pk': self.worker.pk})

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        post_data = {
            'message': 'We are looking for an on-site master plumber.',
            'salary_offer': '175000'
        }
        post_response = self.client.post(url, post_data)
        self.assertRedirects(post_response, reverse('hiring:outreach_list'))
        self.assertTrue(HiringInterest.objects.filter(worker=self.worker, employer=self.employer).exists())

    def test_worker_inbox_and_reply(self):
        interest = HiringInterest.objects.create(
            employer=self.employer,
            worker=self.worker,
            message='Initial outreach'
        )

        self.client.force_login(self.worker_user)
        inbox_url = reverse('hiring:worker_inbox')
        response = self.client.get(inbox_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'BuildCraft Ltd')

        # Reply to interest
        reply_url = reverse('hiring:inbox_reply', kwargs={'pk': interest.pk})
        reply_data = {
            'response': 'interested',
            'message': 'Sounds great, let us connect.'
        }
        post_reply = self.client.post(reply_url, reply_data)
        self.assertRedirects(post_reply, inbox_url)

        interest.refresh_from_db()
        self.assertEqual(interest.status, 'interested')
        self.assertEqual(interest.worker_reply, 'Sounds great, let us connect.')
