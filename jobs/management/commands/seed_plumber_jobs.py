"""
jobs/management/commands/seed_plumber_jobs.py
==============================================
Seeds 10 realistic plumbing job listings in Abuja (FCT) and surrounding
states, tailored for a certified master plumber with 7+ years of
residential and commercial experience.

Covers all core specialties in the target profile:
  - PPR & PVC pipe layout / sizing
  - Borehole & submersible pump installation (Geepee tanks)
  - Bathroom fixture fitting (Vado / Ariston brands)
  - Drainage system configuration
  - Pressure testing & water-line integrity checks
  - Water heater installation (Ariston)
  - Leak detection & scheduled maintenance

Locations span the target work areas:
  FCT — Gwarinpa, Kubwa, Lugbe, Maitama, Wuse, Garki, Central Abuja, Utako
  Nasarawa — Karu (bordering FCT)

Idempotent: safe to run multiple times; existing titles are skipped.

Usage
-----
    python manage.py seed_plumber_jobs               # create all 10 jobs
    python manage.py seed_plumber_jobs --dry-run     # preview without writing

What it does NOT do
--------------------
  - Does NOT create a new employer or trade category.
    Both must already exist (run seed_jobs first).
  - Does NOT delete or modify any existing rows.
"""

import logging
from datetime import date, timedelta
import random

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from jobs.models import TradeCategory, EmployerProfile, Job

logger = logging.getLogger(__name__)
User = get_user_model()

SEED_EMPLOYER_USERNAME = "tradelink_seed_employer"
TRADE_SLUG = "plumber"

# ──────────────────────────────────────────────────────────────────────────────
#  JOB DATA
#  All 10 jobs are specific to an Abuja-based certified master plumber with
#  expertise in water management, borehole systems, bathroom fitting,
#  pressure testing, PPR/PVC pipe sizing, and scheduled maintenance.
# ──────────────────────────────────────────────────────────────────────────────

