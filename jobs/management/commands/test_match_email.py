"""
jobs/management/commands/test_match_email.py
=============================================
Management command to test the job-match email notification
without needing Celery or a real CLIPMatch row.

Usage
-----
# Send to the worker whose username or email you specify:
    python manage.py test_match_email --worker <username_or_email>

# Send to ALL workers who have at least one qualifying CLIPMatch:
    python manage.py test_match_email --all

# Send using the real task (goes through Celery/Resend):
    python manage.py test_match_email --worker <username_or_email> --real

# Dry run (renders the template to stdout, does NOT send):
    python manage.py test_match_email --worker <username_or_email> --dry-run
"""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    help = "Send a test job-match email notification to a worker."

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument(
            '--worker',
            metavar='USERNAME_OR_EMAIL',
            help='Username or email of the WorkerProfile to target.',
        )
        group.add_argument(
            '--all',
            action='store_true',
            dest='all_workers',
            help='Send to all workers who have qualifying CLIPMatch rows.',
        )
        parser.add_argument(
            '--real',
            action='store_true',
            help='Use the real Celery task (requires Celery worker running). '
                 'Default: run the task inline (synchronous).',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            dest='dry_run',
            help='Render the template and print to stdout - do NOT send.',
        )

    # --------------------------------------------------------------------------

    def handle(self, *args, **options):
        from jobs.models import WorkerProfile, CLIPMatch, Job

        if options['all_workers']:
            profiles = list(
                WorkerProfile.objects.select_related('user')
                .filter(user__email__gt='')  # must have an email
            )
            if not profiles:
                raise CommandError("No WorkerProfiles with email addresses found.")
            self.stdout.write(f"Targeting {len(profiles)} workers...")
        else:
            ident = options['worker']
            try:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                user = User.objects.get(email=ident) if '@' in ident else User.objects.get(username=ident)
                profiles = [user.worker_profile]
            except Exception as exc:
                raise CommandError(f"Could not find a WorkerProfile for '{ident}': {exc}")

        for profile in profiles:
            self._process(profile, options)

    # --------------------------------------------------------------------------

    def _process(self, worker, options):
        from jobs.models import CLIPMatch, Job
        from django.template.loader import render_to_string

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\n>  Worker: {worker.user.username} <{worker.user.email}>"
        ))

        # -- Build match data --------------------------------------------------
        # Try real CLIPMatch rows first; fall back to fake data for testing
        matches_qs = (
            CLIPMatch.objects.filter(
                worker=worker,
                job__status=Job.Status.ACTIVE,
                job__deadline__gte=timezone.now().date(),
                is_applied=False,
                score__gte=0.60,
            )
            .exclude(job__applications__worker=worker)
            .select_related('job__employer', 'job__trade_category')
            .prefetch_related('job__required_skills')
            .order_by('-score')[:5]
        )

        match_data = []
        for m in matches_qs:
            job = m.job
            pay_display = (
                f"NGN {job.pay_min:,.0f}-NGN {job.pay_max:,.0f} {job.get_pay_type_display()}"
                if job.pay_min and job.pay_max
                else job.get_pay_type_display()
            )
            location = ', '.join(filter(None, [job.lga, job.get_state_display()]))
            match_data.append({
                'title':    job.title,
                'employer': str(job.employer),
                'location': location or 'Nigeria',
                'pay':      pay_display,
                'score':    round(m.score * 100),
                'job_type': job.get_job_type_display(),
                'job_url':  f"https://tradelink.ng/jobs/{job.pk}/",
            })

        # -- Use fake data when no real matches exist --------------------------
        if not match_data:
            self.stdout.write(
                self.style.WARNING(
                    "  No real CLIPMatch rows found - using FAKE data for preview."
                )
            )
            match_data = [
                {
                    'title':    'Senior Electrician - Solar Installation',
                    'employer': 'GreenTech Energy Ltd',
                    'location': 'Lekki, Lagos',
                    'pay':      'NGN 45,000-NGN 60,000 Per Day',
                    'score':    94,
                    'job_type': 'Contract',
                    'job_url':  'https://tradelink.ng/jobs/test-1/',
                },
                {
                    'title':    'Lead Plumber - New Housing Project',
                    'employer': 'BuildRight Construction',
                    'location': 'Abuja, FCT',
                    'pay':      'NGN 30,000-NGN 50,000 Per Day',
                    'score':    88,
                    'job_type': 'Contract',
                    'job_url':  'https://tradelink.ng/jobs/test-2/',
                },
                {
                    'title':    'CCTV & Security Systems Technician',
                    'employer': 'SecureMax Nigeria',
                    'location': 'Ikeja, Lagos',
                    'pay':      'Negotiable',
                    'score':    81,
                    'job_type': 'Full-Time',
                    'job_url':  'https://tradelink.ng/jobs/test-3/',
                },
            ]

        ctx = {
            'worker_name': worker.user.first_name or worker.user.username,
            'matches':     match_data,
            'match_count': len(match_data),
        }

        # -- Dry run: just print the rendered HTML ----------------------------─
        if options['dry_run']:
            html = render_to_string('emails/job_matches_notification.html', ctx)
            self.stdout.write(self.style.SUCCESS("\n-- Rendered HTML (dry run) --"))
            self.stdout.write(html[:3000] + "\n... (truncated)")
            return

        # -- Real Celery task --------------------------------------------------
        if options['real']:
            from jobs.tasks import send_job_match_email_task
            send_job_match_email_task.delay(str(worker.pk))
            self.stdout.write(self.style.SUCCESS(
                f"  [OK] Queued send_job_match_email_task for worker {worker.pk}"
            ))
            return

        # -- Inline send (default - synchronous, uses Django Email Backend / Gmail) --
        from django.conf import settings
        from django.core.mail import EmailMultiAlternatives
        from django.utils.html import strip_tags

        html_content = render_to_string('emails/job_matches_notification.html', ctx)

        count = len(match_data)
        suffix = 'es' if count > 1 else ''
        subject = f"[MATCH] {count} new job match{suffix} for you on TradeLink NG"
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None) or getattr(settings, 'EMAIL_HOST_USER', 'noreply@tradelink.ng')
        to_email = [worker.user.email]
        text_content = strip_tags(html_content)

        try:
            msg = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=from_email,
                to=to_email,
            )
            msg.attach_alternative(html_content, "text/html")
            msg.send(fail_silently=False)

            self.stdout.write(self.style.SUCCESS(
                f"  [OK] Email successfully sent to {worker.user.email} via {settings.EMAIL_BACKEND}!"
            ))
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"  [ERROR] Send failed: {exc}"))
