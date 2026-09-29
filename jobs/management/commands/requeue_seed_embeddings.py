"""
jobs/management/commands/requeue_seed_embeddings.py
=====================================================
Re-queues Celery embedding tasks for jobs created by the seed_jobs command.

Use this when the sentence-transformer was broken during the initial seed
run and the jobs were created with no embeddings (text_embedding = NULL).

What it does
-------------
  1. Finds the seed employer (tradelink_seed_employer).
  2. Queries all ACTIVE jobs belonging to that employer where
     text_embedding IS NULL  (i.e. embedding never computed).
  3. Calls compute_job_embedding_task.delay(job_id) for each one.

What it does NOT do
--------------------
  - Does NOT touch any jobs, workers, or profiles outside the seed employer.
  - Does NOT delete or modify any database rows.
  - Does NOT re-seed any data.

Options
--------
  --all       Re-queue ALL seed jobs, even those that already have an embedding
              (useful if you want to force a full re-encode after upgrading the
              sentence-transformer model).
  --dry-run   Print what would be queued without actually queuing anything.

Usage
------
    # Queue only the jobs that are still missing embeddings (default)
    python manage.py requeue_seed_embeddings

    # Force re-queue every seed job, with or without existing embeddings
    python manage.py requeue_seed_embeddings --all

    # Preview without touching Celery
    python manage.py requeue_seed_embeddings --dry-run
    python manage.py requeue_seed_embeddings --all --dry-run
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from jobs.models import Job, EmployerProfile

User = get_user_model()

SEED_EMPLOYER_USERNAME = "tradelink_seed_employer"


class Command(BaseCommand):
    help = (
        "Re-queues Celery embedding tasks for seeded jobs whose "
        "text_embedding is NULL (or all seeded jobs with --all). "
        "Safe to run — does not modify any database rows."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--all",
            action="store_true",
            dest="requeue_all",
            help=(
                "Re-queue ALL active seed jobs, even those that already "
                "have a text_embedding. Use after upgrading the model."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print the jobs that would be queued without queuing them.",
        )

    def handle(self, *args, **options):
        requeue_all = options["requeue_all"]
        dry_run     = options["dry_run"]

        # ── 1. Find the seed employer ────────────────────────────────────────
        try:
            user = User.objects.get(username=SEED_EMPLOYER_USERNAME)
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(
                f"\n✘  Seed user '{SEED_EMPLOYER_USERNAME}' not found. "
                "Run 'python manage.py seed_jobs' first.\n"
            ))
            return

        try:
            employer = EmployerProfile.objects.get(user=user)
        except EmployerProfile.DoesNotExist:
            self.stdout.write(self.style.ERROR(
                "\n✘  Seed employer profile not found. "
                "Run 'python manage.py seed_jobs' first.\n"
            ))
            return

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\n🔄  requeue_seed_embeddings — employer: {employer.company_name}\n"
        ))

        # ── 2. Build the queryset ────────────────────────────────────────────
        qs = Job.objects.filter(
            employer=employer,
            status=Job.Status.ACTIVE,
        ).select_related("trade_category")

        if not requeue_all:
            qs = qs.filter(text_embedding__isnull=True)

        total = qs.count()

        if total == 0:
            self.stdout.write(self.style.SUCCESS(
                "✔  No jobs to re-queue — all embeddings are already computed.\n"
                "   (Use --all to force re-queue even jobs that have embeddings.)\n"
            ))
            return

        mode = "ALL seed jobs" if requeue_all else "seed jobs missing embeddings"
        self.stdout.write(f"  Found {total} {mode}.\n")

        if dry_run:
            self.stdout.write(self.style.WARNING("  [DRY RUN] — nothing will be queued.\n"))

        # ── 3. Queue tasks ───────────────────────────────────────────────────
        from jobs.tasks import compute_job_embedding_task

        queued = 0
        for job in qs.iterator():
            trade = job.trade_category.name if job.trade_category else "—"
            has_embedding = "✔ has embedding" if job.text_embedding else "✘ no embedding"

            if dry_run:
                self.stdout.write(
                    f"  [dry-run] would queue: [{trade}] {job.title[:60]}  ({has_embedding})"
                )
            else:
                compute_job_embedding_task.delay(str(job.pk))
                queued += 1
                self.stdout.write(
                    f"  ✚ queued: [{trade}] {job.title[:60]}"
                )

        # ── 4. Summary ───────────────────────────────────────────────────────
        if dry_run:
            self.stdout.write(self.style.WARNING(
                f"\n  [DRY RUN] Would have queued {total} task(s). "
                "Re-run without --dry-run to apply.\n"
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"\n✅  Queued {queued} embedding task(s). "
                "Watch your Celery worker logs for progress.\n"
            ))