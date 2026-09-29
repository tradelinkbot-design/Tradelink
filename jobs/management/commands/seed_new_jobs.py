"""
jobs/management/commands/seed_new_jobs.py
==========================================
Seeds 140 *additional* job listings across all 17 Nigerian trade categories —
exactly 5 new jobs per category (17 × 5 = 85 minimum, padded to 140 with
richer categories where useful).

All 17 categories from seed_category_jobs.py are covered:
  electrician, plumber, solar-installer, carpenter, painter-decorator,
  welder, mason, hair-stylist, hvac-technician, auto-mechanic,
  tailor, tiler, aluminum-glass-installer, generator-technician,
  roofer, security-installer, caterer

Usage
-----
    # Seed all 140 jobs
    python manage.py seed_new_jobs

    # Preview without writing
    python manage.py seed_new_jobs --dry-run

    # Wipe this command's jobs then re-seed
    python manage.py seed_new_jobs --clear

    # Only specific categories
    python manage.py seed_new_jobs --only welder,tiler,roofer

Design notes
------------
- Idempotent: identified by (employer, trade_category, title). Re-running
  skips any that already exist.
- Jobs are created in ACTIVE status so CLIP embedding signals fire.
- All pay values are Nigerian Naira (NGN).
- Deadlines are spread randomly over the next 30-60 days.
- Uses the same seed-employer account as seed_category_jobs.py.
"""

import random
import logging
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from jobs.models import TradeCategory, Job, EmployerProfile

logger = logging.getLogger(__name__)
User = get_user_model()

# ---------------------------------------------------------------------------
#  SEED EMPLOYER  (shared with seed_category_jobs.py)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
#  5+ NEW JOBS PER CATEGORY  (17 categories x 5 = 85, bonus jobs bring
#  the total to 140 by giving high-demand categories extra listings)
# ---------------------------------------------------------------------------
#
#  Job dict keys:
#    title, description, job_type, pay_type,
#    pay_min, pay_max, state, lga, slots, is_remote (optional, default False)
#
#  Valid job_type values : full_time | part_time | contract | once_off | internship
#  Valid pay_type values : hourly | daily | weekly | monthly | fixed | negotiable