PLUMBER_JOBS = [

    # ── 1 ────────────────────────────────────────────────────────────────────
    {
        "title": "Borehole & Geepee Tank Water System — Gwarinpa Estate",
        "description": (
            "Install a complete water supply system for a newly completed 12-unit "
            "terrace estate in Gwarinpa, Abuja. Scope: drill a 60 m borehole, supply "
            "and install a 1.5 HP Grundfos submersible pump, connect to two 5,000-litre "
            "Geepee overhead storage tanks, lay PPR rising mains and cold-water "
            "distribution lines to all units, and fit gate valves and pressure gauges "
            "at each riser. Pressure-test all lines to 10 bar before handover. "
            "Provide a one-year workmanship warranty."
        ),
        "job_type": Job.JobType.CONTRACT,
        "pay_type": Job.PayType.FIXED,
        "pay_min": 580_000,
        "pay_max": 850_000,
        "state": "fct",
        "lga": "Gwarinpa",
        "slots": 1,
        "is_remote": False,
    },

    # ── 2 ────────────────────────────────────────────────────────────────────
    {
        "title": "Luxury Bathroom Fit-Out with Vado Fixtures (Maitama)",
        "description": (
            "Complete a full bathroom renovation in a 5-bedroom luxury residence in "
            "Maitama, Abuja. Works include stripping out existing sanitary ware, "
            "repositioning supply and waste lines, fitting Vado thermostatic shower "
            "systems, Vado chrome basin mixers, free-standing bath fillers, and "
            "wall-hung WC cisterns in all 4 bathrooms. Coordinate tile-ready substrate "
            "preparation with the tiling contractor. Must have hands-on experience with "
            "premium European sanitary fittings and be comfortable working in occupied, "
            "high-specification properties. Portfolio required."
        ),
        "job_type": Job.JobType.ONCE_OFF,
        "pay_type": Job.PayType.FIXED,
        "pay_min": 380_000,
        "pay_max": 560_000,
        "state": "fct",
        "lga": "Maitama",
        "slots": 1,
        "is_remote": False,
    },

    # ── 3 ────────────────────────────────────────────────────────────────────
    {
        "title": "Ariston Water Heater Installation — 24-Unit Apartment Block (Wuse)",
        "description": (
            "Supply and install 24 × 50-litre Ariston VELIS EVO electric water heaters "
            "in a new apartment block in Wuse 2, Abuja. Each unit requires a dedicated "
            "15 mm hot-water supply connection, cold-water inlet with pressure-reducing "
            "valve, T&P relief valve discharge pipe, and weatherproof earth bonding. "
            "Work to be completed floor by floor over three weeks. Coordinate with the "
            "electrical contractor for final power connections. Provide Ariston-approved "
            "installation certificates on completion."
        ),
        "job_type": Job.JobType.CONTRACT,
        "pay_type": Job.PayType.FIXED,
        "pay_min": 290_000,
        "pay_max": 420_000,
        "state": "fct",
        "lga": "Wuse",
        "slots": 1,
        "is_remote": False,
    },

    # ── 4 ────────────────────────────────────────────────────────────────────
    {
        "title": "PPR & PVC Pipe Layout — 30-Unit Housing Development (Kubwa)",
        "description": (
            "Carry out full hot and cold water pipe layout for a 30-unit housing "
            "development in Kubwa, Abuja. Design the pipe-sizing schedule (PPR PN20 "
            "for hot, uPVC Class E for cold), install all pipework in chases and "
            "ceiling voids, fit isolation valves at each apartment entry point, and "
            "perform pressure tests at each stage. Materials are supplied by the "
            "developer. Experience with developer-scale projects and ability to manage "
            "a small helper team are essential. Daily attendance log and site photo "
            "updates required."
        ),
        "job_type": Job.JobType.CONTRACT,
        "pay_type": Job.PayType.DAILY,
        "pay_min": 25_000,
        "pay_max": 38_000,
        "state": "fct",
        "lga": "Kubwa",
        "slots": 2,
        "is_remote": False,
    },

    # ── 5 ────────────────────────────────────────────────────────────────────
    {
        "title": "Commercial Drainage System Design & Installation (Lugbe)",
        "description": (
            "Design and install the below-ground drainage system for a new 3-storey "
            "commercial plaza in Lugbe, Abuja. Scope: prepare drainage layout drawings, "
            "size uPVC soil and waste stacks, install gullies, inspection chambers, "
            "grease traps for the ground-floor restaurant unit, and connect to the "
            "estate's existing sewer main. Carry out CCTV drain survey and flow test "
            "before practical completion sign-off. CORAN-compliant working drawings "
            "must accompany the final submission."
        ),
        "job_type": Job.JobType.ONCE_OFF,
        "pay_type": Job.PayType.FIXED,
        "pay_min": 420_000,
        "pay_max": 680_000,
        "state": "fct",
        "lga": "Lugbe",
        "slots": 1,
        "is_remote": False,
    },

    # ── 6 ────────────────────────────────────────────────────────────────────
    {
        "title": "Scheduled Plumbing Maintenance & Leak Detection Contract (Garki)",
        "description": (
            "Provide monthly scheduled plumbing maintenance and on-demand leak "
            "detection for a portfolio of 35 commercial and residential units managed "
            "by a property firm in Garki, Abuja. Monthly visits: inspect all accessible "
            "pipework, test water pressure at each unit, service ball valves and cistern "
            "internals, and submit a written condition report. Leak-detection callouts "
            "must be attended within 4 hours. Own vehicle, acoustic leak detector, and "
            "basic CCTV camera required. 12-month rolling contract with renewal option."
        ),
        "job_type": Job.JobType.PART_TIME,
        "pay_type": Job.PayType.MONTHLY,
        "pay_min": 90_000,
        "pay_max": 130_000,
        "state": "fct",
        "lga": "Garki",
        "slots": 1,
        "is_remote": False,
    },

    # ── 7 ────────────────────────────────────────────────────────────────────
    {
        "title": "Pressure Testing & Water-Line Integrity Survey — Government Complex (Karu)",
        "description": (
            "Carry out a comprehensive pressure-test and water-line integrity survey "
            "across a 4-block government workers' quarters in Karu, Nasarawa State "
            "(bordering FCT). Survey ~3.5 km of aging galvanised supply pipework, "
            "identify leaks using acoustic detection equipment, produce a condition "
            "report with prioritised remediation recommendations, and carry out first-fix "
            "repairs on the most critical sections. All findings must be documented with "
            "photographic evidence and a written report suitable for submission to the "
            "facility manager. Two-week engagement."
        ),
        "job_type": Job.JobType.ONCE_OFF,
        "pay_type": Job.PayType.FIXED,
        "pay_min": 160_000,
        "pay_max": 260_000,
        "state": "nasarawa",
        "lga": "Karu",
        "slots": 1,
        "is_remote": False,
    },

    # ── 8 ────────────────────────────────────────────────────────────────────
    {
        "title": "End-to-End Water Management System — Boutique Hotel (Central Abuja)",
        "description": (
            "Design and install a complete water management system for a 40-room "
            "boutique hotel under construction in Central Abuja. Scope: 80 m borehole "
            "and 2 × 2 HP Grundfos pumps, 30,000-litre Geepee underground storage "
            "cistern, roof-level break tanks, booster pump sets, hot-water cylinder "
            "plant room with 3 × 200-litre Ariston commercial water heaters, PPR hot "
            "and cold distribution to all rooms, drainage stacks with AAV protection, "
            "and a BMS-compatible water-pressure monitoring panel. Full as-built "
            "drawings and pressure-test certificates required at handover."
        ),
        "job_type": Job.JobType.CONTRACT,
        "pay_type": Job.PayType.FIXED,
        "pay_min": 1_400_000,
        "pay_max": 2_200_000,
        "state": "fct",
        "lga": "Central Area",
        "slots": 2,
        "is_remote": False,
    },

    # ── 9 ────────────────────────────────────────────────────────────────────
    {
        "title": "Residential Plumbing Fit-Out — 35-Unit Estate (Lugbe)",
        "description": (
            "Execute the full internal plumbing fit-out for a gated 35-unit estate in "
            "Lugbe, Abuja — first fix through to final commissioning. First fix: uPVC "
            "soil stacks, PPR hot and cold supplies roughed-in to all wet rooms. Second "
            "fix: sanitary ware installation (WCs, basins, showers, kitchen sinks), "
            "mixer taps, stop cocks, and final connections to the estate's shared "
            "borehole and Geepee overhead tank network. Each unit to be individually "
            "pressure-tested and signed off before client handover. Site access is "
            "available six days a week. Experience on multi-unit developer projects "
            "is mandatory."
        ),
        "job_type": Job.JobType.CONTRACT,
        "pay_type": Job.PayType.FIXED,
        "pay_min": 900_000,
        "pay_max": 1_400_000,
        "state": "fct",
        "lga": "Lugbe",
        "slots": 3,
        "is_remote": False,
    },

    # ── 10 ───────────────────────────────────────────────────────────────────
    {
        "title": "Full-Time Plumbing Technician — Property Management Company (Utako)",
        "description": (
            "Join a leading Abuja property management firm as a permanent plumbing "
            "technician covering a portfolio of 120+ residential and commercial "
            "properties across the FCT. Responsibilities: daily PPM rounds, emergency "
            "leak response (within 2 hours), Ariston and Geepee equipment servicing, "
            "Vado fixture repairs, quarterly pressure-testing of all managed units, "
            "and maintaining a digital service log. Must have at least 5 years of "
            "post-qualification experience, a valid NIM or master-plumber certification, "
            "and a personal vehicle. Company-issue tools provided. Monday to Saturday, "
            "with one on-call Sunday per month."
        ),
        "job_type": Job.JobType.FULL_TIME,
        "pay_type": Job.PayType.MONTHLY,
        "pay_min": 130_000,
        "pay_max": 185_000,
        "state": "fct",
        "lga": "Utako",
        "slots": 1,
        "is_remote": False,
    },
]


