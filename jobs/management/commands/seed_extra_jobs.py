"""
jobs/management/commands/seed_extra_jobs.py
============================================
Seeds an additional 140 active job listings across the same 17 Nigerian
trade categories used by seed_category_jobs.py.

Distribution
------------
Four high-demand categories carry 9 jobs each; the remaining 13 carry
8 jobs each:

    9 jobs × 4  (electrician, welder, auto-mechanic, caterer)  =  36
    8 jobs × 13 (all other categories)                          = 104
    ─────────────────────────────────────────────────────────────────
    Total                                                        = 140

All categories are looked up by slug (never re-created here).
Skills are added via get_or_create, so running this command before
seed_category_jobs is safe.

All jobs are owned by the shared ``tradelink_seed_employer`` account.

Usage
-----
    # Full seed (all 17 categories, 140 jobs)
    python manage.py seed_extra_jobs

    # Limit to specific categories (comma-separated slugs)
    python manage.py seed_extra_jobs --only electrician,welder

    # Preview without writing anything
    python manage.py seed_extra_jobs --dry-run

    # Wipe this command's jobs first, then re-seed
    python manage.py seed_extra_jobs --clear

Design notes
------------
- Idempotent: jobs are keyed by (employer, trade_category, title).
  Re-running skips any that already exist.
- No title in this file duplicates any title in seed_category_jobs.py.
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
#  SEED EMPLOYER  (shared with seed_jobs.py and seed_category_jobs.py)
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
#  TRADE CATEGORIES + JOBS
# ──────────────────────────────────────────────────────────────────────────────

TRADE_CATEGORIES = [

    # ── 1. ELECTRICIAN (9 jobs) ───────────────────────────────────────────────
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
            "Smart Home Automation", "EV Charging Point Installation",
            "Lightning Protection Systems", "UPS & Data Centre Power",
            "Emergency & Exit Lighting", "Substation Maintenance",
            "Building Management Systems (BMS)", "Earthing & Bonding",
            "Energy Metering & Monitoring", "Low-Voltage Switchgear",
        ],
        "jobs": [
            {
                "title": "Smart Home Automation Installer — Banana Island",
                "description": (
                    "Design and commission a full KNX/Lutron smart home system in a "
                    "6-bedroom mansion on Banana Island, Lagos. Scope covers lighting "
                    "scenes, motorised blinds, climate control integration, and a "
                    "centralised control app. KNX certification or equivalent required; "
                    "portfolio of completed smart home projects must be supplied."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 800_000, "pay_max": 1_200_000,
                "state": "lagos", "lga": "Ikoyi", "slots": 1,
            },
            {
                "title": "Street Light Network Upgrade — Enugu State Contractor",
                "description": (
                    "Replace 500 sodium-vapour streetlights with LED fittings along "
                    "three state highways in Enugu. Work includes feeder-pillar "
                    "connections, cable fault rectification, and re-commissioning. "
                    "Mobile elevating work platform provided on site."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 2_000_000, "pay_max": 3_000_000,
                "state": "enugu", "lga": "Enugu North", "slots": 4,
            },
            {
                "title": "Periodic Inspection & Testing Officer — Insurance Survey (Lagos)",
                "description": (
                    "Carry out Periodic Inspection & Testing (PIR) reports for a "
                    "commercial insurance underwriter across 30 industrial properties "
                    "in Lagos. Issue EICR certificates and defect reports. "
                    "City & Guilds 2391-52 or equivalent required. Own car essential."
                ),
                "job_type": Job.JobType.PART_TIME,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 25_000, "pay_max": 40_000,
                "state": "lagos", "lga": "Ikeja", "slots": 2,
                "is_remote": False,
            },
            {
                "title": "EV Charging Point Installer — Shopping Mall (Victoria Island)",
                "description": (
                    "Supply and install 20 Type 2 AC and 4 DC fast-charging stations "
                    "in the car park of a major shopping mall on Victoria Island. "
                    "Covers trenching, cable draw, DBs, and OCPP back-end commissioning. "
                    "Experience with ChargePoint or Zaptec hardware preferred."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 1_500_000, "pay_max": 2_200_000,
                "state": "lagos", "lga": "Victoria Island", "slots": 2,
            },
            {
                "title": "Lightning Protection & Earthing Installer — Telecom Towers",
                "description": (
                    "Install BS EN 62305-compliant lightning protection systems (air "
                    "terminals, down conductors, earth electrodes) and equipotential "
                    "bonding at 15 telecom tower sites across Ogun and Oyo states. "
                    "Earth resistance testing and certification for each site required."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 900_000, "pay_max": 1_300_000,
                "state": "ogun", "lga": "Abeokuta South", "slots": 2,
            },
            {
                "title": "UPS & Data Centre Power Systems Installer — Bank Branch (Abuja)",
                "description": (
                    "Install double-conversion UPS units (10–40 kVA), static bypass "
                    "switches, PDUs, and battery strings for 6 new bank branches in "
                    "Abuja. Full factory acceptance test documentation required before "
                    "site delivery. Experience with APC or Eaton systems preferred."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 1_200_000, "pay_max": 1_800_000,
                "state": "fct", "lga": "Garki", "slots": 2,
            },
            {
                "title": "Emergency Lighting & Fire Alarm Commissioning — Hotel (Abuja)",
                "description": (
                    "Install and commission a fully addressable Hochiki fire alarm "
                    "system and BS 5266 emergency lighting across a 120-room hotel "
                    "in Wuse 2, Abuja. Includes cause-and-effect programming, "
                    "logbooks, and three-hour endurance test."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 500_000, "pay_max": 750_000,
                "state": "fct", "lga": "Wuse", "slots": 2,
            },
            {
                "title": "Substation Maintenance Electrician — Industrial Estate (Ogun)",
                "description": (
                    "Carry out routine and corrective maintenance on 33/11 kV and "
                    "11/0.415 kV transformer substations in an industrial estate in "
                    "Sagamu. Tasks include oil sampling, relay calibration, insulation "
                    "resistance testing, and switchgear servicing. HV authorised person "
                    "status required."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 200_000, "pay_max": 300_000,
                "state": "ogun", "lga": "Sagamu", "slots": 1,
            },
            {
                "title": "Building Energy Management System (BMS) Engineer — Lekki",
                "description": (
                    "Configure and maintain a Siemens Desigo or Honeywell BMS covering "
                    "HVAC, lighting, and energy metering across two commercial towers "
                    "in Lekki Free Zone. Remote monitoring capabilities and energy "
                    "dashboard setup required. Experience with Modbus/BACnet essential."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 250_000, "pay_max": 380_000,
                "state": "lagos", "lga": "Lekki", "slots": 1,
            },
        ],
    },

    # ── 2. PLUMBER (8 jobs) ───────────────────────────────────────────────────
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
            "Swimming Pool Plumbing", "Industrial Pipe Fitting",
            "Rainwater Harvesting", "Hot Water System Installation",
            "Thermostatic Shower Valve Fitting", "Water Treatment",
            "Hydrostatic Pressure Testing", "Roof Gutter Installation",
        ],
        "jobs": [
            {
                "title": "Swimming Pool Plumber — Luxury Villa (Banana Island)",
                "description": (
                    "Install the full hydraulic system for a 20 m infinity pool on "
                    "Banana Island: main drains, skimmers, return jets, filtration "
                    "plant room, chemical dosing, and heat pump connections. "
                    "Experience with Hayward or Pentair pool equipment required. "
                    "Watertight handover certificate expected."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 1_200_000, "pay_max": 1_800_000,
                "state": "lagos", "lga": "Ikoyi", "slots": 2,
            },
            {
                "title": "Sanitary Installation Plumber — Hospital Project (Enugu)",
                "description": (
                    "Fit sanitary ware — clinical hand-wash basins, sluice sinks, "
                    "bedpan washers, and isolation-room shower trays — across 4 floors "
                    "of a new district hospital in Enugu. HTM 64 knowledge preferred. "
                    "Hot and cold water, waste, and vent stacks included."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 900_000, "pay_max": 1_300_000,
                "state": "enugu", "lga": "Enugu North", "slots": 3,
            },
            {
                "title": "Rainwater Harvesting System Installer — Commercial Building (Abuja)",
                "description": (
                    "Design and install a 50,000-litre rainwater harvesting system "
                    "(first-flush diverter, underground tank, filtration, UV treatment, "
                    "and booster pump) for a LEED-targeting office in Maitama, Abuja. "
                    "Produce an as-built drawing and handover manual."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 650_000, "pay_max": 950_000,
                "state": "fct", "lga": "Maitama", "slots": 1,
            },
            {
                "title": "Industrial Pipe Fitter — Beverage Factory (Sagamu, Ogun)",
                "description": (
                    "Fit stainless-steel food-grade process pipework (to hygienic "
                    "welding standards) in a soft-drink bottling plant in Sagamu. "
                    "Scope includes CIP lines, CO₂ supply, compressed-air ring main, "
                    "and chilled-water distribution. Orbital welding experience an asset."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 22_000, "pay_max": 35_000,
                "state": "ogun", "lga": "Sagamu", "slots": 4,
            },
            {
                "title": "Leak Detection & Repair Specialist — Gated Estate (Lekki Phase 2)",
                "description": (
                    "Use acoustic leak detection equipment to locate and repair hidden "
                    "leaks on the underground distribution network of a 300-unit gated "
                    "estate. Provide a survey report and repair schedule. "
                    "Own detection equipment required or hire reimbursed."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 350_000, "pay_max": 550_000,
                "state": "lagos", "lga": "Lekki", "slots": 1,
            },
            {
                "title": "Hot Water & Boiler System Installer — Boutique Hotel (PH GRA)",
                "description": (
                    "Supply and install a commercial condensing boiler plant room "
                    "serving 60 hotel rooms in Port Harcourt GRA: boilers, pressurisation "
                    "units, calorifiers, pump sets, expansion vessels, and balancing "
                    "valves. Commissioning and CIBSE handover documentation required."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 1_500_000, "pay_max": 2_200_000,
                "state": "rivers", "lga": "Port Harcourt", "slots": 2,
            },
            {
                "title": "Roof Gutter & Downpipe Installer — 80-Unit Estate (Kubwa, Abuja)",
                "description": (
                    "Supply and fix PVC gutters, downpipes, and gully connections for "
                    "80 semi-detached houses in Kubwa. Ensure correct falls (1:200) "
                    "and connect into the estate drainage system. "
                    "Materials provided; own ladders and tools required."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 500_000, "pay_max": 750_000,
                "state": "fct", "lga": "Kubwa", "slots": 3,
            },
            {
                "title": "Water Treatment Plant Operator — Food Processing Plant (Kano)",
                "description": (
                    "Operate and maintain a reverse osmosis and UV water treatment plant "
                    "supplying process and drinking water in a food factory in Kano. "
                    "Responsibilities include chemical dosing, membrane replacement, "
                    "water quality logging, and regulatory compliance reporting."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 120_000, "pay_max": 180_000,
                "state": "kano", "lga": "Kano Municipal", "slots": 2,
            },
        ],
    },

    # ── 3. SOLAR INSTALLER (8 jobs) ───────────────────────────────────────────
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
            "Solar Cold Room Systems", "Hybrid Microgrid Design",
            "PV Module Cleaning & O&M", "Solar Carport Structures",
            "Battery Commissioning (BESS)", "TVET Solar Training",
            "Solar Mini-Grid Operation", "Agri-PV Systems",
        ],
        "jobs": [
            {
                "title": "Solar Cold Room Installer — Fishery Co-operative (Yenagoa, Bayelsa)",
                "description": (
                    "Design and install a 3 kW solar-powered cold room system (panels, "
                    "batteries, DC compressor unit, insulated cold room structure) for "
                    "a fish-storage cooperative in Yenagoa. Provide operator training "
                    "and a 12-month service agreement. Transport allowance included."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 900_000, "pay_max": 1_300_000,
                "state": "bayelsa", "lga": "Yenagoa", "slots": 2,
            },
            {
                "title": "Hybrid Solar & Grid System Technician — Mission Hospital (Kano)",
                "description": (
                    "Install a 50 kW hybrid solar system (PV array, 80 kWh lithium "
                    "battery bank, hybrid inverters, and grid tie-in) for a mission "
                    "hospital in Kano. System must prioritise surgical theatre and ICU "
                    "circuits. Commissioning report and as-built drawings required."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 4_000_000, "pay_max": 6_000_000,
                "state": "kano", "lga": "Kano Municipal", "slots": 2,
            },
            {
                "title": "Solar Pump O&M Technician — State Waterworks (Plateau)",
                "description": (
                    "Carry out quarterly preventive maintenance on 40 solar borehole "
                    "pump systems installed across Plateau State under a World Bank "
                    "WASH project. Tasks: panel cleaning, battery checks, pump "
                    "performance tests, and fault resolution within 48 hours."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 130_000, "pay_max": 190_000,
                "state": "plateau", "lga": "Jos North", "slots": 3,
            },
            {
                "title": "PV Module Cleaning Technician — Residential Estate (Ajah, Lagos)",
                "description": (
                    "Clean and inspect rooftop solar panels on 150 homes in a Ajah "
                    "gated estate on a monthly contract. Use deionised water and "
                    "soft brushes; check connections and log generation data. "
                    "Safe roof-access training and PPE provided."
                ),
                "job_type": Job.JobType.PART_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 60_000, "pay_max": 90_000,
                "state": "lagos", "lga": "Eti-Osa", "slots": 2,
            },
            {
                "title": "Solar Carport Installer — Shopping Centre (Abuja)",
                "description": (
                    "Fabricate and install a 200 kW solar carport structure (steel "
                    "canopy, galvanised mounting, bifacial panels) over a 300-car "
                    "car park in Wuse 2. Integrate with the building's HV supply and "
                    "export-limitation relay. Structural drawings provided by engineer."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 15_000_000, "pay_max": 22_000_000,
                "state": "fct", "lga": "Wuse", "slots": 3,
            },
            {
                "title": "Battery Energy Storage Commissioning Engineer — Lagos Data Centre",
                "description": (
                    "Commission a 500 kWh containerised BESS (lithium iron phosphate) "
                    "at a colocation data centre in Ikeja. Scope: BMS configuration, "
                    "protection relay settings, black-start testing, and integration "
                    "with the site's SCADA. Manufacturer training certificate required."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 2_000_000, "pay_max": 3_000_000,
                "state": "lagos", "lga": "Ikeja", "slots": 1,
            },
            {
                "title": "Solar Training Instructor — TVET Centre (Kaduna)",
                "description": (
                    "Teach a 12-week practical solar installation course to 20 "
                    "trainees at a technical college in Kaduna under a government "
                    "skills programme. Develop lesson plans, hands-on lab sessions, "
                    "and assessment instruments. NABCEP or NABTEB qualification required."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 150_000, "pay_max": 220_000,
                "state": "kaduna", "lga": "Kaduna North", "slots": 1,
            },
            {
                "title": "Grid-Tie Solar System Installer — University Campus (Ibadan)",
                "description": (
                    "Install a 500 kW rooftop grid-tie PV system across four faculty "
                    "buildings at a university in Ibadan. Includes string inverters, "
                    "monitoring system, and export limitation device. University "
                    "engineering department sign-off required before energisation."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 30_000_000, "pay_max": 45_000_000,
                "state": "oyo", "lga": "Ibadan North", "slots": 4,
            },
        ],
    },

    # ── 4. CARPENTER (8 jobs) ─────────────────────────────────────────────────
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
            "Exhibition Stand Construction", "Timber Decking & Pergolas",
            "Hardwood Flooring", "Built-In Wardrobes & Joinery",
            "Acoustic Ceiling Panels", "Shopfront Joinery",
            "Formwork for Bridges", "Mosque & Religious Furniture",
        ],
        "jobs": [
            {
                "title": "Exhibition Stand Builder — Events Company (Eko Convention Centre)",
                "description": (
                    "Design and construct bespoke timber exhibition stands and display "
                    "booths for a corporate events company operating at Eko Convention "
                    "Centre, Lagos. Covers cutting, assembly, branding panel fitting, "
                    "and breakdown. Turnaround between events is typically 48 hours."
                ),
                "job_type": Job.JobType.PART_TIME,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 20_000, "pay_max": 35_000,
                "state": "lagos", "lga": "Lagos Island", "slots": 4,
            },
            {
                "title": "Timber Deck & Pergola Installer — Waterfront Estate (PH)",
                "description": (
                    "Construct hardwood decking, pergolas, and garden seating structures "
                    "across 10 waterfront properties in a Port Harcourt estate. "
                    "Use treated Iroko or Teak boards; include balustrades and steps. "
                    "Must supply portfolio showing previous outdoor timber installations."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 800_000, "pay_max": 1_200_000,
                "state": "rivers", "lga": "Port Harcourt", "slots": 2,
            },
            {
                "title": "Engineered Hardwood Flooring Installer — Office Complex (Abuja)",
                "description": (
                    "Supply and lay engineered oak click-lock flooring across 2,000 m² "
                    "of open-plan office space in Central Business District, Abuja. "
                    "Includes subfloor levelling, acoustic underlay, and skirting. "
                    "No gaps or squeaks accepted; 5-year installation guarantee."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 1_400_000, "pay_max": 2_000_000,
                "state": "fct", "lga": "Central Business District", "slots": 2,
            },
            {
                "title": "Built-In Wardrobe & Joinery Installer — Luxury Apartments (Lekki)",
                "description": (
                    "Measure, fabricate, and install floor-to-ceiling built-in wardrobes, "
                    "dressing room units, and bespoke TV walls across 20 luxury apartments "
                    "in Lekki Phase 1. Use HDF, mirror panels, and soft-close hardware. "
                    "Must work to interior designer's finish schedule."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 2_500_000, "pay_max": 3_500_000,
                "state": "lagos", "lga": "Lekki", "slots": 2,
            },
            {
                "title": "Acoustic Ceiling & Wooden Panelling Installer — Hotel (Calabar)",
                "description": (
                    "Install decorative acoustic timber ceiling panels and wall cladding "
                    "in the lobby, restaurant, and conference rooms of a 4-star hotel "
                    "in Calabar. CAD shop drawings and fixing schedule provided by "
                    "interior architect. Scissor lift available on site."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 700_000, "pay_max": 1_000_000,
                "state": "cross river", "lga": "Calabar South", "slots": 2,
            },
            {
                "title": "Mosque Furniture Maker — Community Project (Kano)",
                "description": (
                    "Fabricate and install wooden minbar (pulpit), mimbar steps, "
                    "imam's lectern, and decorative Arabic latticework screens for a "
                    "new mosque in Kano. Intricate carving skills required; "
                    "designs to be approved by the mosque committee before production."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 400_000, "pay_max": 650_000,
                "state": "kano", "lga": "Kano Municipal", "slots": 1,
            },
            {
                "title": "Formwork Carpenter — Bridge Deck Construction (Ibadan Bypass)",
                "description": (
                    "Set, prop, and strike multi-use plywood formwork systems for the "
                    "deck slab and abutments of a 120 m bridge on the Ibadan bypass "
                    "road. Familiarity with PERI or Doka systems preferred. "
                    "Work alongside a resident structural engineer."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.WEEKLY,
                "pay_min": 45_000, "pay_max": 65_000,
                "state": "oyo", "lga": "Ibadan South West", "slots": 5,
            },
            {
                "title": "Shop Counter & Display Unit Maker — Retail Pharmacy Chain (Lagos)",
                "description": (
                    "Manufacture and install pharmacy prescription counters, OTC shelving "
                    "gondolas, and cashier stations for a 10-outlet pharmacy rollout in "
                    "Lagos. Consistent finishes across all branches; detailed millwork "
                    "drawings provided. Workshop must accommodate batch production."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 1_200_000, "pay_max": 1_800_000,
                "state": "lagos", "lga": "Surulere", "slots": 2,
            },
        ],
    },

    # ── 5. PAINTER & DECORATOR (8 jobs) ───────────────────────────────────────
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
            "Road Marking & Line Painting", "Wallpaper & Mural Hanging",
            "Colour Consultation", "Basement Waterproofing Paint",
            "Concrete Floor Coating", "Graffiti Removal",
            "Intumescent Fire-Retardant Coating", "Decorative Concrete Coatings",
        ],
        "jobs": [
            {
                "title": "Road Marking & Line Painter — State Highway Contractor (Ogun)",
                "description": (
                    "Apply thermoplastic road-marking paint (centre lines, edge lines, "
                    "pedestrian crossings, speed legends) along 80 km of state roads "
                    "in Ogun. Operate a ride-on thermoplastic applicator machine. "
                    "Night-work shifts required; traffic management plan provided."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 2_500_000, "pay_max": 3_800_000,
                "state": "ogun", "lga": "Abeokuta South", "slots": 3,
            },
            {
                "title": "Wallpaper Hanger — High-End Apartments (Ikoyi, Lagos)",
                "description": (
                    "Hang designer wallpaper (fabric-backed, grasscloth, and foil "
                    "finishes) in bedrooms and feature walls across 12 luxury "
                    "apartments in Ikoyi. Pattern-match and seam-join to zero-defect "
                    "standard. Products supplied by interior designer."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 30_000, "pay_max": 50_000,
                "state": "lagos", "lga": "Ikoyi", "slots": 1,
            },
            {
                "title": "Colour Consultant & Paint Specification Advisor (Remote/Lagos)",
                "description": (
                    "Provide professional colour consultancy for residential and "
                    "commercial clients across Lagos — site visits, mood boards, "
                    "RAL/NCS specification sheets, and coordination with contractors. "
                    "Retainer arrangement with a property development company. "
                    "Interior design qualification or equivalent experience required."
                ),
                "job_type": Job.JobType.PART_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 100_000, "pay_max": 150_000,
                "state": "lagos", "lga": "Victoria Island", "slots": 1,
                "is_remote": True,
            },
            {
                "title": "Waterproofing Paint Specialist — Basement & Retaining Walls (Abuja)",
                "description": (
                    "Apply crystalline and cementitious waterproofing coatings to "
                    "basement walls and floors in a new mixed-use development in "
                    "Maitama. Surface preparation includes grinding, filling blowholes, "
                    "and applying bonding slurry. Sika or Fosroc product experience "
                    "preferred."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 600_000, "pay_max": 900_000,
                "state": "fct", "lga": "Maitama", "slots": 2,
            },
            {
                "title": "Decorative Concrete Floor Coating Applicator — Car Showroom (Abuja)",
                "description": (
                    "Apply a metallic epoxy and polyaspartic topcoat system to 1,500 m² "
                    "of showroom floor in Garki, Abuja. Produce a high-gloss, slip-"
                    "resistant finish with colour-flake inlay. Diamond-grind and "
                    "moisture-test floor prior to application. 5-year warranty expected."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 1_200_000, "pay_max": 1_800_000,
                "state": "fct", "lga": "Garki", "slots": 2,
            },
            {
                "title": "Graffiti Removal & Repainting Specialist — Corporate Estate (Ikeja)",
                "description": (
                    "Provide an ongoing graffiti removal and reactive repainting service "
                    "for a corporate campus in Ikeja GRA. Respond within 24 hours of "
                    "call-out. Use chemical removers, pressure washing, and colour-"
                    "matched touch-up paint. Own transport and pressure washer required."
                ),
                "job_type": Job.JobType.PART_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 80_000, "pay_max": 120_000,
                "state": "lagos", "lga": "Ikeja", "slots": 1,
            },
            {
                "title": "Intumescent Fire-Retardant Coating Applicator — Steel Frame (Lagos)",
                "description": (
                    "Apply thin-film intumescent paint (to BS 476 / EN 13381) on "
                    "structural steel beams, columns, and connections in a 6-storey "
                    "commercial building in Yaba. Full DFT gauging and documentation "
                    "required. Experience with Nullifire or Nullifire / Sherwin-Williams "
                    "systems preferred."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 850_000, "pay_max": 1_300_000,
                "state": "lagos", "lga": "Yaba", "slots": 2,
            },
            {
                "title": "Anti-Rust Primer & Topcoat Painter — Steel Fabrication Yard (Delta)",
                "description": (
                    "Apply blast-primer, zinc-rich intermediate, and polyurethane "
                    "topcoat to fabricated structural steel sections at a fabrication "
                    "yard in Warri. SSPC SP-10 surface preparation required. "
                    "DFT records and batch certificates to accompany each shipment."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 90_000, "pay_max": 140_000,
                "state": "delta", "lga": "Warri South", "slots": 3,
            },
        ],
    },

    # ── 6. WELDER (9 jobs) ────────────────────────────────────────────────────
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
            "Stainless Steel Balustrade Fabrication", "Offshore Structural Welding",
            "Exhaust & Manifold Welding", "Conveyor Frame Fabrication",
            "Ship Hull Repair Welding", "Ornamental Iron Fabrication",
            "Boiler & Heat Exchanger Repair", "FCAW Welding",
            "Hyperbaric Welding", "3D Pipe Spooling",
        ],
        "jobs": [
            {
                "title": "Stainless Steel Balustrade Fabricator — Luxury Apartments (Lagos)",
                "description": (
                    "Fabricate and install polished 316 stainless-steel glass-infill "
                    "balustrades on staircases, balconies, and roof terraces across "
                    "30 luxury apartments in Oniru, Lagos. CNC-laser cut posts; "
                    "TIG-weld to mirror finish. Shop drawings provided by architect."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 1_200_000, "pay_max": 1_800_000,
                "state": "lagos", "lga": "Eti-Osa", "slots": 2,
            },
            {
                "title": "Steel Roof Truss Fabricator — Industrial Warehouse (Sagamu, Ogun)",
                "description": (
                    "Fabricate and erect 120 m span steel portal-frame trusses for a "
                    "15,000 m² logistics warehouse in Sagamu. Work from structural "
                    "engineer's drawings; MIG weld and bolt-up connections on site. "
                    "Working-at-height permit and fall-arrest equipment required."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 35_000, "pay_max": 55_000,
                "state": "ogun", "lga": "Sagamu", "slots": 6,
            },
            {
                "title": "Offshore Structural Welder — FPSO Conversion (Rivers State)",
                "description": (
                    "Join a steel-renewal and structural modification crew on an FPSO "
                    "vessel undergoing conversion at a yard in Bonny Island. "
                    "CSWIP 3.1 (6G) and valid offshore survival certificate required. "
                    "Offshore rotation (28/28), accommodation and meals on vessel."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 80_000, "pay_max": 120_000,
                "state": "rivers", "lga": "Bonny", "slots": 8,
            },
            {
                "title": "Exhaust Manifold & Downpipe Welder — Performance Workshop (Lagos)",
                "description": (
                    "Fabricate and weld stainless-steel exhaust manifolds, headers, "
                    "and downpipes for a high-performance car tuning workshop in "
                    "Surulere, Lagos. TIG welding on thin-wall stainless tube; "
                    "ability to read engine bay templates essential."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 120_000, "pay_max": 180_000,
                "state": "lagos", "lga": "Surulere", "slots": 2,
            },
            {
                "title": "Conveyor Frame & Chute Fabricator — Cement Factory (Ogun)",
                "description": (
                    "Fabricate mild-steel conveyor support frames, transfer chutes, "
                    "and splitter boxes during a planned maintenance shutdown at a "
                    "cement plant in Ogun. Work from isometric drawings; "
                    "ARC welding, angle iron, and plate work. PPE and safety induction "
                    "mandatory before entry to plant."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 25_000, "pay_max": 40_000,
                "state": "ogun", "lga": "Ewekoro", "slots": 4,
            },
            {
                "title": "Ship Hull & Tank Repair Welder — Inland Dockyard (Port Harcourt)",
                "description": (
                    "Carry out hull plate renewal, bracket repairs, and tank testing "
                    "on river barges and patrol vessels at a dockyard in Port Harcourt. "
                    "ARC (SMAW) and MIG welding on 8–20 mm mild steel. "
                    "Confined-space entry certificate required."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 130_000, "pay_max": 190_000,
                "state": "rivers", "lga": "Port Harcourt", "slots": 3,
            },
            {
                "title": "Ornamental Iron Gate & Fence Fabricator — Housing Estate (Lekki)",
                "description": (
                    "Fabricate decorative wrought-iron estate entrance gates (twin "
                    "leaf, electric-operated) and perimeter fencing panels for a "
                    "new gated estate in Lekki Phase 2. Scroll work, forged finials, "
                    "and powder-coat finish. Deliver and install on site."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 700_000, "pay_max": 1_100_000,
                "state": "lagos", "lga": "Lekki", "slots": 2,
            },
            {
                "title": "Boiler & Heat Exchanger Repair Welder — Textile Mill (Kaduna)",
                "description": (
                    "Repair fire-tube boiler shells, tube plates, and process heat "
                    "exchanger bundles during annual shutdown at a textile mill in "
                    "Kaduna. ASME IX qualified welding procedures required. "
                    "Work closely with third-party NDT inspector."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 55_000, "pay_max": 80_000,
                "state": "kaduna", "lga": "Kaduna North", "slots": 3,
            },
            {
                "title": "3D Pipe Spool Fabricator — Gas Processing Plant (Delta)",
                "description": (
                    "Fabricate carbon-steel and stainless-steel pipe spools from "
                    "isometric drawings for a new gas processing module in Delta. "
                    "GTAW root pass, SMAW fill/cap; P91 material experience a plus. "
                    "ISO 9001 fabrication environment; full traceability documents required."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 50_000, "pay_max": 75_000,
                "state": "delta", "lga": "Warri North", "slots": 5,
            },
        ],
    },

    # ── 7. MASON (8 jobs) ─────────────────────────────────────────────────────
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
            "Terrazzo Flooring", "Retaining Wall Construction",
            "Stone Cladding", "Pool Shell Rendering",
            "Concrete Road Repair", "Fireplace & Chimney Construction",
            "Precast Panel Installation", "Dry-Stack Block Systems",
        ],
        "jobs": [
            {
                "title": "Terrazzo Floor Layer — Government Office Complex (Abuja)",
                "description": (
                    "Lay and grind terrazzo flooring (poured-in-place marble chip) "
                    "across 3,000 m² of corridors and offices in a new government "
                    "complex in Abuja CBD. Divider strips, grinding, honing, and "
                    "final sealing included. Experience with epoxy terrazzo preferred."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 2_500_000, "pay_max": 3_500_000,
                "state": "fct", "lga": "Central Business District", "slots": 4,
            },
            {
                "title": "Retaining Wall Mason — Hillside Development (Asokoro, Abuja)",
                "description": (
                    "Construct reinforced blockwork retaining walls (up to 4 m high) "
                    "to level a hillside plot in Asokoro, Abuja. Place concrete, set "
                    "rebar to engineer's drawings, and render exposed faces. "
                    "Drainage backing and weep holes must be correctly installed."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 700_000, "pay_max": 1_100_000,
                "state": "fct", "lga": "Asokoro", "slots": 3,
            },
            {
                "title": "Natural Stone Cladding Installer — Luxury Villa (Banana Island)",
                "description": (
                    "Fix travertine and limestone cladding panels to external facades "
                    "and feature walls in a high-end villa on Banana Island. "
                    "Use polymer-modified adhesive and grout; joints must align with "
                    "architect's coursing plan. Scissor-lift access provided."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 1_000_000, "pay_max": 1_500_000,
                "state": "lagos", "lga": "Ikoyi", "slots": 2,
            },
            {
                "title": "Swimming Pool Shell Mason & Renderer — GRA (Port Harcourt)",
                "description": (
                    "Build blockwork pool shell, apply Waterite render coat, and "
                    "prepare the surface for tiling for a 12 m × 5 m pool in "
                    "Port Harcourt GRA. Coordinate with plumber for inlet/outlet "
                    "sleeves. Water-tightness test required before handover."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 600_000, "pay_max": 900_000,
                "state": "rivers", "lga": "Port Harcourt", "slots": 2,
            },
            {
                "title": "Concrete Road Repair Mason — Lagos Island Road Maintenance",
                "description": (
                    "Carry out concrete patch repairs and reinstatement of road "
                    "surfaces on Lagos Island under a state road maintenance contract. "
                    "Remove failed sections, form and pour rapid-hardening concrete, "
                    "and ensure flush joints. Night shifts required on busy roads."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 80_000, "pay_max": 120_000,
                "state": "lagos", "lga": "Lagos Island", "slots": 4,
            },
            {
                "title": "Fireplace & Chimney Mason — Luxury Homes (Abuja)",
                "description": (
                    "Build fire-rated masonry fireplaces, decorative chimney breasts, "
                    "and flue systems in high-end residential projects in Abuja. "
                    "Fire-clay brick laying, cast concrete lintels, and marble hearth "
                    "setting. Portfolio of completed fireplaces required."
                ),
                "job_type": Job.JobType.PART_TIME,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 250_000, "pay_max": 450_000,
                "state": "fct", "lga": "Maitama", "slots": 1,
            },
            {
                "title": "Precast Concrete Panel Installer — Fast-Track School Build (Lagos)",
                "description": (
                    "Erect precast structural concrete wall panels and hollowcore floor "
                    "planks for a 24-classroom school block in Alimosho under a "
                    "fast-track construction programme. Work alongside a crane crew; "
                    "grout joints and fix steel ties per engineer's spec."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.WEEKLY,
                "pay_min": 40_000, "pay_max": 60_000,
                "state": "lagos", "lga": "Alimosho", "slots": 4,
            },
            {
                "title": "Interlocking Block Layer — Industrial Estate Roads (Ogun)",
                "description": (
                    "Lay interlocking concrete block paving for access roads and "
                    "loading bays within a new industrial estate in Sagamu. "
                    "Include sand bedding, edge restraints, and cut blocks around "
                    "drainage gullies. Compaction plate and block splitter provided."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 900_000, "pay_max": 1_400_000,
                "state": "ogun", "lga": "Sagamu", "slots": 5,
            },
        ],
    },

    # ── 8. HAIR STYLIST (8 jobs) ──────────────────────────────────────────────
    {
        "name": "Hair Stylist",
        "slug": "hair-stylist",
        "icon_class":      "fas fa-cut",
        "display_order":   7,
        "clip_context_text": "professional hair stylist braiding natural hair salon Nigeria",
        "description": (
            "Talented hair stylists specialising in braiding, weaves, natural "
            "hair, colouring, and grooming for Nigerian and international clients."
        ),
        "skills": [
            "Bridal & Event Styling", "Loctician Services",
            "Hair Colouring & Balayage", "Mobile Styling",
            "Barbering & Men's Grooming", "Wig Making & Installation",
            "Scalp Treatment & Trichology", "Hair Training & Instruction",
        ],
        "jobs": [
            {
                "title": "Bridal Hair Specialist — Luxury Bridal Studio (Lekki, Lagos)",
                "description": (
                    "Join an upscale bridal studio in Lekki as the lead bridal hair "
                    "stylist. Responsibilities include client consultations, trial runs, "
                    "and on-the-day styling for up to 6 bridal parties per weekend. "
                    "Portfolio of editorial and bridal work required. Must be available "
                    "for early-morning call times on Saturdays."
                ),
                "job_type": Job.JobType.PART_TIME,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 50_000, "pay_max": 100_000,
                "state": "lagos", "lga": "Lekki", "slots": 1,
            },
            {
                "title": "Loctician & Natural Hair Specialist — Afrocentric Studio (Abuja)",
                "description": (
                    "Practise loc installation (freeform, sisterlocks, traditional), "
                    "retightening, loc repair, and natural hair styling at a "
                    "specialist natural hair salon in Wuse 2, Abuja. "
                    "Sisterlock certification preferred. Full-time in-studio role "
                    "with commission structure."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 80_000, "pay_max": 130_000,
                "state": "fct", "lga": "Wuse", "slots": 2,
            },
            {
                "title": "Hair Colourist — Premium Salon (Victoria Island, Lagos)",
                "description": (
                    "Specialise in balayage, colour correction, ombre, and global tint "
                    "services for a high-end clientele on Victoria Island. Schwarzkopf "
                    "or Wella certification required. Participate in quarterly "
                    "educational sessions. Commission on retail product sales."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 100_000, "pay_max": 160_000,
                "state": "lagos", "lga": "Victoria Island", "slots": 1,
            },
            {
                "title": "Mobile Hair Stylist — Corporate Client Retainer (Lagos)",
                "description": (
                    "Provide mobile hair-styling services to a roster of corporate "
                    "executives and their families across Lagos Island, Victoria Island, "
                    "and Ikoyi. Flexible scheduling; own kit and transport required. "
                    "Ability to style diverse hair textures and lengths essential."
                ),
                "job_type": Job.JobType.PART_TIME,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 25_000, "pay_max": 50_000,
                "state": "lagos", "lga": "Lagos Island", "slots": 2,
            },
            {
                "title": "Men's Grooming Specialist — Barbershop Chain Manager (Abuja)",
                "description": (
                    "Manage the day-to-day operations of a 3-chair barbershop in "
                    "Garki, Abuja: client appointments, staff scheduling, inventory, "
                    "and quality control. Must be a skilled barber (fades, tapers, "
                    "beard sculpting) as well as competent in people management."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 100_000, "pay_max": 150_000,
                "state": "fct", "lga": "Garki", "slots": 1,
            },
            {
                "title": "Wig Maker & Closure/Frontal Specialist — Hair Boutique (Lekki)",
                "description": (
                    "Construct bespoke human-hair wigs, closures, and frontal units "
                    "to client measurement for a boutique hair studio in Lekki. "
                    "Ventilate lace, customise hairlines, and apply secure install "
                    "methods (glue, tape, sew-in). Own ventilating needle and tools "
                    "required."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 90_000, "pay_max": 140_000,
                "state": "lagos", "lga": "Lekki", "slots": 2,
            },
            {
                "title": "Scalp Treatment & Trichology Technician — Hair Clinic (Lagos)",
                "description": (
                    "Assess and treat scalp conditions (alopecia, dandruff, seborrheic "
                    "dermatitis) at a dedicated hair and scalp clinic in Ikeja. "
                    "Administer LLLT sessions, scalp massages, and topical treatments. "
                    "Trichology diploma or equivalent certificate required."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 120_000, "pay_max": 180_000,
                "state": "lagos", "lga": "Ikeja", "slots": 1,
            },
            {
                "title": "Hair Stylist Trainer — Vocational Skills Centre (Ibadan)",
                "description": (
                    "Deliver a 10-week practical hair styling curriculum to 25 trainees "
                    "at a vocational centre in Ibadan under a state empowerment "
                    "programme. Topics: braiding, weave application, relaxers, "
                    "and salon business basics. NVQ Level 3 or equivalent required."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 80_000, "pay_max": 120_000,
                "state": "oyo", "lga": "Ibadan North", "slots": 1,
            },
        ],
    },

    # ── 9. HVAC TECHNICIAN (8 jobs) ───────────────────────────────────────────
    {
        "name": "HVAC Technician",
        "slug": "hvac-technician",
        "icon_class":      "fas fa-wind",
        "display_order":   8,
        "clip_context_text": "HVAC air conditioning refrigeration installation technician Nigeria",
        "description": (
            "Qualified HVAC technicians for air conditioning installation, "
            "chiller servicing, cold room construction, and ventilation systems."
        ),
        "skills": [
            "Chiller Plant Operation & Maintenance", "VRF/VRV System Installation",
            "Cold Room Construction & Commissioning", "HVAC Commissioning & Balancing",
            "Industrial Ductwork Fabrication", "Refrigerant Recovery & Handling",
            "Air Curtain & Ventilation Installation", "Heat Pump Water Heaters",
        ],
        "jobs": [
            {
                "title": "Chiller Plant Technician — 5-Star Hotel (Eko Hotel, Lagos)",
                "description": (
                    "Operate, maintain, and troubleshoot Carrier and York centrifugal "
                    "chiller plants (2 × 600 TR) serving a 5-star hotel in Lagos. "
                    "Responsibilities include water treatment checks, efficiency "
                    "logging, preventive maintenance, and emergency fault response. "
                    "F-Gas / refrigerant handling certification required."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 200_000, "pay_max": 300_000,
                "state": "lagos", "lga": "Lagos Island", "slots": 2,
            },
            {
                "title": "VRF/VRV System Installer — Office Tower (Abuja)",
                "description": (
                    "Install a Daikin or Mitsubishi VRF system (48 indoor units, "
                    "4 outdoor units) across 8 floors of an office building in "
                    "Central Abuja. Covers refrigerant pipework, condensate drainage, "
                    "electrical connections, and commissioning. Manufacturer training "
                    "certificate preferred."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 3_000_000, "pay_max": 4_500_000,
                "state": "fct", "lga": "Central Business District", "slots": 3,
            },
            {
                "title": "Walk-In Cold Room Installer — Supermarket Chain (Lagos)",
                "description": (
                    "Supply and install 6 modular cold rooms (0°C to –20°C ranges) "
                    "across three supermarket branches in Lagos. Covers panel assembly, "
                    "refrigeration plant installation, electrical connections, and "
                    "temperature logger commissioning. 12-month parts warranty required."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 2_500_000, "pay_max": 3_800_000,
                "state": "lagos", "lga": "Ikeja", "slots": 2,
            },
            {
                "title": "HVAC Commissioning & Air Balancing Engineer — Hospital (PH)",
                "description": (
                    "Commission and air-balance AHUs, FCUs, VAV boxes, and ventilation "
                    "systems in a new private hospital in Port Harcourt. Produce "
                    "commissioning sheets, air-change calculations, and HEPA filter "
                    "test reports for theatre and isolation rooms. BSRIA training preferred."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 30_000, "pay_max": 50_000,
                "state": "rivers", "lga": "Port Harcourt", "slots": 1,
            },
            {
                "title": "Industrial Ductwork Fabricator & Installer — Factory (Sagamu)",
                "description": (
                    "Fabricate galvanised rectangular and spiral ductwork and install "
                    "a process extraction and general ventilation system for a "
                    "pharmaceutical factory in Sagamu. Work from M&E drawings; "
                    "includes dampers, flexible connections, and silencers."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 1_500_000, "pay_max": 2_200_000,
                "state": "ogun", "lga": "Sagamu", "slots": 3,
            },
            {
                "title": "Refrigerant Recovery & Retrofit Technician — Lagos Properties",
                "description": (
                    "Safely recover R-22 from ageing AC systems, replace with R-410A "
                    "or R-32 compatible units, and recommission for a property "
                    "management company with 400+ units in Lagos. "
                    "Refrigerant handling certificate and recovery cylinders required."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 120_000, "pay_max": 180_000,
                "state": "lagos", "lga": "Lekki", "slots": 2,
            },
            {
                "title": "Air Curtain & Kitchen Ventilation Installer — Food Factory (Kano)",
                "description": (
                    "Install industrial air curtains, canopy extraction hoods, "
                    "make-up air units, and exhaust fans in a new food-processing "
                    "plant in Kano. Coordinate with kitchen-equipment suppliers; "
                    "provide grease duct fire suppression connection."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 900_000, "pay_max": 1_400_000,
                "state": "kano", "lga": "Kano Municipal", "slots": 2,
            },
            {
                "title": "Heat Pump Water Heater Installer — Hotel Refurbishment (Abuja)",
                "description": (
                    "Replace electric immersion heaters with air-source heat pump "
                    "water heaters across 80 hotel rooms in Abuja. Includes pipework "
                    "reconfiguration, electrical supply upgrade, and commissioning. "
                    "Energy savings report comparing old vs new system expected."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 1_200_000, "pay_max": 1_800_000,
                "state": "fct", "lga": "Garki", "slots": 2,
            },
        ],
    },

    # ── 10. AUTO MECHANIC (9 jobs) ────────────────────────────────────────────
    {
        "name": "Auto Mechanic",
        "slug": "auto-mechanic",
        "icon_class":      "fas fa-car",
        "display_order":   9,
        "clip_context_text": "auto mechanic vehicle repair servicing workshop Nigeria",
        "description": (
            "Experienced auto mechanics for vehicle servicing, engine repair, "
            "diagnostics, and fleet maintenance across Nigeria."
        ),
        "skills": [
            "EV & Hybrid Powertrain Servicing", "Heavy Vehicle & Truck Mechanics",
            "Automatic Transmission Overhaul", "Wheel Alignment & Tyre Fitting",
            "Diesel Injection & Common Rail", "Auto Electrical & CAN Bus",
            "Panel Beating & Spray Painting", "Performance Tuning",
            "Auto AC Servicing", "Fleet Preventive Maintenance",
        ],
        "jobs": [
            {
                "title": "Hybrid & Electric Vehicle Technician — Dealership (Lagos)",
                "description": (
                    "Service and repair Toyota hybrid vehicles (Camry, Corolla, "
                    "Sienna) and any BEV stock at a franchise dealership in Ikeja. "
                    "Must hold Toyota HEV certification or manufacturer-equivalent. "
                    "Training on new EV models provided; tool set supplied by dealership."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 180_000, "pay_max": 260_000,
                "state": "lagos", "lga": "Ikeja", "slots": 2,
            },
            {
                "title": "Heavy Truck & Equipment Mechanic — Haulage Company (Kano)",
                "description": (
                    "Maintain a fleet of 40 Mack and Volvo long-haul trucks at a "
                    "logistics base in Kano. Carry out scheduled service, engine "
                    "overhauls, brake and suspension repairs, and tyre management. "
                    "Cummins or Volvo engine training certificate preferred."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 150_000, "pay_max": 220_000,
                "state": "kano", "lga": "Kano Municipal", "slots": 3,
            },
            {
                "title": "Automatic Transmission Specialist — Gearbox Workshop (PH)",
                "description": (
                    "Diagnose, rebuild, and remanufacture automatic transmissions "
                    "(ZF, Aisin, CVT) at a specialist gearbox workshop in Port "
                    "Harcourt. Use electronic scan tools and hydraulic bench test "
                    "equipment. Minimum 5 years transmission-only experience required."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 160_000, "pay_max": 240_000,
                "state": "rivers", "lga": "Port Harcourt", "slots": 2,
            },
            {
                "title": "Tyre & Wheel Alignment Technician — Fleet Company (Ikeja, Lagos)",
                "description": (
                    "Manage tyre fitting, balancing, rotation, and 3D wheel alignment "
                    "for a 120-vehicle corporate fleet based in Ikeja. Operate "
                    "Hunter or Hofmann alignment and balancing equipment. "
                    "Tyre pressure monitoring system servicing included."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 100_000, "pay_max": 150_000,
                "state": "lagos", "lga": "Ikeja", "slots": 2,
            },
            {
                "title": "Diesel Common Rail Injection Technician — Workshop (Abuja)",
                "description": (
                    "Test, clean, and recalibrate common rail diesel injectors and "
                    "high-pressure fuel pumps using Bosch EPS 815 or equivalent test "
                    "bench at a specialist diesel workshop in Kubwa, Abuja. "
                    "Hands-on CR system training certificate required."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 120_000, "pay_max": 180_000,
                "state": "fct", "lga": "Kubwa", "slots": 1,
            },
            {
                "title": "Auto Electrician — Bus Assembly Plant (Lagos)",
                "description": (
                    "Install and test full electrical harnesses (body, chassis, "
                    "dashboard, lighting, CAN bus) on locally assembled city buses "
                    "at a plant in Ijora, Lagos. Read wiring diagrams; terminate "
                    "connectors and carry out road-ready PDI checks on each vehicle."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 120_000, "pay_max": 180_000,
                "state": "lagos", "lga": "Lagos Island", "slots": 4,
            },
            {
                "title": "Panel Beater & Insurance Repair Technician — Workshop (Ibadan)",
                "description": (
                    "Carry out insurance-approved panel beating, MIG welding, and "
                    "spray painting repairs on accident-damaged vehicles for an "
                    "assessor-approved bodyshop in Ibadan. Work to insurer photo "
                    "estimates; achieve cycle-time targets. Waterborne paint system."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 100_000, "pay_max": 160_000,
                "state": "oyo", "lga": "Ibadan North", "slots": 2,
            },
            {
                "title": "Performance Tuning & Dyno Technician — Motorsport Shop (Lagos)",
                "description": (
                    "Map ECUs (on a Dynapack or Dynojet chassis dyno), install "
                    "performance parts, and fault-diagnose modified vehicles for "
                    "a high-performance car shop in Apapa. Tuning software experience "
                    "(ECUTEK, Haltech, or MoTeC) required; racing circuit familiarity "
                    "a strong advantage."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 180_000, "pay_max": 280_000,
                "state": "lagos", "lga": "Apapa", "slots": 1,
            },
            {
                "title": "Automotive AC Service Technician — Fleet Management Company (Abuja)",
                "description": (
                    "Service, regas, and repair air-conditioning systems across a "
                    "200-vehicle government fleet managed from Abuja. Operate AC "
                    "recovery/recharge machines; diagnose leaks with electronic "
                    "detectors and UV dye. AC handler certification required."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 100_000, "pay_max": 150_000,
                "state": "fct", "lga": "Garki", "slots": 2,
            },
        ],
    },

    # ── 11. TAILOR (8 jobs) ───────────────────────────────────────────────────
    {
        "name": "Tailor",
        "slug": "tailor",
        "icon_class":      "fas fa-tshirt",
        "display_order":   10,
        "clip_context_text": "expert tailor clothing alterations fashion Nigeria",
        "description": (
            "Skilled tailors and seamstresses for bespoke clothing, alterations, "
            "corporate uniforms, and traditional Nigerian attire."
        ),
        "skills": [
            "Corporate Uniform Tailoring", "Traditional Attire Construction",
            "Pattern Cutting & Grading", "Wedding Gown Making",
            "Children's Clothing", "Curtain & Soft Furnishing Making",
            "Industrial Protective Clothing", "Fashion Lecturing",
        ],
        "jobs": [
            {
                "title": "Corporate Uniform Tailor — Bank Staff Wardrobe (Lagos)",
                "description": (
                    "Produce an annual run of 1,200 staff uniforms (shirts, skirts, "
                    "trousers, blazers) for a commercial bank's Lagos branches. "
                    "Work from tech packs and size charts; ensure consistent sizing "
                    "and colour match. Workshop in Yaba with industrial sewing machines."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 2_000_000, "pay_max": 3_000_000,
                "state": "lagos", "lga": "Yaba", "slots": 4,
            },
            {
                "title": "Traditional Attire Specialist — Aso-ebi Studio (Abuja)",
                "description": (
                    "Cut and sew Aso-oke, Ankara, Adire, and Damask fabric into "
                    "traditional outfits (buba, iro, gele) for event groups at a "
                    "specialist studio in Abuja. Handle rush orders around owambe "
                    "seasons. Speed and consistency across identical group outfits "
                    "critical."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 70_000, "pay_max": 110_000,
                "state": "fct", "lga": "Garki", "slots": 3,
            },
            {
                "title": "Pattern Cutter & Grader — Garment Factory (Apapa, Lagos)",
                "description": (
                    "Create and grade master patterns for a mid-scale garment factory "
                    "in Apapa producing casualwear for the domestic market. "
                    "Operate a digital pattern software (Lectra or Optitex) preferred; "
                    "manual grading skill acceptable. Marker planning for fabric "
                    "efficiency required."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 100_000, "pay_max": 150_000,
                "state": "lagos", "lga": "Apapa", "slots": 2,
            },
            {
                "title": "Wedding Gown Seamstress — Luxury Bridal Boutique (VI, Lagos)",
                "description": (
                    "Construct and fit bespoke wedding gowns, bridesmaids' dresses, "
                    "and mother-of-the-bride outfits for a high-end bridal boutique "
                    "on Victoria Island. Experience with structured corseted bodices, "
                    "lace insertion, and French seams required. Client fittings on "
                    "weekends."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 120_000, "pay_max": 180_000,
                "state": "lagos", "lga": "Victoria Island", "slots": 1,
            },
            {
                "title": "Children's Clothing Production Tailor — Kids Fashion Brand (Lagos)",
                "description": (
                    "Produce children's clothing (0–12 years) for a fast-growing "
                    "Nigerian kidswear brand sold online and in pop-up stores. "
                    "Work from tech packs to tight weekly production targets. "
                    "Experience finishing jersey, cotton twill, and denim essential."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 80_000, "pay_max": 120_000,
                "state": "lagos", "lga": "Surulere", "slots": 3,
            },
            {
                "title": "Curtain & Soft Furnishing Maker — Interior Design Company (Lagos)",
                "description": (
                    "Measure, cut, and sew made-to-measure curtains, Roman blinds, "
                    "cushion covers, and upholstery panels for a boutique interior "
                    "design firm in Ikoyi. Work on domestic and hospitality projects. "
                    "Own lockstitch and overlocking machines required."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 90_000, "pay_max": 140_000,
                "state": "lagos", "lga": "Ikoyi", "slots": 2,
            },
            {
                "title": "Industrial Protective Clothing Stitcher — Safety Gear Company (PH)",
                "description": (
                    "Manufacture FR coveralls, high-vis vests, and chemical-resistant "
                    "PPE garments for the oil and gas market. Sew to EN/ISO standards; "
                    "handle Nomex and Tencate Tecasafe fabrics. Quality-check seam "
                    "strength with pull-test gauge. Production targets enforced."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 90_000, "pay_max": 130_000,
                "state": "rivers", "lga": "Port Harcourt", "slots": 4,
            },
            {
                "title": "Fashion Design & Garment Construction Lecturer — Polytechnic (Ogun)",
                "description": (
                    "Teach fashion design, pattern making, and garment technology to "
                    "ND and HND students at a polytechnic in Ogun State. Develop "
                    "coursework, supervise studio projects, and liaise with industry "
                    "for graduate placements. OND/HND plus teaching experience required."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 100_000, "pay_max": 160_000,
                "state": "ogun", "lga": "Abeokuta South", "slots": 1,
            },
        ],
    },

    # ── 12. TILER (8 jobs) ────────────────────────────────────────────────────
    {
        "name": "Tiler",
        "slug": "tiler",
        "icon_class":      "fas fa-th",
        "display_order":   11,
        "clip_context_text": "professional tiler floor wall tile installation Nigeria",
        "description": (
            "Expert tilers for floor, wall, pool, and roof tile installation across "
            "residential, commercial, and hospitality projects in Nigeria."
        ),
        "skills": [
            "Marble & Natural Stone Flooring", "Pool & Wet Area Tiling",
            "Roof Tile Fixing", "Mosaic Art & Installation",
            "Large Format Porcelain Tiling", "Wall & Fascia Tiling",
            "Outdoor Patio & Decking Tiles", "Tile Restoration & Regrouting",
        ],
        "jobs": [
            {
                "title": "Marble Floor Installer — Luxury Villa (Maitama, Abuja)",
                "description": (
                    "Supply and lay 1,200 m² of Carrara and Calacatta marble tiles "
                    "(800 × 800 mm) throughout a luxury villa in Maitama. Use "
                    "levelling-system clips for zero-lippage finish. Cut around "
                    "curved walls and inlaid feature medallions. Must have portfolio "
                    "of completed marble projects."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 2_000_000, "pay_max": 3_000_000,
                "state": "fct", "lga": "Maitama", "slots": 2,
            },
            {
                "title": "Pool & Wet-Area Mosaic Tiler — Hotel (Lekki, Lagos)",
                "description": (
                    "Tile the pool shell, water features, and changing-room wet areas "
                    "of a 5-star hotel in Lekki with glass mosaic and porcelain tiles. "
                    "Apply Mapei Kerapoxy epoxy grout in pool areas. Hydraulic test "
                    "sign-off required before water filling."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 1_500_000, "pay_max": 2_200_000,
                "state": "lagos", "lga": "Lekki", "slots": 2,
            },
            {
                "title": "Concrete Roof Tile Fixer — 60-Unit Estate (Ibeju-Lekki)",
                "description": (
                    "Fix interlocking concrete roof tiles on pitched roofs of 60 "
                    "terrace houses in a new estate in Ibeju-Lekki. Include ridge "
                    "tiles, verge trims, and valley flashings. Supply own safety "
                    "harness; materials provided on site."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 1_200_000, "pay_max": 1_800_000,
                "state": "lagos", "lga": "Ibeju-Lekki", "slots": 4,
            },
            {
                "title": "Mosaic Artist & Tiler — Boutique Hotel Feature Wall (Lagos)",
                "description": (
                    "Create a hand-set glass and ceramic mosaic mural (8 m × 3 m) "
                    "in the lobby of a boutique hotel on Lagos Island. Work from "
                    "a digital artwork cartoon; cut tiles to shape and set in custom "
                    "pattern. Must supply examples of previous mosaic art commissions."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 600_000, "pay_max": 1_000_000,
                "state": "lagos", "lga": "Lagos Island", "slots": 1,
            },
            {
                "title": "Large Format Porcelain Tiler — Bank HQ Showroom (Abuja)",
                "description": (
                    "Lay 1,200 × 600 mm full-body porcelain tiles using a suction "
                    "cup handler and levelling system across 2,000 m² of a bank "
                    "headquarters in Abuja CBD. Perfect lippage control and diagonal "
                    "joint layout. Tile saw and levelling kit required."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 1_800_000, "pay_max": 2_600_000,
                "state": "fct", "lga": "Central Business District", "slots": 3,
            },
            {
                "title": "Supermarket Wall & Column Tiler — Retail Chain Fit-Out (Lagos)",
                "description": (
                    "Fix ceramic wall tiles on service counters, column cladding, "
                    "and food preparation areas across 5 new supermarket branches "
                    "in Lagos. Work to tight programme alongside other trades. "
                    "Non-slip and food-safe tile specifications supplied by client."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 900_000, "pay_max": 1_400_000,
                "state": "lagos", "lga": "Ikeja", "slots": 4,
            },
            {
                "title": "Outdoor Patio & Decking Tiler — Waterfront Estate (PH GRA)",
                "description": (
                    "Lay non-slip external porcelain tiles (600 × 600 mm, R11 rating) "
                    "on terraces, pool surrounds, and garden paths at 8 waterfront "
                    "properties in Port Harcourt GRA. Use rapid-set flexible adhesive "
                    "and movement joints at 3 m centres."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 700_000, "pay_max": 1_100_000,
                "state": "rivers", "lga": "Port Harcourt", "slots": 2,
            },
            {
                "title": "Tile Restoration & Regrouting Specialist — Property Management (Lagos)",
                "description": (
                    "Restore tiled floors and walls across a portfolio of 80 "
                    "residential and commercial properties managed in Lagos: remove "
                    "stained grout, regrout, seal, and re-polish natural stone. "
                    "Diamond-polishing and crystallisation equipment required. "
                    "Own vehicle essential."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 90_000, "pay_max": 140_000,
                "state": "lagos", "lga": "Lekki", "slots": 2,
            },
        ],
    },

    # ── 13. ALUMINIUM & GLASS INSTALLER (8 jobs) ──────────────────────────────
    {
        "name": "Aluminium & Glass Installer",
        "slug": "aluminum-glass-installer",
        "icon_class":      "fas fa-window-maximize",
        "display_order":   12,
        "clip_context_text": "aluminium glass installer windows doors curtain wall Nigeria",
        "description": (
            "Specialist aluminium and glass installers for curtain walling, "
            "shopfronts, partitions, shower enclosures, and structural glazing."
        ),
        "skills": [
            "Curtain Wall System Installation", "Glass Partition Systems",
            "Automatic Sliding Door Installation", "Structural Glazing",
            "Louvre Blade Installation", "Shopfront Aluminium Framing",
            "Shower Enclosure & Frameless Glass", "Skylight & Roof Glazing",
        ],
        "jobs": [
            {
                "title": "Curtain Wall Installer — High-Rise Office (Broad Street, Lagos)",
                "description": (
                    "Install unitised aluminium curtain wall panels on a 22-storey "
                    "commercial tower on Broad Street, Lagos. Erect, seal, and test "
                    "each panel to watertightness specification. Work on a jump scaffold "
                    "system; anchor points and safety plan provided by principal contractor."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 30_000, "pay_max": 50_000,
                "state": "lagos", "lga": "Lagos Island", "slots": 6,
            },
            {
                "title": "Glass Partition Installer — Co-working Space (Abuja)",
                "description": (
                    "Install demountable frameless glass partition systems, solid-core "
                    "glazed doors, and manifestation film across 3 floors of a "
                    "co-working space in Wuse 2. Work from M&E coordination drawings; "
                    "coordinate with ceiling and floor trades. 3-day lead time required."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 1_200_000, "pay_max": 1_800_000,
                "state": "fct", "lga": "Wuse", "slots": 2,
            },
            {
                "title": "Automatic Sliding Door Installer — Supermarket (Ikeja, Lagos)",
                "description": (
                    "Supply and install 8 sets of ASSA ABLOY or Dorma automatic "
                    "sliding door systems (sensor, operator, track, safety beam) "
                    "at a supermarket in Ikeja. Commission each pair and set "
                    "opening/closing forces to EN 16005 standard."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 800_000, "pay_max": 1_200_000,
                "state": "lagos", "lga": "Ikeja", "slots": 2,
            },
            {
                "title": "Structural Glazing Technician — Airport Terminal (Abuja)",
                "description": (
                    "Apply structural silicone sealant and fix structural glazing "
                    "panels to a new terminal building at Nnamdi Azikiwe Airport, "
                    "Abuja. Work from structural engineer's load calculations; "
                    "silicone bonding must comply with ETAG 002. "
                    "Height and silicone application experience required."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 30_000, "pay_max": 50_000,
                "state": "fct", "lga": "Lugbe", "slots": 4,
            },
            {
                "title": "Aluminium Louvre Blade & Brise Soleil Installer — School (Enugu)",
                "description": (
                    "Fabricate and install aluminium louvre blade sun-shading systems "
                    "on the south and west facades of 8 classroom blocks at a secondary "
                    "school in Enugu. Angle louvres to optimise natural ventilation "
                    "and shading per architect's design."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 700_000, "pay_max": 1_000_000,
                "state": "enugu", "lga": "Enugu North", "slots": 3,
            },
            {
                "title": "Shopfront Aluminium Fitter — New Retail Complex (Kano)",
                "description": (
                    "Fabricate and install aluminium shopfront systems (framing, "
                    "toughened glass infill, top-hung doors, and canopy brackets) "
                    "for 25 retail units in a shopping complex in Kano. "
                    "Ensure weatherseal integrity; supply installation certification."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 1_500_000, "pay_max": 2_200_000,
                "state": "kano", "lga": "Kano Municipal", "slots": 3,
            },
            {
                "title": "Frameless Shower Enclosure Installer — Luxury Homes (Abuja)",
                "description": (
                    "Measure, cut, and install frameless 10 mm toughened glass shower "
                    "enclosures, wet room screens, and pivot doors in luxury bathrooms "
                    "across 20 properties in Abuja. Use professional channel, patch "
                    "fittings, and TESA or similar seals."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 600_000, "pay_max": 950_000,
                "state": "fct", "lga": "Maitama", "slots": 2,
            },
            {
                "title": "Skylight & Rooflights Installer — Factory (Sagamu, Ogun)",
                "description": (
                    "Install factory-made aluminium rooflights (continuous barrel vault "
                    "and pyramid units) on the roof of a logistics warehouse in Sagamu. "
                    "Ensure correct upstand height, weathering flashing, and condensation "
                    "drainage. Work from structural drawings; cherry picker available."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 900_000, "pay_max": 1_400_000,
                "state": "ogun", "lga": "Sagamu", "slots": 2,
            },
        ],
    },

    # ── 14. GENERATOR TECHNICIAN (8 jobs) ─────────────────────────────────────
    {
        "name": "Generator Technician",
        "slug": "generator-technician",
        "icon_class":      "fas fa-plug",
        "display_order":   13,
        "clip_context_text": "generator technician diesel maintenance repair Nigeria power",
        "description": (
            "Expert generator technicians for diesel and gas generator maintenance, "
            "overhaul, ATS installation, and emergency power systems in Nigeria."
        ),
        "skills": [
            "Fleet Generator Maintenance", "Gas Generator Installation",
            "Standby Power Commissioning", "Generator Rewinding",
            "Load Bank Testing", "Acoustic Enclosure & Exhaust Installation",
            "Emergency Power Systems Engineering", "Generator Panel & Controls",
        ],
        "jobs": [
            {
                "title": "Diesel Generator Fleet Engineer — Telecom Company (Lagos)",
                "description": (
                    "Manage preventive and reactive maintenance on a fleet of 60 "
                    "diesel generators (20–500 kVA) at telecom base stations across "
                    "Lagos State. Maintain fuel logs, service records, and KPI reports. "
                    "Field-based role; company pickup truck provided."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 180_000, "pay_max": 260_000,
                "state": "lagos", "lga": "Ikeja", "slots": 2,
            },
            {
                "title": "Natural Gas Generator Installer — Industrial Estate (Warri, Delta)",
                "description": (
                    "Commission two Himoinsa 500 kVA natural-gas generator sets "
                    "for a factory in Warri. Connect gas supply, exhaust system, "
                    "ATS panel, and site synchronisation relay. Full factory acceptance "
                    "test documentation required. Gas Safe / DPR registration needed."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 1_500_000, "pay_max": 2_200_000,
                "state": "delta", "lga": "Warri South", "slots": 2,
            },
            {
                "title": "Standby Generator Commissioning Engineer — Hospital (Abuja)",
                "description": (
                    "Commission a 1,000 kVA Perkins standby generator set with "
                    "a paralleling ATS and a 12-hour fuel tank for a private hospital "
                    "in Garki, Abuja. Carry out full load test, time-to-transfer test, "
                    "and produce a commissioning report and O&M manual."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 800_000, "pay_max": 1_200_000,
                "state": "fct", "lga": "Garki", "slots": 1,
            },
            {
                "title": "Generator Stator & Rotor Rewinding Specialist — Workshop (Lagos)",
                "description": (
                    "Rewind alternator stators and rotors for diesel generators (up to "
                    "500 kVA) at an electrical rewind workshop in Mushin, Lagos. "
                    "Strip, wind, varnish, and test output voltage, insulation "
                    "resistance, and waveform distortion."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 100_000, "pay_max": 150_000,
                "state": "lagos", "lga": "Mushin", "slots": 2,
            },
            {
                "title": "Load Bank Test Technician — Data Centre (Lekki, Lagos)",
                "description": (
                    "Conduct annual full-load and step-load testing on 2 × 2,000 kVA "
                    "diesel generator sets at a Tier III data centre in Lekki using "
                    "a resistive-reactive load bank. Issue test certificates "
                    "and recommendations for fuel and cooling upgrades."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 400_000, "pay_max": 600_000,
                "state": "lagos", "lga": "Lekki", "slots": 1,
            },
            {
                "title": "Generator Acoustic Enclosure & Exhaust Fitter — Estate (Lekki)",
                "description": (
                    "Design and build acoustic enclosures and exhaust silencer "
                    "systems for 10 community generators in a Lekki gated estate "
                    "to meet Lagos State noise regulations (<70 dB at 7 m). "
                    "Fabricate steel housing, fit acoustic lining, and route exhaust "
                    "stacks to safe exit points."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 700_000, "pay_max": 1_100_000,
                "state": "lagos", "lga": "Lekki", "slots": 2,
            },
            {
                "title": "Airport Emergency Power Systems Engineer — Abuja",
                "description": (
                    "Maintain and test all emergency and standby power systems "
                    "(generators, UPS, static inverters, rectifiers) at Nnamdi Azikiwe "
                    "International Airport under an annual maintenance contract. "
                    "24-hour on-call rota; airside pass and security vetting required."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 250_000, "pay_max": 380_000,
                "state": "fct", "lga": "Lugbe", "slots": 2,
            },
            {
                "title": "Generator Control Panel & PLC Technician — Factory (Kano)",
                "description": (
                    "Programme and maintain Deepsea Electronics DSE 8610 and "
                    "ComAp InteliGen control modules for 4 generator sets at a "
                    "manufacturing plant in Kano. Configure load sharing, AMF, and "
                    "SCADA interface. Fault-find PLC and relay logic."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 150_000, "pay_max": 220_000,
                "state": "kano", "lga": "Kano Municipal", "slots": 1,
            },
        ],
    },

    # ── 15. ROOFER (8 jobs) ───────────────────────────────────────────────────
    {
        "name": "Roofer",
        "slug": "roofer",
        "icon_class":      "fas fa-home",
        "display_order":   14,
        "clip_context_text": "roofer roofing contractor waterproofing sheet metal Nigeria",
        "description": (
            "Experienced roofers for metal, tile, flat, and green roof systems, "
            "waterproofing, guttering, and maintenance across Nigeria."
        ),
        "skills": [
            "Standing Seam Metal Roofing", "Torch-On Flat Roofing",
            "Green Roof Systems", "Roof Insulation",
            "Concrete & Clay Roof Tile Fixing", "Industrial Roof Drainage",
            "Roof Safety Anchors & Walkways", "Thatch & Traditional Roofing",
        ],
        "jobs": [
            {
                "title": "Aluminium Standing Seam Roofer — Commercial Building (Lekki)",
                "description": (
                    "Install a pre-painted aluminium standing seam roof system on "
                    "a 4,000 m² commercial building in Lekki Free Zone. Use a "
                    "roll-forming machine on site for clip-fixed seam panels. "
                    "Ridge, valley, and eaves flashings to watertight standard. "
                    "10-year weathertight warranty certificate required."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 5_000_000, "pay_max": 7_500_000,
                "state": "lagos", "lga": "Lekki", "slots": 4,
            },
            {
                "title": "Torch-On Flat Roof Waterproof Membrane Installer — Warehouse (Ogun)",
                "description": (
                    "Apply a two-layer SBS modified bitumen torch-on membrane system "
                    "to an 8,000 m² flat roof of a logistics warehouse in Sagamu. "
                    "Includes insulation board, vapour barrier, and aluminium-faced "
                    "capsheet. Watertight hose test certification required."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 3_500_000, "pay_max": 5_000_000,
                "state": "ogun", "lga": "Sagamu", "slots": 4,
            },
            {
                "title": "Green Roof Installer — Eco-Hotel (Abuja)",
                "description": (
                    "Construct an extensive green roof (sedum mat, substrate, drainage "
                    "layer, root barrier, and waterproof membrane) on the roof of a "
                    "boutique eco-hotel in Maitama, Abuja. Coordinate with structural "
                    "engineer on load limits and irrigation design."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 2_000_000, "pay_max": 3_000_000,
                "state": "fct", "lga": "Maitama", "slots": 2,
            },
            {
                "title": "Cold Storage Roof Insulation Installer — Logistics Hub (Lagos)",
                "description": (
                    "Install PIR rigid insulation boards (100–200 mm) and vapour-"
                    "control layers on the cold store roof of a logistics hub in "
                    "Apapa. Ensure thermal bridge-free junction details. "
                    "Issued with specific fixing schedule by M&E consultant."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 1_200_000, "pay_max": 1_800_000,
                "state": "lagos", "lga": "Apapa", "slots": 3,
            },
            {
                "title": "Clay Roof Tile Fixer — Heritage Building Restoration (Ibadan)",
                "description": (
                    "Re-fix and replace handmade clay roof tiles on a Grade 1 listed "
                    "colonial building in Ibadan. Source matching replacement tiles; "
                    "use traditional lime mortar bedding. Work with heritage architect "
                    "and historic preservation officer."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 800_000, "pay_max": 1_200_000,
                "state": "oyo", "lga": "Ibadan North", "slots": 2,
            },
            {
                "title": "Industrial Roof Drainage & Siphonic System Installer — PH",
                "description": (
                    "Design and install a siphonic roof drainage system for a 12,000 m² "
                    "factory roof in Port Harcourt Industrial Layout. Size outlets, "
                    "pipe runs, and de-siphoning chambers to BS EN 12056-3. "
                    "Coordinate with structural engineer for pipe supports."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 1_500_000, "pay_max": 2_200_000,
                "state": "rivers", "lga": "Port Harcourt", "slots": 2,
            },
            {
                "title": "Roof Safety Anchor & Walkway Installer — Office Complex (Lagos)",
                "description": (
                    "Install BS 7883 compliant roof anchor points, ridgeway safety "
                    "wire line, and anti-slip walkway matting on 6 commercial roofs "
                    "in Lagos for a property management company. Supply test "
                    "certificates and site-specific rescue plan for each roof."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 500_000, "pay_max": 800_000,
                "state": "lagos", "lga": "Ikeja", "slots": 1,
            },
            {
                "title": "Thatch & Traditional Roof Installer — Eco-Resort (Osun State)",
                "description": (
                    "Install elephant grass and palm-leaf thatched roofs on 20 "
                    "eco-lodge chalets at a tourist resort in Oshogbo, Osun State. "
                    "Apply fire-retardant treatment; ensure pitch and overhang drain "
                    "clear of walls. Local traditional knowledge of thatching techniques "
                    "required."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 600_000, "pay_max": 950_000,
                "state": "osun", "lga": "Oshogbo", "slots": 3,
            },
        ],
    },

    # ── 16. SECURITY INSTALLER (8 jobs) ───────────────────────────────────────
    {
        "name": "Security Installer",
        "slug": "security-installer",
        "icon_class":      "fas fa-shield-alt",
        "display_order":   15,
        "clip_context_text": "security system installer CCTV alarm access control Nigeria",
        "description": (
            "Professional security system installers for CCTV, access control, "
            "alarms, electric fencing, and integrated security solutions in Nigeria."
        ),
        "skills": [
            "Video Analytics & AI Surveillance", "Video Intercom Installation",
            "Electric Fence & PIDS", "Safe & Vault Installation",
            "Fire Suppression Systems", "Panic Button Systems",
            "Turnstile & Speed Gate Installation", "Security System Auditing",
        ],
        "jobs": [
            {
                "title": "Video Analytics & AI Camera Specialist — Bank Head Office (Lagos)",
                "description": (
                    "Deploy an AI-powered video analytics platform (crowd counting, "
                    "loitering detection, licence plate recognition) integrated with "
                    "a 64-camera IP network at a bank head office in Marina, Lagos. "
                    "Configure Milestone or Genetec VMS; provide staff training."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 2_500_000, "pay_max": 4_000_000,
                "state": "lagos", "lga": "Lagos Island", "slots": 2,
            },
            {
                "title": "Video Door Phone & Intercom Installer — Apartment Complex (Lekki)",
                "description": (
                    "Supply and install a Comelit or 2N IP video intercom system "
                    "with individual handsets for 80 apartments and a management "
                    "office in Lekki Phase 1. Integrate with existing access control "
                    "system; program directory and concierge call routing."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 1_200_000, "pay_max": 1_800_000,
                "state": "lagos", "lga": "Lekki", "slots": 2,
            },
            {
                "title": "Electric Fence & PIDS Installer — Residential Estate (Abuja)",
                "description": (
                    "Install a 3,000 m Gallagher electric fence energiser system "
                    "with perimeter intrusion detection sensors (microwave, PIR fence "
                    "disturbance) and zone alarm mapping for a gated estate in "
                    "Jabi, Abuja. Provide training on alarm response procedures."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 1_500_000, "pay_max": 2_500_000,
                "state": "fct", "lga": "Jabi", "slots": 2,
            },
            {
                "title": "Safe & Vault Installation Technician — Bank Branches (Lagos)",
                "description": (
                    "Transport, position, and anchor freestanding safes and walk-in "
                    "vaults for 5 new bank branches in Lagos. Install electronic "
                    "lock mechanisms, relockers, and time-lock devices. Carry out "
                    "handover testing and code programming with branch manager."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 800_000, "pay_max": 1_200_000,
                "state": "lagos", "lga": "Ikeja", "slots": 2,
            },
            {
                "title": "FM200 Fire Suppression System Installer — Server Room (Lagos)",
                "description": (
                    "Design, supply, and install an FM200 (HFC-227ea) total-flooding "
                    "fire suppression system in a server room and UPS room complex "
                    "in Ikeja. Includes cylinder mounting, nozzle positioning, "
                    "solenoid valves, pressure switch, and abort station. "
                    "NFPA 2001 compliant documentation required."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 2_000_000, "pay_max": 3_000_000,
                "state": "lagos", "lga": "Ikeja", "slots": 2,
            },
            {
                "title": "Panic Button & Lone Worker Safety System Installer — School (Abuja)",
                "description": (
                    "Install fixed panic buttons, personal attack alarms, and staff "
                    "lone-worker devices connected to a central ARC-monitored platform "
                    "across a school campus in Gwarinpa. Include training sessions "
                    "for teaching and administrative staff."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 600_000, "pay_max": 900_000,
                "state": "fct", "lga": "Gwarinpa", "slots": 1,
            },
            {
                "title": "Turnstile & Speed Gate Installer — Corporate Headquarters (Lagos)",
                "description": (
                    "Supply and install 6 full-height turnstiles and 4 speed gates "
                    "at the reception and car park of a corporate HQ in Alausa, Lagos. "
                    "Integrate with HID OSDP access control and visitor management "
                    "system. Provide commissioning documentation and staff training."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 1_800_000, "pay_max": 2_800_000,
                "state": "lagos", "lga": "Ikeja", "slots": 2,
            },
            {
                "title": "Security System Auditor & Risk Assessor (Nationwide, Remote)",
                "description": (
                    "Conduct technical security surveys and produce written risk "
                    "assessments and remediation plans for commercial insurance "
                    "clients across Nigeria. Review CCTV quality, access control "
                    "policies, lighting, guarding, and physical security. "
                    "ASIS CPP or similar qualification preferred."
                ),
                "job_type": Job.JobType.PART_TIME,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 40_000, "pay_max": 70_000,
                "state": "lagos", "lga": "Victoria Island", "slots": 2,
                "is_remote": True,
            },
        ],
    },

    # ── 17. CATERER (9 jobs) ──────────────────────────────────────────────────
    {
        "name": "Caterer",
        "slug": "caterer",
        "icon_class":      "fas fa-utensils",
        "display_order":   16,
        "clip_context_text": "professional caterer chef food service events Nigeria",
        "description": (
            "Professional caterers, chefs, and food-service staff for corporate, "
            "event, hospital, offshore, and restaurant catering across Nigeria."
        ),
        "skills": [
            "Corporate Canteen Management", "Event & Banquet Catering",
            "Hospital & Dietetic Catering", "School Cafeteria Management",
            "Offshore Catering & Galley Cook", "Continental & International Cuisine",
            "Pastry, Baking & Confectionery", "Bar Management & Cocktails",
            "Food Truck & Street Food Operations", "Food Safety & HACCP",
        ],
        "jobs": [
            {
                "title": "Corporate Canteen Manager — Manufacturing Plant (Sagamu, Ogun)",
                "description": (
                    "Manage all catering operations for a 400-staff factory canteen "
                    "in Sagamu: menu planning, procurement, stock control, hygiene "
                    "compliance, and supervision of 8 kitchen staff. "
                    "HACCP qualification and 3+ years institutional catering management "
                    "experience required."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 150_000, "pay_max": 220_000,
                "state": "ogun", "lga": "Sagamu", "slots": 1,
            },
            {
                "title": "Wedding Catering Supervisor — Events Management Company (Lagos)",
                "description": (
                    "Supervise food production and service for high-volume weddings "
                    "(500–2,000 guests) managed by a Lagos events company. "
                    "Coordinate kitchen team, service crew, and chafing dish setup. "
                    "Available every weekend (Fri–Sun). Own transport for early "
                    "morning arrival at event venues essential."
                ),
                "job_type": Job.JobType.PART_TIME,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 30_000, "pay_max": 60_000,
                "state": "lagos", "lga": "Ikeja", "slots": 3,
            },
            {
                "title": "Hospital Dietitian & Catering Officer — Private Hospital (Abuja)",
                "description": (
                    "Plan and oversee therapeutic diets for in-patients, manage the "
                    "hospital kitchen, and ensure nutritional standards for all wards "
                    "(cardiac, diabetic, paediatric, surgical) at a private hospital "
                    "in Abuja. B.Sc Nutrition/Dietetics and CNRHP registration required."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 180_000, "pay_max": 260_000,
                "state": "fct", "lga": "Garki", "slots": 1,
            },
            {
                "title": "School Cafeteria Cook — International School (Ikeja, Lagos)",
                "description": (
                    "Prepare nutritious breakfasts and lunches for 600 pupils and "
                    "staff at an international school in Ikeja. Cook a rotating "
                    "4-week menu (Nigerian, continental, and halal options). "
                    "Observe strict allergen management and maintain daily "
                    "temperature logs."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 90_000, "pay_max": 140_000,
                "state": "lagos", "lga": "Ikeja", "slots": 2,
            },
            {
                "title": "Offshore Galley Cook — Accommodation Barge (Rivers State)",
                "description": (
                    "Cook three full meals per day plus midnight snack for 180 "
                    "offshore workers on an accommodation barge in the Niger Delta. "
                    "28/28 rotation; BOSIET/HUET certificate required. "
                    "Ability to cook Nigerian and continental menus. "
                    "Experience in galley or institutional catering essential."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 200_000, "pay_max": 300_000,
                "state": "rivers", "lga": "Bonny", "slots": 3,
            },
            {
                "title": "Shawarma & Continental Cuisine Chef — Upscale QSR (Abuja)",
                "description": (
                    "Operate a busy shawarma station and continental grill in a "
                    "fast-casual restaurant in Wuse 2, Abuja. Maintain consistent "
                    "flavour profiles, food cost targets, and hygiene standards. "
                    "Experience with vertical rotisserie, charcoal grill, and "
                    "panini press required."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 100_000, "pay_max": 150_000,
                "state": "fct", "lga": "Wuse", "slots": 2,
            },
            {
                "title": "Pastry Chef & Artisan Baker — 5-Star Hotel (Lagos)",
                "description": (
                    "Lead the pastry section at a 5-star hotel in Victoria Island "
                    "producing croissants, sourdough breads, celebration cakes, "
                    "petit fours, and plated desserts. Manage two pastry assistants; "
                    "develop seasonal menus in consultation with the executive chef."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 200_000, "pay_max": 300_000,
                "state": "lagos", "lga": "Victoria Island", "slots": 1,
            },
            {
                "title": "Bar & Cocktail Manager — Luxury Events Company (Lagos)",
                "description": (
                    "Design cocktail menus and manage mobile bar operations for high-"
                    "end corporate events, weddings, and VIP parties across Lagos "
                    "and Abuja. Manage a team of 4 bartenders; responsible for stock, "
                    "presentation, and service speed. Mixology certification preferred."
                ),
                "job_type": Job.JobType.PART_TIME,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 40_000, "pay_max": 80_000,
                "state": "lagos", "lga": "Victoria Island", "slots": 1,
            },
            {
                "title": "Food Truck Operator & Chef — Tech Hub Lunch Service (Yaba, Lagos)",
                "description": (
                    "Operate a company-owned food truck serving daily lunch (10+ "
                    "menu items) to 200+ tech workers at a hub campus in Yaba, Lagos. "
                    "Plan the weekly menu, procure ingredients, cook, serve, and "
                    "maintain the truck. Previous food truck or street food "
                    "experience required. Health certificate mandatory."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 120_000, "pay_max": 180_000,
                "state": "lagos", "lga": "Yaba", "slots": 1,
            },
        ],
    },

]  # end TRADE_CATEGORIES


# ──────────────────────────────────────────────────────────────────────────────
#  MANAGEMENT COMMAND
# ──────────────────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = (
        "Seed an additional 140 active job listings across all 17 Nigerian "
        "trade categories. No title duplicates seed_category_jobs.py."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview what would be created without writing to the database.",
        )
        parser.add_argument(
            "--only",
            default="",
            metavar="SLUGS",
            help="Comma-separated category slugs to seed (default: all).",
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
            "\n🔧  TradeLink NG — seed_extra_jobs (140 jobs target)\n"
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
        total_cats_new   = 0
        total_skills_new = 0
        total_jobs_new   = 0

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
        Ensure the trade category, its extra skills, and its new jobs exist.
        Returns (cats_new, skills_new, jobs_new) counts.
        """
        slug = trade_data["slug"]

        # ── Trade Category ───────────────────────────────────────────────────
        if dry_run:
            cat_exists = TradeCategory.objects.filter(slug=slug).exists()
            cat_new = 0 if cat_exists else 1
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

        for job_data in trade_data["jobs"]:
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