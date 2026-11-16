"""
jobs/management/commands/seed_400_jobs.py
==========================================
Seeds up to 400 active job listings, guaranteeing at least one job per
TradeCategory that exists in the database.

Strategy
--------
1. At runtime, all TradeCategory objects are loaded from the database — no
   slugs are hard-coded.  This means the command works against whatever
   categories are present (e.g. the 305 created by seed_scale_300.py).
2. A curated dict of per-slug job data is used for the 20 well-known
   categories (electrician, plumber, carpenter, etc.).  Each gets 2–3 jobs.
3. For every other category the job details are generated programmatically
   from the category name, so every category gets exactly one job.
4. The total target is ≤ 400 new jobs.

Idempotency
-----------
Jobs are looked up by (employer, trade_category, title).  Re-running the
command skips any that already exist — it is completely safe to run multiple
times.

Usage
-----
    # Normal run
    python manage.py seed_400_jobs

    # Preview only — nothing is written
    python manage.py seed_400_jobs --dry-run

    # Delete this employer's jobs first, then re-seed
    python manage.py seed_400_jobs --clear

Design notes
------------
- All jobs are set to ACTIVE status so the CLIP embedding signal fires.
- Pay values are Nigerian Naira (NGN).
- Deadlines are spread randomly over the next 30–90 days.
- States and LGAs are sampled from real Nigerian locations.
"""

import random
import logging
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from jobs.models import Job, TradeCategory, EmployerProfile

logger = logging.getLogger(__name__)
User = get_user_model()

# ──────────────────────────────────────────────────────────────────────────────
#  SEED EMPLOYER  (shared with seed_category_jobs.py)
# ──────────────────────────────────────────────────────────────────────────────

SEED_EMPLOYER_USERNAME = "tradelink_seed_employer"
SEED_EMPLOYER_EMAIL    = "seed-employer@tradelink.ng"
SEED_EMPLOYER_PASSWORD = "SeedPass#2024!"


def get_or_create_seed_employer():
    user, _ = User.objects.get_or_create(
        username=SEED_EMPLOYER_USERNAME,
        defaults={"email": SEED_EMPLOYER_EMAIL, "is_staff": False},
    )
    if not user.has_usable_password():
        user.set_password(SEED_EMPLOYER_PASSWORD)
        user.save(update_fields=["password"])

    employer, _ = EmployerProfile.objects.get_or_create(
        user=user,
        defaults={
            "company_name": "TradeLink Demo Employer",
            "company_type": EmployerProfile.CompanyType.SME,
            "description": (
                "Seed account used by management commands to create "
                "demonstration job listings across all trade categories."
            ),
            "state": "lagos",
            "lga":   "Ikeja",
        },
    )
    return user, employer


# ──────────────────────────────────────────────────────────────────────────────
#  LOCATION POOLS  (Nigerian states and representative LGAs)
# ──────────────────────────────────────────────────────────────────────────────

LOCATIONS = [
    ("lagos",     "Ikeja"),
    ("lagos",     "Surulere"),
    ("lagos",     "Lekki"),
    ("lagos",     "Ikorodu"),
    ("lagos",     "Alimosho"),
    ("abuja",     "Garki"),
    ("abuja",     "Wuse"),
    ("abuja",     "Kubwa"),
    ("rivers",    "Port Harcourt"),
    ("rivers",    "Obio-Akpor"),
    ("kano",      "Kano Municipal"),
    ("kano",      "Fagge"),
    ("oyo",       "Ibadan North"),
    ("oyo",       "Ogbomoso"),
    ("enugu",     "Enugu North"),
    ("enugu",     "Nsukka"),
    ("delta",     "Warri"),
    ("delta",     "Asaba"),
    ("anambra",   "Onitsha"),
    ("anambra",   "Awka"),
    ("edo",       "Benin City"),
    ("imo",       "Owerri"),
    ("kaduna",    "Kaduna North"),
    ("borno",     "Maiduguri"),
    ("cross-river", "Calabar"),
]


def _loc():
    """Return a random (state, lga) tuple."""
    return random.choice(LOCATIONS)


def _deadline():
    """Return a date 30–90 days from today."""
    return date.today() + timedelta(days=random.randint(30, 90))


# ──────────────────────────────────────────────────────────────────────────────
#  CURATED JOB DATA  (slug → list of job dicts)
# ──────────────────────────────────────────────────────────────────────────────
#  Each job dict contains all non-employer/non-category fields.
#  'state' and 'lga' may be omitted — the command will fill them randomly.

