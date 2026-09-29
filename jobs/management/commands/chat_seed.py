"""
jobs/management/commands/seed_additional_category_jobs.py
==========================================================

Adds 5 additional job listings to EVERY trade category defined
in seed_category_jobs.py.

17 categories × 5 jobs = 85 additional jobs.

The command reuses:
    - TRADE_CATEGORIES
    - get_or_create_seed_employer()

from seed_category_jobs.py

Features:
    - Idempotent: safe to run multiple times
    - Creates exactly 5 additional jobs per category
    - Does not duplicate existing jobs
    - Supports --dry-run
    - Supports --only
    - Supports --clear
    - Jobs are ACTIVE
    - Deadlines are spread over the next 30–60 days

Usage:

    python manage.py seed_additional_category_jobs

    python manage.py seed_additional_category_jobs --dry-run

    python manage.py seed_additional_category_jobs \
        --only electrician,plumber,carpenter

    python manage.py seed_additional_category_jobs --clear
"""

import random
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction

from jobs.models import TradeCategory, Skill, Job, EmployerProfile

from .seed_category_jobs import (
    TRADE_CATEGORIES,
    get_or_create_seed_employer,
)


# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

JOBS_PER_CATEGORY = 5

ADDITIONAL_JOB_PREFIX = "Additional Seed — "

LOCATIONS = [
    ("lagos", "Ikeja"),
    ("lagos", "Lekki"),
    ("lagos", "Surulere"),
    ("fct", "Garki"),
    ("fct", "Wuse 2"),
    ("rivers", "Port Harcourt"),
    ("oyo", "Ibadan North"),
    ("ogun", "Ado-Odo/Ota"),
    ("enugu", "Enugu North"),
    ("kano", "Kano Municipal"),
    ("kaduna", "Kaduna South"),
    ("delta", "Warri South"),
    ("anambra", "Awka South"),
    ("abia", "Aba North"),
    ("plateau", "Jos North"),
]


# ---------------------------------------------------------------------------
# JOB TYPES / PAYMENT TYPES
# ---------------------------------------------------------------------------

JOB_TYPES = [
    Job.JobType.CONTRACT,
    Job.JobType.ONCE_OFF,
    Job.JobType.FULL_TIME,
    Job.JobType.PART_TIME,
]

PAYMENT_TYPES = [
    Job.PayType.FIXED,
    Job.PayType.MONTHLY,
    Job.PayType.DAILY,
]


# ---------------------------------------------------------------------------
# PAY RANGES
#
# Generic ranges are used because the command is designed to work across
# every category without hard-coding 85 individual jobs.
# ---------------------------------------------------------------------------

PAY_RANGES = {
    Job.PayType.FIXED: [
        (50_000, 100_000),
        (100_000, 200_000),
        (150_000, 300_000),
        (250_000, 450_000),
        (400_000, 700_000),
    ],

    Job.PayType.MONTHLY: [
        (60_000, 100_000),
        (80_000, 130_000),
        (100_000, 160_000),
        (120_000, 200_000),
        (150_000, 250_000),
    ],

    Job.PayType.DAILY: [
        (10_000, 18_000),
        (15_000, 25_000),
        (20_000, 35_000),
        (25_000, 40_000),
        (30_000, 50_000),
    ],
}