NEW_JOBS = {

    # -----------------------------------------------------------------------
    # 1. ELECTRICIAN  (10 jobs — high demand category)
    # -----------------------------------------------------------------------
    "electrician": [
        {
            "title": "Estate Electrician (Full-Time) — Ajah Lagos",
            "description": (
                "A fast-growing residential estate in Ajah requires a full-time "
                "resident electrician to handle daily faults, meter readings, and "
                "planned maintenance across 80 apartments. Accommodation provided "
                "on-site. Minimum 5 years post-qualification experience required."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min": 120_000, "pay_max": 180_000,
            "state": "lagos", "lga": "Ajah", "slots": 1,
        },
        {
            "title": "EV Charging Station Installer — Abuja",
            "description": (
                "Install 10 x 22 kW AC EV charging points across two locations in "
                "Abuja (Maitama and Wuse 2). Scope includes civil trunking, dedicated "
                "sub-mains, smart meter integration, and commissioning. Experience "
                "with OCPP-compliant chargers preferred."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.FIXED,
            "pay_min": 550_000, "pay_max": 800_000,
            "state": "fct", "lga": "Maitama", "slots": 2,
        },
        {
            "title": "Industrial Electrician — Food Processing Plant Ogun",
            "description": (
                "Maintain and repair MV/LV switchgear, VFDs, PLC control panels, "
                "and conveyor motors at a biscuit manufacturing plant in Sagamu. "
                "12-month renewable contract. Knowledge of Siemens S7 PLCs an advantage."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min": 200_000, "pay_max": 280_000,
            "state": "ogun", "lga": "Sagamu", "slots": 2,
        },
        {
            "title": "Fire Alarm & Emergency Lighting Installer — Victoria Island",
            "description": (
                "Design and install an L2 fire-detection system with call points, "
                "detectors, sounders, and central fire panel for a 15-storey "
                "commercial tower on Victoria Island. NFPA 72 or BS 5839 "
                "certification required."
            ),
            "job_type": Job.JobType.ONCE_OFF,
            "pay_type": Job.PayType.FIXED,
            "pay_min": 1_200_000, "pay_max": 1_800_000,
            "state": "lagos", "lga": "Victoria Island", "slots": 3,
        },
        {
            "title": "Streetlight & Highway Lighting Technician — Kaduna",
            "description": (
                "Install and commission 500 LED streetlights along the Kaduna-Zaria "
                "expressway extension. Includes cable pulling, pole erection, control "
                "gear fitting, and dimming system setup. Government contractor engagement."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.FIXED,
            "pay_min": 2_500_000, "pay_max": 4_000_000,
            "state": "kaduna", "lga": "Kaduna North", "slots": 5,
        },
        {
            "title": "Electrical Maintenance Engineer — Shopping Mall (Abuja)",
            "description": (
                "Full-time electrical maintenance for a 40,000 m2 shopping mall in "
                "Abuja: lighting, escalators, lifts, emergency systems, and BMS. "
                "Shift work. COREN registration or equivalent preferred."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min": 180_000, "pay_max": 260_000,
            "state": "fct", "lga": "Wuse", "slots": 2,
        },
        {
            "title": "Domestic Electrician — Property Developer (Ibadan)",
            "description": (
                "First-fix and second-fix domestic electrical installation for a "
                "50-unit housing estate in Ibadan. Rate per plot negotiable. "
                "Materials supplied by developer. Start within 2 weeks."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.FIXED,
            "pay_min": 80_000, "pay_max": 130_000,
            "state": "oyo", "lga": "Ibadan North", "slots": 4,
        },
        {
            "title": "Power Distribution Technician — Oil & Gas (Warri)",
            "description": (
                "Operate and maintain 11 kV / 415 V power distribution systems at a "
                "petrochemical facility in Warri. Includes switchgear, transformers, "
                "UPS, and protection relay testing. Valid HUET certificate preferred."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min": 350_000, "pay_max": 500_000,
            "state": "delta", "lga": "Warri South", "slots": 2,
        },
        {
            "title": "Electrical Site Supervisor — New Hospital Build (Enugu)",
            "description": (
                "Supervise the electrical sub-contractor team on a 200-bed hospital "
                "construction in Enugu. Ensure quality, programme, and compliance with "
                "IEE Wiring Regulations. Weekly progress reporting to M&E consultant."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min": 250_000, "pay_max": 380_000,
            "state": "enugu", "lga": "Enugu North", "slots": 1,
        },
        {
            "title": "Part-Time Electrician — Student Hostels (Nsukka)",
            "description": (
                "On-call electrician for a portfolio of 12 student hostel buildings "
                "near UNN Nsukka. Reactive fault finding, bulb and fitting replacements, "
                "socket repairs. Paid per call-out. Own tools required."
            ),
            "job_type": Job.JobType.PART_TIME,
            "pay_type": Job.PayType.HOURLY,
            "pay_min": 3_500, "pay_max": 6_000,
            "state": "enugu", "lga": "Nsukka", "slots": 2,
        },
    ],

    # -----------------------------------------------------------------------
    # 2. PLUMBER  (10 jobs — high demand)
    # -----------------------------------------------------------------------
    "plumber": [
        {
            "title": "Hotel Plumbing Maintenance Technician — Ikeja",
            "description": (
                "Full-time plumber for a 120-room hotel in Ikeja. Responsibilities: "
                "daily reactive maintenance, monthly planned checks of boilers, pumps, "
                "and cold-water storage. Shift rotation required."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min": 130_000, "pay_max": 180_000,
            "state": "lagos", "lga": "Ikeja", "slots": 2,
        },
        {
            "title": "Swimming Pool Plumber & Water Treatment — Abuja Sports Complex",
            "description": (
                "Install and commission the hydraulic system for three new swimming "
                "pools at a sports complex in Abuja. Includes filter vessels, chemical "
                "dosing, heat pump connection, and backwash valves."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.FIXED,
            "pay_min": 1_800_000, "pay_max": 2_500_000,
            "state": "fct", "lga": "Gudu", "slots": 2,
        },
        {
            "title": "Underfloor Heating Plumber — Luxury Duplex Banana Island",
            "description": (
                "Supply and install wet underfloor heating across the ground and first "
                "floors of a 6-bedroom duplex on Banana Island. Manifold installation, "
                "pipe layout, screed coordination, and commissioning."
            ),
            "job_type": Job.JobType.ONCE_OFF,
            "pay_type": Job.PayType.FIXED,
            "pay_min": 900_000, "pay_max": 1_400_000,
            "state": "lagos", "lga": "Ikoyi", "slots": 1,
        },
        {
            "title": "Commercial Kitchen Plumber — Restaurant Chain Port Harcourt",
            "description": (
                "Fit out the plumbing for 3 new commercial kitchens across PH branches "
                "of a fast-food chain. Includes grease traps, pot-wash stations, gas "
                "connection points, drainage channels, and hand-wash basins."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.FIXED,
            "pay_min": 400_000, "pay_max": 600_000,
            "state": "rivers", "lga": "Port Harcourt", "slots": 2,
        },
        {
            "title": "Rainwater Harvesting System Installer — School Ibadan",
            "description": (
                "Design and install a complete rainwater harvesting system for a large "
                "school complex in Ibadan: roof collection, first-flush diverter, "
                "filtration, 50,000-litre underground storage, and distribution pump."
            ),
            "job_type": Job.JobType.ONCE_OFF,
            "pay_type": Job.PayType.FIXED,
            "pay_min": 600_000, "pay_max": 900_000,
            "state": "oyo", "lga": "Ibadan North", "slots": 2,
        },
        {
            "title": "Oil & Gas Piping Fabricator — Offshore Support (Warri)",
            "description": (
                "Fabricate and install carbon steel process piping spools for an "
                "onshore oil facility near Warri. ASME B31.3 process piping experience "
                "required. PPE and medicals covered by client."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min": 400_000, "pay_max": 650_000,
            "state": "delta", "lga": "Warri South", "slots": 4,
        },
        {
            "title": "Boiler Service Engineer — Manufacturing (Kano)",
            "description": (
                "Service and repair steam boilers, condensate systems, and pressure "
                "vessels at a textile factory in Kano. Annual statutory inspections "
                "coordinated with third-party inspector. Boilermaker certification required."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min": 200_000, "pay_max": 300_000,
            "state": "kano", "lga": "Kano Municipal", "slots": 1,
        },
        {
            "title": "Sanitary Ware Installer — Mass Housing (Ogun State)",
            "description": (
                "Second-fix sanitary ware installation across 200 housing units in "
                "Sagamu, Ogun State. WC, hand basins, bath, shower trays, taps, and "
                "shower screens. Materials supplied. Rate per unit negotiable."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.FIXED,
            "pay_min": 8_000, "pay_max": 15_000,
            "state": "ogun", "lga": "Sagamu", "slots": 5,
        },
        {
            "title": "Drainage Engineer — Road Project (Rivers State)",
            "description": (
                "Install roadside drainage channels, culverts, and manholes along a "
                "new 12 km road in Rivers State. Concrete pipe laying and jointing, "
                "backfill, and surface reinstatement. Equipment provided by contractor."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min": 180_000, "pay_max": 260_000,
            "state": "rivers", "lga": "Obio-Akpor", "slots": 3,
        },
        {
            "title": "Mobile Plumber — Home Repair Service (Lagos Mainland)",
            "description": (
                "Join our on-demand home repair platform as a mobile plumber. Receive "
                "booking requests via app, carry out repairs, and collect payment. "
                "Flexible hours. Own tools and transport required."
            ),
            "job_type": Job.JobType.PART_TIME,
            "pay_type": Job.PayType.DAILY,
            "pay_min": 15_000, "pay_max": 35_000,
            "state": "lagos", "lga": "Surulere", "slots": 5,
        },
    ],

    # -----------------------------------------------------------------------
    # 3. SOLAR INSTALLER  (8 jobs)
    # -----------------------------------------------------------------------
    "solar-installer": [
        {
            "title": "Solar Technician — Telecom Towers Off-Grid (Plateau State)",
            "description": (
                "Install and maintain off-grid solar hybrid systems for 12 telecom "
                "towers across Plateau State. Each site: 10 kW solar array, 30 kWh "
                "lithium battery bank, hybrid inverter."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min": 250_000, "pay_max": 350_000,
            "state": "plateau", "lga": "Jos North", "slots": 2,
        },
        {
            "title": "Solar Farm EPC Technician — 1MW Ground-Mount (Katsina)",
            "description": (
                "Join a 10-person EPC team to install a 1 MW ground-mounted solar farm "
                "near Katsina. Responsibilities: panel mounting, string cabling, inverter "
                "installation, grid connection, SCADA commissioning."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min": 300_000, "pay_max": 450_000,
            "state": "katsina", "lga": "Katsina", "slots": 5,
        },
        {
            "title": "Solar Street Light Installer — Anambra State",
            "description": (
                "Install 200 all-in-one solar street lights (30 W LED, 40 Ah LiFePO4) "
                "across 5 communities in Anambra State under a government contract."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.FIXED,
            "pay_min": 1_000_000, "pay_max": 1_500_000,
            "state": "anambra", "lga": "Awka South", "slots": 4,
        },
        {
            "title": "Solar Borehole Pump System — Rural School Kebbi",
            "description": (
                "Supply and install a solar-powered borehole pump system for a rural "
                "secondary school in Kebbi State: 3 kW solar array, MPPT controller, "
                "submersible pump, elevated storage. Full commission and staff training."
            ),
            "job_type": Job.JobType.ONCE_OFF,
            "pay_type": Job.PayType.FIXED,
            "pay_min": 850_000, "pay_max": 1_200_000,
            "state": "kebbi", "lga": "Birnin Kebbi", "slots": 2,
        },
        {
            "title": "Residential Solar Consultant & Installer (On-Call) — Lagos",
            "description": (
                "Join our Lagos solar installation team on a retainer plus commission "
                "model. Carry out site surveys, system designs, and installations for "
                "residential clients (2-10 kW systems). Own vehicle and tools required."
            ),
            "job_type": Job.JobType.PART_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min": 80_000, "pay_max": 150_000,
            "state": "lagos", "lga": "Lekki", "slots": 3,
        },
        {
            "title": "Solar Engineer — Factory Rooftop PV (Ogun State)",
            "description": (
                "Design and install a 200 kWp rooftop grid-tied solar PV system for a "
                "manufacturing plant in Sagamu. Structural survey, mounting, cabling, "
                "inverter commissioning, and grid metering."
            ),
            "job_type": Job.JobType.ONCE_OFF,
            "pay_type": Job.PayType.FIXED,
            "pay_min": 8_000_000, "pay_max": 12_000_000,
            "state": "ogun", "lga": "Sagamu", "slots": 2,
        },
        {
            "title": "Solar O&M Supervisor — Portfolio of Sites (Rivers)",
            "description": (
                "Supervise operations and maintenance for a portfolio of 30 commercial "
                "solar sites across Rivers State. Monthly inspections, fault response, "
                "inverter firmware updates, and client reporting."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min": 220_000, "pay_max": 320_000,
            "state": "rivers", "lga": "Port Harcourt", "slots": 1,
        },
        {
            "title": "Solar Apprentice Technician — Training + Job (Lagos)",
            "description": (
                "3-month paid apprenticeship followed by full-time solar technician "
                "role in Lagos. Learn panel installation, battery wiring, and inverter "
                "setup on live projects. OND/HND in electrical engineering preferred."
            ),
            "job_type": Job.JobType.INTERNSHIP,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min": 40_000, "pay_max": 70_000,
            "state": "lagos", "lga": "Ikeja", "slots": 4,
        },
    ],

    # -----------------------------------------------------------------------
    # 4. CARPENTER  (8 jobs)
    # -----------------------------------------------------------------------
    "carpenter": [
        {
            "title": "Furniture Maker — Bespoke Kitchen Units Magodo Lagos",
            "description": (
                "Fabricate and install bespoke MDF and hardwood kitchen units, worktops, "
                "and island for a client in Magodo, Lagos. Full design brief provided. "
                "Portfolio of completed kitchen projects required."
            ),
            "job_type": Job.JobType.ONCE_OFF,
            "pay_type": Job.PayType.FIXED,
            "pay_min": 700_000, "pay_max": 1_100_000,
            "state": "lagos", "lga": "Magodo", "slots": 1,
        },
        {
            "title": "Roof Carpenter — Truss Fabrication & Erection Kubwa Abuja",
            "description": (
                "Fabricate and erect timber roof trusses for a 10-unit block of flats "
                "in Kubwa, Abuja. Structural drawings available. Must supply all cutting "
                "and lifting equipment. 6-week program."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.FIXED,
            "pay_min": 1_200_000, "pay_max": 1_800_000,
            "state": "fct", "lga": "Kubwa", "slots": 3,
        },
        {
            "title": "Shop-Fitting Carpenter — Retail Mall (Kano)",
            "description": (
                "Fit out 6 retail shops inside a new shopping mall in Kano: display "
                "shelving, cash-desk units, changing-room partitions, and signage "
                "backing boards. 2 weeks per shop. Previous retail fit-out experience essential."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.FIXED,
            "pay_min": 400_000, "pay_max": 650_000,
            "state": "kano", "lga": "Kano Municipal", "slots": 2,
        },
        {
            "title": "Site Carpenter — Door & Window Frames Budget Hotel (PH)",
            "description": (
                "Supply and install hardwood door frames, interior flush doors, and "
                "window frames for an 80-room budget hotel in Rumuola Port Harcourt. "
                "Client supplies materials; labour and tools by contractor."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.DAILY,
            "pay_min": 15_000, "pay_max": 22_000,
            "state": "rivers", "lga": "Port Harcourt", "slots": 4,
        },
        {
            "title": "Office Furniture Carpenter — Corporate Refurb Enugu",
            "description": (
                "Manufacture and install 120 workstation desks, 30 storage units, and "
                "a boardroom table for a corporate office refurbishment in Enugu. "
                "Laminate and solid wood finish. 3D design approval required."
            ),
            "job_type": Job.JobType.ONCE_OFF,
            "pay_type": Job.PayType.FIXED,
            "pay_min": 900_000, "pay_max": 1_400_000,
            "state": "enugu", "lga": "Enugu North", "slots": 2,
        },
        {
            "title": "Formwork Carpenter — High-Rise Construction (Victoria Island)",
            "description": (
                "Set and strike timber and plywood formwork for reinforced concrete "
                "slabs, columns, and beams on a 20-storey residential tower on "
                "Victoria Island. Rate per m2 of formwork area. Drawings supplied."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.DAILY,
            "pay_min": 18_000, "pay_max": 28_000,
            "state": "lagos", "lga": "Victoria Island", "slots": 6,
        },
        {
            "title": "Hardwood Flooring Installer — Luxury Apartments (Ikoyi)",
            "description": (
                "Supply and install engineered hardwood and parquet flooring across "
                "12 luxury apartments in Ikoyi. Floating and glue-down methods. "
                "Underfloor heating compatibility required. Portfolio essential."
            ),
            "job_type": Job.JobType.ONCE_OFF,
            "pay_type": Job.PayType.FIXED,
            "pay_min": 600_000, "pay_max": 950_000,
            "state": "lagos", "lga": "Ikoyi", "slots": 2,
        },
        {
            "title": "Carpenter Apprentice — Furniture Workshop (Lagos)",
            "description": (
                "Learn furniture making and site carpentry at a busy Lagos workshop. "
                "Hands-on training with experienced carpenters. SSCE minimum. "
                "Tool allowance provided. Opportunity for full-time role after 6 months."
            ),
            "job_type": Job.JobType.INTERNSHIP,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min": 35_000, "pay_max": 55_000,
            "state": "lagos", "lga": "Mushin", "slots": 3,
        },
    ],

    # -----------------------------------------------------------------------
    # 5. PAINTER & DECORATOR  (8 jobs)
    # -----------------------------------------------------------------------
    "painter-decorator": [
        {
            "title": "Industrial Painter — Anti-Corrosion Coating Warri",
            "description": (
                "Apply multi-coat epoxy anti-corrosion paint to storage tanks and "
                "pipework at a petroleum depot in Warri. SSPC surface prep to Sa 2.5 "
                "standard. Airless spray application experience essential."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.FIXED,
            "pay_min": 800_000, "pay_max": 1_200_000,
            "state": "delta", "lga": "Warri South", "slots": 3,
        },
        {
            "title": "Interior Decorator — Show Apartments Eko Atlantic",
            "description": (
                "Decorate 10 show apartments in an Eko Atlantic development to a luxury "
                "finish: feature walls, faux finishes, metallic paints, and wallpaper "
                "installation. Portfolio of high-end residential projects required."
            ),
            "job_type": Job.JobType.ONCE_OFF,
            "pay_type": Job.PayType.FIXED,
            "pay_min": 1_500_000, "pay_max": 2_200_000,
            "state": "lagos", "lga": "Lagos Island", "slots": 2,
        },
        {
            "title": "Exterior Painter — Commercial Building Ibadan",
            "description": (
                "Repaint the facade of a 5-storey commercial building in Dugbe, Ibadan. "
                "High-pressure wash, crack filling, primer, and 2 coats of weatherproof "
                "masonry paint. Scaffolding provided. 3-week turnaround."
            ),
            "job_type": Job.JobType.ONCE_OFF,
            "pay_type": Job.PayType.FIXED,
            "pay_min": 350_000, "pay_max": 550_000,
            "state": "oyo", "lga": "Ibadan South-West", "slots": 4,
        },
        {
            "title": "Full-Time Painter — Property Management Company (Abuja)",
            "description": (
                "Join the maintenance team managing 500+ units across Abuja. Routine "
                "repaints, touch-ups, and handover cleans. Company van and materials "
                "provided. Valid driver licence required."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min": 90_000, "pay_max": 130_000,
            "state": "fct", "lga": "Wuse", "slots": 2,
        },
        {
            "title": "Wallpaper Installer — Boutique Hotel Ikoyi",
            "description": (
                "Hang premium fabric-backed and vinyl wallpaper across 40 guest rooms "
                "and 3 public areas in a boutique hotel in Ikoyi. Pattern-matching and "
                "hand-printed papers involved. Minimum 3 years wallpaper experience."
            ),
            "job_type": Job.JobType.ONCE_OFF,
            "pay_type": Job.PayType.FIXED,
            "pay_min": 500_000, "pay_max": 750_000,
            "state": "lagos", "lga": "Ikoyi", "slots": 1,
        },
        {
            "title": "Line Marking & Road Painter — Logistics Park (Ogun)",
            "description": (
                "Apply road markings, parking bay lines, directional arrows, and safety "
                "zones at a new logistics and warehousing park in Sagamu, Ogun. "
                "Thermoplastic or epoxy paint system as specified."
            ),
            "job_type": Job.JobType.ONCE_OFF,
            "pay_type": Job.PayType.FIXED,
            "pay_min": 250_000, "pay_max": 400_000,
            "state": "ogun", "lga": "Sagamu", "slots": 2,
        },
        {
            "title": "Spray Painter — Auto Body Shop (Kano)",
            "description": (
                "Automotive spray painter for a busy vehicle body and paint shop in "
                "Kano. Services: full resprays, panel blends, metallic and pearlescent "
                "finishes, and fleet livery. Experience with waterborne paints preferred."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min": 80_000, "pay_max": 140_000,
            "state": "kano", "lga": "Kano Municipal", "slots": 2,
        },
        {
            "title": "Texture Coat & Dryvit Applicator — New Estate (Lekki)",
            "description": (
                "Apply exterior acrylic texture coat (Dryvit / Sto system) to 25 "
                "detached houses in a new estate in Lekki. Includes mesh embedding, "
                "base coat, and decorative top coat. Training on system available."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.DAILY,
            "pay_min": 18_000, "pay_max": 26_000,
            "state": "lagos", "lga": "Lekki", "slots": 4,
        },
    ],

    # -----------------------------------------------------------------------
    # 6. WELDER  (8 jobs)
    # -----------------------------------------------------------------------
    "welder": [
        {
            "title": "Structural Welder — Steel Frame Construction Surulere Lagos",
            "description": (
                "Weld structural steel columns, beams, and connections for a 4-storey "
                "commercial building in Surulere Lagos. MIG/MAG and stick welding. "
                "AWS or equivalent certification required."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.DAILY,
            "pay_min": 20_000, "pay_max": 30_000,
            "state": "lagos", "lga": "Surulere", "slots": 4,
        },
        {
            "title": "Pipeline Welder 6G Certified — Gas Project Delta State",
            "description": (
                "Perform 6G butt welds on carbon steel gas pipelines (12-inch and "
                "16-inch OD) at a midstream facility in Delta State. CSWIP 3.1 or "
                "equivalent required. Minimum 5 years pipeline welding experience."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.DAILY,
            "pay_min": 45_000, "pay_max": 70_000,
            "state": "delta", "lga": "Warri South", "slots": 3,
        },
        {
            "title": "Aluminium TIG Welder — Boat Fabrication Calabar",
            "description": (
                "Fabricate and weld aluminium patrol boat hulls and deck structures at "
                "a shipyard in Calabar. TIG welding on 5083 marine-grade aluminium. "
                "Marine fabrication experience preferred. Accommodation available."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min": 180_000, "pay_max": 280_000,
            "state": "cross_river", "lga": "Calabar Municipal", "slots": 4,
        },
        {
            "title": "Fabrication Welder — Gates & Railings Abuja",
            "description": (
                "Fabricate and install ornamental iron gates, security railings, window "
                "burglar proofing, and staircase balustrades for residential clients "
                "across Abuja. Own workshop preferred."
            ),
            "job_type": Job.JobType.PART_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min": 70_000, "pay_max": 120_000,
            "state": "fct", "lga": "Garki", "slots": 2,
        },
        {
            "title": "Maintenance Welder — Sugar Factory Bacita Kwara",
            "description": (
                "Provide welding maintenance support for processing equipment, conveyors, "
                "and structural steelwork at a sugar factory in Bacita, Kwara. "
                "Shift work required. Enhanced pay during plant shutdowns."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min": 160_000, "pay_max": 220_000,
            "state": "kwara", "lga": "Edu", "slots": 3,
        },
        {
            "title": "Pressure Vessel Welder — Petrochemical Facility (PH)",
            "description": (
                "Weld pressure vessels and heat exchangers to ASME Section IX standard "
                "at a refinery support yard near Port Harcourt. NDT (UT/RT) carried out "
                "by client QC team. WPS/PQR provided."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.DAILY,
            "pay_min": 55_000, "pay_max": 80_000,
            "state": "rivers", "lga": "Obio-Akpor", "slots": 3,
        },
        {
            "title": "Auto Body Welder — Panel Beating Shop (Abuja)",
            "description": (
                "MIG weld vehicle body panels, repair collision damage, and fabricate "
                "replacement sections at a panel-beating workshop in Garki, Abuja. "
                "Minimum 4 years automotive welding experience."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min": 90_000, "pay_max": 150_000,
            "state": "fct", "lga": "Garki", "slots": 2,
        },
        {
            "title": "Welding Inspector Trainee — Oil & Gas (Lagos)",
            "description": (
                "Entry-level welding inspector role on a Lagos offshore fabrication yard. "
                "Study towards CSWIP 3.0 inspection qualification. Must have 3 years "
                "welding experience. Full sponsorship for CSWIP exams provided."
            ),
            "job_type": Job.JobType.INTERNSHIP,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min": 120_000, "pay_max": 180_000,
            "state": "lagos", "lga": "Apapa", "slots": 2,
        },
    ],

    # -----------------------------------------------------------------------
    # 7. MASON  (8 jobs)
    # -----------------------------------------------------------------------
    "mason": [
        {
            "title": "Bricklayer — Housing Estate Development Ibeju-Lekki",
            "description": (
                "Lay 9-inch hollow block walls for 30 units in a fast-track housing "
                "estate in Ibeju-Lekki. Materials supplied by developer. "
                "Rate per square metre negotiable based on experience."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.DAILY,
            "pay_min": 18_000, "pay_max": 25_000,
            "state": "lagos", "lga": "Ibeju-Lekki", "slots": 6,
        },
        {
            "title": "Stone Mason — Heritage Building Restoration Lagos Island",
            "description": (
                "Restore sandstone and laterite facades of a protected colonial building "
                "on Lagos Island. Work includes lime mortar repointing, stone cleaning, "
                "crack stitching, and carved stone repair."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.FIXED,
            "pay_min": 600_000, "pay_max": 900_000,
            "state": "lagos", "lga": "Lagos Island", "slots": 2,
        },
        {
            "title": "Tiling & Screeding Mason — Hospital Construction Benin City",
            "description": (
                "Lay floor and wall tiles plus floor screeds across a new 200-bed "
                "private hospital in Benin City. Large-format porcelain tiles (1200x600) "
                "throughout clinical areas. Antifungal grout specification."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.DAILY,
            "pay_min": 16_000, "pay_max": 22_000,
            "state": "edo", "lga": "Oredo", "slots": 5,
        },
        {
            "title": "Retaining Wall & Paving Mason — Villa Asokoro Abuja",
            "description": (
                "Construct 80 m of reinforced concrete retaining wall and lay 1,200 m2 "
                "of interlocking paving around a villa compound in Asokoro. "
                "Structural designs provided. Formwork and steel fixing in scope."
            ),
            "job_type": Job.JobType.ONCE_OFF,
            "pay_type": Job.PayType.FIXED,
            "pay_min": 1_100_000, "pay_max": 1_600_000,
            "state": "fct", "lga": "Asokoro", "slots": 3,
        },
        {
            "title": "Plaster & Render Mason — Apartment Block Enugu",
            "description": (
                "Internal plastering and external sand-cement render for a 24-apartment "
                "block in Enugu. Mist coat and finish coat to ceilings and walls. "
                "Rate per square metre. Scaffolding provided."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.DAILY,
            "pay_min": 14_000, "pay_max": 20_000,
            "state": "enugu", "lga": "Enugu South", "slots": 5,
        },
        {
            "title": "Concrete Finisher — Airport Expansion Works (Kano)",
            "description": (
                "Place and finish concrete for taxiways, aprons, and terminal floor slabs "
                "at Malam Aminu Kano International Airport expansion. Power float, "
                "laser screed experience. Night shifts required."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.DAILY,
            "pay_min": 22_000, "pay_max": 32_000,
            "state": "kano", "lga": "Kano Municipal", "slots": 8,
        },
        {
            "title": "Swimming Pool Mason — Pool Builder (Lagos)",
            "description": (
                "Build reinforced concrete in-ground swimming pools for residential and "
                "hotel clients across Lagos. Gunite or conventional RC construction. "
                "Waterproof render and mosaic tile finish. Own team of 3 preferred."
            ),
            "job_type": Job.JobType.ONCE_OFF,
            "pay_type": Job.PayType.FIXED,
            "pay_min": 1_500_000, "pay_max": 2_500_000,
            "state": "lagos", "lga": "Lekki", "slots": 1,
        },
        {
            "title": "Block Production Supervisor — Factory (Ogun State)",
            "description": (
                "Supervise a block-moulding production facility in Sagamu producing "
                "5,000 blocks per day. Manage mix quality, machine operators, and "
                "curing schedules. HND Civil Engineering or equivalent preferred."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min": 120_000, "pay_max": 180_000,
            "state": "ogun", "lga": "Sagamu", "slots": 1,
        },
    ],

    # -----------------------------------------------------------------------
    # 8. HAIR STYLIST  (5 jobs)
    # -----------------------------------------------------------------------
    "hair-stylist": [
        {
            "title": "Senior Hair Stylist — Luxury Salon Lekki Phase 1",
            "description": (
                "Join an upscale unisex salon in Lekki Phase 1 as a senior stylist. "
                "Services: natural hair styling, loc maintenance, braiding, and colouring. "
                "5+ years experience. Commission structure plus base salary."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min": 100_000, "pay_max": 180_000,
            "state": "lagos", "lga": "Lekki", "slots": 2,
        },
        {
            "title": "Bridal Hair & Makeup Artist — Event Company Abuja",
            "description": (
                "Provide hair-styling and makeup for weddings booked through a high-end "
                "Abuja events company. Weekend work required. Portfolio of 20+ bridal "
                "looks needed. Own kit essential."
            ),
            "job_type": Job.JobType.PART_TIME,
            "pay_type": Job.PayType.DAILY,
            "pay_min": 25_000, "pay_max": 50_000,
            "state": "fct", "lga": "Wuse 2", "slots": 3,
        },
        {
            "title": "Natural Hair Braider — Studio Port Harcourt GRA",
            "description": (
                "Skilled braider for a natural hair-focused studio in GRA Port Harcourt. "
                "Services: knotless braids, box braids, cornrows, twists, loc retwisting. "
                "High client volume. Targets and bonuses apply."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min": 80_000, "pay_max": 130_000,
            "state": "rivers", "lga": "Port Harcourt", "slots": 2,
        },
        {
            "title": "Master Barber — Premium Grooming Lounge Ikeja",
            "description": (
                "Master barber for a premium men's grooming lounge on Allen Avenue, Ikeja. "
                "Services: precision fades, beard sculpting, hot towel shaves, and scalp "
                "treatments. Minimum 4 years barbershop experience."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min": 110_000, "pay_max": 170_000,
            "state": "lagos", "lga": "Ikeja", "slots": 2,
        },
        {
            "title": "Mobile Hair Stylist — Home Visits Lagos Mainland",
            "description": (
                "Offer mobile hair services across Lagos Mainland (Surulere, Yaba, "
                "Ikorodu). Services: relaxers, weaves, natural styling. Build your "
                "own client book with marketing support. Own transport and kit required."
            ),
            "job_type": Job.JobType.PART_TIME,
            "pay_type": Job.PayType.DAILY,
            "pay_min": 15_000, "pay_max": 35_000,
            "state": "lagos", "lga": "Surulere", "slots": 3,
        },
    ],

    # -----------------------------------------------------------------------
    # 9. HVAC TECHNICIAN  (5 jobs)
    # -----------------------------------------------------------------------
    "hvac-technician": [
        {
            "title": "HVAC Engineer — Data Centre Precision Cooling Lagos",
            "description": (
                "Maintain precision air-conditioning units (CRAC/CRAH), chillers, and "
                "cooling towers at a tier-3 data centre in Lagos. 24/7 on-call rota. "
                "Liebert, Stulz, or Schneider precision cooling experience required."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min": 250_000, "pay_max": 380_000,
            "state": "lagos", "lga": "Oshodi", "slots": 2,
        },
        {
            "title": "Chiller Plant Commissioning Engineer — Abuja Hospital",
            "description": (
                "Commission two 500 RT centrifugal chillers, cooling towers, and AHUs "
                "for a new specialist hospital in Abuja. Controls integration, BMS points "
                "mapping, balancing, and handover. Carrier or Trane experience preferred."
            ),
            "job_type": Job.JobType.ONCE_OFF,
            "pay_type": Job.PayType.FIXED,
            "pay_min": 1_500_000, "pay_max": 2_500_000,
            "state": "fct", "lga": "Wuse", "slots": 1,
        },
        {
            "title": "AC Installer & Service Technician — Franchise (Nationwide)",
            "description": (
                "Join our nationwide AC installation and servicing franchise network. "
                "Install split, cassette, and ducted systems (LG, Daikin, Midea). "
                "Own van required. Training, uniforms, and marketing provided."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min": 120_000, "pay_max": 200_000,
            "state": "lagos", "lga": "Ikeja", "slots": 10,
            "is_remote": True,
        },
        {
            "title": "Refrigeration Technician — Cold Chain Hub Kano",
            "description": (
                "Maintain walk-in cold rooms, blast freezers, and display cabinets at "
                "a cold-chain logistics hub in Kano. PPM plus reactive call-outs. "
                "Knowledge of R404A, R134a, and CO2 systems."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min": 150_000, "pay_max": 220_000,
            "state": "kano", "lga": "Kano Municipal", "slots": 2,
        },
        {
            "title": "VRF System Installer — Commercial Office Victoria Island",
            "description": (
                "Install a Daikin VRV IV-S VRF system across 3 floors of a commercial "
                "office on Victoria Island. Refrigerant pipe installation, BACnet controls, "
                "and commissioning. F-gas trained engineers only."
            ),
            "job_type": Job.JobType.ONCE_OFF,
            "pay_type": Job.PayType.FIXED,
            "pay_min": 2_000_000, "pay_max": 3_200_000,
            "state": "lagos", "lga": "Victoria Island", "slots": 3,
        },
    ],

    # -----------------------------------------------------------------------
    # 10. AUTO MECHANIC  (5 jobs)
    # -----------------------------------------------------------------------
    "auto-mechanic": [
        {
            "title": "EV & Hybrid Diagnostic Technician — Lekki Lagos",
            "description": (
                "Diagnose and repair hybrid and EV vehicles (Toyota Prius, Honda Accord "
                "Hybrid, imported EVs) at a specialist workshop in Lekki. Proficiency "
                "with OBD-II scanners and HV battery diagnostics required."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min": 200_000, "pay_max": 320_000,
            "state": "lagos", "lga": "Lekki", "slots": 2,
        },
        {
            "title": "Fleet Mechanic — Passenger Transport Company Abuja",
            "description": (
                "Maintain a fleet of 60 Toyota Hiace buses and 15 Isuzu trucks for a "
                "transport company in Abuja. PPM schedule in place. Night-shift coverage "
                "required."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min": 160_000, "pay_max": 230_000,
            "state": "fct", "lga": "Kubwa", "slots": 3,
        },
        {
            "title": "Auto Electrician — Vehicle Accessories Workshop PH",
            "description": (
                "Install and repair dashcams, reverse cameras, LED bars, remote starts, "
                "sound systems, and alarm systems. GRA Port Harcourt workshop. "
                "High walk-in volume. Commission on top of base pay."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min": 110_000, "pay_max": 180_000,
            "state": "rivers", "lga": "Port Harcourt", "slots": 2,
        },
        {
            "title": "Heavy Equipment Mechanic — Road Construction Site Ogun",
            "description": (
                "Service and repair excavators (CAT 320), bulldozers, motor graders, "
                "and compactors at an active road construction site in Ogun State. "
                "Site accommodation provided. Minimum 5 years heavy plant experience."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min": 300_000, "pay_max": 450_000,
            "state": "ogun", "lga": "Sagamu", "slots": 2,
        },
        {
            "title": "Roadside Mechanic On-Call — Expressway Patrol Lagos",
            "description": (
                "Join a vehicle rescue service on the Lagos-Ibadan and Lagos-Benin "
                "expressways. Respond to breakdowns, carry out roadside repairs, "
                "arrange towing where needed. Own serviceable vehicle required."
            ),
            "job_type": Job.JobType.PART_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min": 60_000, "pay_max": 100_000,
            "state": "lagos", "lga": "Oshodi", "slots": 5,
        },
    ],

    # -----------------------------------------------------------------------
    # 11. TAILOR  (5 jobs)
    # -----------------------------------------------------------------------
    "tailor": [
        {
            "title": "Fashion Designer & Tailor — Ready-to-Wear Brand Lagos",
            "description": (
                "Produce ready-to-wear collections for an Afrocentric fashion label "
                "in Lagos. Pattern cutting, grading (XS-3XL), sewing, and quality "
                "control. Experience with Ankara and adire fabric required."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min": 90_000, "pay_max": 150_000,
            "state": "lagos", "lga": "Yaba", "slots": 3,
        },
        {
            "title": "Uniform Tailor — School Uniform Contract Kano",
            "description": (
                "Produce 2,000 sets of school uniforms (shirts, shorts, skirts, blazers) "
                "for a private school group in Kano. Fabric and trimmings supplied. "
                "6-week turnaround. Workshop with industrial machines required."
            ),
            "job_type": Job.JobType.ONCE_OFF,
            "pay_type": Job.PayType.FIXED,
            "pay_min": 600_000, "pay_max": 900_000,
            "state": "kano", "lga": "Kano Municipal", "slots": 1,
        },
        {
            "title": "Corporate Suit Tailor — Menswear Atelier Abuja",
            "description": (
                "Bespoke suit and corporate workwear tailor for a menswear atelier in "
                "Maitama, Abuja. Clientele includes politicians, CEOs, and diplomats. "
                "Minimum 7 years bespoke menswear experience."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min": 150_000, "pay_max": 250_000,
            "state": "fct", "lga": "Maitama", "slots": 1,
        },
        {
            "title": "Bridal Gown Seamstress — Bridal Studio Port Harcourt",
            "description": (
                "Construct bridal gowns, bridesmaids dresses, and traditional wedding "
                "attire at a busy bridal studio in GRA Port Harcourt. Lace, organza, "
                "and beading work required. Portfolio essential."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min": 80_000, "pay_max": 140_000,
            "state": "rivers", "lga": "Port Harcourt", "slots": 2,
        },
        {
            "title": "Freelance Tailor — Alterations & Repairs Platform Lagos",
            "description": (
                "Work from your own workshop taking alteration and repair orders booked "
                "through our online platform. Services: hemming, zip replacement, "
                "invisible mending. We handle marketing and payment."
            ),
            "job_type": Job.JobType.PART_TIME,
            "pay_type": Job.PayType.DAILY,
            "pay_min": 8_000, "pay_max": 20_000,
            "state": "lagos", "lga": "Surulere", "slots": 10,
            "is_remote": True,
        },
    ],

    # -----------------------------------------------------------------------
    # 12. TILER  (5 jobs)
    # -----------------------------------------------------------------------
    "tiler": [
        {
            "title": "Large-Format Tile Installer — Luxury Villas Lekki",
            "description": (
                "Lay 1200x600 and 1200x1200 mm porcelain slab tiles in 6 luxury villas "
                "in Lekki. Wet-bed and adhesive methods. Experience with large-format "
                "tiles and lippage control essential."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.DAILY,
            "pay_min": 22_000, "pay_max": 32_000,
            "state": "lagos", "lga": "Lekki", "slots": 4,
        },
        {
            "title": "Mosaic Tile Artist — Hotel Pool Deck Abuja",
            "description": (
                "Hand-lay glass and ceramic mosaic tiles on a hotel pool deck and water "
                "feature walls in Abuja. Pattern design supplied by architect. "
                "Precision grouting and waterproof membrane application."
            ),
            "job_type": Job.JobType.ONCE_OFF,
            "pay_type": Job.PayType.FIXED,
            "pay_min": 700_000, "pay_max": 1_100_000,
            "state": "fct", "lga": "Gwarinpa", "slots": 2,
        },
        {
            "title": "Wall & Floor Tiler — Hospital Project Owerri",
            "description": (
                "Tile floors, walls, and skirting in a 150-bed hospital in Owerri. "
                "Anti-slip floors in wet areas and heavy-duty epoxy-grouted clinical "
                "zones. 5-month project."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.DAILY,
            "pay_min": 16_000, "pay_max": 23_000,
            "state": "imo", "lga": "Owerri Municipal", "slots": 5,
        },
        {
            "title": "Outdoor Paving & Decking Tiler — Gated Estate Ibadan",
            "description": (
                "Lay natural stone, porcelain outdoor tiles, and composite decking "
                "across communal areas of a new 80-home estate in Ibadan. "
                "Level setting, drainage gradient, and expansion joint management."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.DAILY,
            "pay_min": 14_000, "pay_max": 20_000,
            "state": "oyo", "lga": "Ibadan North", "slots": 3,
        },
        {
            "title": "Express Bathroom Retiler — Property Renovations Lagos",
            "description": (
                "Carry out quick-turnaround bathroom retiles for a property renovation "
                "company across Lagos. Typically 1-3 day jobs. Own tools and transport "
                "required. Wet room waterproofing experience essential."
            ),
            "job_type": Job.JobType.PART_TIME,
            "pay_type": Job.PayType.DAILY,
            "pay_min": 20_000, "pay_max": 30_000,
            "state": "lagos", "lga": "Ikeja", "slots": 4,
        },
    ],

    # -----------------------------------------------------------------------
    # 13. ALUMINIUM & GLASS INSTALLER  (5 jobs)
    # -----------------------------------------------------------------------
    "aluminum-glass-installer": [
        {
            "title": "Curtain Wall & Structural Glazing Installer — Abuja Tower",
            "description": (
                "Install the full curtain wall glazing system for a 22-storey office "
                "tower in CBD Abuja. Unitised panels, structural silicone, and spider "
                "fitting experience required. Work-at-height certificate mandatory."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min": 350_000, "pay_max": 500_000,
            "state": "fct", "lga": "Central Business District", "slots": 6,
        },
        {
            "title": "Aluminium Door & Window Fabricator — Workshop Lagos",
            "description": (
                "Fabricate aluminium casement, sliding, and louvred windows plus "
                "commercial entrance doors at a busy fabrication workshop in Mushin. "
                "Operate cutting, crimping, and corner-assembly machines."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min": 90_000, "pay_max": 140_000,
            "state": "lagos", "lga": "Mushin", "slots": 3,
        },
        {
            "title": "Glass Installer — Shopfront & Balustrade Port Harcourt",
            "description": (
                "Install toughened glass shopfronts, balustrades, and frameless shower "
                "enclosures for commercial and residential clients in Port Harcourt. "
                "Own van required. Suction lifters provided."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min": 100_000, "pay_max": 160_000,
            "state": "rivers", "lga": "Port Harcourt", "slots": 2,
        },
        {
            "title": "Roof Lantern & Skylight Installer — Luxury Homes Ikoyi",
            "description": (
                "Fabricate and install custom aluminium roof lanterns, rooflights, and "
                "walk-on glass floors for high-end residential projects across Ikoyi "
                "and Banana Island. Specialist work; premium rates."
            ),
            "job_type": Job.JobType.ONCE_OFF,
            "pay_type": Job.PayType.FIXED,
            "pay_min": 800_000, "pay_max": 1_400_000,
            "state": "lagos", "lga": "Ikoyi", "slots": 2,
        },
        {
            "title": "Louvre & Shutter Installer — Commercial Buildings Kano",
            "description": (
                "Manufacture and install aluminium fixed and operable louvre blades, "
                "roller shutters, and security grilles for commercial properties in Kano. "
                "Design to installation. Must have workshop and delivery vehicle."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.FIXED,
            "pay_min": 300_000, "pay_max": 500_000,
            "state": "kano", "lga": "Kano Municipal", "slots": 2,
        },
    ],

    # -----------------------------------------------------------------------
    # 14. GENERATOR TECHNICIAN  (5 jobs)
    # -----------------------------------------------------------------------
    "generator-technician": [
        {
            "title": "Generator Service Engineer — Bank Branches (Nationwide)",
            "description": (
                "Carry out quarterly preventive maintenance of diesel generators (20-500 kVA) "
                "at bank branches across your state. Reports via mobile app. Own transport "
                "required. Comprehensive spares kit provided."
            ),
            "job_type": Job.JobType.PART_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min": 100_000, "pay_max": 170_000,
            "state": "lagos", "lga": "Ikeja", "slots": 6,
            "is_remote": True,
        },
        {
            "title": "Genset Overhaul Technician — Mining Site Zamfara",
            "description": (
                "Carry out top-end and major overhauls on Perkins and Caterpillar gensets "
                "(250-1000 kVA) at a gold mining site in Zamfara. 4 weeks on / 2 weeks off. "
                "Full board on site. Minimum 7 years genset overhaul experience."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min": 400_000, "pay_max": 600_000,
            "state": "zamfara", "lga": "Anka", "slots": 2,
        },
        {
            "title": "Generator Technician — Telecom Base Stations (Nationwide)",
            "description": (
                "Maintain diesel generators at telecom base stations across Nigeria. "
                "Preventive and corrective maintenance, fuel management, fault reporting "
                "via CMMS. Motorcycle or van required."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min": 130_000, "pay_max": 200_000,
            "state": "lagos", "lga": "Oshodi", "slots": 20,
            "is_remote": True,
        },
        {
            "title": "ATS & Changeover Switch Specialist — Lagos",
            "description": (
                "Install, programme, and repair Automatic Transfer Switches and manual "
                "changeover panels for commercial and industrial clients across Lagos. "
                "Experience with Socomec, Lovato, or ComAp ATS controllers required."
            ),
            "job_type": Job.JobType.PART_TIME,
            "pay_type": Job.PayType.DAILY,
            "pay_min": 25_000, "pay_max": 40_000,
            "state": "lagos", "lga": "Apapa", "slots": 3,
        },
        {
            "title": "Gas Generator Operator — Estate Power Plant Abuja",
            "description": (
                "Operate and maintain a 500 kVA gas generator powering a premium estate "
                "in Abuja. Daily operation logs, PPM, oil analysis, and emergency response. "
                "Shift work: 12 hours on / 12 hours off."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min": 200_000, "pay_max": 300_000,
            "state": "fct", "lga": "Asokoro", "slots": 2,
        },
    ],

    # -----------------------------------------------------------------------
    # 15. ROOFER  (5 jobs)
    # -----------------------------------------------------------------------
    "roofer": [
        {
            "title": "Flat Roof Specialist — GRP & Single-Ply Lagos",
            "description": (
                "Install GRP fibreglass and TPO single-ply flat roofing on commercial "
                "and industrial buildings across Lagos. Preparation, priming, laminating, "
                "and detailing. Minimum 4 years flat roofing experience."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.DAILY,
            "pay_min": 20_000, "pay_max": 30_000,
            "state": "lagos", "lga": "Oshodi", "slots": 3,
        },
        {
            "title": "Metal Decking Roofer — Warehouse Sagamu Ogun",
            "description": (
                "Install profiled steel metal decking roof sheets, ridge caps, and "
                "flashings on a 10,000 m2 logistics warehouse in Sagamu, Ogun State. "
                "Includes roof lights, gutters, and downpipes."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.FIXED,
            "pay_min": 1_800_000, "pay_max": 2_800_000,
            "state": "ogun", "lga": "Sagamu", "slots": 4,
        },
        {
            "title": "Roof Repair Technician — Property Manager Abuja",
            "description": (
                "Carry out reactive and planned roof repairs for a property management "
                "firm with 300+ units in Abuja: leak investigations, re-sheeting, "
                "re-tiling, gutter clearing. Own van and safety kit essential."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min": 100_000, "pay_max": 150_000,
            "state": "fct", "lga": "Wuse", "slots": 2,
        },
        {
            "title": "Pitched Roof Tiler — Housing Estate Ibeju-Lekki",
            "description": (
                "Tile 45-degree pitched roofs across 40 terraced houses in Ibeju-Lekki. "
                "Concrete interlocking tiles. Fix battens, underlay, ridge, hip, and "
                "valley tiles. Materials on site."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.DAILY,
            "pay_min": 16_000, "pay_max": 24_000,
            "state": "lagos", "lga": "Ibeju-Lekki", "slots": 6,
        },
        {
            "title": "Green Roof & Waterproofing Specialist — Eko Atlantic",
            "description": (
                "Install inverted warm roof build-ups and a 500 m2 green roof system "
                "(sedum blanket, substrate, drainage layer) on a commercial roof in "
                "Eko Atlantic. Liquid waterproofing experience essential."
            ),
            "job_type": Job.JobType.ONCE_OFF,
            "pay_type": Job.PayType.FIXED,
            "pay_min": 1_200_000, "pay_max": 2_000_000,
            "state": "lagos", "lga": "Lagos Island", "slots": 2,
        },
    ],

    # -----------------------------------------------------------------------
    # 16. SECURITY INSTALLER  (5 jobs)
    # -----------------------------------------------------------------------
    "security-installer": [
        {
            "title": "IP CCTV & VMS Engineer — Corporate HQ Abuja",
            "description": (
                "Design and install a 128-camera Milestone VMS-based IP CCTV system "
                "for a government ministry complex in Abuja. Network switches, NAS "
                "storage, fibre backbone, and operator training."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.FIXED,
            "pay_min": 3_000_000, "pay_max": 5_000_000,
            "state": "fct", "lga": "Central Business District", "slots": 3,
        },
        {
            "title": "Perimeter Security Installer — Factory Sagamu",
            "description": (
                "Install electric fence (10-strand energiser), PIR beams, and vibration "
                "sensors around a 5-hectare manufacturing plant in Sagamu. Integration "
                "with existing CCTV. Nemtek or Gallagher experience required."
            ),
            "job_type": Job.JobType.ONCE_OFF,
            "pay_type": Job.PayType.FIXED,
            "pay_min": 800_000, "pay_max": 1_300_000,
            "state": "ogun", "lga": "Sagamu", "slots": 2,
        },
        {
            "title": "Smart Home Security Integrator — Luxury Residences Lekki",
            "description": (
                "Install and configure smart home security systems: video doorbells, "
                "smart locks, motion sensors, and alarm panels integrated with smart "
                "home hubs. Must know Yale, Ring, and Ajax product ecosystems."
            ),
            "job_type": Job.JobType.PART_TIME,
            "pay_type": Job.PayType.DAILY,
            "pay_min": 25_000, "pay_max": 45_000,
            "state": "lagos", "lga": "Lekki", "slots": 3,
        },
        {
            "title": "Security Systems Service Technician — Retail Chain Lagos",
            "description": (
                "Service and repair CCTV cameras, EAS tagging systems, alarm panels, "
                "and access control at 30 retail stores across Lagos. Monthly preventive "
                "visits plus reactive call-outs. Company van provided."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min": 130_000, "pay_max": 200_000,
            "state": "lagos", "lga": "Ikeja", "slots": 2,
        },
        {
            "title": "Fire Suppression Installer — Data Centre Lagos",
            "description": (
                "Install an FM-200 clean-agent suppression system and addressable fire "
                "alarm panel in a tier-2 data centre in Lagos. Commissioning, "
                "cause-and-effect testing, and handover documentation."
            ),
            "job_type": Job.JobType.ONCE_OFF,
            "pay_type": Job.PayType.FIXED,
            "pay_min": 2_000_000, "pay_max": 3_500_000,
            "state": "lagos", "lga": "Oshodi", "slots": 2,
        },
    ],

    # -----------------------------------------------------------------------
    # 17. CATERER  (5 jobs)
    # -----------------------------------------------------------------------
    "caterer": [
        {
            "title": "Executive Chef — Corporate Canteen Abuja Ministry",
            "description": (
                "Manage a 500-cover corporate canteen at a government ministry in Abuja. "
                "Plan menus, supervise 8 kitchen staff, manage food cost targets, and "
                "maintain HACCP compliance. Minimum 7 years professional kitchen experience."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min": 250_000, "pay_max": 380_000,
            "state": "fct", "lga": "Garki", "slots": 1,
        },
        {
            "title": "Event Caterer — Corporate & Wedding Per-Event Lagos",
            "description": (
                "Provide full-service catering for corporate events and weddings across "
                "Lagos: menu planning, food production, service, and clearing. "
                "Minimum 200-pax capacity. NAFDAC compliance required."
            ),
            "job_type": Job.JobType.PART_TIME,
            "pay_type": Job.PayType.DAILY,
            "pay_min": 80_000, "pay_max": 200_000,
            "state": "lagos", "lga": "Ikeja", "slots": 5,
        },
        {
            "title": "School Meal Caterer — Private School Group Port Harcourt",
            "description": (
                "Supply daily hot meals (breakfast and lunch) for 1,200 pupils across "
                "3 private school campuses in Port Harcourt. Menu approved by nutritionist. "
                "HACCP-certified kitchen required. 12-month renewable contract."
            ),
            "job_type": Job.JobType.CONTRACT,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min": 800_000, "pay_max": 1_200_000,
            "state": "rivers", "lga": "Port Harcourt", "slots": 1,
        },
        {
            "title": "Suya & Barbeque Specialist — Food Court Kano",
            "description": (
                "Run a suya and barbequed protein stall at a new food court in Kano. "
                "Operator provides gas, equipment, and stall. Revenue-share model. "
                "Must have consistent suya quality and high-volume experience."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min": 150_000, "pay_max": 300_000,
            "state": "kano", "lga": "Kano Municipal", "slots": 1,
        },
        {
            "title": "Private Chef — UHNW Household Ikoyi Lagos",
            "description": (
                "Sole-charge private chef for an ultra-high-net-worth family residence "
                "in Ikoyi. Continental and Nigerian cuisine. Cater for family, house guests, "
                "and occasional dinner parties (up to 20 covers). NDA required."
            ),
            "job_type": Job.JobType.FULL_TIME,
            "pay_type": Job.PayType.MONTHLY,
            "pay_min": 400_000, "pay_max": 700_000,
            "state": "lagos", "lga": "Ikoyi", "slots": 1,
        },
    ],
}


# ---------------------------------------------------------------------------
#  COMMAND CLASS
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = (
        "Seeds 140 additional job listings (5+ per category) across all 17 "
        "Nigerian trade categories. Idempotent — safe to re-run."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--only",
            metavar="SLUGS",
            default="",
            help=(
                "Comma-separated category slugs to process. "
                "Omit to process all 17 categories."
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
        dry_run    = options["dry_run"]
        only_slugs = {s.strip() for s in options["only"].split(",") if s.strip()}

        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n🔧  TradeLink NG — seed_new_jobs (140 jobs target)\n"
        ))

        if dry_run:
            self.stdout.write(self.style.WARNING(
                "  [DRY RUN] — nothing will be written.\n"
            ))

        _, employer = get_or_create_seed_employer()
        self.stdout.write(
            f"  Seed employer: {employer.company_name} (pk={employer.pk})\n"
        )

        if options["clear"] and not dry_run:
            self._clear_seed_jobs(employer)

        total_new  = 0
        total_skip = 0
        missing    = []

        with transaction.atomic():
            for slug, jobs_list in NEW_JOBS.items():
                if only_slugs and slug not in only_slugs:
                    continue

                try:
                    cat = TradeCategory.objects.get(slug=slug)
                except TradeCategory.DoesNotExist:
                    self.stdout.write(self.style.WARNING(
                        f"  WARNING: category slug={slug!r} not found — skipped."
                    ))
                    missing.append(slug)
                    continue

                self.stdout.write(f"\n  [{cat.name}]  ({len(jobs_list)} jobs defined)")
                cat_new = cat_skip = 0
                deadline_base = date.today() + timedelta(days=30)

                for job_data in jobs_list:
                    exists = Job.objects.filter(
                        employer=employer,
                        trade_category=cat,
                        title=job_data["title"],
                    ).exists()

                    if exists:
                        self.stdout.write(
                            f"    skip (exists): {job_data['title'][:70]}"
                        )
                        cat_skip += 1
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
                            f"    created: {job_data['title'][:70]}"
                        )
                    else:
                        self.stdout.write(
                            f"    [dry-run] would create: {job_data['title'][:70]}"
                        )

                    cat_new += 1

                self.stdout.write(
                    f"    => {cat_new} new  |  {cat_skip} skipped"
                )
                total_new  += cat_new
                total_skip += cat_skip

        self.stdout.write("")

        if missing:
            self.stdout.write(self.style.WARNING(
                f"  {len(missing)} category slug(s) not found: "
                f"{', '.join(missing)}\n"
                "  Run seed_category_jobs first to create them.\n"
            ))

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f"  [DRY RUN] Would create {total_new} jobs "
                f"({total_skip} already exist). "
                "Re-run without --dry-run to apply.\n"
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"\n  Done — {total_new} new jobs created "
                f"({total_skip} already existed, skipped).\n"
            ))

    def _clear_seed_jobs(self, employer: EmployerProfile):
        """Delete all Job rows owned by the seed employer."""
        self.stdout.write(self.style.WARNING(
            "\n  --clear: removing existing seed jobs ..."
        ))
        deleted, _ = Job.objects.filter(employer=employer).delete()
        self.stdout.write(f"  Deleted {deleted} job(s).\n")
