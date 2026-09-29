"""
jobs/management/commands/seed_category_jobs.py
===============================================
Seeds job listings across 17 Nigerian trade categories,
producing exactly 120 active jobs in total.

The Electrician category carries 8 jobs; all other 16 categories
carry 7 jobs each (8 + 16 × 7 = 120).

The 10 trade categories that seed_jobs already defines are reused here
(looked up by slug, never re-created). Seven additional categories that
are common in the Nigerian market are created if they do not yet exist.

All jobs are owned by the shared ``tradelink_seed_employer`` account.

Usage
-----
    # Full seed (all 17 categories)
    python manage.py seed_category_jobs

    # Limit to specific categories (comma-separated slugs)
    python manage.py seed_category_jobs --only electrician,tailor,tiler

    # Preview without writing anything
    python manage.py seed_category_jobs --dry-run

    # Wipe this command's jobs first, then re-seed
    python manage.py seed_category_jobs --clear

What it creates
---------------
    Existing categories (slug must already exist, created by seed_jobs):
      electrician, plumber, solar-installer, carpenter,
      painter-decorator, welder, mason, hair-stylist,
      hvac-technician, auto-mechanic

    New categories (created if absent):
      tailor, tiler, aluminum-glass-installer,
      generator-technician, roofer, security-installer, caterer

    8 jobs (electrician) + 7 jobs × 16 categories = 120 jobs total.

Design notes
------------
- Idempotent: jobs are identified by (employer, trade_category, title).
  Re-running skips any that already exist.
- Jobs are created in ACTIVE status so the CLIP embedding signal fires.
- All pay values are Nigerian Naira (NGN).
- Deadlines are spread randomly over the next 30–60 days.
"""

import random
import logging
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from jobs.models import TradeCategory, Skill, EmployerProfile, Job

logger = logging.getLogger(__name__)
User = get_user_model()

# ──────────────────────────────────────────────────────────────────────────────
#  SEED EMPLOYER  (shared with seed_jobs.py)
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
#  TRADE CATEGORIES + 7 JOBS EACH
# ──────────────────────────────────────────────────────────────────────────────
#
#  Each entry has:
#    slug          – used for idempotency lookup
#    name          – human-readable label
#    icon_class    – Font Awesome class (used only when creating a new category)
#    display_order – ordering hint (new categories start at 10+)
#    clip_context_text  – CLIP search hint
#    description        – category blurb
#    skills        – list of skill names (created if absent)
#    jobs          – exactly 7 job dicts
#
#  Job dict keys:
#    title, description, job_type, pay_type,
#    pay_min, pay_max, state, lga, slots, is_remote (optional, default False)

