"""
jobs/management/commands/seed_plumber_match_jobs.py
===================================================

Creates 10 highly relevant plumbing jobs designed to match experienced
residential/commercial plumber profiles, especially profiles containing:

    - Abuja / FCT
    - Gwarinpa
    - Kubwa
    - Lugbe
    - Maitama
    - residential plumbing
    - commercial plumbing
    - water management
    - pipe layout
    - PPR / PVC pipework
    - pipe sizing
    - borehole installation
    - submersible pumps
    - water tanks
    - bathroom / sanitary fixtures
    - water heaters
    - drainage systems
    - pressure testing
    - leak detection
    - preventive maintenance
    - Ariston
    - Geepee
    - Vado

Usage
-----

    python manage.py seed_plumber_match_jobs

    python manage.py seed_plumber_match_jobs --dry-run

    python manage.py seed_plumber_match_jobs --clear
"""

from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction

from jobs.models import TradeCategory, Job
from .seed_category_jobs import get_or_create_seed_employer


PLUMBER_CATEGORY_SLUG = "plumber"
JOB_DEADLINE_DAYS = 45


# ============================================================================
# 10 PLUMBER JOBS
# ============================================================================

PLUMBER_MATCH_JOBS = [

    # ------------------------------------------------------------------------
    # 1
    # ------------------------------------------------------------------------
    {
        "title": (
            "Residential Plumber — PPR Water Supply & Bathroom Installation "
            "(Gwarinpa)"
        ),
        "description": (
            "Experienced plumber required for residential plumbing work in "
            "Gwarinpa, Abuja. The project covers complete water-management "
            "installation including PPR and PVC pipe layout, pipe sizing, "
            "hot and cold water distribution, bathroom sanitary fixture "
            "installation, water heater installation, pressure testing, "
            "leak detection and final plumbing commissioning. Experience "
            "with Ariston water heaters and Vado bathroom fittings is "
            "preferred. Previous residential plumbing experience in Abuja "
            "and the FCT is an advantage."
        ),
        "job_type": Job.JobType.CONTRACT,
        "pay_type": Job.PayType.FIXED,
        "pay_min": 250_000,
        "pay_max": 450_000,
        "state": "fct",
        "lga": "Gwarinpa",
        "slots": 2,
    },

    # ------------------------------------------------------------------------
    # 2
    # ------------------------------------------------------------------------
    {
        "title": (
            "Borehole & Submersible Pump Installation Plumber — Kubwa"
        ),
        "description": (
            "Skilled plumber required for installation and commissioning of "
            "a complete water supply system for a residential property in "
            "Kubwa, Abuja. Responsibilities include borehole pump and "
            "submersible pump installation, underground and overhead water "
            "tank connections, PPR and PVC pipework, pipe sizing, water "
            "distribution, pressure testing and leak detection. Candidate "
            "must understand water pressure management, pump connections "
            "and complete residential plumbing systems."
        ),
        "job_type": Job.JobType.ONCE_OFF,
        "pay_type": Job.PayType.FIXED,
        "pay_min": 300_000,
        "pay_max": 550_000,
        "state": "fct",
        "lga": "Kubwa",
        "slots": 1,
    },

    # ------------------------------------------------------------------------
    # 3
    # ------------------------------------------------------------------------
    {
        "title": (
            "Commercial Plumbing Technician — Office Building (Maitama)"
        ),
        "description": (
            "Commercial plumber required for installation and maintenance "
            "of plumbing systems in a multi-floor office building in "
            "Maitama, Abuja. Work includes PPR and PVC pipe installation, "
            "water supply pipe layout, pipe sizing, bathroom and sanitary "
            "fixture installation, water heater connections, drainage "
            "configuration, pressure testing, leak detection and plumbing "
            "fault diagnosis. Preventive maintenance experience is required."
        ),
        "job_type": Job.JobType.CONTRACT,
        "pay_type": Job.PayType.FIXED,
        "pay_min": 350_000,
        "pay_max": 650_000,
        "state": "fct",
        "lga": "Maitama",
        "slots": 2,
    },

    # ------------------------------------------------------------------------
    # 4
    # ------------------------------------------------------------------------
    {
        "title": (
            "Leak Detection & Plumbing Maintenance Technician — Lugbe"
        ),
        "description": (
            "Experienced plumbing technician required to provide scheduled "
            "maintenance and leak detection services for residential "
            "properties in Lugbe, Abuja. Duties include diagnosing concealed "
            "water leaks, repairing PPR and PVC pipework, water-pressure "
            "testing, bathroom fixture repairs, water distribution system "
            "maintenance, drainage inspection and preventive plumbing "
            "maintenance."
        ),
        "job_type": Job.JobType.PART_TIME,
        "pay_type": Job.PayType.MONTHLY,
        "pay_min": 100_000,
        "pay_max": 180_000,
        "state": "fct",
        "lga": "Lugbe",
        "slots": 1,
    },

    # ------------------------------------------------------------------------
    # 5
    # ------------------------------------------------------------------------
    {
        "title": (
            "Water Heater & Bathroom Plumbing Specialist — Maitama"
        ),
        "description": (
            "Plumber required for luxury residential bathroom plumbing in "
            "Maitama. The project includes installation of Ariston water "
            "heaters, hot and cold water pipework, Vado bathroom fixtures, "
            "showers, washbasins, concealed plumbing, pressure testing, "
            "water-pressure checks, leak detection and final commissioning. "
            "Strong hands-on experience in bathroom plumbing and water heater "
            "installation is required."
        ),
        "job_type": Job.JobType.CONTRACT,
        "pay_type": Job.PayType.FIXED,
        "pay_min": 220_000,
        "pay_max": 400_000,
        "state": "fct",
        "lga": "Maitama",
        "slots": 1,
    },

    # ------------------------------------------------------------------------
    # 6
    # ------------------------------------------------------------------------
    {
        "title": (
            "Residential Water Management Plumber — Estate Project (Abuja)"
        ),
        "description": (
            "Experienced plumber required for complete water-management "
            "services across a residential estate in Abuja. Responsibilities "
            "include borehole and pump connections, overhead and underground "
            "water tanks, PPR and PVC distribution pipework, pipe sizing, "
            "water-pressure testing, bathroom and sanitary fixture fitting, "
            "water heater installation, drainage maintenance and routine "
            "leak detection. Previous experience on residential estates is "
            "preferred."
        ),
        "job_type": Job.JobType.FULL_TIME,
        "pay_type": Job.PayType.MONTHLY,
        "pay_min": 140_000,
        "pay_max": 220_000,
        "state": "fct",
        "lga": "Gwarinpa",
        "slots": 2,
    },

    # ------------------------------------------------------------------------
    # 7
    # ------------------------------------------------------------------------
    {
        "title": (
            "Drainage & Sanitary Plumbing Technician — Kubwa"
        ),
        "description": (
            "Professional plumber needed for residential and commercial "
            "drainage and sanitary plumbing work in Kubwa, Abuja. The role "
            "includes bathroom plumbing, WC and basin installation, sanitary "
            "fittings, PVC waste pipes, drainage system configuration, water "
            "supply pipe installation, pressure testing, leak detection and "
            "general plumbing maintenance. Strong practical experience in "
            "Abuja plumbing projects is preferred."
        ),
        "job_type": Job.JobType.CONTRACT,
        "pay_type": Job.PayType.FIXED,
        "pay_min": 180_000,
        "pay_max": 320_000,
        "state": "fct",
        "lga": "Kubwa",
        "slots": 2,
    },

    # ------------------------------------------------------------------------
    # 8
    # ------------------------------------------------------------------------
    {
        "title": (
            "PPR/PVC Pipe Fitting & Pressure Testing Specialist — Lugbe"
        ),
        "description": (
            "Skilled plumbing technician required for a new housing "
            "development in Lugbe, Abuja. Work includes measuring and sizing "
            "PPR and PVC pipes, installing cold and hot water lines, "
            "connecting storage tanks and water pumps, pressure testing the "
            "complete water system, identifying leaks and completing final "
            "plumbing commissioning. Residential water distribution "
            "experience is required."
        ),
        "job_type": Job.JobType.CONTRACT,
        "pay_type": Job.PayType.FIXED,
        "pay_min": 280_000,
        "pay_max": 500_000,
        "state": "fct",
        "lga": "Lugbe",
        "slots": 3,
    },

    # ------------------------------------------------------------------------
    # 9
    # ------------------------------------------------------------------------
    {
        "title": (
            "Borehole, Water Tank & Plumbing Maintenance Technician — Abuja"
        ),
        "description": (
            "Plumbing technician required for ongoing maintenance of "
            "borehole water systems serving residential and commercial "
            "properties across Abuja. Duties include borehole pump inspection, "
            "water tank connections, PPR and PVC pipe repairs, pressure "
            "testing, leak detection, water heater servicing, bathroom "
            "fixture repairs, drainage checks and scheduled preventive "
            "maintenance."
        ),
        "job_type": Job.JobType.PART_TIME,
        "pay_type": Job.PayType.DAILY,
        "pay_min": 20_000,
        "pay_max": 35_000,
        "state": "fct",
        "lga": "Garki",
        "slots": 2,
    },

    # ------------------------------------------------------------------------
    # 10
    # ------------------------------------------------------------------------
    {
        "title": (
            "Senior Master Plumber — Residential & Commercial Water "
            "Management (Abuja)"
        ),
        "description": (
            "Senior certified plumber required for residential and commercial "
            "plumbing projects throughout the FCT, including Gwarinpa, "
            "Kubwa, Lugbe and Maitama. The role covers complete water-"
            "management systems from pipe layout and PPR/PVC pipe sizing "
            "through borehole and submersible pump installation, overhead "
            "and underground water tanks, bathroom and sanitary fittings, "
            "water heater installation, drainage configuration, pressure "
            "testing, leak detection and scheduled preventive maintenance. "
            "Experience with Ariston water heaters, Geepee water tanks and "
            "Vado bathroom fittings is preferred. Applicants should have a "
            "strong record of completed residential and commercial plumbing "
            "projects and strong practical knowledge of water-pressure "
            "management and plumbing system commissioning in Abuja."
        ),
        "job_type": Job.JobType.FULL_TIME,
        "pay_type": Job.PayType.MONTHLY,
        "pay_min": 160_000,
        "pay_max": 280_000,
        "state": "fct",
        "lga": "Abuja Municipal",
        "slots": 1,
    },
]