class Command(BaseCommand):

    help = (
        "Creates 5 additional jobs for every trade category "
        "(85 jobs across 17 categories). Idempotent and safe to re-run."
    )

    # -----------------------------------------------------------------------
    # ARGUMENTS
    # -----------------------------------------------------------------------

    def add_arguments(self, parser):

        parser.add_argument(
            "--only",
            metavar="SLUGS",
            default="",
            help=(
                "Comma-separated category slugs to process. "
                "Example: --only electrician,plumber"
            ),
        )

        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created without writing to the database.",
        )

        parser.add_argument(
            "--clear",
            action="store_true",
            help=(
                "Delete jobs created by this command before creating them again."
            ),
        )

    # -----------------------------------------------------------------------
    # MAIN
    # -----------------------------------------------------------------------

    def handle(self, *args, **options):

        dry_run = options["dry_run"]

        only_slugs = {
            slug.strip()
            for slug in options["only"].split(",")
            if slug.strip()
        }

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                "\n🔧 TradeLink NG — Additional Category Jobs\n"
            )
        )

        self.stdout.write(
            f"  Target: {JOBS_PER_CATEGORY} new jobs × "
            f"{len(TRADE_CATEGORIES)} categories = "
            f"{JOBS_PER_CATEGORY * len(TRADE_CATEGORIES)} jobs\n"
        )

        if only_slugs:
            self.stdout.write(
                f"  Categories selected: {', '.join(sorted(only_slugs))}\n"
            )

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "\n  [DRY RUN] Nothing will be written to the database.\n"
                )
            )

        # -------------------------------------------------------------------
        # SEED EMPLOYER
        # -------------------------------------------------------------------

        _, employer = get_or_create_seed_employer()

        self.stdout.write(
            f"  Seed employer: {employer.company_name} "
            f"(pk={employer.pk})\n"
        )

        # -------------------------------------------------------------------
        # CLEAR
        # -------------------------------------------------------------------

        if options["clear"] and not dry_run:

            self._clear_additional_jobs(employer)

        # -------------------------------------------------------------------
        # CREATE JOBS
        # -------------------------------------------------------------------

        total_categories = 0
        total_jobs = 0

        with transaction.atomic():

            for trade_data in TRADE_CATEGORIES:

                if (
                    only_slugs
                    and trade_data["slug"] not in only_slugs
                ):
                    continue

                jobs_created = self._seed_category(
                    trade_data=trade_data,
                    employer=employer,
                    dry_run=dry_run,
                )

                total_categories += 1
                total_jobs += jobs_created

        # -------------------------------------------------------------------
        # SUMMARY
        # -------------------------------------------------------------------

        if dry_run:

            self.stdout.write(
                self.style.WARNING(
                    f"\n[DRY RUN] Would create {total_jobs} jobs "
                    f"across {total_categories} categories.\n"
                )
            )

        else:

            self.stdout.write(
                self.style.SUCCESS(
                    f"\n✅ Done — created {total_jobs} additional jobs "
                    f"across {total_categories} categories.\n"
                )
            )

    # -----------------------------------------------------------------------
    # CATEGORY
    # -----------------------------------------------------------------------

    def _seed_category(
        self,
        trade_data,
        employer,
        dry_run=False,
    ):

        category_slug = trade_data["slug"]

        # ---------------------------------------------------------------
        # GET / CREATE CATEGORY
        # ---------------------------------------------------------------

        category, category_created = TradeCategory.objects.get_or_create(
            slug=category_slug,
            defaults={
                "name": trade_data["name"],
                "icon_class": trade_data["icon_class"],
                "display_order": trade_data["display_order"],
                "clip_context_text": trade_data["clip_context_text"],
                "description": trade_data["description"],
                "is_active": True,
            },
        )

        if category_created:

            self.stdout.write(
                self.style.WARNING(
                    f"\n  ✚ Created missing category: "
                    f"{trade_data['name']}"
                )
            )

        else:

            self.stdout.write(
                f"\n  ✔ Category: {trade_data['name']}"
            )

        # ---------------------------------------------------------------
        # MAKE SURE CATEGORY SKILLS EXIST
        # ---------------------------------------------------------------

        skills = []

        for skill_name in trade_data.get("skills", []):

            skill_slug = (
                skill_name.lower()
                .replace(" ", "-")
                .replace("&", "and")
                .replace("/", "-")
                .replace("(", "")
                .replace(")", "")
            )

            skill, _ = Skill.objects.get_or_create(
                category=category,
                slug=skill_slug,
                defaults={
                    "name": skill_name,
                    "is_active": True,
                },
            )

            skills.append(skill_name)

        # ---------------------------------------------------------------
        # CREATE 5 ADDITIONAL JOBS
        # ---------------------------------------------------------------

        jobs_created = 0

        for index in range(1, JOBS_PER_CATEGORY + 1):

            job = self._build_job_data(
                trade_data=trade_data,
                index=index,
                skills=skills,
            )

            title = job["title"]

            # -----------------------------------------------------------
            # IDEMPOTENCY CHECK
            # -----------------------------------------------------------

            exists = Job.objects.filter(
                employer=employer,
                trade_category=category,
                title=title,
            ).exists()

            if exists:

                self.stdout.write(
                    f"     ↳ skip (exists): {title}"
                )

                continue

            # -----------------------------------------------------------
            # DEADLINE
            # -----------------------------------------------------------

            deadline = (
                date.today()
                + timedelta(
                    days=random.randint(30, 60)
                )
            )

            # -----------------------------------------------------------
            # CREATE
            # -----------------------------------------------------------

            if not dry_run:

                Job.objects.create(
                    employer=employer,
                    trade_category=category,
                    title=job["title"],
                    description=job["description"],
                    job_type=job["job_type"],
                    pay_type=job["pay_type"],
                    pay_min=job["pay_min"],
                    pay_max=job["pay_max"],
                    state=job["state"],
                    lga=job["lga"],
                    slots=job["slots"],
                    is_remote=job["is_remote"],
                    deadline=deadline,
                    status=Job.Status.ACTIVE,
                )

                self.stdout.write(
                    self.style.SUCCESS(
                        f"     ✚ created: {title}"
                    )
                )

            else:

                self.stdout.write(
                    f"     [dry-run] would create: {title}"
                )

            jobs_created += 1

        self.stdout.write(
            f"     Jobs: {jobs_created} new / "
            f"{JOBS_PER_CATEGORY} requested"
        )

        return jobs_created

    # -----------------------------------------------------------------------
    # BUILD JOB DATA
    # -----------------------------------------------------------------------

    def _build_job_data(
        self,
        trade_data,
        index,
        skills,
    ):

        category_name = trade_data["name"]

        # ---------------------------------------------------------------
        # Pick a skill for this job
        # ---------------------------------------------------------------

        if skills:

            skill = skills[
                (index - 1) % len(skills)
            ]

        else:

            skill = category_name

        # ---------------------------------------------------------------
        # Location
        # ---------------------------------------------------------------

        state, lga = LOCATIONS[
            (index - 1) % len(LOCATIONS)
        ]

        # ---------------------------------------------------------------
        # Job type
        # ---------------------------------------------------------------

        job_type = JOB_TYPES[
            (index - 1) % len(JOB_TYPES)
        ]

        # ---------------------------------------------------------------
        # Payment type
        # ---------------------------------------------------------------

        pay_type = PAYMENT_TYPES[
            (index - 1) % len(PAYMENT_TYPES)
        ]

        pay_min, pay_max = PAY_RANGES[pay_type][
            (index - 1) % len(PAY_RANGES[pay_type])
        ]

        # ---------------------------------------------------------------
        # Unique title
        # ---------------------------------------------------------------

        title = (
            f"{ADDITIONAL_JOB_PREFIX}"
            f"{category_name} — "
            f"{skill} Specialist #{index} — "
            f"{lga}"
        )

        # ---------------------------------------------------------------
        # Description
        # ---------------------------------------------------------------

        description = (
            f"We are looking for an experienced {category_name.lower()} "
            f"professional to handle {skill.lower()} work in {lga}, "
            f"{state.upper()}. "
            f"The successful candidate should have practical experience "
            f"in {skill.lower()}, provide quality workmanship, "
            f"communicate clearly with the client, and complete the "
            f"assignment within the agreed timeline. "
            f"Relevant previous work experience or portfolio is preferred."
        )

        # ---------------------------------------------------------------
        # Slots
        # ---------------------------------------------------------------

        slots = [1, 2, 2, 3, 1][index - 1]

        return {
            "title": title,
            "description": description,
            "job_type": job_type,
            "pay_type": pay_type,
            "pay_min": pay_min,
            "pay_max": pay_max,
            "state": state,
            "lga": lga,
            "slots": slots,
            "is_remote": False,
        }

    # -----------------------------------------------------------------------
    # CLEAR ONLY THIS COMMAND'S JOBS
    # -----------------------------------------------------------------------

    def _clear_additional_jobs(self, employer):

        self.stdout.write(
            self.style.WARNING(
                "\n⚠️  Removing jobs created by "
                "seed_additional_category_jobs..."
            )
        )

        deleted, _ = Job.objects.filter(
            employer=employer,
            title__startswith=ADDITIONAL_JOB_PREFIX,
        ).delete()

        self.stdout.write(
            f"  Deleted {deleted} additional seed job(s).\n"
        )