TRADE_CATEGORIES = [

    # ── 1. ELECTRICIAN ────────────────────────────────────────────────────────
    {
        "name":  "Electrician",
        "slug":  "electrician",
        "icon_class":      "fas fa-bolt",
        "display_order":   0,
        "clip_context_text": "skilled electrician wiring installation repair Lagos Nigeria",
        "description": (
            "Certified electricians offering domestic, commercial and industrial "
            "wiring, panel upgrades, CCTV, solar integration and generator work."
        ),
        "skills": [
            "Domestic Wiring", "Industrial Wiring", "Solar Panel Wiring",
            "Generator Installation", "CCTV & Security Systems",
            "Panel & Fuseboard Upgrades", "Fault Finding & Diagnostics",
            "Inverter Installation", "Street & Outdoor Lighting",
            "Electrical Inspection & Testing",
        ],
        "jobs": [
            {
                "title": "Residential Electrician — Lekki Phase 1",
                "description": (
                    "Rewire a 4-bedroom duplex in Lekki Phase 1. Scope covers new "
                    "consumer unit, all lighting circuits, sockets, and commissioning. "
                    "Must hold City & Guilds Level 3 or equivalent Nigerian certification. "
                    "Tools and materials supplied on site."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 350_000, "pay_max": 500_000,
                "state": "lagos", "lga": "Lekki", "slots": 2,
            },
            {
                "title": "Solar PV & Inverter Installer — Ikeja GRA",
                "description": (
                    "Install a 5 kW off-grid solar system (panels, inverter, batteries) "
                    "on a commercial property in Ikeja GRA. Must have hands-on experience "
                    "with Victron or Schneider inverters and proper DC/AC cable sizing. "
                    "Proof of previous installations required."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 200_000, "pay_max": 280_000,
                "state": "lagos", "lga": "Ikeja", "slots": 1,
            },
            {
                "title": "Generator & ATS Maintenance Technician — Apapa",
                "description": (
                    "Monthly maintenance contract for 3 Perkins diesel generators "
                    "(100 kVA, 200 kVA, 500 kVA) and ATS panels at a factory in Apapa. "
                    "Must understand load-sharing and be able to carry out load-bank testing."
                ),
                "job_type": Job.JobType.PART_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 80_000, "pay_max": 120_000,
                "state": "lagos", "lga": "Apapa", "slots": 1,
            },
            {
                "title": "CCTV & Access Control Installer — Abuja School",
                "description": (
                    "Supply and install a 32-camera Hikvision IP CCTV network with NVR, "
                    "biometric access control on 6 doors, and structured cabling at a school "
                    "campus in Gwarinpa, Abuja. Provide a 12-month maintenance warranty."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 450_000, "pay_max": 650_000,
                "state": "fct", "lga": "Gwarinpa", "slots": 2,
            },
            {
                "title": "Commercial Wiring — Office Fit-Out (Port Harcourt)",
                "description": (
                    "Wire a 3-floor open-plan office (~1,200 m²) including data points, "
                    "perimeter sockets, concealed conduit, emergency lighting, and "
                    "fire-alarm integration in Port Harcourt. Start within 2 weeks."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 600_000, "pay_max": 900_000,
                "state": "rivers", "lga": "Port Harcourt", "slots": 3,
            },
            {
                "title": "Inverter Battery Installation & Servicing — Ibadan",
                "description": (
                    "Install and service Luminous / Felicity lithium inverter systems for "
                    "residential clients across Ibadan. Ongoing role covering new "
                    "installations and regular maintenance visits. Own transport preferred."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 90_000, "pay_max": 150_000,
                "state": "oyo", "lga": "Ibadan North", "slots": 2,
            },
            {
                "title": "Fault-Finding Electrician (On-Call) — Lagos Island",
                "description": (
                    "Join the on-call maintenance roster for a property management company "
                    "with 200+ residential units on Lagos Island. Respond to electrical "
                    "faults within 2 hours. Paid per call-out plus a monthly retainer. "
                    "Reliable transport essential."
                ),
                "job_type": Job.JobType.PART_TIME,
                "pay_type": Job.PayType.HOURLY,
                "pay_min": 3_000, "pay_max": 5_000,
                "state": "lagos", "lga": "Lagos Island", "slots": 2,
            },
            {
                "title": "Panel Board & DB Installer — Retail Fit-Out (Kano)",
                "description": (
                    "Supply and install main distribution boards, sub-distribution boards, "
                    "and consumer units for 12 new retail units in a shopping complex "
                    "in Kano. Scope includes busbars, MCBs, RCDs, labelling, and "
                    "final circuit testing. Materials list provided by M&E consultant."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 280_000, "pay_max": 420_000,
                "state": "kano", "lga": "Kano Municipal", "slots": 2,
            },
        ],
    },

    # ── 2. PLUMBER ────────────────────────────────────────────────────────────
    {
        "name": "Plumber",
        "slug": "plumber",
        "icon_class":      "fas fa-wrench",
        "display_order":   1,
        "clip_context_text": "skilled plumber pipe fitting water supply sanitation Nigeria",
        "description": (
            "Licensed plumbers for domestic and commercial water supply, drainage, "
            "gas fitting, borehole installation, and sanitary ware fitting."
        ),
        "skills": [
            "Pipe Installation & Fitting", "Water Heater Installation",
            "Drainage & Sewerage", "Borehole & Pump Installation",
            "Bathroom & Sanitary Fitting", "Leak Detection & Repair",
            "Gas Pipe Installation", "Irrigation Systems",
            "Swimming Pool Plumbing", "Roof Gutter & Rainwater Systems",
        ],
        "jobs": [
            {
                "title": "Plumber — New Estate Water Supply (Kubwa, Abuja)",
                "description": (
                    "Install the internal water supply network for 25 terrace homes in "
                    "Kubwa, Abuja. Work includes header tank installation, rising mains, "
                    "cold-water distribution, and final connections to sanitaryware. "
                    "Materials supplied by client."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 400_000, "pay_max": 550_000,
                "state": "fct", "lga": "Kubwa", "slots": 2,
            },
            {
                "title": "Borehole & Submersible Pump Installer — Ogun State",
                "description": (
                    "Supply and install a 100 m borehole with 1.5 HP Grundfos submersible "
                    "pump, control panel, pressure tank, and overhead storage tank at a "
                    "school in Ogun State. Full water treatment setup included."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 700_000, "pay_max": 1_000_000,
                "state": "ogun", "lga": "Abeokuta South", "slots": 2,
            },
            {
                "title": "Gas Pipe Installation Technician — Residential Estate",
                "description": (
                    "Install LPG supply pipework (copper tubing and CSST) across a "
                    "50-unit residential estate in Lekki Phase 2. Route pipes to kitchen "
                    "hob points, fit isolation valves, and commission with pressure tests. "
                    "Gas Safe / DPR registration required."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 500_000, "pay_max": 750_000,
                "state": "lagos", "lga": "Lekki", "slots": 2,
            },
            {
                "title": "Water Tank Cleaning & Disinfection Technician — Lekki",
                "description": (
                    "Carry out quarterly cleaning and chlorination of 120 overhead and "
                    "underground tanks across a gated estate. Provide written certification "
                    "after each tank. PPE and chemicals supplied by client."
                ),
                "job_type": Job.JobType.PART_TIME,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 18_000, "pay_max": 25_000,
                "state": "lagos", "lga": "Lekki", "slots": 2,
            },
            {
                "title": "Drainage & Sewage Rehabilitation — Enugu",
                "description": (
                    "Reline and repair ageing concrete drainage channels and manholes across "
                    "a commercial district in Enugu. CCTV survey data available. "
                    "Experience with pipe-bursting or CIPP lining preferred."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 800_000, "pay_max": 1_200_000,
                "state": "enugu", "lga": "Enugu North", "slots": 3,
            },
            {
                "title": "Bathroom Renovation Plumber — Ikoyi",
                "description": (
                    "Fit out 8 luxury bathrooms in a high-end Ikoyi apartment complex. "
                    "Install Hansgrohe / Grohe fixtures, concealed cisterns, floor-mounted "
                    "WC pans, rain showers, and underfloor heating manifolds. "
                    "Portfolio of completed luxury bathrooms required."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 600_000, "pay_max": 900_000,
                "state": "lagos", "lga": "Ikoyi", "slots": 1,
            },
            {
                "title": "Irrigation System Installer — Farm (Kano)",
                "description": (
                    "Design and install a drip-irrigation system covering 5 hectares of "
                    "vegetable beds on a commercial farm near Kano. Supply pump, filter "
                    "station, main and lateral lines. Training of farm staff included."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 950_000, "pay_max": 1_400_000,
                "state": "kano", "lga": "Kano Municipal", "slots": 2,
            },
        ],
    },

    # ── 3. SOLAR INSTALLER ────────────────────────────────────────────────────
    {
        "name": "Solar Installer",
        "slug": "solar-installer",
        "icon_class":      "fas fa-solar-panel",
        "display_order":   2,
        "clip_context_text": "certified solar panel installer rooftop PV inverter Nigeria",
        "description": (
            "Certified solar installers for rooftop PV systems, inverter setup, "
            "battery storage, and off-grid solutions across Nigeria."
        ),
        "skills": [
            "Rooftop PV Installation", "Inverter & Battery Setup",
            "Off-Grid System Design", "Grid-Tie Configuration",
            "Solar Maintenance & Repair", "DC Wiring & Cable Management",
            "Energy Audit & Sizing", "Charge Controller Configuration",
            "Mounting Structure Fabrication", "Solar Water Pump Installation",
        ],
        "jobs": [
            {
                "title": "Rooftop Solar Installer — 10 kW Commercial System (Abuja)",
                "description": (
                    "Install a 10 kW grid-tied rooftop PV system on a commercial building "
                    "in Maitama, Abuja. Includes panel mounting, DC cabling, inverter "
                    "installation, and commissioning. Must have NABCEP or equivalent cert."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 550_000, "pay_max": 800_000,
                "state": "fct", "lga": "Maitama", "slots": 2,
            },
            {
                "title": "Off-Grid Solar Technician — Rural Schools (Borno)",
                "description": (
                    "Install standalone 3 kW solar systems in 10 rural primary schools "
                    "across Borno State under an NGO electrification programme. "
                    "Includes lighting, fan circuits, and a charging point. "
                    "Accommodation provided; allowances paid."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 120_000, "pay_max": 180_000,
                "state": "borno", "lga": "Maiduguri", "slots": 4,
            },
            {
                "title": "Solar Water Pump Installer — Irrigation Project (Katsina)",
                "description": (
                    "Supply and install 12 solar-powered submersible pumps (1–3 HP) "
                    "for smallholder irrigation schemes in Katsina. Commission each "
                    "unit and train local operators. Transport allowance included."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 700_000, "pay_max": 1_000_000,
                "state": "katsina", "lga": "Katsina", "slots": 2,
            },
            {
                "title": "Inverter & Battery Storage Specialist — Lagos Residences",
                "description": (
                    "Install and configure Victron MultiPlus II inverter-charger systems "
                    "with lithium battery banks for high-end Lagos homes. Covers MPPT "
                    "charge controllers, VRM portal setup, and customer walk-through. "
                    "Minimum 3 years Victron experience required."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 150_000, "pay_max": 220_000,
                "state": "lagos", "lga": "Victoria Island", "slots": 2,
            },
            {
                "title": "Solar Maintenance Engineer — Telecom Towers (Nationwide)",
                "description": (
                    "Carry out quarterly preventive maintenance on 80 solar-hybrid "
                    "telecom tower sites across 5 states. Tasks include panel cleaning, "
                    "battery health checks, charge controller firmware updates, and "
                    "fault reporting. Company vehicle provided."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 180_000, "pay_max": 250_000,
                "state": "lagos", "lga": "Ikeja", "slots": 3,
            },
            {
                "title": "Energy Auditor & Solar Sizing Consultant",
                "description": (
                    "Conduct on-site energy audits for SMEs in Port Harcourt and produce "
                    "detailed solar sizing reports including load analysis, system "
                    "recommendations, and ROI projections. Engineering background required."
                ),
                "job_type": Job.JobType.PART_TIME,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 20_000, "pay_max": 35_000,
                "state": "rivers", "lga": "Port Harcourt", "slots": 1,
                "is_remote": True,
            },
            {
                "title": "Solar Street Light Installer — State Road Project (Anambra)",
                "description": (
                    "Install 200 all-in-one solar streetlights along a 20 km state road "
                    "in Anambra. Scope includes pole erection, foundation works, and "
                    "controller programming. Team lead role; supervise 5 labourers."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 1_500_000, "pay_max": 2_200_000,
                "state": "anambra", "lga": "Awka South", "slots": 1,
            },
        ],
    },

    # ── 4. CARPENTER ──────────────────────────────────────────────────────────
    {
        "name": "Carpenter",
        "slug": "carpenter",
        "icon_class":      "fas fa-hammer",
        "display_order":   3,
        "clip_context_text": "expert carpenter furniture woodwork interior Nigeria",
        "description": (
            "Expert carpenters for furniture making, door and window fitting, "
            "roofing, and bespoke interior woodwork across Nigeria."
        ),
        "skills": [
            "Furniture Making", "Door & Window Fitting",
            "Roof Carpentry", "Interior Woodwork & Decor",
            "Cabinet & Wardrobe Making", "Formwork & Shuttering",
            "Flooring Installation", "Staircase Construction",
            "Shop Fitting & Joinery", "Restoration & Polishing",
        ],
        "jobs": [
            {
                "title": "Furniture Maker — Hotel Room Fit-Out (Lagos)",
                "description": (
                    "Fabricate and install bespoke bedroom furniture for 30 hotel rooms "
                    "in a boutique hotel on Lagos Island: bedframes, bedside tables, "
                    "wardrobes, writing desks, and TV units. Detailed drawings provided. "
                    "Workshop must be in or near Lagos."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 1_800_000, "pay_max": 2_500_000,
                "state": "lagos", "lga": "Lagos Island", "slots": 1,
            },
            {
                "title": "Roof Carpenter — 50-Unit Housing Estate (Ogun)",
                "description": (
                    "Cut and fix roof trusses, purlins, and rafter systems for 50 "
                    "terrace houses in a new estate in Sagamu, Ogun State. "
                    "Supply your own tools; timber provided by client. "
                    "Site supervisor on site."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 1_200_000, "pay_max": 1_800_000,
                "state": "ogun", "lga": "Sagamu", "slots": 3,
            },
            {
                "title": "Cabinet Maker & Shop Fitter — Pharmacy Chain (Abuja)",
                "description": (
                    "Design, fabricate, and install pharmacy display shelving, dispensary "
                    "counters, and storage cabinets across 4 new outlet locations in Abuja. "
                    "Must be able to read technical drawings and work to tight deadlines."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 600_000, "pay_max": 900_000,
                "state": "fct", "lga": "Garki", "slots": 2,
            },
            {
                "title": "Door & Window Installer — New Apartments (Port Harcourt)",
                "description": (
                    "Supply and fit solid wood internal doors, architraves, and skirting "
                    "boards across 18 apartment units in GRA, Port Harcourt. "
                    "External aluminium windows fitted by a separate contractor. "
                    "Minimum 5 years experience required."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 450_000, "pay_max": 700_000,
                "state": "rivers", "lga": "Port Harcourt", "slots": 2,
            },
            {
                "title": "Staircase Carpenter — Duplex Finishing (Ikoyi)",
                "description": (
                    "Construct and install a feature open-tread oak staircase with glass "
                    "balustrading in a luxury duplex in Ikoyi. Detailed architect's drawings "
                    "provided. Premium finish required; experience with hardwood essential."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 700_000, "pay_max": 1_100_000,
                "state": "lagos", "lga": "Ikoyi", "slots": 1,
            },
            {
                "title": "Formwork Carpenter — High-Rise Construction (Lagos)",
                "description": (
                    "Set and strike formwork for suspended slabs and columns on a 12-storey "
                    "building in Victoria Island. Ongoing contract throughout the structural "
                    "frame. Safety training provided; must have site ID / PPE."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.WEEKLY,
                "pay_min": 35_000, "pay_max": 50_000,
                "state": "lagos", "lga": "Victoria Island", "slots": 6,
            },
            {
                "title": "Antique Furniture Restorer — Interior Design Firm",
                "description": (
                    "Restore and refinish antique and damaged wooden furniture for an "
                    "interior design company serving high-net-worth clients in Lagos. "
                    "Skills needed: stripping, staining, French polishing, and reupholstery "
                    "of frames. Workshop-based role in Surulere."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 120_000, "pay_max": 180_000,
                "state": "lagos", "lga": "Surulere", "slots": 1,
            },
        ],
    },

    # ── 5. PAINTER & DECORATOR ────────────────────────────────────────────────
    {
        "name": "Painter & Decorator",
        "slug": "painter-decorator",
        "icon_class":      "fas fa-paint-roller",
        "display_order":   4,
        "clip_context_text": "painter decorator wall finishing interior exterior Nigeria",
        "description": (
            "Professional painters and decorators for interior and exterior "
            "painting, texture finishes, wallpaper hanging, and protective coatings."
        ),
        "skills": [
            "Interior Emulsion & Gloss", "Exterior Masonry Paint",
            "Texture & Skim Coating", "Wallpaper Hanging",
            "Epoxy Floor Coating", "Protective & Anti-Corrosion Coating",
            "Spray Painting", "Signwriting & Lettering",
            "Render Repair & Paint Prep", "Colour Consultation",
        ],
        "jobs": [
            {
                "title": "Interior Painter — 30-Room Hotel Renovation (Lekki)",
                "description": (
                    "Paint all 30 guest rooms and 6 common areas of a hotel in Lekki "
                    "undergoing refurbishment. Dulux premium emulsions specified. "
                    "Night shifts available to avoid guest disruption. "
                    "Materials provided on site."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 400_000, "pay_max": 600_000,
                "state": "lagos", "lga": "Lekki", "slots": 4,
            },
            {
                "title": "Exterior Masonry Painter — Estate (Abuja)",
                "description": (
                    "Apply exterior masonry paint and anti-algae treatment to 60 "
                    "terrace houses in a Gwarinpa estate. Scaffolding provided. "
                    "Must supply own brushes, rollers, and overalls. "
                    "Colour scheme drawings provided."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 550_000, "pay_max": 800_000,
                "state": "fct", "lga": "Gwarinpa", "slots": 5,
            },
            {
                "title": "Epoxy Floor Coating Applicator — Warehouse (Apapa)",
                "description": (
                    "Apply industrial epoxy floor coating to a 3,000 m² warehouse floor "
                    "in Apapa. Surface preparation (scarifying) included. "
                    "Coating system, equipment, and PPE supplied by client. "
                    "Experience with Sika or Fosroc systems preferred."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 700_000, "pay_max": 1_100_000,
                "state": "lagos", "lga": "Apapa", "slots": 3,
            },
            {
                "title": "Texture & Feature Wall Specialist — Luxury Homes",
                "description": (
                    "Create bespoke textured feature walls (Venetian plaster, "
                    "stucco, skim-coat pattern) in high-end residential projects "
                    "across Lagos. Must have a portfolio; samples may be requested. "
                    "Flexible working pattern to fit client schedules."
                ),
                "job_type": Job.JobType.PART_TIME,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 25_000, "pay_max": 45_000,
                "state": "lagos", "lga": "Ikoyi", "slots": 1,
            },
            {
                "title": "Anti-Corrosion Coating Painter — Oil & Gas Facility (PH)",
                "description": (
                    "Apply NACE-compliant multi-coat anti-corrosion paint systems to "
                    "steel structures, pipework, and vessels at a processing facility "
                    "in Port Harcourt. SSPC or NACE certification required. "
                    "Medicals and HUET card an advantage."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 30_000, "pay_max": 50_000,
                "state": "rivers", "lga": "Port Harcourt", "slots": 6,
            },
            {
                "title": "Spray Painter — Furniture Factory (Ota, Ogun)",
                "description": (
                    "Operate spray booths and apply lacquer / polyurethane finishes to "
                    "MDF and solid-wood furniture in a production factory in Ota. "
                    "Full-time in-factory role; PPE, training, and PAYE provided. "
                    "Experience with HVLP spray guns required."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 80_000, "pay_max": 120_000,
                "state": "ogun", "lga": "Ado-Odo/Ota", "slots": 2,
            },
            {
                "title": "Signwriter & Wall Branding Painter — Lagos SMEs",
                "description": (
                    "Hand-paint shop fronts, wall adverts, and branded murals for "
                    "small businesses across Lagos. Freelance arrangement; jobs "
                    "allocated weekly via our platform. Own brushes and ladder required."
                ),
                "job_type": Job.JobType.PART_TIME,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 30_000, "pay_max": 80_000,
                "state": "lagos", "lga": "Yaba", "slots": 3,
            },
        ],
    },

    # ── 6. WELDER ─────────────────────────────────────────────────────────────
    {
        "name": "Welder",
        "slug": "welder",
        "icon_class":      "fas fa-fire",
        "display_order":   5,
        "clip_context_text": "certified welder fabrication metalwork steel Nigeria",
        "description": (
            "Skilled welders and metal fabricators for structural steelwork, "
            "gates, tanks, pipelines, and industrial fabrication across Nigeria."
        ),
        "skills": [
            "MIG Welding", "TIG Welding", "Arc / Stick Welding",
            "Structural Steel Fabrication", "Pipeline Welding",
            "Gate & Railing Fabrication", "Pressure Vessel Welding",
            "Aluminium Welding", "Cutting & Grinding",
            "Weld Inspection & NDT",
        ],
        "jobs": [
            {
                "title": "Structural Steel Fabricator — Commercial Building (Lagos)",
                "description": (
                    "Fabricate and erect structural steel columns, beams, and purlins "
                    "for a 4-storey commercial building in Yaba. Must read structural "
                    "drawings and work with a site engineer. ARC / MIG certification required."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 900_000, "pay_max": 1_400_000,
                "state": "lagos", "lga": "Yaba", "slots": 4,
            },
            {
                "title": "Pipeline Welder — Oil Field (Delta State)",
                "description": (
                    "Join a pipeline construction crew in Delta State welding 10-inch "
                    "carbon-steel flow lines. CSWIP 3.1 or AWS CWI certification "
                    "required. Camp accommodation and safety gear provided."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 40_000, "pay_max": 65_000,
                "state": "delta", "lga": "Warri South", "slots": 5,
            },
            {
                "title": "Gate & Security Door Fabricator — Residential Projects",
                "description": (
                    "Fabricate and install sliding gates, pedestrian gates, and burglar-"
                    "proof doors for new residential builds across Port Harcourt. "
                    "Measure, quote, weld, powder-coat, and install. Own transport required."
                ),
                "job_type": Job.JobType.PART_TIME,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 80_000, "pay_max": 200_000,
                "state": "rivers", "lga": "Port Harcourt", "slots": 2,
            },
            {
                "title": "TIG Welder — Stainless Steel Kitchen Equipment (Abuja)",
                "description": (
                    "Fabricate stainless-steel commercial kitchen equipment (prep tables, "
                    "shelving, hoods, sinks) for a catering equipment company in Abuja. "
                    "In-workshop role; TIG welding on thin-gauge SS required."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 100_000, "pay_max": 150_000,
                "state": "fct", "lga": "Garki", "slots": 2,
            },
            {
                "title": "Water Tank Fabricator — Agricultural Project (Kaduna)",
                "description": (
                    "Fabricate and install 10 mild-steel water storage tanks (5,000–10,000 "
                    "litres each) for a smallholder irrigation scheme in Kaduna. Welding, "
                    "painting, and pipe stub-out connections included. 6-week project."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 600_000, "pay_max": 900_000,
                "state": "kaduna", "lga": "Kaduna South", "slots": 2,
            },
            {
                "title": "Aluminium Welder — Window & Door Frame Fabrication",
                "description": (
                    "Fabricate aluminium casement windows and entrance door frames for "
                    "a housing development in Ibadan. TIG welding on 6063-T5 alloy. "
                    "Workshop-based; orders supplied weekly. Minimum 3 years experience."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 90_000, "pay_max": 130_000,
                "state": "oyo", "lga": "Ibadan North", "slots": 2,
            },
            {
                "title": "Pressure Vessel Inspector & Welder — Refinery Turnaround",
                "description": (
                    "Participate in a planned maintenance turnaround at a refinery in "
                    "Warri. Repair and re-weld pressure vessel nozzles, flanges, and "
                    "shell plates. CSWIP 3.2 or equivalent required. 6-week contract."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 60_000, "pay_max": 90_000,
                "state": "delta", "lga": "Warri", "slots": 3,
            },
        ],
    },

    # ── 7. MASON ──────────────────────────────────────────────────────────────
    {
        "name": "Mason",
        "slug": "mason",
        "icon_class":      "fas fa-cubes",
        "display_order":   6,
        "clip_context_text": "bricklayer mason block work plastering rendering Nigeria",
        "description": (
            "Experienced masons for brickwork, block laying, plastering, "
            "rendering, tiling, and concrete works across Nigeria."
        ),
        "skills": [
            "Block & Brick Laying", "Plastering & Rendering",
            "Concrete Works", "Tile Fixing",
            "Stone Masonry", "Screed Laying",
            "Fireplace & Feature Wall", "Repointing & Restoration",
            "Swimming Pool Construction", "Retaining Wall Construction",
        ],
        "jobs": [
            {
                "title": "Block Layer — 60-Unit Estate (Ibeju-Lekki)",
                "description": (
                    "Lay 9-inch sandcrete blocks for walls and fence lines across a "
                    "60-unit low-rise estate in Ibeju-Lekki. Mortar mixing machine "
                    "on site. Daily rate paid weekly. Protective gear provided."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 12_000, "pay_max": 18_000,
                "state": "lagos", "lga": "Ibeju-Lekki", "slots": 10,
            },
            {
                "title": "Plasterer — Commercial Office Fit-Out (Victoria Island)",
                "description": (
                    "Skim-plaster all internal walls and ceilings of a 1,000 m² office "
                    "on Victoria Island to a smooth board-finish standard. Bonding and "
                    "finish coats specified. Scaffolding, materials, and mixing equipment "
                    "provided. Clean finish essential."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 350_000, "pay_max": 500_000,
                "state": "lagos", "lga": "Victoria Island", "slots": 4,
            },
            {
                "title": "Swimming Pool Constructor — Luxury Villa (Banana Island)",
                "description": (
                    "Build a 12 m × 5 m infinity swimming pool including excavation, "
                    "blockwork shell, waterproof render, tiling, and plant-room plumbing "
                    "stub-outs at a villa on Banana Island. PE drawings provided. "
                    "Previous pool construction portfolio required."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 2_500_000, "pay_max": 4_000_000,
                "state": "lagos", "lga": "Ikoyi", "slots": 1,
            },
            {
                "title": "Screeder — Warehouse Floor (Sagamu, Ogun)",
                "description": (
                    "Lay a 75 mm power-floated concrete screed over 4,500 m² of "
                    "warehouse floor in Sagamu. Pump truck on site. Must provide "
                    "own float trowels. Measured work; rate per square metre."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 600_000, "pay_max": 900_000,
                "state": "ogun", "lga": "Sagamu", "slots": 6,
            },
            {
                "title": "Retaining Wall Mason — Hillside Development (Jos)",
                "description": (
                    "Construct 4 reinforced concrete retaining walls (ranging 1.5–3 m "
                    "high) to stabilise a sloped site for a residential development "
                    "in Jos, Plateau State. Structural drawings provided. "
                    "Experience with RC retaining walls essential."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 800_000, "pay_max": 1_200_000,
                "state": "plateau", "lga": "Jos North", "slots": 3,
            },
            {
                "title": "Tile Fixer — Luxury Apartments (Abuja)",
                "description": (
                    "Fix large-format (600 × 1200 mm) porcelain floor and wall tiles "
                    "in 12 luxury apartments in Maitama, Abuja. Wet-room shower areas "
                    "and heated floor substrate included. Precision work required; "
                    "experience with rectified large-format tiles essential."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 500_000, "pay_max": 750_000,
                "state": "fct", "lga": "Maitama", "slots": 3,
            },
            {
                "title": "Stone Mason — Feature Walls & Landscaping (Lagos)",
                "description": (
                    "Lay natural stone cladding on garden feature walls, gateposts, and "
                    "entrance pillars for high-end residential projects across Lagos. "
                    "Must be experienced with sandstone, granite, and slate. "
                    "Flexible scheduling; multiple projects running concurrently."
                ),
                "job_type": Job.JobType.PART_TIME,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 18_000, "pay_max": 28_000,
                "state": "lagos", "lga": "Lekki", "slots": 2,
            },
        ],
    },

    # ── 8. HAIR STYLIST ───────────────────────────────────────────────────────
    {
        "name": "Hair Stylist",
        "slug": "hair-stylist",
        "icon_class":      "fas fa-cut",
        "display_order":   7,
        "clip_context_text": "hair stylist braiding weaving salon Nigeria",
        "description": (
            "Professional hair stylists for braiding, weaving, natural hair care, "
            "perms, colouring, and barbering services across Nigeria."
        ),
        "skills": [
            "Braiding & Box Braids", "Weave Installation",
            "Natural Hair Care & Locs", "Hair Colouring & Highlights",
            "Perming & Relaxing", "Blow-Dry & Styling",
            "Wig Making & Installation", "Barbering & Fades",
            "Hair Extensions", "Scalp Treatment",
        ],
        "jobs": [
            {
                "title": "Senior Hair Braider — Busy Victoria Island Salon",
                "description": (
                    "Join a fast-paced unisex salon on Victoria Island as a senior "
                    "braider. Must master knotless braids, box braids, goddess braids, "
                    "and Senegalese twists. Commission-based earnings on top of a base "
                    "salary. Weekend availability essential."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 80_000, "pay_max": 130_000,
                "state": "lagos", "lga": "Victoria Island", "slots": 2,
            },
            {
                "title": "Hair Colourist & Stylist — Upscale Abuja Salon",
                "description": (
                    "Apply balayage, highlights, ombré, and colour correction for "
                    "clients at a premium salon in Wuse 2, Abuja. L'Oréal Professional "
                    "or Wella colour training preferred. Must maintain a clean client book."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 100_000, "pay_max": 160_000,
                "state": "fct", "lga": "Wuse 2", "slots": 1,
            },
            {
                "title": "Mobile Hair Stylist — Corporate & Events (Lagos)",
                "description": (
                    "Provide on-location hair styling for corporate photo shoots, "
                    "weddings, and social events across Lagos. Must own a professional "
                    "kit and transport. Bookings coordinated through our platform. "
                    "Portfolio of editorial/bridal work required."
                ),
                "job_type": Job.JobType.PART_TIME,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 30_000, "pay_max": 100_000,
                "state": "lagos", "lga": "Ikeja", "slots": 5,
                "is_remote": False,
            },
            {
                "title": "Barber — Hotel Men's Grooming Lounge (Lagos)",
                "description": (
                    "Staff the in-house barbershop at a 5-star hotel in Lagos, offering "
                    "haircuts, fades, beard trims, and hot-towel shaves. Smart appearance "
                    "and excellent client communication essential. Experience in a luxury "
                    "environment preferred."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 90_000, "pay_max": 140_000,
                "state": "lagos", "lga": "Victoria Island", "slots": 2,
            },
            {
                "title": "Natural Hair & Loc Specialist — Boutique Salon (Enugu)",
                "description": (
                    "Serve a growing natural-hair clientele at a specialist salon in "
                    "Enugu. Services include loc installation and maintenance, "
                    "steam treatments, protective styles, and scalp consultations. "
                    "Natural hair certification an advantage."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 70_000, "pay_max": 110_000,
                "state": "enugu", "lga": "Enugu North", "slots": 1,
            },
            {
                "title": "Wig Maker & Lace Installer — Online Studio (Remote + Lagos)",
                "description": (
                    "Produce custom lace-front and full-lace wigs for an online wig "
                    "business. Work from home studio (Lagos-based preferred). "
                    "Wigs are dispatched to clients; installation appointments handled "
                    "at the client's location. Hair supplied by employer."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 75_000, "pay_max": 120_000,
                "state": "lagos", "lga": "Surulere", "slots": 2,
                "is_remote": True,
            },
            {
                "title": "Salon Manager & Senior Stylist — Ibadan",
                "description": (
                    "Manage daily operations of a busy salon in Bodija, Ibadan, while "
                    "also servicing clients. Responsibilities include rostering, stock "
                    "ordering, client complaints, and mentoring junior stylists. "
                    "Minimum 5 years salon experience required."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 130_000, "pay_max": 200_000,
                "state": "oyo", "lga": "Ibadan North", "slots": 1,
            },
        ],
    },

    # ── 9. HVAC TECHNICIAN ────────────────────────────────────────────────────
    {
        "name": "HVAC Technician",
        "slug": "hvac-technician",
        "icon_class":      "fas fa-wind",
        "display_order":   8,
        "clip_context_text": "HVAC air conditioning technician installation Nigeria",
        "description": (
            "Trained HVAC technicians for air-conditioner installation, servicing, "
            "ducted systems, cold rooms, and ventilation engineering."
        ),
        "skills": [
            "Split AC Installation & Service", "Ducted & Cassette AC Systems",
            "Cold Room & Refrigeration", "Ventilation Design",
            "Refrigerant Handling (F-Gas)", "VRF / VRV Systems",
            "AC Fault Diagnosis & Repair", "Air Quality & Filtration",
            "Building Automation Systems", "Energy Efficiency Auditing",
        ],
        "jobs": [
            {
                "title": "AC Installation Technician — New Office Towers (Lagos)",
                "description": (
                    "Install Daikin and Mitsubishi split and cassette AC units across "
                    "8 floors of a new office development in Victoria Island. "
                    "Pipe brazing, electrical connections, and commissioning included. "
                    "F-Gas / refrigerant handling certificate required."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 800_000, "pay_max": 1_200_000,
                "state": "lagos", "lga": "Victoria Island", "slots": 4,
            },
            {
                "title": "Cold Room Engineer — Food Processing Factory (Ogun)",
                "description": (
                    "Install and commission two walk-in cold rooms (−18°C freezer and "
                    "4°C chiller) at a food processing plant in Ota. Includes insulated "
                    "panel installation, refrigeration plant, and BMS integration. "
                    "Cold-room experience essential."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 1_200_000, "pay_max": 1_800_000,
                "state": "ogun", "lga": "Ado-Odo/Ota", "slots": 2,
            },
            {
                "title": "HVAC Service Technician — Hotel Maintenance (Abuja)",
                "description": (
                    "Join the maintenance team at a 200-room hotel in Abuja. Carry out "
                    "planned and reactive servicing of split, cassette, and ducted AC "
                    "units. On-call rota for out-of-hours faults. Uniform and tools provided."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 120_000, "pay_max": 180_000,
                "state": "fct", "lga": "Central Area", "slots": 2,
            },
            {
                "title": "VRF System Engineer — Corporate HQ Fit-Out (Lekki)",
                "description": (
                    "Design, supply, and install a Daikin VRF system for a 3,000 m² "
                    "corporate head office in Lekki. Includes duct layout, outdoor unit "
                    "placement, controls wiring, and full commissioning. "
                    "Daikin VRF certification preferred."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 2_500_000, "pay_max": 4_000_000,
                "state": "lagos", "lga": "Lekki", "slots": 1,
            },
            {
                "title": "AC Servicing Technician — Residential Call-Outs (Lagos)",
                "description": (
                    "Handle residential AC servicing call-outs (cleaning, gas top-up, "
                    "fault diagnosis) across Lagos Island and mainland. Minimum 3 jobs "
                    "per day via dispatch. Must own a service kit and have reliable "
                    "transport. Commission per completed job."
                ),
                "job_type": Job.JobType.PART_TIME,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 8_000, "pay_max": 20_000,
                "state": "lagos", "lga": "Lagos Island", "slots": 5,
            },
            {
                "title": "Ventilation Designer & Installer — Hospital (Ibadan)",
                "description": (
                    "Design and install a mechanical ventilation system for an "
                    "operating theatre suite and ICU at a private hospital in Ibadan. "
                    "Must meet ASHRAE 170 and local FMOH guidelines. "
                    "Full M&E drawings provided."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 1_500_000, "pay_max": 2_200_000,
                "state": "oyo", "lga": "Ibadan North", "slots": 1,
            },
            {
                "title": "Refrigeration Technician — Supermarket Chain (Port Harcourt)",
                "description": (
                    "Service and repair refrigeration cabinets, display chillers, "
                    "and walk-in cold stores across 6 supermarket branches in "
                    "Port Harcourt. Reactive call-outs within 4 hours of logging. "
                    "Company van and tools provided."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 100_000, "pay_max": 150_000,
                "state": "rivers", "lga": "Port Harcourt", "slots": 2,
            },
        ],
    },

    # ── 10. AUTO MECHANIC ─────────────────────────────────────────────────────
    {
        "name": "Auto Mechanic",
        "slug": "auto-mechanic",
        "icon_class":      "fas fa-car",
        "display_order":   9,
        "clip_context_text": "auto mechanic vehicle repair engine diagnostics Nigeria",
        "description": (
            "Qualified auto mechanics for engine repairs, diagnostics, "
            "panel beating, spray painting, and fleet maintenance."
        ),
        "skills": [
            "Engine Overhaul & Repair", "Diagnostic & OBD2 Scanning",
            "Brake & Suspension", "Electrical & Auto Electrics",
            "Gearbox & Transmission", "Panel Beating & Body Repair",
            "Spray Painting & Refinishing", "Air Conditioning Service",
            "Tyre & Wheel Alignment", "Fleet Maintenance",
        ],
        "jobs": [
            {
                "title": "Fleet Mechanic — Logistics Company (Lagos)",
                "description": (
                    "Maintain and repair a fleet of 40 Mitsubishi Canter trucks for "
                    "a courier company based in Oshodi, Lagos. Preventive maintenance "
                    "schedules, breakdown response, and parts ordering included. "
                    "Experience with light commercial vehicles essential."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 120_000, "pay_max": 180_000,
                "state": "lagos", "lga": "Oshodi-Isolo", "slots": 3,
            },
            {
                "title": "Diagnostic Technician — Toyota Dealership (Abuja)",
                "description": (
                    "Carry out OBD2 and dealership-level diagnostics on Toyota vehicles "
                    "using Techstream software at an authorised service centre in Abuja. "
                    "Toyota-certified training provided for the right candidate. "
                    "Minimum 4 years workshop experience."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 150_000, "pay_max": 220_000,
                "state": "fct", "lga": "Garki", "slots": 2,
            },
            {
                "title": "Panel Beater & Spray Painter — Auto Body Shop (Warri)",
                "description": (
                    "Repair accident-damaged vehicles (dent removal, panel straightening, "
                    "filler application, primer, and topcoat spray) at a busy body shop "
                    "in Warri. Experience with BASF or Sikkens water-based systems preferred."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 90_000, "pay_max": 140_000,
                "state": "delta", "lga": "Warri South", "slots": 2,
            },
            {
                "title": "Gearbox & Transmission Specialist — Kano",
                "description": (
                    "Overhaul automatic and manual gearboxes and differentials at a "
                    "specialist workshop in Kano. Jobs sourced from dealerships and "
                    "direct clients. Must have own tools; workshop space and parts "
                    "sourcing support provided."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 100_000, "pay_max": 160_000,
                "state": "kano", "lga": "Kano Municipal", "slots": 1,
            },
            {
                "title": "Auto Electrician — Vehicle Electrical Fault Diagnosis",
                "description": (
                    "Diagnose and repair complex electrical faults (wiring harness, "
                    "ECU, CAN-bus, comfort systems) on modern vehicles at a workshop "
                    "in Port Harcourt. Oscilloscope and multimeter skills required. "
                    "Experience with European and Japanese brands preferred."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 130_000, "pay_max": 200_000,
                "state": "rivers", "lga": "Port Harcourt", "slots": 1,
            },
            {
                "title": "Mobile Mechanic — Roadside Assistance (Lagos)",
                "description": (
                    "Respond to roadside breakdowns across Lagos as part of a "
                    "24/7 roadside assistance network. Carry out basic fault diagnosis, "
                    "battery jump-starts, tyre changes, and minor repairs on-site. "
                    "Company van provided; shifts on rota."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 80_000, "pay_max": 120_000,
                "state": "lagos", "lga": "Ikeja", "slots": 4,
            },
            {
                "title": "Heavy Equipment Mechanic — Construction Site (Abuja)",
                "description": (
                    "Service and repair Caterpillar excavators, bulldozers, and "
                    "articulated dump trucks on an active road construction site near "
                    "Abuja. PPE provided. Must have experience with Cat ET diagnostic "
                    "software and hydraulic system repairs."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 25_000, "pay_max": 40_000,
                "state": "fct", "lga": "Abuja Municipal", "slots": 2,
            },
        ],
    },

    # ── 11. TAILOR ────────────────────────────────────────────────────────────
    #  NEW category — created if it doesn't exist
    {
        "name": "Tailor",
        "slug": "tailor",
        "icon_class":      "fas fa-tshirt",
        "display_order":   10,
        "clip_context_text": "tailor fashion designer sewing garments Nigeria",
        "description": (
            "Skilled tailors and fashion designers for bespoke garment making, "
            "alterations, Ankara designs, bridal wear, and uniform production."
        ),
        "skills": [
            "Bespoke Suit & Agbada Making", "Ankara & Aso-Oke Designs",
            "Bridal Gown & Evening Wear", "Trouser & Shirt Tailoring",
            "Fabric Cutting & Pattern Drafting", "Embroidery & Beadwork",
            "School & Corporate Uniforms", "Garment Alterations & Repairs",
            "Machine Sewing & Overlock", "Fashion Illustration & Design",
        ],
        "jobs": [
            {
                "title": "Senior Tailor — Bespoke Men's Wear Studio (Lagos)",
                "description": (
                    "Join a high-end bespoke tailoring studio in Balogun Market, Lagos, "
                    "producing agbadas, suits, and senator outfits for VIP clients. "
                    "Must be able to draft patterns from measurements and cut "
                    "independently. 5+ years experience required."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 100_000, "pay_max": 160_000,
                "state": "lagos", "lga": "Lagos Island", "slots": 2,
            },
            {
                "title": "Bridal & Evening Wear Designer — Abuja",
                "description": (
                    "Design and sew bespoke bridal gowns, bridesmaids' dresses, and "
                    "evening wear for clients in Abuja. Must manage client consultations, "
                    "fittings, and delivery. Portfolio of bridal work required. "
                    "Home studio or small workshop acceptable."
                ),
                "job_type": Job.JobType.PART_TIME,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 150_000, "pay_max": 500_000,
                "state": "fct", "lga": "Wuse 2", "slots": 1,
            },
            {
                "title": "Uniform Production Tailor — School Supplier (Ibadan)",
                "description": (
                    "Mass-produce school uniforms for a school supplies company in "
                    "Ibadan. Must operate industrial sewing machines and meet daily "
                    "output targets. Overtime available during back-to-school periods. "
                    "Fabric and overlock provided."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 60_000, "pay_max": 90_000,
                "state": "oyo", "lga": "Ibadan North", "slots": 5,
            },
            {
                "title": "Ankara Fashion Designer — Export Brand (Lagos)",
                "description": (
                    "Design and sew ready-to-wear Ankara and Adire pieces for an "
                    "export-focused fashion brand based in Yaba. Seasonal collections; "
                    "must work to design briefs and size grading. Experience with "
                    "overseas size standards (UK/US) an advantage."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 90_000, "pay_max": 140_000,
                "state": "lagos", "lga": "Yaba", "slots": 3,
            },
            {
                "title": "Corporate Uniform Tailor — Oil & Gas Contractor (PH)",
                "description": (
                    "Produce and alter corporate and site-safety uniforms (coveralls, "
                    "polo shirts, trousers) for an oil & gas contractor in Port Harcourt. "
                    "Bulk orders; industrial machines provided. "
                    "Experience with heavy-duty fabrics required."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 80_000, "pay_max": 120_000,
                "state": "rivers", "lga": "Port Harcourt", "slots": 3,
            },
            {
                "title": "Garment Alteration Specialist — Dry-Cleaner Chain",
                "description": (
                    "Carry out garment repairs and alterations (hemming, taking in/out, "
                    "zip replacement, patching) for customers of a dry-cleaner chain "
                    "with 5 branches across Lagos. Move between branches as needed. "
                    "Neat hand and machine sewing required."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 55_000, "pay_max": 80_000,
                "state": "lagos", "lga": "Ikeja", "slots": 2,
            },
            {
                "title": "Embroidery & Beadwork Artisan — Aso-Ebi Specialist",
                "description": (
                    "Apply hand and machine embroidery, sequins, and beadwork to "
                    "aso-ebi fabrics for wedding and event outfits. Home-based or "
                    "studio-based; flexible arrangement. Strong portfolio of embellished "
                    "garments required. Lagos-based."
                ),
                "job_type": Job.JobType.PART_TIME,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 20_000, "pay_max": 80_000,
                "state": "lagos", "lga": "Surulere", "slots": 3,
            },
        ],
    },

    # ── 12. TILER ─────────────────────────────────────────────────────────────
    {
        "name": "Tiler",
        "slug": "tiler",
        "icon_class":      "fas fa-th",
        "display_order":   11,
        "clip_context_text": "tiler floor wall tile fixing porcelain ceramic Nigeria",
        "description": (
            "Professional tilers for floor and wall tile fixing, wet rooms, "
            "swimming pools, and decorative mosaic work across Nigeria."
        ),
        "skills": [
            "Porcelain & Ceramic Tile Fixing", "Large-Format Tile Laying",
            "Wet Room & Shower Tiling", "Mosaic & Decorative Tiling",
            "External Paving & Patios", "Swimming Pool Tiling",
            "Tile Levelling System Use", "Grout & Sealant Application",
            "Underfloor Heating Compatibility", "Tile Cutting & Scribing",
        ],
        "jobs": [
            {
                "title": "Floor Tiler — Hotel Lobby & Corridors (Lagos)",
                "description": (
                    "Lay 1200 × 600 mm polished porcelain floor tiles in the lobby, "
                    "corridors, and restaurant of a 4-star hotel in Victoria Island. "
                    "Tile levelling clips required. All materials on site. "
                    "Night shifts available to avoid guest disruption."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 500_000, "pay_max": 750_000,
                "state": "lagos", "lga": "Victoria Island", "slots": 4,
            },
            {
                "title": "Wall & Floor Tiler — 20 Apartments (Lekki Phase 2)",
                "description": (
                    "Fix floor and wall tiles in bathrooms, kitchens, and living areas "
                    "of 20 apartments in a new development in Lekki Phase 2. "
                    "Drawings provided; adhesive and grout supplied by developer. "
                    "Measured rate per m² paid weekly."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 800_000, "pay_max": 1_200_000,
                "state": "lagos", "lga": "Lekki", "slots": 6,
            },
            {
                "title": "Swimming Pool Tiler — Luxury Villa (Abuja)",
                "description": (
                    "Apply glass mosaic and porcelain tiles to the floor and walls of "
                    "an Olympic-size pool and surrounding deck at a villa in Maitama. "
                    "Pool shell already rendered; waterproof adhesive and grout specified. "
                    "Portfolio of pool tiling required."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 1_200_000, "pay_max": 2_000_000,
                "state": "fct", "lga": "Maitama", "slots": 2,
            },
            {
                "title": "External Paving Tiler — Office Landscaping (Port Harcourt)",
                "description": (
                    "Lay anti-slip external porcelain pavers across a 2,000 m² car park, "
                    "walkways, and entrance plaza at a corporate office in Trans-Amadi. "
                    "Drainage falls critical; laser level provided."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 700_000, "pay_max": 1_100_000,
                "state": "rivers", "lga": "Port Harcourt", "slots": 5,
            },
            {
                "title": "Wet Room & Shower Tiler — Luxury Homes (Ikoyi)",
                "description": (
                    "Create frameless shower enclosures with full-height wall tiles, "
                    "linear drain channels, and slip-resistant floor tiles in 10 luxury "
                    "homes in Ikoyi. Tanking membrane system must be applied before tiling."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 450_000, "pay_max": 700_000,
                "state": "lagos", "lga": "Ikoyi", "slots": 2,
            },
            {
                "title": "Decorative Mosaic Artisan — Restaurant Feature Walls",
                "description": (
                    "Design and install bespoke mosaic feature walls and bar facades for "
                    "a chain of upscale restaurants opening across Lagos. "
                    "Must have experience with glass, stone, and ceramic mosaic. "
                    "Artistic portfolio required."
                ),
                "job_type": Job.JobType.PART_TIME,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 200_000, "pay_max": 600_000,
                "state": "lagos", "lga": "Lekki", "slots": 1,
            },
            {
                "title": "General Tiler — Volume House Building (Aba, Abia State)",
                "description": (
                    "Fix standard 40 × 40 cm ceramic floor and wall tiles in bathrooms "
                    "and kitchens of 30 semi-detached houses in Aba. Straightforward "
                    "production tiling; adhesive, grout, and spacers supplied on site. "
                    "Daily rate paid at end of each week."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 12_000, "pay_max": 18_000,
                "state": "abia", "lga": "Aba North", "slots": 8,
            },
        ],
    },

    # ── 13. ALUMINUM & GLASS INSTALLER ────────────────────────────────────────
    {
        "name": "Aluminum & Glass Installer",
        "slug": "aluminum-glass-installer",
        "icon_class":      "fas fa-border-all",
        "display_order":   12,
        "clip_context_text": "aluminium glazing glass installer window curtain wall Nigeria",
        "description": (
            "Specialist installers of aluminium windows, glazed curtain walls, "
            "glass partitions, shopfronts, and frameless shower screens."
        ),
        "skills": [
            "Aluminium Window Fabrication & Fitting", "Curtain Wall & Cladding",
            "Glass Partition Installation", "Shopfront Glazing",
            "Frameless Shower Screen Fitting", "Structural Glazing & Sealants",
            "Aluminium Door Systems", "Louvre & Jalousie Windows",
            "Powder Coat & Anodising Knowledge", "Site Measurement & Survey",
        ],
        "jobs": [
            {
                "title": "Aluminium Window Installer — New Estate (Lekki Phase 1)",
                "description": (
                    "Fabricate and fit aluminium casement and sliding windows for "
                    "60 houses in a new estate in Lekki Phase 1. Factory-cut profiles "
                    "delivered to site; site assembly, sealing, and glazing required. "
                    "Must have own cutting tools."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 1_200_000, "pay_max": 1_800_000,
                "state": "lagos", "lga": "Lekki", "slots": 4,
            },
            {
                "title": "Curtain Wall Glazier — High-Rise (Victoria Island)",
                "description": (
                    "Install structural silicone-bonded curtain wall panels on a "
                    "15-storey commercial tower in Victoria Island. Works at height "
                    "using BMU and cradle. WAMITAB working at height certification "
                    "required. Safety harness and PPE provided."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 20_000, "pay_max": 35_000,
                "state": "lagos", "lga": "Victoria Island", "slots": 6,
            },
            {
                "title": "Glass Partition Installer — Corporate Office (Abuja)",
                "description": (
                    "Supply and install 10 mm toughened glass partitions with aluminium "
                    "framing for open-plan office pods in a corporate headquarters "
                    "in Maitama. Includes framed doors, manifestation film, and acoustic "
                    "seals. Drawings provided."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 600_000, "pay_max": 950_000,
                "state": "fct", "lga": "Maitama", "slots": 2,
            },
            {
                "title": "Shopfront Glazing Fitter — Retail Chain (Lagos)",
                "description": (
                    "Fit aluminium-framed shopfronts with automatic sliding doors "
                    "and structural glass panels for a retail chain opening 8 new "
                    "stores in Lagos. Must be comfortable measuring, ordering, "
                    "and installing to tight retail fit-out schedules."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 800_000, "pay_max": 1_200_000,
                "state": "lagos", "lga": "Ikeja", "slots": 3,
            },
            {
                "title": "Frameless Shower Screen Installer — Luxury Homes",
                "description": (
                    "Measure, fabricate, and install frameless 10 mm toughened glass "
                    "shower screens, bath screens, and towel-rail channels in high-end "
                    "residential projects across Lagos. Precision work; sealant finish "
                    "must be flawless. Portfolio of similar work required."
                ),
                "job_type": Job.JobType.PART_TIME,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 80_000, "pay_max": 250_000,
                "state": "lagos", "lga": "Ikoyi", "slots": 2,
            },
            {
                "title": "Aluminium Door & Louvre Installer — Estate (Enugu)",
                "description": (
                    "Fit aluminium entrance doors, security screen doors, and louvre "
                    "windows across 40 semi-detached units in a new housing estate "
                    "in Enugu. Profiles and glass panels supplied to site. "
                    "Experience with mechanical locks and multipoint lock systems."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 500_000, "pay_max": 800_000,
                "state": "enugu", "lga": "Enugu South", "slots": 3,
            },
            {
                "title": "Aluminium Fabricator & Installer — Factory (Kano)",
                "description": (
                    "Produce and install aluminium industrial windows, ventilation "
                    "louvres, and factory door systems at a new manufacturing plant "
                    "in Kano. In-house workshop with cutting and welding equipment. "
                    "Permanent role with competitive benefits."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 90_000, "pay_max": 140_000,
                "state": "kano", "lga": "Kano Municipal", "slots": 3,
            },
        ],
    },

    # ── 14. GENERATOR TECHNICIAN ──────────────────────────────────────────────
    {
        "name": "Generator Technician",
        "slug": "generator-technician",
        "icon_class":      "fas fa-plug",
        "display_order":   13,
        "clip_context_text": "generator technician diesel servicing maintenance Nigeria",
        "description": (
            "Specialist generator technicians for diesel genset installation, "
            "servicing, overhaul, ATS wiring, and emergency repair across Nigeria."
        ),
        "skills": [
            "Diesel Generator Servicing", "Generator Installation & Commissioning",
            "ATS & Changeover Panel Wiring", "Engine Overhaul & Reboring",
            "Fuel System Repair", "Electrical Fault Finding",
            "Load Testing & Balancing", "Soundproofing & Housing",
            "Remote Monitoring Setup", "Exhaust & Cooling System Repair",
        ],
        "jobs": [
            {
                "title": "Generator Technician — Factory Maintenance (Lagos)",
                "description": (
                    "Carry out weekly and monthly preventive maintenance on four Cummins "
                    "generators (150–500 kVA) powering a bottling plant in Mushin. "
                    "Tasks include oil and filter changes, load testing, and fault response. "
                    "24-hour on-call rota."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 100_000, "pay_max": 160_000,
                "state": "lagos", "lga": "Mushin", "slots": 2,
            },
            {
                "title": "Generator Installer — New Housing Estate (Lekki)",
                "description": (
                    "Supply, install, and commission three Mikano generators (100 kVA "
                    "each) with ATS panels and automatic changeover for an estate in "
                    "Lekki. Cable laying, earthing, and acoustic housing included. "
                    "Materials and plant supplied by developer."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 800_000, "pay_max": 1_200_000,
                "state": "lagos", "lga": "Lekki", "slots": 2,
            },
            {
                "title": "Diesel Engine Rebuilder — Generator Workshop (Aba)",
                "description": (
                    "Overhaul and rebuild diesel generator engines (Perkins, Lister, "
                    "Cummins) at a specialist repair workshop in Aba. Tasks include "
                    "head skimming, bore measurement, piston ring replacement, and "
                    "injector reconditioning. Must have own tools."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 90_000, "pay_max": 140_000,
                "state": "abia", "lga": "Aba North", "slots": 2,
            },
            {
                "title": "ATS & Changeover Panel Engineer — Commercial Properties",
                "description": (
                    "Wire and commission automatic transfer switch (ATS) and changeover "
                    "panels for banks, telecom offices, and commercial buildings across "
                    "Abuja. Must understand 3-phase power and be comfortable working "
                    "inside LV switchrooms."
                ),
                "job_type": Job.JobType.PART_TIME,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 100_000, "pay_max": 200_000,
                "state": "fct", "lga": "Central Area", "slots": 2,
            },
            {
                "title": "Genset Field Service Engineer — Telecom Towers (Nationwide)",
                "description": (
                    "Service and repair diesel generators on 120 telecom tower sites "
                    "across the North-West zone. Travel to remote sites; company "
                    "4×4 and allowances provided. Experience with FG Wilson or "
                    "Aggreko sets preferred."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 150_000, "pay_max": 220_000,
                "state": "kano", "lga": "Kano Municipal", "slots": 3,
            },
            {
                "title": "Soundproof Housing Fabricator — Generator Enclosures",
                "description": (
                    "Design and build acoustic enclosures for diesel generators "
                    "(10–200 kVA) at residential and commercial sites. Mild steel "
                    "carcass, acoustic foam lining, ventilation baffles, and "
                    "anti-vibration mounts. Lagos-based; own workshop preferred."
                ),
                "job_type": Job.JobType.PART_TIME,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 120_000, "pay_max": 350_000,
                "state": "lagos", "lga": "Ikeja", "slots": 2,
            },
            {
                "title": "Generator Maintenance Technician — Hospital (Kano)",
                "description": (
                    "Ensure 99.9% uptime of two 250 kVA Perkins generators providing "
                    "critical power to a 150-bed hospital in Kano. Daily checks, "
                    "fault reporting, and liaison with electrical team. "
                    "On-site accommodation provided."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 110_000, "pay_max": 160_000,
                "state": "kano", "lga": "Kano Municipal", "slots": 1,
            },
        ],
    },

    # ── 15. ROOFER ────────────────────────────────────────────────────────────
    {
        "name": "Roofer",
        "slug": "roofer",
        "icon_class":      "fas fa-home",
        "display_order":   14,
        "clip_context_text": "roofer roofing contractor waterproofing Nigeria",
        "description": (
            "Specialist roofers for metal sheet, concrete tile, flat roof, "
            "and waterproofing works on residential and commercial buildings."
        ),
        "skills": [
            "Metal Roof Sheet Installation", "Concrete & Clay Tile Roofing",
            "Flat Roof & Bitumen Membrane", "Waterproofing & Damp Proofing",
            "Fascia, Soffit & Guttering", "Roof Repair & Re-Roofing",
            "Ridge & Hip Capping", "Roof Truss Erection Support",
            "Insulation & Vapour Barrier", "Roof Safety & Rigging",
        ],
        "jobs": [
            {
                "title": "Metal Roof Sheet Installer — 50-Unit Estate (Ogun)",
                "description": (
                    "Fix Colorcoat / Alumasc long-run steel roof sheets on 50 terrace "
                    "houses in a new estate in Ifo, Ogun. Trusses already erected; "
                    "purlin fixing, sheeting, ridge capping, and guttering included. "
                    "Tools and safety harnesses provided."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 1_000_000, "pay_max": 1_500_000,
                "state": "ogun", "lga": "Ifo", "slots": 6,
            },
            {
                "title": "Waterproofing Specialist — Flat Roofs (Lagos Commercial)",
                "description": (
                    "Apply torch-on bituminous membrane waterproofing to flat roofs "
                    "of 5 commercial buildings across Lagos Island. Surface preparation, "
                    "primer, and 2-layer torch-on system. Materials supplied. "
                    "10-year NDT bond warranty required."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 600_000, "pay_max": 950_000,
                "state": "lagos", "lga": "Lagos Island", "slots": 3,
            },
            {
                "title": "Roof Repair & Leak Remediation — Property Manager (Abuja)",
                "description": (
                    "Carry out reactive and scheduled roof repairs for a property "
                    "management company with 80 buildings in Abuja. Works include "
                    "re-bedding ridge tiles, replacing broken sheets, and sealing "
                    "skylights. Company van available; on-call rosters."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 90_000, "pay_max": 140_000,
                "state": "fct", "lga": "Garki", "slots": 2,
            },
            {
                "title": "Concrete Tile Roofer — Church Complex (Enugu)",
                "description": (
                    "Lay sand-faced concrete roof tiles on a large church complex in "
                    "Enugu. Roof area approx. 2,500 m². Battens and felt underlay "
                    "installed; tiling, ridge, hip, and valley work required. "
                    "Scaffolding on site."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 900_000, "pay_max": 1_400_000,
                "state": "enugu", "lga": "Enugu North", "slots": 5,
            },
            {
                "title": "Fascia, Soffit & Guttering Installer — New Builds (PH)",
                "description": (
                    "Fit uPVC fascia boards, soffits, and half-round guttering with "
                    "downpipes on 30 new houses in Port Harcourt. Materials delivered "
                    "to site. Must have own ladders, saws, and mitring equipment. "
                    "Measured rate per linear metre."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 400_000, "pay_max": 650_000,
                "state": "rivers", "lga": "Port Harcourt", "slots": 3,
            },
            {
                "title": "Insulation & Vapour Barrier Installer — Warehouse (Kano)",
                "description": (
                    "Fit 100 mm rock wool insulation blanket and foil vapour barrier "
                    "beneath the metal roof of a 5,000 m² cold storage warehouse in "
                    "Kano. Scissor-lift and harness required; PPE provided by client."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 700_000, "pay_max": 1_100_000,
                "state": "kano", "lga": "Kano Municipal", "slots": 4,
            },
            {
                "title": "Re-Roofing Contractor — Old Estate Renovation (Lagos)",
                "description": (
                    "Strip and replace ageing asbestos-cement roof sheets on 20 "
                    "old bungalows in a Lagos estate with new long-span aluminium sheets. "
                    "Asbestos removal must comply with NESREA guidelines. "
                    "Full PPE and disposal bags provided by estate management."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 700_000, "pay_max": 1_100_000,
                "state": "lagos", "lga": "Surulere", "slots": 4,
            },
        ],
    },

    # ── 16. SECURITY SYSTEMS INSTALLER ───────────────────────────────────────
    {
        "name": "Security Systems Installer",
        "slug": "security-installer",
        "icon_class":      "fas fa-shield-alt",
        "display_order":   15,
        "clip_context_text": "security systems installer CCTV alarm access control Nigeria",
        "description": (
            "Professional installers of CCTV, intruder alarms, electric fencing, "
            "access control, and integrated security systems for homes and businesses."
        ),
        "skills": [
            "IP CCTV & NVR Installation", "Intruder Alarm Systems",
            "Electric Fence Installation", "Access Control & Biometrics",
            "Video Intercom Systems", "Perimeter Detection",
            "Structured Cabling (Cat6/Fibre)", "ANPR & Barrier Systems",
            "Remote Monitoring Setup", "Security System Commissioning",
        ],
        "jobs": [
            {
                "title": "CCTV & Alarm Installer — Residential Estate (Lekki)",
                "description": (
                    "Install Hikvision IP CCTV cameras, NVR, and perimeter PIR alarm "
                    "systems across a 200-home estate in Lekki Phase 2. Structured "
                    "Cat6 cabling from gatehouse to each villa. Commission central "
                    "monitoring station. 12-month maintenance included."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 1_500_000, "pay_max": 2_500_000,
                "state": "lagos", "lga": "Lekki", "slots": 3,
            },
            {
                "title": "Electric Fence Installer — Factory Perimeter (Lagos)",
                "description": (
                    "Install a 2 km electric fence perimeter with energiser, warning "
                    "signs, and zone alarm panel for a manufacturing site in Ikorodu. "
                    "Integration with existing guard gatehouse and CCTV system. "
                    "Energetics or Nemtek product experience preferred."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 700_000, "pay_max": 1_100_000,
                "state": "lagos", "lga": "Ikorodu", "slots": 2,
            },
            {
                "title": "Access Control & Biometric Installer — Bank Branches (PH)",
                "description": (
                    "Deploy ZKTeco biometric access control, door controllers, and "
                    "electric bolt locks across 10 bank branch offices in Port Harcourt. "
                    "Include staff enrolment and admin training. "
                    "Banking sector security experience an advantage."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 1_000_000, "pay_max": 1_600_000,
                "state": "rivers", "lga": "Port Harcourt", "slots": 2,
            },
            {
                "title": "Security Systems Technician — Hotel (Abuja)",
                "description": (
                    "Maintain and troubleshoot the integrated security system (CCTV, "
                    "access control, fire alarm, video intercom) at a 180-room hotel "
                    "in Abuja. On-call for faults; planned maintenance visits monthly. "
                    "Full system documentation provided."
                ),
                "job_type": Job.JobType.PART_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 80_000, "pay_max": 130_000,
                "state": "fct", "lga": "Central Area", "slots": 1,
            },
            {
                "title": "ANPR & Barrier Installer — Shopping Mall Car Park (Lagos)",
                "description": (
                    "Supply and install ANPR cameras, boom barriers, ticketing terminals, "
                    "and LPR server software at a 500-space mall car park in Ikeja. "
                    "Integration with payment system and security desk. "
                    "ANPR/LPR installation experience essential."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 2_000_000, "pay_max": 3_500_000,
                "state": "lagos", "lga": "Ikeja", "slots": 1,
            },
            {
                "title": "Fibre Optic & Structured Cabling Engineer — Corporate Office",
                "description": (
                    "Design and install Cat6A structured cabling and OM3 multimode "
                    "fibre backbone for a 5-floor corporate campus in Victoria Island. "
                    "Includes patch panel termination, rack build, and end-to-end testing. "
                    "Fluke certification preferred."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 1_200_000, "pay_max": 1_800_000,
                "state": "lagos", "lga": "Victoria Island", "slots": 2,
            },
            {
                "title": "Perimeter Detection Installer — University Campus (Ibadan)",
                "description": (
                    "Install microwave perimeter detection sensors, PTZ tracking cameras, "
                    "and central alarm software across a 3 km university perimeter wall "
                    "in Ibadan. Must co-ordinate with campus security team and IT. "
                    "6-week installation project."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 1_800_000, "pay_max": 2_800_000,
                "state": "oyo", "lga": "Ibadan North", "slots": 2,
            },
        ],
    },

    # ── 17. CATERER / CHEF ────────────────────────────────────────────────────
    {
        "name": "Caterer",
        "slug": "caterer",
        "icon_class":      "fas fa-utensils",
        "display_order":   16,
        "clip_context_text": "caterer chef cook events catering Nigeria",
        "description": (
            "Professional caterers and chefs for events, corporate catering, "
            "restaurants, and institutional feeding programmes across Nigeria."
        ),
        "skills": [
            "Nigerian Cuisine & Local Dishes", "Continental & International Cuisine",
            "Event & Buffet Catering", "Pastry & Confectionery",
            "Institutional / Staff Canteen", "Food Safety & Hygiene (NAFDAC)",
            "Menu Planning & Costing", "Outdoor & On-Site Cooking",
            "Cake Decorating & Baking", "Kitchen Management",
        ],
        "jobs": [
            {
                "title": "Head Chef — Upscale Restaurant (Lagos)",
                "description": (
                    "Lead the kitchen team at a contemporary Nigerian fine-dining "
                    "restaurant on Victoria Island. Create seasonal menus, manage "
                    "food cost and wastage, and mentor junior cooks. "
                    "Minimum 5 years experience in a senior kitchen role."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 250_000, "pay_max": 400_000,
                "state": "lagos", "lga": "Victoria Island", "slots": 1,
            },
            {
                "title": "Event Caterer — Wedding & Party Catering (Lagos)",
                "description": (
                    "Provide full outdoor catering service (cooking, food display, "
                    "serving staff) for weddings and social events in Lagos. "
                    "Events booked through our platform; 48-hour advance notice "
                    "standard. Own equipment (pots, gas, chafers) required."
                ),
                "job_type": Job.JobType.PART_TIME,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 150_000, "pay_max": 500_000,
                "state": "lagos", "lga": "Ikeja", "slots": 10,
            },
            {
                "title": "Staff Canteen Cook — Oil & Gas Facility (Port Harcourt)",
                "description": (
                    "Cook daily breakfast, lunch, and dinner for 200 staff at an oil "
                    "& gas base camp in Trans-Amadi, Port Harcourt. Accommodation "
                    "available. NAFDAC food handler certification required. "
                    "Experience with bulk cooking essential."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 90_000, "pay_max": 140_000,
                "state": "rivers", "lga": "Port Harcourt", "slots": 3,
            },
            {
                "title": "Pastry Chef & Baker — Artisan Bakery (Abuja)",
                "description": (
                    "Produce croissants, sourdough, celebration cakes, and artisan "
                    "pastries for a busy bakery café in Maitama, Abuja. Early morning "
                    "start (4 AM). Must be confident with laminated doughs and "
                    "multi-tiered cake decoration."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 120_000, "pay_max": 180_000,
                "state": "fct", "lga": "Maitama", "slots": 2,
            },
            {
                "title": "School Feeding Programme Cook — Kaduna State",
                "description": (
                    "Cook balanced midday meals for 500 primary school pupils under "
                    "the Federal Government School Feeding Programme in Kaduna. "
                    "Community-based role; cooking takes place at the school. "
                    "Must have WAEC home economics or equivalent qualification."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 40_000, "pay_max": 60_000,
                "state": "kaduna", "lga": "Kaduna North", "slots": 5,
            },
            {
                "title": "Corporate Caterer — Office Lunch Service (Abuja)",
                "description": (
                    "Provide daily hot lunch boxes for 80 staff at a corporate office "
                    "in Garki, Abuja. Menu agreed weekly; delivery by 12:30 PM each day. "
                    "Own kitchen or commercial kitchen rental required. "
                    "NAFDAC registration preferred."
                ),
                "job_type": Job.JobType.PART_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 150_000, "pay_max": 250_000,
                "state": "fct", "lga": "Garki", "slots": 1,
            },
            {
                "title": "Continental Chef — Expatriate Camp (Delta State)",
                "description": (
                    "Prepare continental and international meals for 30 expatriate "
                    "staff at an oil company camp near Warri. Breakfast, lunch, and "
                    "dinner daily. Camp accommodation and full board provided. "
                    "Experience cooking European and Asian cuisine required."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 200_000, "pay_max": 320_000,
                "state": "delta", "lga": "Warri South", "slots": 1,
            },
        ],
    },
]


# ──────────────────────────────────────────────────────────────────────────────
#  MANAGEMENT COMMAND
# ──────────────────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = (
        "Seeds job listings across 17 Nigerian trade categories "
        "(120 jobs total: 8 for Electrician, 7 for each other category). "
        "Idempotent — safe to re-run."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--only",
            metavar="SLUGS",
            default="",
            help=(
                "Comma-separated list of category slugs to process. "
                "Omit to process all 17 categories (120 jobs total)."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be created without writing to the database.",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help=(
                "Delete all jobs owned by the seed employer before re-seeding. "
                "Does NOT delete trade categories or skills."
            ),
        )

    def handle(self, *args, **options):
        dry_run     = options["dry_run"]
        only_slugs  = {s.strip() for s in options["only"].split(",") if s.strip()}

        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n🔧  TradeLink NG — seed_category_jobs (120 jobs target)\n"
        ))

        if dry_run:
            self.stdout.write(self.style.WARNING("  [DRY RUN] — nothing will be written.\n"))

        # ── Seed employer ────────────────────────────────────────────────────
        _, employer = get_or_create_seed_employer()
        self.stdout.write(
            f"  Seed employer: {employer.company_name} (pk={employer.pk})\n"
        )

        # ── Optional clear ───────────────────────────────────────────────────
        if options["clear"] and not dry_run:
            self._clear_seed_jobs(employer)

        # ── Seed each category ───────────────────────────────────────────────
        total_cats_new = 0
        total_skills_new = 0
        total_jobs_new = 0

        with transaction.atomic():
            for trade_data in TRADE_CATEGORIES:
                if only_slugs and trade_data["slug"] not in only_slugs:
                    continue

                cats_new, skills_new, jobs_new = self._seed_trade(
                    trade_data, employer, dry_run
                )
                total_cats_new   += cats_new
                total_skills_new += skills_new
                total_jobs_new   += jobs_new

        # ── Summary ──────────────────────────────────────────────────────────
        if dry_run:
            self.stdout.write(self.style.WARNING(
                f"\n  [DRY RUN] Would create: "
                f"{total_cats_new} new categories · "
                f"{total_skills_new} new skills · "
                f"{total_jobs_new} new jobs.\n"
                "  Re-run without --dry-run to apply.\n"
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"\n✅  Done — "
                f"{total_cats_new} new categories · "
                f"{total_skills_new} new skills · "
                f"{total_jobs_new} new jobs created.\n"
            ))

    # ── Private helpers ───────────────────────────────────────────────────────

    def _seed_trade(self, trade_data: dict, employer: EmployerProfile, dry_run: bool):
        """
        Ensure the trade category, its skills, and its 7 jobs exist.
        Returns (cats_new, skills_new, jobs_new) counts.
        """
        slug = trade_data["slug"]

        # ── Trade Category ───────────────────────────────────────────────────
        if dry_run:
            cat_exists = TradeCategory.objects.filter(slug=slug).exists()
            cat_new = 0 if cat_exists else 1
            # We still need a real object for downstream logic in dry-run;
            # get or create temporarily within the atomic block (rolled back).
            cat, _ = TradeCategory.objects.get_or_create(
                slug=slug,
                defaults={
                    "name":              trade_data["name"],
                    "icon_class":        trade_data["icon_class"],
                    "display_order":     trade_data["display_order"],
                    "clip_context_text": trade_data["clip_context_text"],
                    "description":       trade_data["description"],
                    "is_active":         True,
                },
            )
        else:
            cat, cat_created = TradeCategory.objects.get_or_create(
                slug=slug,
                defaults={
                    "name":              trade_data["name"],
                    "icon_class":        trade_data["icon_class"],
                    "display_order":     trade_data["display_order"],
                    "clip_context_text": trade_data["clip_context_text"],
                    "description":       trade_data["description"],
                    "is_active":         True,
                },
            )
            cat_new = 1 if cat_created else 0

        label = "✚ new" if cat_new else "✔ exists"
        self.stdout.write(f"\n  [{label}] TradeCategory: {trade_data['name']}")

        # ── Skills ───────────────────────────────────────────────────────────
        skills_new = 0
        for skill_name in trade_data["skills"]:
            skill_slug = (
                skill_name.lower()
                .replace(" ", "-")
                .replace("&", "and")
                .replace("/", "-")
                .replace("(", "")
                .replace(")", "")
            )
            if not dry_run:
                _, created = Skill.objects.get_or_create(
                    category=cat,
                    slug=skill_slug,
                    defaults={"name": skill_name, "is_active": True},
                )
                if created:
                    skills_new += 1
            else:
                if not Skill.objects.filter(category=cat, slug=skill_slug).exists():
                    skills_new += 1

        self.stdout.write(
            f"     Skills: {skills_new} new / {len(trade_data['skills'])} total"
        )

        # ── Jobs ─────────────────────────────────────────────────────────────
        jobs_new = 0
        deadline_base = date.today() + timedelta(days=30)

        for job_data in trade_data["jobs"]:  # exactly 7 per category
            exists = Job.objects.filter(
                employer=employer,
                trade_category=cat,
                title=job_data["title"],
            ).exists()

            if exists:
                self.stdout.write(
                    f"     ↳ skip (exists): {job_data['title'][:60]}"
                )
                continue

            deadline = deadline_base + timedelta(days=random.randint(0, 30))

            if not dry_run:
                Job.objects.create(
                    employer=employer,
                    trade_category=cat,
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
                    status=Job.Status.ACTIVE,
                )
                self.stdout.write(
                    f"     ✚ created: {job_data['title'][:60]}"
                )
            else:
                self.stdout.write(
                    f"     [dry-run] would create: {job_data['title'][:60]}"
                )

            jobs_new += 1

        self.stdout.write(
            f"     Jobs: {jobs_new} new / {len(trade_data['jobs'])} total"
        )
        return cat_new, skills_new, jobs_new

    def _clear_seed_jobs(self, employer: EmployerProfile):
        """Delete all Job rows owned by the seed employer."""
        self.stdout.write(self.style.WARNING(
            "\n⚠️   --clear flag: removing existing seed jobs …"
        ))
        deleted, _ = Job.objects.filter(employer=employer).delete()
        self.stdout.write(f"  Deleted {deleted} job(s).\n")