"""
jobs/management/commands/recompute_embeddings.py
================================================
Management command to trigger a full embedding recompute for all
Jobs, WorkerProfiles, and Products via Celery tasks.

Usage (Railway "Run Command" or local shell):
    python manage.py recompute_embeddings
    python manage.py recompute_embeddings --jobs-only
    python manage.py recompute_embeddings --dry-run

This is needed after switching embedding models (e.g. from
sentence-transformers/all-mpnet-base-v2 to BAAI/bge-base-en-v1.5)
because the vector spaces are incompatible and all stored embeddings
must be regenerated.
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Queue Celery tasks to regenerate text_embedding for all Jobs, "
        "WorkerProfiles, and Products. Run this after switching embedding models."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--jobs-only",
            action="store_true",
            help="Only recompute Job + WorkerProfile embeddings (skip Products).",
        )
        parser.add_argument(
            "--products-only",
            action="store_true",
            help="Only recompute Product embeddings (skip Jobs + Workers).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print counts but don't actually queue any tasks.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        jobs_only = options["jobs_only"]
        products_only = options["products_only"]

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no tasks will be queued."))

        # ── Jobs + WorkerProfiles ──────────────────────────────────────────
        if not products_only:
            try:
                from jobs.tasks import recompute_all_embeddings_task
                from jobs.models import Job, WorkerProfile

                job_count = Job.objects.filter(status=Job.Status.ACTIVE).count()
                worker_count = WorkerProfile.objects.count()

                self.stdout.write(
                    f"Jobs app: {job_count} active jobs + {worker_count} worker profiles to recompute."
                )

                if not dry_run:
                    result = recompute_all_embeddings_task.delay()
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"✓ Queued recompute_all_embeddings_task (task id: {result.id})"
                        )
                    )
            except Exception as exc:
                self.stderr.write(
                    self.style.ERROR(f"✗ Failed to queue jobs embedding task: {exc}")
                )

        # ── Products ──────────────────────────────────────────────────────
        if not jobs_only:
            try:
                from marketplace.tasks import recompute_all_product_embeddings_task
                from marketplace.models import Product

                product_count = Product.objects.filter(
                    status=Product.Status.ACTIVE
                ).count()

                self.stdout.write(
                    f"Marketplace app: {product_count} active products to recompute."
                )

                if not dry_run:
                    result = recompute_all_product_embeddings_task.delay()
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"✓ Queued recompute_all_product_embeddings_task (task id: {result.id})"
                        )
                    )
            except Exception as exc:
                self.stderr.write(
                    self.style.ERROR(f"✗ Failed to queue products embedding task: {exc}")
                )

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run complete — nothing was queued."))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    "\nAll embedding tasks queued! Celery workers will process them in the background.\n"
                    "Monitor progress in Celery logs — look for 'compute_job_embedding_task' and\n"
                    "'compute_product_embedding_task' completions."
                )
            )
