"""
jobs/management/commands/seed_more_plumber_jobs.py
=================================================

Creates 10 additional plumbing jobs designed to be semantically relevant
to experienced plumber profiles focused on:

    - Abuja / FCT
    - Residential and commercial plumbing
    - Water management
    - Pipe layout and sizing
    - PPR / PVC pipework
    - Borehole systems
    - Water pumps
    - Water tanks
    - Bathroom / sanitary fittings
    - Water heaters
    - Drainage
    - Pressure testing
    - Leak detection
    - Preventive maintenance
    - Gwarinpa
    - Kubwa
    - Lugbe
    - Maitama
    - Ariston
    - Geepee
    - Vado

Usage
-----

    python manage.py seed_more_plumber_jobs

    python manage.py seed_more_plumber_jobs --dry-run

    python manage.py seed_more_plumber_jobs --clear
"""

from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction

from jobs.models import TradeCategory, Job
from .seed_category_jobs import get_or_create_seed_employer


PLUMBER_CATEGORY_SLUG = "plumber"
JOB_DEADLINE_DAYS = 45


# ============================================================================
# 10 ADDITIONAL PLUMBER JOBS
# ============================================================================

MORE_PLUMBER_JOBS = [

    {
        "title": (
            "Plumbing Installation Technician — 20 Luxury Duplexes "
            "(Maitama)"
        ),
        "description": (
            "Experienced plumber required for plumbing installation across "
            "20 luxury duplexes in Maitama, Abuja. Work includes PPR and PVC "
            "cold and hot water pipework, pipe sizing, bathroom and sanitary "
            "fixture installation, concealed plumbing, water heater "
            "installation, drainage connections, pressure testing and final "
            "commissioning. Experience with Ariston water heaters and premium "
            "bathroom fittings is preferred."
        ),
        "job_type": Job.JobType.CONTRACT,
        "pay_type": Job.PayType.FIXED,
        "pay_min": 450_000,
        "pay_max": 750_000,
        "state": "fct",
        "lga": "Maitama",
        "slots": 3,
    },

    {
        "title": (
            "Borehole Water System Technician — Gwarinpa Estate"
        ),
        "description": (
            "Plumbing technician required to maintain and upgrade the complete "
            "borehole water system of a residential estate in Gwarinpa, Abuja. "
            "Responsibilities include submersible pump installation, pump "
            "connections, pressure testing, water tank connections, PPR and "
            "PVC distribution lines, leak detection and water-pressure "
            "management. Experience with residential borehole and water "
            "storage systems is required."
        ),
        "job_type": Job.JobType.FULL_TIME,
        "pay_type": Job.PayType.MONTHLY,
        "pay_min": 120_000,
        "pay_max": 190_000,
        "state": "fct",
        "lga": "Gwarinpa",
        "slots": 1,
    },

    {
        "title": (
            "PPR Pipe Network Installer — New Apartments (Lugbe)"
        ),
        "description": (
            "Skilled plumber needed for installation of PPR water supply "
            "networks in 30 new apartments in Lugbe, Abuja. The scope includes "
            "pipe layout, PPR pipe sizing, hot and cold water distribution, "
            "tank connections, bathroom fixture connections, pressure testing, "
            "leak checks and final commissioning. Experience with multi-unit "
            "residential plumbing projects is preferred."
        ),
        "job_type": Job.JobType.CONTRACT,
        "pay_type": Job.PayType.FIXED,
        "pay_min": 380_000,
        "pay_max": 620_000,
        "state": "fct",
        "lga": "Lugbe",
        "slots": 4,
    },

    {
        "title": (
            "Commercial Plumbing Maintenance Specialist — Abuja"
        ),
        "description": (
            "Commercial plumbing specialist required for scheduled "
            "maintenance across offices and commercial buildings in Abuja. "
            "Duties include leak detection, PPR and PVC pipe repairs, water "
            "pressure testing, bathroom and sanitary fixture maintenance, "
            "water heater servicing, drainage inspection, tank connections "
            "and preventive plumbing maintenance. Candidate should be "
            "comfortable handling both reactive plumbing faults and planned "
            "maintenance."
        ),
        "job_type": Job.JobType.PART_TIME,
        "pay_type": Job.PayType.MONTHLY,
        "pay_min": 110_000,
        "pay_max": 190_000,
        "state": "fct",
        "lga": "Wuse",
        "slots": 2,
    },

    {
        "title": (
            "Bathroom & Sanitary Fitting Plumber — Luxury Residence "
            "(Kubwa)"
        ),
        "description": (
            "Experienced bathroom plumber required for a luxury residence "
            "in Kubwa, Abuja. Install and commission showers, WC systems, "
            "washbasins, bathroom mixers, concealed pipework, hot and cold "
            "water lines and drainage connections. Additional duties include "
            "water heater installation, pressure testing and leak detection. "
            "Experience with Vado or similar premium bathroom fittings is "
            "an advantage."
        ),
        "job_type": Job.JobType.ONCE_OFF,
        "pay_type": Job.PayType.FIXED,
        "pay_min": 180_000,
        "pay_max": 320_000,
        "state": "fct",
        "lga": "Kubwa",
        "slots": 1,
    },

    {
        "title": (
            "Water Tank & Pump Plumbing Specialist — Lugbe Housing Project"
        ),
        "description": (
            "Plumbing technician required to install and connect overhead "
            "and underground water tanks for a housing project in Lugbe, "
            "Abuja. Work includes borehole pump connections, tank inlet and "
            "outlet pipework, PPR and PVC distribution systems, valves, "
            "pressure testing, leak detection and commissioning of the complete "
            "water supply network."
        ),
        "job_type": Job.JobType.CONTRACT,
        "pay_type": Job.PayType.FIXED,
        "pay_min": 300_000,
        "pay_max": 520_000,
        "state": "fct",
        "lga": "Lugbe",
        "slots": 2,
    },

    {
        "title": (
            "Drainage & Wastewater Plumber — Commercial Property (Abuja)"
        ),
        "description": (
            "Professional plumber required for drainage and wastewater "
            "installation and repair at a commercial property in Abuja. "
            "Work includes PVC waste pipe installation, drainage system "
            "configuration, inspection of blocked lines, sanitary fixture "
            "connections, leak detection, pressure testing and general "
            "plumbing maintenance. Experience with commercial drainage "
            "systems is required."
        ),
        "job_type": Job.JobType.CONTRACT,
        "pay_type": Job.PayType.FIXED,
        "pay_min": 250_000,
        "pay_max": 450_000,
        "state": "fct",
        "lga": "Garki",
        "slots": 2,
    },

    {
        "title": (
            "Water Heater Installation & Plumbing Technician — Gwarinpa"
        ),
        "description": (
            "Plumber required for installation and servicing of domestic "
            "water heaters in residential properties across Gwarinpa, Abuja. "
            "Responsibilities include Ariston water heater installation, "
            "hot and cold PPR/PVC pipe connections, water pressure checks, "
            "bathroom fixture connections, leak detection, pressure testing "
            "and preventive maintenance. Hands-on experience with residential "
            "water-heating systems is preferred."
        ),
        "job_type": Job.JobType.PART_TIME,
        "pay_type": Job.PayType.FIXED,
        "pay_min": 80_000,
        "pay_max": 180_000,
        "state": "fct",
        "lga": "Gwarinpa",
        "slots": 2,
    },

    {
        "title": (
            "Master Plumber — Estate Water Supply & Maintenance "
            "(Abuja)"
        ),
        "description": (
            "Master plumber required to oversee water supply, plumbing "
            "installation and maintenance for a residential estate in Abuja. "
            "Responsibilities cover complete water-management systems, "
            "borehole pumps, storage tanks, PPR and PVC pipe sizing, water "
            "distribution, bathroom and sanitary fittings, drainage systems, "
            "water heaters, pressure testing, leak detection and scheduled "
            "preventive maintenance. Candidates should have extensive "
            "residential and commercial plumbing experience."
        ),
        "job_type": Job.JobType.FULL_TIME,
        "pay_type": Job.PayType.MONTHLY,
        "pay_min": 170_000,
        "pay_max": 300_000,
        "state": "fct",
        "lga": "Abuja Municipal",
        "slots": 1,
    },

    {
        "title": (
            "Residential Plumbing Fault & Leak Specialist — Maitama"
        ),
        "description": (
            "Experienced residential plumber required for plumbing fault "
            "diagnosis and leak repairs in Maitama. Duties include locating "
            "concealed pipe leaks, repairing PPR and PVC pipework, testing "
            "water pressure, repairing bathroom fixtures, servicing water "
            "heaters, inspecting drainage systems and carrying out scheduled "
            "preventive maintenance. Experience with high-end residential "
            "plumbing systems is preferred."
        ),
        "job_type": Job.JobType.PART_TIME,
        "pay_type": Job.PayType.DAILY,
        "pay_min": 20_000,
        "pay_max": 35_000,
        "state": "fct",
        "lga": "Maitama",
        "slots": 2,
    },
]