# ============================================================================
# MANAGEMENT COMMAND
# ============================================================================

class Command(BaseCommand):

    help = (
        "Creates 10 plumber jobs strongly aligned with an experienced "
        "Abuja residential/commercial plumber profile."
    )

    def add_arguments(self, parser):

        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview jobs without writing to the database.",
        )

        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete these seeded plumber jobs before recreating them.",
        )

    def handle(self, *args, **options):

        dry_run = options["dry_run"]
        clear = options["clear"]

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                "\n🔧 TradeLink NG — seed_plumber_match_jobs\n"
            )
        )

        self.stdout.write(
            f"  Configured jobs: {len(PLUMBER_MATCH_JOBS)}\n"
        )

        # ------------------------------------------------------------------
        # SHARED SEED EMPLOYER
        # ------------------------------------------------------------------

        _, employer = get_or_create_seed_employer()

        self.stdout.write(
            f"  Seed employer: {employer.company_name} "
            f"(pk={employer.pk})\n"
        )

        # ------------------------------------------------------------------
        # PLUMBER CATEGORY
        # ------------------------------------------------------------------

        try:
            category = TradeCategory.objects.get(
                slug=PLUMBER_CATEGORY_SLUG
            )
        except TradeCategory.DoesNotExist:

            self.stdout.write(
                self.style.ERROR(
                    "\n❌ Plumber category does not exist."
                )
            )

            self.stdout.write(
                "Run:\n"
                "python manage.py seed_category_jobs --only plumber"
            )

            return

        # ------------------------------------------------------------------
        # DRY RUN
        # ------------------------------------------------------------------

        if dry_run:

            self.stdout.write(
                self.style.WARNING(
                    "\n[DRY RUN] Nothing will be written.\n"
                )
            )

        # ------------------------------------------------------------------
        # CLEAR
        # ------------------------------------------------------------------

        if clear and not dry_run:

            self._clear_jobs(
                employer=employer,
                category=category,
            )

        created = 0
        skipped = 0

        # ------------------------------------------------------------------
        # CREATE JOBS
        # ------------------------------------------------------------------

        with transaction.atomic():

            for job_data in PLUMBER_MATCH_JOBS:

                title = job_data["title"]

                # Idempotent check
                exists = Job.objects.filter(
                    employer=employer,
                    trade_category=category,
                    title=title,
                ).exists()

                if exists:

                    self.stdout.write(
                        f"  ↳ skip (exists): {title}"
                    )

                    skipped += 1
                    continue

                deadline = (
                    date.today()
                    + timedelta(days=JOB_DEADLINE_DAYS)
                )

                if dry_run:

                    self.stdout.write(
                        f"  [dry-run] would create: {title}"
                    )

                else:

                    Job.objects.create(
                        employer=employer,
                        trade_category=category,

                        title=job_data["title"],
                        description=job_data["description"],

                        job_type=job_data["job_type"],
                        pay_type=job_data["pay_type"],

                        pay_min=job_data["pay_min"],
                        pay_max=job_data["pay_max"],

                        state=job_data["state"],
                        lga=job_data["lga"],

                        slots=job_data.get("slots", 1),

                        is_remote=False,

                        deadline=deadline,

                        # Your matching pipeline expects active jobs.
                        status=Job.Status.ACTIVE,
                    )

                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  ✚ created: {title}"
                        )
                    )

                created += 1

        # ------------------------------------------------------------------
        # SUMMARY
        # ------------------------------------------------------------------

        if dry_run:

            self.stdout.write(
                self.style.WARNING(
                    f"\n[DRY RUN] Would create {created} jobs."
                )
            )

        else:

            self.stdout.write(
                self.style.SUCCESS(
                    "\n✅ Plumber job seeding completed.\n"
                    f"   Created: {created}\n"
                    f"   Skipped: {skipped}\n"
                    f"   Configured: {len(PLUMBER_MATCH_JOBS)}"
                )
            )

    # =========================================================================
    # CLEAR
    # =========================================================================

    def _clear_jobs(self, employer, category):

        titles = [
            job["title"]
            for job in PLUMBER_MATCH_JOBS
        ]

        deleted, _ = Job.objects.filter(
            employer=employer,
            trade_category=category,
            title__in=titles,
        ).delete()

        self.stdout.write(
            self.style.WARNING(
                f"\n⚠️ Deleted {deleted} existing plumber "
                f"match job(s).\n"
            )
        )