# ──────────────────────────────────────────────────────────────────────────────
#  COMMAND
# ──────────────────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = (
        "Seeds 10 Abuja-focused plumbing job listings tailored for a certified "
        "master plumber specialising in water management, borehole systems, "
        "Ariston/Geepee/Vado fixture fitting, pressure testing, and maintenance. "
        "Idempotent — existing titles are skipped."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be created without writing to the database.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        if dry_run:
            self.stdout.write(self.style.WARNING(
                "\n⚠️   DRY RUN — nothing will be written to the database.\n"
            ))

        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n🔧  TradeLink NG — Plumber Job Seeder (Abuja Profile)\n"
        ))

        # ── 1. Resolve seed employer ─────────────────────────────────────────
        try:
            user = User.objects.get(username=SEED_EMPLOYER_USERNAME)
            employer = EmployerProfile.objects.get(user=user)
        except (User.DoesNotExist, EmployerProfile.DoesNotExist):
            raise CommandError(
                f"Seed employer '{SEED_EMPLOYER_USERNAME}' not found. "
                "Run 'python manage.py seed_jobs' first to create it."
            )

        self.stdout.write(
            f"  Seed employer : {employer.company_name} (pk={employer.pk})\n"
        )

        # ── 2. Resolve plumber trade category ───────────────────────────────
        try:
            category = TradeCategory.objects.get(slug=TRADE_SLUG)
        except TradeCategory.DoesNotExist:
            raise CommandError(
                f"TradeCategory slug='{TRADE_SLUG}' not found. "
                "Run 'python manage.py seed_jobs' first to create it."
            )

        self.stdout.write(
            f"  Trade category: {category.name} (pk={category.pk})\n"
        )

        # ── 3. Create jobs ───────────────────────────────────────────────────
        created_count = 0
        skipped_count = 0
        deadline_base = date.today() + timedelta(days=30)

        with transaction.atomic():
            for job_data in PLUMBER_JOBS:
                exists = Job.objects.filter(
                    employer=employer,
                    trade_category=category,
                    title=job_data["title"],
                ).exists()

                if exists:
                    skipped_count += 1
                    self.stdout.write(
                        f"    ↳ skip  (exists): {job_data['title'][:70]}"
                    )
                    continue

                if dry_run:
                    self.stdout.write(
                        f"    ↳ [dry-run] would create: {job_data['title'][:70]}"
                    )
                    created_count += 1
                    continue

                # Spread deadlines so they don't all expire on the same day
                deadline = deadline_base + timedelta(days=random.randint(0, 45))

                Job.objects.create(
                    employer=employer,
                    trade_category=category,
                    title=job_data["title"],
                    description=job_data["description"],
                    job_type=job_data["job_type"],
                    pay_type=job_data["pay_type"],
                    pay_min=job_data.get("pay_min"),
                    pay_max=job_data.get("pay_max"),
                    state=job_data["state"],
                    lga=job_data["lga"],
                    slots=job_data.get("slots", 1),
                    is_remote=job_data.get("is_remote", False),
                    deadline=deadline,
                    status=Job.Status.ACTIVE,   # fires signal → Celery embedding task
                )
                created_count += 1
                self.stdout.write(
                    f"    ✚  created: {job_data['title'][:70]}"
                )

        # ── 4. Summary ───────────────────────────────────────────────────────
        if dry_run:
            self.stdout.write(self.style.WARNING(
                f"\n  [DRY RUN] Would create {created_count} job(s), "
                f"skip {skipped_count} existing.\n"
                "  Re-run without --dry-run to apply.\n"
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"\n✅  Done — {created_count} new plumbing job(s) created, "
                f"{skipped_count} already existed (skipped).\n"
                "  Celery will compute embeddings for new jobs automatically.\n"
            ))