# ============================================================================
# MANAGEMENT COMMAND
# ============================================================================

class Command(BaseCommand):

    help = (
        "Creates 10 additional plumbing jobs strongly aligned with "
        "experienced Abuja plumber profiles."
    )

    def add_arguments(self, parser):

        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview the jobs without writing to the database.",
        )

        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete these 10 jobs before recreating them.",
        )

    def handle(self, *args, **options):

        dry_run = options["dry_run"]
        clear = options["clear"]

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                "\n🔧 TradeLink NG — seed_more_plumber_jobs\n"
            )
        )

        self.stdout.write(
            f"  Configured jobs: {len(MORE_PLUMBER_JOBS)}\n"
        )

        # ------------------------------------------------------------------
        # SEED EMPLOYER
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
        # CLEAR
        # ------------------------------------------------------------------

        if clear and not dry_run:

            self._clear_jobs(
                employer=employer,
                category=category,
            )

        # ------------------------------------------------------------------
        # CREATE
        # ------------------------------------------------------------------

        created = 0
        skipped = 0

        with transaction.atomic():

            for job_data in MORE_PLUMBER_JOBS:

                title = job_data["title"]

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
                    "\n✅ Additional plumber jobs completed.\n"
                    f"   Created: {created}\n"
                    f"   Skipped: {skipped}\n"
                    f"   Configured: {len(MORE_PLUMBER_JOBS)}"
                )
            )

    # =========================================================================
    # CLEAR
    # =========================================================================

    def _clear_jobs(self, employer, category):

        titles = [
            job["title"]
            for job in MORE_PLUMBER_JOBS
        ]

        deleted, _ = Job.objects.filter(
            employer=employer,
            trade_category=category,
            title__in=titles,
        ).delete()

        self.stdout.write(
            self.style.WARNING(
                f"\n⚠️ Deleted {deleted} additional plumber jobs.\n"
            )
        )