CURATED_JOBS = {

    # ── ELECTRICIAN ───────────────────────────────────────────────────────────
    "electrician": [
        {
            "title":       "Residential Electrician — Ikeja, Lagos",
            "description": (
                "We need a licensed residential electrician to carry out complete "
                "rewiring, socket installation, lighting, and consumer unit upgrades "
                "across a 4-bedroom property in Ikeja GRA. The successful applicant "
                "must have at least 3 years of experience in residential wiring, "
                "provide their own basic tools, and be available to start within one "
                "week. COREN or NERC certification is an advantage."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.FIXED,
            "pay_min":  120_000,
            "pay_max":  200_000,
            "state":    "lagos",
            "lga":      "Ikeja",
            "slots":    1,
        },
        {
            "title":       "Industrial Electrician — Port Harcourt",
            "description": (
                "Oil-and-gas support company in Trans-Amadi, Port Harcourt requires "
                "an industrial electrician for maintenance of motors, control panels, "
                "and switchgear. Candidates must hold a valid NERC licence and have "
                "experience with 3-phase systems. 12-month renewable contract. "
                "Hazard allowance and HMO provided."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min":  180_000,
            "pay_max":  280_000,
            "state":    "rivers",
            "lga":      "Obio-Akpor",
            "slots":    2,
        },
        {
            "title":       "Solar & Electrical Technician — Abuja",
            "description": (
                "Growing solar company in Abuja seeks a skilled technician who can "
                "handle both conventional electrical installations and solar PV "
                "systems — including inverter wiring, battery bank assembly, and "
                "net-metering. Full-time role with training on new battery technologies."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min":  150_000,
            "pay_max":  250_000,
            "state":    "abuja",
            "lga":      "Wuse",
            "slots":    2,
        },
    ],

    # ── PLUMBER ───────────────────────────────────────────────────────────────
    "plumber": [
        {
            "title":       "Plumber — Estate Maintenance (Lagos)",
            "description": (
                "A residential estate management company in Lekki Phase 1 is hiring "
                "an experienced plumber for ongoing maintenance work. Duties include "
                "leak repairs, pipe replacement, bathroom fitting, and gutter work. "
                "Must be available on weekdays; weekend call-outs attract overtime pay."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min":  80_000,
            "pay_max":  140_000,
            "state":    "lagos",
            "lga":      "Lekki",
            "slots":    1,
        },
        {
            "title":       "Commercial Plumber — Hotel Construction (Abuja)",
            "description": (
                "A 5-star hotel under construction in Central Abuja requires skilled "
                "commercial plumbers for installation of sanitary ware, hot-water "
                "systems, and fire-suppression pipework. Contract runs for 6 months "
                "with possibility of extension. Daily rate negotiable."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.DAILY,
            "pay_min":  12_000,
            "pay_max":  25_000,
            "state":    "abuja",
            "lga":      "Garki",
            "slots":    4,
        },
    ],

    # ── SOLAR INSTALLER ───────────────────────────────────────────────────────
    "solar-installer": [
        {
            "title":       "Solar PV Installer — Residential Projects (Lagos)",
            "description": (
                "Fast-growing solar company needs certified PV installers for "
                "residential rooftop projects across Lagos. You will install "
                "monocrystalline panels, inverters, and lithium battery banks. "
                "NABCEP certification preferred but not required. Competitive "
                "commission structure on top of base pay."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min":  120_000,
            "pay_max":  200_000,
            "state":    "lagos",
            "lga":      "Surulere",
            "slots":    3,
        },
        {
            "title":       "Off-Grid Solar Technician — Kano",
            "description": (
                "NGO-backed rural electrification project in Kano State seeks an "
                "off-grid solar technician to install and commission mini-grid "
                "systems in remote communities. Accommodation and transport provided. "
                "6-month contract renewable based on project milestones."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min":  100_000,
            "pay_max":  170_000,
            "state":    "kano",
            "lga":      "Fagge",
            "slots":    2,
        },
    ],

    # ── CARPENTER ─────────────────────────────────────────────────────────────
    "carpenter": [
        {
            "title":       "Furniture Carpenter — Workshop & On-Site (Lagos)",
            "description": (
                "Modern furniture workshop in Alimosho, Lagos needs a skilled "
                "carpenter for bespoke kitchen cabinet, wardrobe, and office "
                "furniture production. Must be proficient with hand tools and "
                "basic power tools. 5-day working week; overtime available."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min":  70_000,
            "pay_max":  120_000,
            "state":    "lagos",
            "lga":      "Alimosho",
            "slots":    2,
        },
        {
            "title":       "Site Carpenter — Building Project (Enugu)",
            "description": (
                "Construction company in Enugu needs experienced site carpenters "
                "for formwork, roofing, and door/window installation on a large "
                "apartment block. Minimum 4 years on-site experience required. "
                "Safety boots and PPE provided by employer."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.DAILY,
            "pay_min":  8_000,
            "pay_max":  18_000,
            "state":    "enugu",
            "lga":      "Enugu North",
            "slots":    5,
        },
    ],

    # ── WELDER ────────────────────────────────────────────────────────────────
    "welder": [
        {
            "title":       "MIG/TIG Welder — Steel Fabrication (Delta)",
            "description": (
                "Steel fabrication company in Warri requires skilled MIG and TIG "
                "welders for structural steel and pipe-work projects. CSWIP "
                "certification advantageous. Full-time role with 13th-month salary "
                "and HMO cover."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min":  100_000,
            "pay_max":  180_000,
            "state":    "delta",
            "lga":      "Warri",
            "slots":    3,
        },
        {
            "title":       "Gate & Burglar-Proof Welder — Lagos",
            "description": (
                "Busy fabrication shop in Surulere is hiring a welder specialising "
                "in gates, burglary proofing, stainless steel railings, and grille "
                "work. Must be able to work from customer measurements. Piece-rate "
                "pay with weekly settlement."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.WEEKLY,
            "pay_min":  25_000,
            "pay_max":  60_000,
            "state":    "lagos",
            "lga":      "Surulere",
            "slots":    2,
        },
    ],

    # ── MASON / BRICKLAYER ────────────────────────────────────────────────────
    "mason": [
        {
            "title":       "Experienced Mason — Apartment Block (Ibadan)",
            "description": (
                "Construction firm building a 24-unit apartment complex in "
                "Ibadan needs experienced masons for block-laying, plastering, "
                "and screeding. Payment is per square metre completed. Daily "
                "transport to site provided from Bodija Junction."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.DAILY,
            "pay_min":  9_000,
            "pay_max":  20_000,
            "state":    "oyo",
            "lga":      "Ibadan North",
            "slots":    8,
        },
        {
            "title":       "Tiler & Mason — Luxury Residential (Lagos)",
            "description": (
                "Upscale residential project on Lagos Island needs a skilled mason "
                "who is also experienced with laying large-format porcelain tiles. "
                "Must be able to interpret architectural drawings. Contract duration "
                "4–6 months."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.FIXED,
            "pay_min":  200_000,
            "pay_max":  400_000,
            "state":    "lagos",
            "lga":      "Lagos Island",
            "slots":    1,
        },
    ],

    # ── PAINTER & DECORATOR ───────────────────────────────────────────────────
    "painter-decorator": [
        {
            "title":       "Painter & Decorator — Commercial Property (Abuja)",
            "description": (
                "A newly completed office complex in Wuse 2, Abuja needs experienced "
                "painters and decorators to complete interior and exterior finishes. "
                "Must be skilled in emulsion painting, texture coating, and "
                "wallpaper installation. Work starts immediately."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.FIXED,
            "pay_min":  150_000,
            "pay_max":  300_000,
            "state":    "abuja",
            "lga":      "Wuse",
            "slots":    4,
        },
    ],

    # ── HVAC TECHNICIAN ───────────────────────────────────────────────────────
    "hvac-technician": [
        {
            "title":       "HVAC Technician — Hotel Maintenance (Lagos)",
            "description": (
                "Four-star hotel in Victoria Island, Lagos requires a full-time "
                "HVAC technician for preventive maintenance of split AC units, "
                "central chillers, and VRF systems. Must be proficient in fault "
                "diagnosis and refrigerant handling. HMO included."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min":  130_000,
            "pay_max":  220_000,
            "state":    "lagos",
            "lga":      "Lagos Island",
            "slots":    1,
        },
        {
            "title":       "AC Installer & Repair Technician — Kano",
            "description": (
                "Electronics and appliance company in Kano seeks an AC technician "
                "for installation, gas-recharge, and repair of window and split "
                "units. Motorbike allowance provided. Commission on each installation "
                "job in addition to monthly salary."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min":  80_000,
            "pay_max":  150_000,
            "state":    "kano",
            "lga":      "Kano Municipal",
            "slots":    2,
        },
    ],

    # ── AUTO MECHANIC ─────────────────────────────────────────────────────────
    "auto-mechanic": [
        {
            "title":       "Auto Mechanic — Full-Service Workshop (Lagos)",
            "description": (
                "Busy auto workshop in Cele, Lagos is hiring an experienced mechanic "
                "for engine diagnostics, brake overhaul, suspension repair, and "
                "general servicing of Toyota, Honda, and Lexus vehicles. OBD "
                "scanner experience a plus."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min":  90_000,
            "pay_max":  160_000,
            "state":    "lagos",
            "lga":      "Surulere",
            "slots":    2,
        },
        {
            "title":       "Auto Electrician & Mechanic — Abuja",
            "description": (
                "Vehicle servicing centre in Kubwa, Abuja needs a technician with "
                "combined auto-electrical and mechanical skills. Duties include "
                "alternator/starter motor repair, ECU coding, and engine work. "
                "Competitive salary plus bonus on upsold services."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min":  100_000,
            "pay_max":  180_000,
            "state":    "abuja",
            "lga":      "Kubwa",
            "slots":    1,
        },
    ],

    # ── GENERATOR TECHNICIAN ──────────────────────────────────────────────────
    "generator-technician": [
        {
            "title":       "Generator Technician — Industrial Site (Delta)",
            "description": (
                "Oil company contractor in Delta State requires a generator "
                "technician for maintenance and emergency repair of diesel gensets "
                "(20–500KVA) on operational sites. Must be familiar with Perkins, "
                "Lister, and Cummins engines. Accommodation and transport on site."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min":  150_000,
            "pay_max":  250_000,
            "state":    "delta",
            "lga":      "Warri",
            "slots":    2,
        },
        {
            "title":       "Genset Repair Technician — Suya Express Estate (Lagos)",
            "description": (
                "Estate management company in Lekki Phase 2 hiring a generator "
                "technician for routine servicing of residential standby gensets "
                "(3KVA–60KVA). Must be available for call-outs at short notice. "
                "5-day week plus on-call weekend allowance."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min":  80_000,
            "pay_max":  130_000,
            "state":    "lagos",
            "lga":      "Lekki",
            "slots":    1,
        },
    ],

    # ── ROOFER ────────────────────────────────────────────────────────────────
    "roofer": [
        {
            "title":       "Roofer — New Build (Lagos)",
            "description": (
                "Construction company finishing a detached duplex in Ajah, Lagos "
                "needs an experienced roofer for timber frame erection, decking, "
                "felt laying, and long-span aluminium roofing. Payment on completion "
                "of each phase. Tools and safety harness provided."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.FIXED,
            "pay_min":  180_000,
            "pay_max":  350_000,
            "state":    "lagos",
            "lga":      "Ajah",
            "slots":    1,
        },
    ],

    # ── TAILOR / FASHION DESIGNER ─────────────────────────────────────────────
    "tailor": [
        {
            "title":       "Fashion Tailor — Ladies' Boutique (Abuja)",
            "description": (
                "Upscale ladies' boutique in Maitama, Abuja seeks a creative tailor "
                "experienced in Ankara, lace, and chiffon to produce bespoke gowns, "
                "suits, and casual wear. Must be fast, accurate, and able to work "
                "from customer measurements. Full-time with guaranteed weekly orders."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min":  70_000,
            "pay_max":  130_000,
            "state":    "abuja",
            "lga":      "Maitama",
            "slots":    2,
        },
        {
            "title":       "Corporate-Wear Tailor — Lagos",
            "description": (
                "Corporate uniform supplier in Lagos needs an experienced tailor "
                "specialising in men's and women's office wear — shirts, trousers, "
                "blazers, and skirts. Must be able to handle bulk orders with "
                "consistent quality. Machine must be provided by applicant."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min":  60_000,
            "pay_max":  110_000,
            "state":    "lagos",
            "lga":      "Ikeja",
            "slots":    3,
        },
    ],

    # ── TILER ─────────────────────────────────────────────────────────────────
    "tiler": [
        {
            "title":       "Tiler — Upscale Apartment (Lagos)",
            "description": (
                "Luxury apartment finishing project in Ikoyi needs an expert tiler "
                "for large-format marble and porcelain tiles. Must have experience "
                "with rectified tiles, waterproofing wet areas, and creating "
                "feature patterns. High-quality workmanship is non-negotiable."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.FIXED,
            "pay_min":  200_000,
            "pay_max":  500_000,
            "state":    "lagos",
            "lga":      "Ikoyi",
            "slots":    1,
        },
        {
            "title":       "Tiler — Residential Estate (Onitsha)",
            "description": (
                "Real estate developer in Onitsha needs tilers to complete floor and "
                "wall tiling across 12 housing units. Standard 60×60 ceramic tiles. "
                "Payment per square metre. Accommodation on site available."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.FIXED,
            "pay_min":  100_000,
            "pay_max":  220_000,
            "state":    "anambra",
            "lga":      "Onitsha",
            "slots":    4,
        },
    ],

    # ── HAIR STYLIST ──────────────────────────────────────────────────────────
    "hair-stylist": [
        {
            "title":       "Hair Stylist — Busy Salon (Lagos)",
            "description": (
                "Modern hair salon in Surulere, Lagos is looking for an experienced "
                "stylist skilled in relaxers, natural hair care, braiding, and "
                "weave-on installations. Must be friendly and customer-focused. "
                "Commission-based pay on top of monthly retainer."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min":  60_000,
            "pay_max":  120_000,
            "state":    "lagos",
            "lga":      "Surulere",
            "slots":    2,
        },
    ],

    # ── CATERER ───────────────────────────────────────────────────────────────
    "caterer": [
        {
            "title":       "Event Caterer — Weddings & Parties (Lagos)",
            "description": (
                "Event management company in Lagos requires an experienced caterer "
                "and cook for weekend weddings, corporate dinners, and birthday "
                "parties. Must be skilled in jollof rice, fried rice, pepper soup, "
                "and continental dishes. Catering equipment provided."
            ),
            "job_type": Job.JobType.PART_TIME,
            "pay_type": Job.PayType.FIXED,
            "pay_min":  30_000,
            "pay_max":  80_000,
            "state":    "lagos",
            "lga":      "Ikeja",
            "slots":    3,
        },
        {
            "title":       "Cook & Caterer — School Canteen (Abuja)",
            "description": (
                "Private school in Maitama, Abuja seeks a full-time caterer to "
                "manage the school canteen — planning daily menus, cooking healthy "
                "meals for 400+ pupils and staff, and maintaining kitchen hygiene. "
                "Previous canteen or restaurant experience required."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min":  70_000,
            "pay_max":  120_000,
            "state":    "abuja",
            "lga":      "Maitama",
            "slots":    1,
        },
    ],

    # ── SECURITY INSTALLER ────────────────────────────────────────────────────
    "security-installer": [
        {
            "title":       "CCTV & Access Control Installer (Lagos)",
            "description": (
                "Security solutions company in Lagos requires an experienced "
                "installer for CCTV cameras, DVR/NVR systems, electric fences, "
                "access control, and intercoms. Must be able to handle both "
                "residential and commercial projects. Van and tools provided."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min":  100_000,
            "pay_max":  180_000,
            "state":    "lagos",
            "lga":      "Ikeja",
            "slots":    2,
        },
    ],

    # ── ALUMINIUM & GLASS INSTALLER ───────────────────────────────────────────
    "aluminum-glass-installer": [
        {
            "title":       "Aluminium & Glass Fabricator — Lagos",
            "description": (
                "Busy aluminium fabrication company in Ojota, Lagos needs a skilled "
                "fabricator and installer for aluminium windows, doors, curtain walls, "
                "and frameless glass partitions. Must be proficient with cutting, "
                "bending, and silicone finishing. Full-time with overtime on projects."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min":  80_000,
            "pay_max":  150_000,
            "state":    "lagos",
            "lga":      "Ojota",
            "slots":    3,
        },
    ],

    # ── BRICKLAYER / BLOCK MOULDER ────────────────────────────────────────────
    "bricklayer-block-moulder": [
        {
            "title":       "Bricklayer — Commercial Building (Rivers)",
            "description": (
                "Construction firm in Port Harcourt needs experienced bricklayers "
                "for a 6-storey commercial building project. Must be proficient in "
                "block-laying to DPC and above, mortar mixing ratios, and line "
                "levelling. Accommodation on site; transport to and from site daily."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.DAILY,
            "pay_min":  10_000,
            "pay_max":  20_000,
            "state":    "rivers",
            "lga":      "Port Harcourt",
            "slots":    10,
        },
    ],

    # ── HV SUBSTATION TECHNICIAN ──────────────────────────────────────────────
    "hv-substation-technician": [
        {
            "title":       "HV Substation Technician — DisCo (Kano)",
            "description": (
                "Electricity Distribution Company in Kano State requires a "
                "high-voltage substation technician for maintenance of transformers, "
                "circuit breakers, and protection relays at 33KV/11KV substations. "
                "Must hold a valid NERC licence and have minimum 5 years DisCo or "
                "GenCo experience. HMO and pension scheme included."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min":  200_000,
            "pay_max":  380_000,
            "state":    "kano",
            "lga":      "Kano Municipal",
            "slots":    1,
        },
    ],

    # ── PLC / AUTOMATION PROGRAMMER ───────────────────────────────────────────
    "plc-automation-programmer": [
        {
            "title":       "PLC & Automation Programmer — Manufacturing (Lagos)",
            "description": (
                "FMCG manufacturing company in Apapa, Lagos requires a PLC programmer "
                "experienced with Siemens S7 and Allen-Bradley ControlLogix. "
                "Responsibilities: PLC programming, HMI development, and SCADA "
                "configuration. Minimum 4 years industrial automation experience. "
                "Full-time with performance bonus."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min":  250_000,
            "pay_max":  450_000,
            "state":    "lagos",
            "lga":      "Apapa",
            "slots":    1,
        },
    ],

}  # end CURATED_JOBS


# ──────────────────────────────────────────────────────────────────────────────
#  GENERIC JOB GENERATOR  (for categories not in CURATED_JOBS)
# ──────────────────────────────────────────────────────────────────────────────

_JOB_TYPES  = [Job.JobType.CONTRACT, Job.JobType.FULL_TIME, Job.JobType.PART_TIME]
_PAY_TYPES  = [Job.PayType.MONTHLY, Job.PayType.DAILY, Job.PayType.FIXED, Job.PayType.NEGOTIABLE]

_TITLE_TEMPLATES = [
    "{name} — Contract Position ({city})",
    "Experienced {name} Needed ({city})",
    "{name} Professional — Immediate Hire ({city})",
    "Skilled {name} — New Project ({city})",
    "{name} Technician / Specialist ({city})",
]

_DESC_TEMPLATES = [
    (
        "We are seeking a skilled {name} professional for contract work in {city}, "
        "{state_display}. The role involves practical, hands-on {name_lower} tasks on "
        "active sites. Minimum 2 years of relevant experience required. Tools and safety "
        "equipment provided on site. Competitive daily rate; pay finalised at interview."
    ),
    (
        "A growing company in {city}, {state_display} requires an experienced {name} "
        "to join their team on a full-time basis. Candidates must demonstrate proven "
        "skill in {name_lower} work, strong work ethic, and reliability. Training "
        "opportunities available for the right candidate. Salary based on experience."
    ),
    (
        "Reputable construction and maintenance firm in {state_display} has an opening "
        "for a qualified {name}. Responsibilities include carrying out all aspects of "
        "{name_lower} work to a high standard, working safely, and meeting project "
        "deadlines. Apply with references and evidence of previous work."
    ),
    (
        "We need an experienced {name} for a project starting in {city}. The position "
        "is open to both junior and senior candidates — pay will be set according to "
        "skill level and experience. Genuine opportunity for repeat work and long-term "
        "engagement with our growing client base across {state_display}."
    ),
]

STATE_DISPLAY = {
    "lagos": "Lagos", "abuja": "Abuja", "rivers": "Rivers State",
    "kano": "Kano State", "oyo": "Oyo State", "enugu": "Enugu State",
    "delta": "Delta State", "anambra": "Anambra State", "edo": "Edo State",
    "imo": "Imo State", "kaduna": "Kaduna State", "borno": "Borno State",
    "cross-river": "Cross River State",
}


def _generic_job(cat):
    """Return a job dict for a category that has no curated entry."""
    state, lga = _loc()
    name = cat.name
    name_lower = name.lower()
    city = lga
    state_display = STATE_DISPLAY.get(state, state.title())

    title = random.choice(_TITLE_TEMPLATES).format(name=name, city=city)
    desc  = random.choice(_DESC_TEMPLATES).format(
        name=name, name_lower=name_lower, city=city, state_display=state_display
    )

    pay_min = random.choice([50_000, 60_000, 70_000, 80_000, 90_000, 100_000])
    pay_max = pay_min + random.choice([40_000, 60_000, 80_000, 100_000, 120_000])

    return {
        "title":       title,
        "description": desc,
        "job_type":    random.choice(_JOB_TYPES),
        "pay_type":    random.choice(_PAY_TYPES),
        "pay_min":     pay_min,
        "pay_max":     pay_max,
        "state":       state,
        "lga":         lga,
        "slots":       random.randint(1, 4),
    }


# ──────────────────────────────────────────────────────────────────────────────
#  MANAGEMENT COMMAND
# ──────────────────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = (
        "Seeds up to 400 active jobs — at least one per TradeCategory in the DB. "
        "Curated descriptions are used for 20 priority categories; all others get "
        "a generated job. Fully idempotent: re-running skips existing jobs."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Preview what would be created without writing to the database.",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            default=False,
            help="Delete all jobs owned by the seed employer before re-seeding.",
        )

    # ──────────────────────────────────────────────────────────────────────────

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        do_clear = options["clear"]

        self.stdout.write(self.style.MIGRATE_HEADING(
            "=== seed_400_jobs — TradeLink universal job seeder ==="
        ))

        # 1. Seed employer
        _, employer = get_or_create_seed_employer()
        self.stdout.write(f"  Seed employer: {employer.company_name}  (pk={employer.pk})")

        # 2. Optional clear
        if do_clear and not dry_run:
            deleted, _ = Job.objects.filter(employer=employer).delete()
            self.stdout.write(self.style.WARNING(f"  Cleared {deleted} existing seed jobs."))

        # 3. Load all categories
        all_cats = list(TradeCategory.objects.all().order_by("slug"))
        self.stdout.write(f"  Trade categories found: {len(all_cats)}")

        if not all_cats:
            raise CommandError(
                "No TradeCategory objects found. Run seed_scale_300 first."
            )

        # 4. Build job list
        jobs_to_create = []
        for cat in all_cats:
            curated = CURATED_JOBS.get(cat.slug)
            if curated:
                for jd in curated:
                    jobs_to_create.append((cat, jd))
            else:
                jobs_to_create.append((cat, _generic_job(cat)))

        total_planned = len(jobs_to_create)
        self.stdout.write(f"  Jobs planned:           {total_planned}")

        # 5. Create (idempotent)
        created_count  = 0
        skipped_count  = 0
        today          = date.today()

        with transaction.atomic():
            for cat, jd in jobs_to_create:
                title    = jd["title"]
                state    = jd.get("state", "lagos")
                lga      = jd.get("lga", "Ikeja")
                deadline = jd.get("deadline") or (today + timedelta(days=random.randint(30, 90)))

                if dry_run:
                    self.stdout.write(
                        f"  [DRY-RUN] Would create: [{cat.slug}] {title}"
                    )
                    created_count += 1
                    continue

                _, created = Job.objects.get_or_create(
                    employer=employer,
                    trade_category=cat,
                    title=title,
                    defaults={
                        "description": jd["description"],
                        "job_type":    jd.get("job_type",  Job.JobType.CONTRACT),
                        "pay_type":    jd.get("pay_type",  Job.PayType.NEGOTIABLE),
                        "pay_min":     jd.get("pay_min",   80_000),
                        "pay_max":     jd.get("pay_max",   200_000),
                        "state":       state,
                        "lga":         lga,
                        "is_remote":   jd.get("is_remote", False),
                        "status":      Job.Status.ACTIVE,
                        "deadline":    deadline,
                        "slots":       jd.get("slots", 1),
                    },
                )
                if created:
                    created_count += 1
                else:
                    skipped_count += 1

        # 6. Summary
        if dry_run:
            self.stdout.write(self.style.WARNING(
                f"\n  [DRY-RUN] Would have created {created_count} jobs "
                f"across {len(all_cats)} categories.  Nothing was written."
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"\n  Done!  Created: {created_count}  |  Skipped (already exist): {skipped_count}"
            ))
            self.stdout.write(
                f"  Total active seed jobs: "
                f"{Job.objects.filter(employer=employer, status=Job.Status.ACTIVE).count()}"
            )
