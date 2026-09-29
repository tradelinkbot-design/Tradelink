"""
jobs/management/commands/seed_plumber_jobs_v2.py
=================================================
Second batch of 10 Abuja-focused plumbing jobs for a certified master
plumber with 7+ years of residential and commercial experience in the FCT.

All 10 titles are unique — no clash with:
  - seed_jobs.py          (10 original plumber listings)
  - seed_extra_jobs.py    (5 extra plumber listings)
  - seed_plumber_jobs.py  (first Abuja-profile batch of 10)

Specialties covered in this batch
----------------------------------
  - Galvanised-to-PPR repiping (old estates)
  - Borehole pump overhaul & pressure tank replacement
  - Full sanitary ware installation (hotel / guesthouse scale)
  - Underground supply line fault-finding & repair
  - Ariston water heater service contracts
  - Multi-storey PVC soil stack & drainage fit-out
  - Pressure booster pump room installation
  - Plumbing audit & written condition reports
  - Vado mixer tap & thermostatic shower fitting
  - Resident estate plumber (full-time)

Locations
----------
  FCT — Jabi, Kubwa, Garki, Gwarinpa, Wuse 2, Central District,
         Asokoro, Maitama, Gwagwalada
  Nasarawa — Keffi (satellite town bordering FCT)

Idempotent: safe to run multiple times; existing titles are skipped.

Usage
-----
    python manage.py seed_plumber_jobs_v2               # create all 10
    python manage.py seed_plumber_jobs_v2 --dry-run     # preview only
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
#  JOB DATA  —  all titles unique across the full seed suite
# ──────────────────────────────────────────────────────────────────────────────

PLUMBER_JOBS_V2 = [

    # ── 1 ────────────────────────────────────────────────────────────────────
    {
        "title": "Galvanised-to-PPR Repiping — Federal Housing Estate (Jabi, Abuja)",
        "description": (
            "Strip out and replace approximately 2.8 km of corroded galvanised steel "
            "water supply pipework with PN20 PPR throughout a 48-unit federal housing "
            "estate in Jabi, Abuja. Work is to be carried out unit by unit to keep "
            "residents connected at all times — a phased isolation schedule must be "
            "agreed with the estate manager before work begins. Scope includes new "
            "ball-valve isolators at every branch point, PPR pipe sizing calculations "
            "for each riser, pressure testing at 10 bar for 1 hour after each phase, "
            "and a photographic record of before/after conditions. Experience with "
            "occupied-estate repiping and PPR fusion welding is mandatory."
        ),
        "job_type": Job.JobType.CONTRACT,
        "pay_type": Job.PayType.DAILY,
        "pay_min": 28_000,
        "pay_max": 42_000,
        "state": "fct",
        "lga": "Jabi",
        "slots": 2,
        "is_remote": False,
    },

    # ── 2 ────────────────────────────────────────────────────────────────────
    {
        "title": "Borehole Pump Overhaul & Pressure Tank Replacement (Kubwa, Abuja)",
        "description": (
            "Diagnose and overhaul a failing 1.5 HP submersible borehole pump at a "
            "private compound in Kubwa, Abuja. Pull the pump from 55 m, inspect motor "
            "windings and impeller, replace worn components or swap the pump unit "
            "entirely if beyond repair, and re-set the pump to the correct depth. "
            "Additionally, replace the existing waterlogged 100-litre pressure/diaphragm "
            "tank with a new 150-litre Geepee-compatible pressure tank, recalibrate the "
            "pressure switch to 2.5–4.5 bar, and flush the delivery line before "
            "commissioning. Provide a 6-month workmanship warranty on the pump works."
        ),
        "job_type": Job.JobType.ONCE_OFF,
        "pay_type": Job.PayType.FIXED,
        "pay_min": 185_000,
        "pay_max": 290_000,
        "state": "fct",
        "lga": "Kubwa",
        "slots": 1,
        "is_remote": False,
    },

    # ── 3 ────────────────────────────────────────────────────────────────────
    {
        "title": "Sanitary Ware & WC Installation — 45-Room Guesthouse (Garki, Abuja)",
        "description": (
            "Supply and install all sanitary ware for a newly completed 45-room "
            "guesthouse in Garki, Abuja. Each room requires a close-coupled WC with "
            "dual-flush cistern, wall-hung or pedestal wash basin with chrome monobloc "
            "tap, and an overhead shower set with riser rail. Common areas require "
            "additional floor-standing WCs and hand-rinse basins. All waste connections "
            "to existing soil stacks, final water-pressure balance across all floors, "
            "and a snag-free sign-off inspection are included in scope. Must be "
            "comfortable working alongside tilers on a live construction site. "
            "Experience with hospitality fit-outs preferred."
        ),
        "job_type": Job.JobType.CONTRACT,
        "pay_type": Job.PayType.FIXED,
        "pay_min": 480_000,
        "pay_max": 720_000,
        "state": "fct",
        "lga": "Garki",
        "slots": 1,
        "is_remote": False,
    },

    # ── 4 ────────────────────────────────────────────────────────────────────
    {
        "title": "Underground Supply Line Fault-Finding & Repair (Gwarinpa, Abuja)",
        "description": (
            "Locate and repair one or more suspected underground water supply leaks "
            "within a gated estate of 20 houses in Gwarinpa, Abuja. Use acoustic leak "
            "detection equipment to pinpoint the faults without unnecessary excavation, "
            "expose the affected sections, carry out permanent pipe repairs or section "
            "replacements in uPVC or PPR, and reinstate ground surfaces. After repair, "
            "pressure-test the full underground network and submit a written leak "
            "report to the estate facilities manager. Candidate must own or have "
            "access to a calibrated acoustic correlator. Same-day mobilisation "
            "capability is an advantage."
        ),
        "job_type": Job.JobType.ONCE_OFF,
        "pay_type": Job.PayType.FIXED,
        "pay_min": 130_000,
        "pay_max": 220_000,
        "state": "fct",
        "lga": "Gwarinpa",
        "slots": 1,
        "is_remote": False,
    },

    # ── 5 ────────────────────────────────────────────────────────────────────
    {
        "title": "Ariston Water Heater Bi-Monthly Service Contract — Apartment Block (Wuse 2)",
        "description": (
            "Provide a 12-month bi-monthly preventive maintenance service for 30 "
            "Ariston VELIS and LYDOS electric water heaters installed across a "
            "residential apartment block in Wuse 2, Abuja. Each service visit: "
            "inspect anode rods, check and re-seat T&P relief valves, descale heating "
            "elements where required, verify thermostat accuracy, and confirm earth "
            "bonding integrity. Issue a signed service sheet per unit after each round. "
            "Attend emergency call-outs (no-hot-water faults) within 3 hours Monday "
            "to Saturday. Prior Ariston product training or certification is an "
            "advantage."
        ),
        "job_type": Job.JobType.PART_TIME,
        "pay_type": Job.PayType.MONTHLY,
        "pay_min": 65_000,
        "pay_max": 100_000,
        "state": "fct",
        "lga": "Wuse",
        "slots": 1,
        "is_remote": False,
    },

    # ── 6 ────────────────────────────────────────────────────────────────────
    {
        "title": "PVC Soil Stack & Internal Drainage — 7-Storey Office Block (Central Abuja)",
        "description": (
            "Install all PVC soil, waste, and vent stacks for a 7-storey commercial "
            "office building in the Central District, Abuja. Scope: size and install "
            "110 mm and 160 mm uPVC soil stacks from basement to roof, connect floor "
            "gullies, urinal wastes, kitchen sink connections, and cleanout access "
            "plates at each floor. Vent pipes to terminate 900 mm above flat roof. "
            "Carry out a full water and air test on completion before ceiling boards "
            "are installed. Work closely with the M&E coordinator to maintain the "
            "programme — slab penetrations are already core-drilled. "
            "Experience on multi-storey commercial drainage is essential."
        ),
        "job_type": Job.JobType.CONTRACT,
        "pay_type": Job.PayType.FIXED,
        "pay_min": 400_000,
        "pay_max": 620_000,
        "state": "fct",
        "lga": "Central District",
        "slots": 2,
        "is_remote": False,
    },

    # ── 7 ────────────────────────────────────────────────────────────────────
    {
        "title": "Pressure Booster Pump Room Installation — Private Estate (Asokoro, Abuja)",
        "description": (
            "Design and install a twin-pump pressure booster system in a purpose-built "
            "pump room serving a 16-unit private estate in Asokoro, Abuja. Equipment: "
            "2 × 1.1 kW Grundfos CM5 booster pumps in duty-standby configuration, "
            "2,000-litre break tank with float valve, manifold with isolating and "
            "non-return valves, pressure gauge, and pressure-switch controller. "
            "Connect to the estate's Geepee overhead tank inlet and to the internal "
            "ring main. Commission and set delivery pressure to 3.5 bar. Provide "
            "laminated schematic drawing for the pump room wall and a 12-month "
            "parts-and-labour warranty."
        ),
        "job_type": Job.JobType.ONCE_OFF,
        "pay_type": Job.PayType.FIXED,
        "pay_min": 270_000,
        "pay_max": 420_000,
        "state": "fct",
        "lga": "Asokoro",
        "slots": 1,
        "is_remote": False,
    },

    # ── 8 ────────────────────────────────────────────────────────────────────
    {
        "title": "Plumbing Audit & Written Condition Report — Government School (Keffi, Nasarawa)",
        "description": (
            "Carry out a full plumbing audit across a government secondary school "
            "campus in Keffi, Nasarawa State — a 45-minute drive from Central Abuja. "
            "Survey all accessible cold-water supply pipework, WC cisterns, wash "
            "basins, urinals, ablution blocks, and underground drainage. Identify "
            "defects, assess remaining service life of each element, and produce a "
            "written condition report with colour-coded priority ratings (urgent / "
            "within 6 months / planned). Minor first-fix repairs (replacing float "
            "valves, re-seating taps, patching exposed pipe lagging) are included in "
            "scope. The report must be formatted for submission to the state Ministry "
            "of Education. Five-day engagement."
        ),
        "job_type": Job.JobType.ONCE_OFF,
        "pay_type": Job.PayType.FIXED,
        "pay_min": 95_000,
        "pay_max": 165_000,
        "state": "nasarawa",
        "lga": "Keffi",
        "slots": 1,
        "is_remote": False,
    },

    # ── 9 ────────────────────────────────────────────────────────────────────
    {
        "title": "Vado Mixer Tap & Thermostatic Shower Fitting — 8 New Apartments (Maitama, Abuja)",
        "description": (
            "Carry out second-fix plumbing in 8 newly plastered luxury apartments in "
            "Maitama, Abuja. Each unit requires installation of Vado Life monobloc "
            "basin mixers, Vado Synergie bath fillers, Vado bar-valve thermostatic "
            "shower systems, and matching kitchen mixer taps. All chrome finished — "
            "zero scratches tolerated on handover. Connect shower wastes to existing "
            "waste stubs, balance hot and cold pressures across all outlets, and "
            "complete a leak-check soak test before the client's final inspection. "
            "Candidate must have demonstrable experience fitting premium European "
            "sanitary fittings and understand the importance of correct torque on "
            "compression fittings in high-specification properties."
        ),
        "job_type": Job.JobType.ONCE_OFF,
        "pay_type": Job.PayType.DAILY,
        "pay_min": 22_000,
        "pay_max": 35_000,
        "state": "fct",
        "lga": "Maitama",
        "slots": 1,
        "is_remote": False,
    },

    # ── 10 ───────────────────────────────────────────────────────────────────
    {
        "title": "Resident Estate Plumber — Gated Community (Gwagwalada, FCT)",
        "description": (
            "Permanent in-house plumbing technician for a 60-unit gated community in "
            "Gwagwalada, FCT. Day-to-day responsibilities: respond to resident "
            "plumbing faults within 1 hour, carry out monthly PPM rounds (check float "
            "valves and overflow pipes on all Geepee overhead tanks, inspect borehole "
            "pump performance, test water pressure at estate boundary), service "
            "Ariston water heaters twice yearly, maintain a digital fault log, and "
            "source spare parts within the approved budget. "
            "Six-day week; one on-call Sunday per month. Accommodation on site is "
            "available. Minimum 5 years post-qualification experience; NIM or "
            "master-plumber certification required. Own basic hand tools expected."
        ),
        "job_type": Job.JobType.FULL_TIME,
        "pay_type": Job.PayType.MONTHLY,
        "pay_min": 115_000,
        "pay_max": 160_000,
        "state": "fct",
        "lga": "Gwagwalada",
        "slots": 1,
        "is_remote": False,
    },
]


# ──────────────────────────────────────────────────────────────────────────────
#  COMMAND
# ──────────────────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = (
        "Second batch: seeds 10 more Abuja-focused plumbing job listings "
        "tailored for a certified master plumber (PPR repiping, borehole "
        "overhauls, Vado/Ariston fitting, soil stacks, pressure boosting, "
        "audit & maintenance). All titles are unique across the full seed suite."
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
            "\n🔧  TradeLink NG — Plumber Job Seeder v2 (Abuja Profile — Batch 2)\n"
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
            for job_data in PLUMBER_JOBS_V2:
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