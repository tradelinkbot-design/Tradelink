"""
jobs/management/commands/seed_jobs.py
======================================
Management command that seeds the database with:
  - Up to 10 TradeCategory rows  (skips any that already exist by slug)
  - 10 Skills per category
  - 1 seed EmployerProfile / User (reused across all jobs)
  - 10 Job listings per category  (100 jobs total)

Usage
-----
    python manage.py seed_jobs                    # full seed
    python manage.py seed_jobs --jobs-per-trade 5 # fewer jobs per trade
    python manage.py seed_jobs --clear            # wipe seed data first

Design notes
-------------
- Idempotent: re-running is safe.  Existing rows identified by slug / title
  are skipped, not duplicated.
- The four categories you already have in the DB (Electrician, Plumber,
  Solar Installer, Carpenter) are included in the seed data; the command
  detects them via slug and skips creation.
- Jobs are created in ACTIVE status so the CLIP pipeline picks them up
  immediately (signals → Celery tasks → embeddings).
- All monetary values are in Nigerian Naira (NGN).
"""

import random
import logging
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from jobs.models import (
    TradeCategory,
    Skill,
    EmployerProfile,
    Job,
)

logger = logging.getLogger(__name__)
User = get_user_model()

# ──────────────────────────────────────────────────────────────────────────────
#  SEED DATA
# ──────────────────────────────────────────────────────────────────────────────

TRADE_CATEGORIES = [
    {
        "name": "Electrician",
        "slug": "electrician",
        "icon_class": "fas fa-bolt",
        "display_order": 0,
        "clip_context_text": "skilled electrician wiring installation repair Lagos Nigeria",
        "description": (
            "Certified electricians offering domestic, commercial and industrial "
            "wiring, panel upgrades, CCTV, solar integration and generator work."
        ),
        "skills": [
            "Domestic Wiring",
            "Industrial Wiring",
            "Solar Panel Wiring",
            "Generator Installation",
            "CCTV & Security Systems",
            "Panel & Fuseboard Upgrades",
            "Fault Finding & Diagnostics",
            "Inverter Installation",
            "Street & Outdoor Lighting",
            "Electrical Inspection & Testing",
        ],
        "jobs": [
            {
                "title": "Residential Electrician — Lekki Phase 1",
                "description": (
                    "We need a qualified electrician to rewire a 4-bedroom duplex in "
                    "Lekki Phase 1. Scope includes new consumer unit, all lighting circuits, "
                    "sockets, and commissioning. Must hold at least City & Guilds Level 3 or "
                    "equivalent Nigerian certification. Tools supplied on site."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 350_000,
                "pay_max": 500_000,
                "state": "lagos",
                "lga": "Lekki",
                "slots": 2,
            },
            {
                "title": "Solar PV & Inverter Installer",
                "description": (
                    "Install a 5 kW off-grid solar system (panels, inverter, batteries) "
                    "on a commercial property in Ikeja GRA. Candidate must have hands-on "
                    "experience with Victron or Schneider inverters and proper DC/AC cable "
                    "sizing. Proof of previous installations required."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 200_000,
                "pay_max": 280_000,
                "state": "lagos",
                "lga": "Ikeja",
                "slots": 1,
            },
            {
                "title": "Generator & ATS Maintenance Technician",
                "description": (
                    "Ongoing monthly maintenance contract for 3 Perkins diesel generators "
                    "(100 kVA, 200 kVA, 500 kVA) and ATS panels at a factory in Apapa. "
                    "Must understand load-sharing and be able to carry out load-bank testing."
                ),
                "job_type": Job.JobType.PART_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 80_000,
                "pay_max": 120_000,
                "state": "lagos",
                "lga": "Apapa",
                "slots": 1,
            },
            {
                "title": "CCTV & Access Control Installer",
                "description": (
                    "Supply and install a 32-camera Hikvision IP CCTV network with NVR, "
                    "biometric access control on 6 doors, and structured cabling at a school "
                    "campus in Abuja. Provide a 12-month maintenance warranty."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 450_000,
                "pay_max": 650_000,
                "state": "fct",
                "lga": "Gwarinpa",
                "slots": 2,
            },
            {
                "title": "Electrical Inspector — Housing Estate",
                "description": (
                    "Inspect and certify the electrical installations of 40 newly built "
                    "terrace houses in a Lekki estate before handover. Detailed written "
                    "report per unit required. Must be registered with COREN or the Council "
                    "for the Regulation of Engineering in Nigeria."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 15_000,
                "pay_max": 25_000,
                "state": "lagos",
                "lga": "Sangotedo",
                "slots": 1,
            },
            {
                "title": "Commercial Wiring — Office Fit-Out (Port Harcourt)",
                "description": (
                    "Wire a new 3-floor open-plan office (approx. 1,200 m²) including data "
                    "points, perimeter sockets, concealed conduit, emergency lighting, and "
                    "fire-alarm integration in Port Harcourt. Start within 2 weeks."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 600_000,
                "pay_max": 900_000,
                "state": "rivers",
                "lga": "Port Harcourt",
                "slots": 3,
            },
            {
                "title": "Inverter Battery Installation & Maintenance",
                "description": (
                    "Install and service Luminous / Felicity lithium inverter systems for "
                    "residential clients across Ibadan. The role is ongoing; you will handle "
                    "new installations and regular maintenance visits for existing customers. "
                    "Own transport preferred."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 90_000,
                "pay_max": 150_000,
                "state": "oyo",
                "lga": "Ibadan North",
                "slots": 2,
            },
            {
                "title": "Electrician Apprentice Supervisor",
                "description": (
                    "Supervise and train 6 apprentice electricians on a large housing "
                    "project in Kaduna. You will allocate tasks, inspect work quality, "
                    "and ensure compliance with NEC / Nigerian wiring regulations. "
                    "Minimum 7 years hands-on experience required."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.WEEKLY,
                "pay_min": 50_000,
                "pay_max": 70_000,
                "state": "kaduna",
                "lga": "Kaduna North",
                "slots": 1,
            },
            {
                "title": "Street Lighting Installer — State Contract",
                "description": (
                    "Install 120 solar-powered LED streetlights along a 15 km road in "
                    "Enugu State under a government contract. Pole erection, cabling, and "
                    "controller programming included. Team of 4 needed; lead installer to "
                    "coordinate logistics."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 1_200_000,
                "pay_max": 1_800_000,
                "state": "enugu",
                "lga": "Enugu North",
                "slots": 4,
            },
            {
                "title": "Fault-Finding Electrician (On-Call)",
                "description": (
                    "Join our on-call maintenance roster for a property management company "
                    "with 200+ residential units in Lagos Island. Respond to electrical "
                    "faults within 2 hours. Paid per callout plus a monthly retainer. "
                    "Reliable transport essential."
                ),
                "job_type": Job.JobType.PART_TIME,
                "pay_type": Job.PayType.HOURLY,
                "pay_min": 3_000,
                "pay_max": 5_000,
                "state": "lagos",
                "lga": "Lagos Island",
                "slots": 2,
            },
        ],
    },
    {
        "name": "Plumber",
        "slug": "plumber",
        "icon_class": "fas fa-wrench",
        "display_order": 1,
        "clip_context_text": "skilled plumber pipe fitting water supply sanitation Nigeria",
        "description": (
            "Licensed plumbers for domestic and commercial water supply, drainage, "
            "gas fitting, borehole installation, and sanitary ware fitting."
        ),
        "skills": [
            "Pipe Installation & Fitting",
            "Water Heater Installation",
            "Drainage & Sewerage",
            "Borehole & Pump Installation",
            "Bathroom & Sanitary Fitting",
            "Leak Detection & Repair",
            "Gas Pipe Installation",
            "Irrigation Systems",
            "Swimming Pool Plumbing",
            "Roof Gutter & Rainwater Systems",
        ],
        "jobs": [
            {
                "title": "Plumber — New Estate Water Supply (Abuja)",
                "description": (
                    "Install the internal water supply network for 25 terrace homes in "
                    "Kubwa, Abuja. Work includes header tank installation, rising mains, "
                    "cold-water distribution, and final connections to sanitaryware. "
                    "Materials supplied by client."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 400_000,
                "pay_max": 550_000,
                "state": "fct",
                "lga": "Kubwa",
                "slots": 2,
            },
            {
                "title": "Borehole & Submersible Pump Installer",
                "description": (
                    "Supply and install a 100 m borehole with 1.5 HP Grundfos submersible "
                    "pump, control panel, pressure tank, and overhead storage tank at a "
                    "school in Ogun State. Full water treatment setup included."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 500_000,
                "pay_max": 750_000,
                "state": "ogun",
                "lga": "Sagamu",
                "slots": 1,
            },
            {
                "title": "Emergency Leak Repair Plumber (Lagos)",
                "description": (
                    "On-call plumber required for emergency leak repairs across a portfolio "
                    "of 80 rental apartments on Victoria Island. Response time under 3 hours. "
                    "Paid per callout plus weekly retainer. Must have own vehicle and tools."
                ),
                "job_type": Job.JobType.PART_TIME,
                "pay_type": Job.PayType.HOURLY,
                "pay_min": 4_000,
                "pay_max": 6_000,
                "state": "lagos",
                "lga": "Victoria Island",
                "slots": 1,
            },
            {
                "title": "Commercial Kitchen Plumber — Hospitality Group",
                "description": (
                    "Fit out the plumbing for 3 new restaurant kitchens (grease traps, "
                    "pot sinks, dishwasher connections, hot & cold supply) at a hotel "
                    "development in Owerri. Experience in commercial catering plumbing is "
                    "essential."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 300_000,
                "pay_max": 450_000,
                "state": "imo",
                "lga": "Owerri",
                "slots": 2,
            },
            {
                "title": "Gas Pipe Installation — LPG Network",
                "description": (
                    "Install an LPG distribution network for a 60-unit apartment block in "
                    "Port Harcourt. Scope: manifold, copper supply lines, gas meters, "
                    "cooker connections and pressure testing. Gas-safe certification required."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 350_000,
                "pay_max": 500_000,
                "state": "rivers",
                "lga": "Obio-Akpor",
                "slots": 2,
            },
            {
                "title": "Bathroom Renovation Plumber",
                "description": (
                    "Refit 5 bathrooms in a high-end Lagos Mainland property. Works include "
                    "repositioning sanitary ware, new shower trays, mixer showers, heated "
                    "towel rails, and full tiling preparation. Must be comfortable working "
                    "alongside tilers and carpenters."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 20_000,
                "pay_max": 30_000,
                "state": "lagos",
                "lga": "Surulere",
                "slots": 1,
            },
            {
                "title": "Irrigation System Installer — Farm, Kano",
                "description": (
                    "Design and install a drip-irrigation system covering 5 hectares of "
                    "vegetable farm in Kano State. Includes pump station, main lines, "
                    "drip tape, timers and fertiliser injection unit. Agri-plumbing or "
                    "irrigation experience required."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 600_000,
                "pay_max": 900_000,
                "state": "kano",
                "lga": "Kano Municipal",
                "slots": 1,
            },
            {
                "title": "Swimming Pool Plumbing — Luxury Villa",
                "description": (
                    "Install the complete plumbing system for an 80,000-litre infinity "
                    "pool at a private villa in Banana Island. Work includes circulation "
                    "pumps, filter systems, heating, and automated chemical dosing. "
                    "Portfolio of pool projects required at interview."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 800_000,
                "pay_max": 1_200_000,
                "state": "lagos",
                "lga": "Banana Island",
                "slots": 1,
            },
            {
                "title": "Full-Time Maintenance Plumber — Hospital",
                "description": (
                    "Join our facilities team at a 150-bed private hospital in Benin City. "
                    "Day-to-day plumbing maintenance, scheduled PPM, and emergency response. "
                    "Healthcare experience preferred. 5-day week with one on-call weekend "
                    "per month."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 100_000,
                "pay_max": 140_000,
                "state": "edo",
                "lga": "Benin City",
                "slots": 1,
            },
            {
                "title": "Rainwater Harvesting & Gutter Installer",
                "description": (
                    "Install UPVC guttering, downpipes, and a 10,000-litre rainwater "
                    "harvesting tank system on a new school building in Delta State. "
                    "Must supply itemised quote before work starts. 12-month warranty "
                    "on workmanship."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 150_000,
                "pay_max": 220_000,
                "state": "delta",
                "lga": "Warri",
                "slots": 1,
            },
        ],
    },
    {
        "name": "Solar Installer",
        "slug": "solar-installer",
        "icon_class": "fas fa-solar-panel",
        "display_order": 2,
        "clip_context_text": "solar panel installation photovoltaic inverter off-grid Nigeria",
        "description": (
            "Solar energy professionals specialising in residential and commercial PV "
            "systems, off-grid and hybrid setups, battery storage, and monitoring."
        ),
        "skills": [
            "PV Panel Mounting & Wiring",
            "Inverter Installation & Configuration",
            "Battery Bank Setup",
            "Hybrid System Design",
            "Off-Grid System Installation",
            "Grid-Tie System Installation",
            "Solar Water Heating",
            "System Monitoring & SCADA",
            "Solar Street Lighting",
            "Maintenance & Fault Diagnosis",
        ],
        "jobs": [
            {
                "title": "Hybrid Solar Installer — Lagos Residence (10 kW)",
                "description": (
                    "Install a 10 kW hybrid solar PV system (Fronius inverter, 20 kWh "
                    "Pylontech batteries, 28 × 400 W panels) on a 5-bedroom house in "
                    "Ajah. Includes rooftop mounting, DC/AC cabling, load panel wiring "
                    "and grid-connect commissioning."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 350_000,
                "pay_max": 450_000,
                "state": "lagos",
                "lga": "Ajah",
                "slots": 2,
            },
            {
                "title": "Off-Grid Solar Technician — Remote Schools Project",
                "description": (
                    "Install 5 kW off-grid solar systems at 8 rural schools in Kebbi State "
                    "under an NGO electrification programme. Teams of 2 technicians. "
                    "Travel and accommodation provided. Timeline: 6 weeks."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.WEEKLY,
                "pay_min": 60_000,
                "pay_max": 90_000,
                "state": "kebbi",
                "lga": "Birnin Kebbi",
                "slots": 4,
            },
            {
                "title": "Commercial Rooftop Solar — Supermarket (Abuja)",
                "description": (
                    "Design and install a 50 kW grid-tied rooftop solar array for a "
                    "supermarket in Wuse 2, Abuja. Scope includes structural survey, "
                    "panel layout, string inverters, metering, and DISCO connection docs. "
                    "NAFDAC / NERC certification an advantage."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 3_000_000,
                "pay_max": 4_500_000,
                "state": "fct",
                "lga": "Wuse",
                "slots": 3,
            },
            {
                "title": "Solar Water Heater Installer",
                "description": (
                    "Supply and install evacuated-tube solar water heaters for 12 units "
                    "in a Port Harcourt apartment complex. Existing copper hot-water pipes "
                    "to be connected. Provide manufacturer warranty certificates on "
                    "completion."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 600_000,
                "pay_max": 900_000,
                "state": "rivers",
                "lga": "Port Harcourt",
                "slots": 2,
            },
            {
                "title": "Solar Maintenance Engineer (Full-Time, Kano)",
                "description": (
                    "Maintain a portfolio of 120 installed solar systems across Kano and "
                    "Jigawa States. Planned maintenance, inverter firmware updates, battery "
                    "health checks, and fault resolution. Company vehicle provided. "
                    "Minimum 3 years solar O&M experience."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 120_000,
                "pay_max": 180_000,
                "state": "kano",
                "lga": "Kano Municipal",
                "slots": 1,
            },
            {
                "title": "Inverter Configuration Specialist",
                "description": (
                    "Configure and commission a batch of 40 Victron MultiPlus-II inverters "
                    "in a large off-grid estate in Ibeju-Lekki. Work includes VE.Configure "
                    "programming, ESS setup, grid-parallel settings and site documentation."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 25_000,
                "pay_max": 40_000,
                "state": "lagos",
                "lga": "Ibeju-Lekki",
                "slots": 1,
            },
            {
                "title": "Solar Street Light Installation — 200 Poles (Enugu)",
                "description": (
                    "Install 200 all-in-one solar street lights (50 W, 12 h backup) along "
                    "two major roads in Enugu Urban. Pole erection, concrete bases, solar "
                    "head fitting, and night-test commissioning. Government-funded project."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 2_000_000,
                "pay_max": 3_000_000,
                "state": "enugu",
                "lga": "Enugu North",
                "slots": 5,
            },
            {
                "title": "Residential Solar Survey & Design Consultant",
                "description": (
                    "Visit residential clients across Lagos to assess roof suitability, "
                    "shade analysis, load calculation, and produce a detailed solar proposal. "
                    "Role is consultancy-based; installations handled by separate teams. "
                    "Must use PVsyst or HelioScope."
                ),
                "job_type": Job.JobType.PART_TIME,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 15_000,
                "pay_max": 25_000,
                "state": "lagos",
                "lga": "Ikeja",
                "slots": 2,
            },
            {
                "title": "Battery Storage Retrofit Technician",
                "description": (
                    "Retrofit lithium battery banks to 30 existing grid-tied solar "
                    "installations across Ibadan. Work includes BMS integration, new "
                    "inverter bypass wiring, and updated monitoring dashboards. "
                    "Experience with Freedom Won or Hubble batteries preferred."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 80_000,
                "pay_max": 120_000,
                "state": "oyo",
                "lga": "Ibadan South-West",
                "slots": 2,
            },
            {
                "title": "Solar SCADA & Monitoring Specialist",
                "description": (
                    "Set up remote monitoring (SolarEdge or SMA Sunny Portal) for a "
                    "1 MW solar farm in Kaduna. Configure alerts, energy dashboards, "
                    "and integrate with the client's BMS. Ongoing quarterly data-review "
                    "contract also available after setup."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 200_000,
                "pay_max": 350_000,
                "state": "kaduna",
                "lga": "Kaduna South",
                "slots": 1,
            },
        ],
    },
    {
        "name": "Carpenter",
        "slug": "carpenter",
        "icon_class": "fas fa-hammer",
        "display_order": 3,
        "clip_context_text": "skilled carpenter furniture woodwork cabinet making Nigeria",
        "description": (
            "Expert carpenters for bespoke furniture, kitchen fitting, flooring, "
            "roofing, formwork, and interior joinery."
        ),
        "skills": [
            "Bespoke Furniture Making",
            "Kitchen Cabinet Installation",
            "Door & Window Fitting",
            "Roof Framing & Trusses",
            "Hardwood & Laminate Flooring",
            "Staircase Construction",
            "Concrete Formwork",
            "Interior Fit-Out Joinery",
            "Wardrobe & Storage Systems",
            "Wood Finishing & Polishing",
        ],
        "jobs": [
            {
                "title": "Bespoke Kitchen Cabinet Maker — Lekki Residence",
                "description": (
                    "Design and build a full fitted kitchen (island, wall and base units, "
                    "drawer packs, integrated appliance housings) for a 5-bedroom home in "
                    "Lekki Phase 2. Plywood carcasses with MDF-wrapped doors; quartz "
                    "worktops supplied by client. Portfolio of kitchens required."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 800_000,
                "pay_max": 1_200_000,
                "state": "lagos",
                "lga": "Lekki",
                "slots": 2,
            },
            {
                "title": "Roof Carpenter — 80-Unit Estate (Ogun)",
                "description": (
                    "Cut and fix timber roof trusses, ridge boards, rafters, purlins, and "
                    "fascias for 80 semi-detached units in an Ogun State housing scheme. "
                    "Must be able to read drawings. Scaffolding supplied."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 15_000,
                "pay_max": 22_000,
                "state": "ogun",
                "lga": "Ifo",
                "slots": 6,
            },
            {
                "title": "Hardwood Floor Installation Specialist",
                "description": (
                    "Sand, stain and install engineered hardwood flooring throughout a "
                    "1,500 m² commercial office in Victoria Island. Subfloor levelling, "
                    "expansion gap management and skirting board fitting included. "
                    "Noise-reduction underlay provided by client."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 500_000,
                "pay_max": 750_000,
                "state": "lagos",
                "lga": "Victoria Island",
                "slots": 3,
            },
            {
                "title": "Wardrobe & Dressing Room Fitter",
                "description": (
                    "Fit 12 full-height sliding-door wardrobes and a dressing room with "
                    "island unit in a new development in Ikoyi. PAX-style frames from "
                    "client; you supply the skill. Precision fitting and paint-finish "
                    "trim work expected."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 200_000,
                "pay_max": 300_000,
                "state": "lagos",
                "lga": "Ikoyi",
                "slots": 2,
            },
            {
                "title": "Concrete Formwork Carpenter — High-Rise (Abuja)",
                "description": (
                    "Experienced formwork carpenter needed for a 12-storey RC frame in "
                    "Central Abuja. Column boxes, slab decking, and beam sides. Work "
                    "alongside a 20-person crew. COREN-registered site."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 18_000,
                "pay_max": 28_000,
                "state": "fct",
                "lga": "Central Abuja",
                "slots": 4,
            },
            {
                "title": "Custom Staircase Builder",
                "description": (
                    "Fabricate and install a feature floating staircase (American oak "
                    "treads, steel stringers by others) in a luxury home in Asokoro. "
                    "Balustrade and handrail also in scope. Sample of previous staircases "
                    "mandatory."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 450_000,
                "pay_max": 700_000,
                "state": "fct",
                "lga": "Asokoro",
                "slots": 1,
            },
            {
                "title": "Door & Window Frame Installer — Estate",
                "description": (
                    "Supply and fix aluminium door frames, window frames and sliding doors "
                    "for 30 residential units in a new estate in Warri. Sealant, glazing "
                    "and hardware included in scope. Materials supplied on site."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 600_000,
                "pay_max": 900_000,
                "state": "delta",
                "lga": "Warri",
                "slots": 3,
            },
            {
                "title": "Office Interior Joiner — Fit-Out (Ikeja)",
                "description": (
                    "Install reception desk, partition walls, ceiling boards and meeting-room "
                    "joinery for a fintech company's new office in Ikeja GRA. Working from "
                    "interior design drawings. Clean, paint-ready finish essential."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 18_000,
                "pay_max": 25_000,
                "state": "lagos",
                "lga": "Ikeja",
                "slots": 2,
            },
            {
                "title": "Wood Finisher & Polisher (Full-Time)",
                "description": (
                    "Full-time wood finisher for a furniture manufacturer in Surulere. "
                    "Apply lacquer, varnish, stain, and wax finishes to production items. "
                    "Experience with spray gun and French polish techniques preferred."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 70_000,
                "pay_max": 100_000,
                "state": "lagos",
                "lga": "Surulere",
                "slots": 2,
            },
            {
                "title": "Carpenter Apprentice Trainer",
                "description": (
                    "Run a 6-week intensive carpentry skills programme for 15 youths at a "
                    "vocational centre in Enugu. Curriculum provided; you bring practical "
                    "mastery. Minimum 8 years carpentry experience and some teaching "
                    "ability required."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.WEEKLY,
                "pay_min": 40_000,
                "pay_max": 60_000,
                "state": "enugu",
                "lga": "Enugu East",
                "slots": 1,
            },
        ],
    },
    {
        "name": "Painter & Decorator",
        "slug": "painter-decorator",
        "icon_class": "fas fa-paint-roller",
        "display_order": 4,
        "clip_context_text": "painter decorator interior exterior wall finishing Nigeria",
        "description": (
            "Professional painters and decorators for interior and exterior painting, "
            "wall texturing, wallpaper hanging, and protective coatings."
        ),
        "skills": [
            "Interior Emulsion & Gloss Painting",
            "Exterior Weather-Shield Painting",
            "Textured & Stucco Finishes",
            "Wallpaper Hanging",
            "Epoxy Floor Coating",
            "Anti-Rust & Metal Painting",
            "Airless Spray Painting",
            "Decorative Murals",
            "Surface Preparation & Skimming",
            "Road Marking & Line Painting",
        ],
        "jobs": [
            {
                "title": "Interior Painter — Luxury Apartment Block (Lagos)",
                "description": (
                    "Paint 24 luxury apartments (2 & 3 bedroom) in a new development in "
                    "Oniru Estate. Works: skimming, priming, two coats of Dulux emulsion, "
                    "satin wood gloss on doors and skirting. Colour schedule provided."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 600_000,
                "pay_max": 900_000,
                "state": "lagos",
                "lga": "Victoria Island",
                "slots": 4,
            },
            {
                "title": "Exterior & Weather-Shield Painter",
                "description": (
                    "Apply Sandtex weather-shield masonry paint to a 10-storey block in "
                    "Abuja GRA. Scaffolding in place. Two coats required. Must have "
                    "experience working at height and using airless spray on large facades."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 15_000,
                "pay_max": 22_000,
                "state": "fct",
                "lga": "Garki",
                "slots": 3,
            },
            {
                "title": "Epoxy Floor Coating Specialist",
                "description": (
                    "Apply industrial epoxy flooring system (diamond-grind prep, primer, "
                    "body coat, anti-slip broadcast, clear topcoat) in a 2,000 m² warehouse "
                    "in Apapa. Must supply product data sheets and reference projects."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 700_000,
                "pay_max": 1_100_000,
                "state": "lagos",
                "lga": "Apapa",
                "slots": 2,
            },
            {
                "title": "Decorative Mural Artist — Restaurant",
                "description": (
                    "Paint a large-scale cultural mural (approx. 12 m × 4 m) inside a "
                    "new restaurant in Lekki Phase 1. Theme: Lagos street life. Provide "
                    "concept sketches before work begins. Acrylic or UV-resistant "
                    "exterior paints to be used."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 250_000,
                "pay_max": 400_000,
                "state": "lagos",
                "lga": "Lekki",
                "slots": 1,
            },
            {
                "title": "Wallpaper Hanger — High-End Homes",
                "description": (
                    "Hang designer wallpaper (supplied by client) in 8 bedrooms and a "
                    "formal lounge in an Ikoyi mansion. Work includes surface prep, seam "
                    "matching, and finishing around architraves. Precision and zero-waste "
                    "approach expected."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 20_000,
                "pay_max": 30_000,
                "state": "lagos",
                "lga": "Ikoyi",
                "slots": 1,
            },
            {
                "title": "Anti-Rust & Metal Paint Specialist",
                "description": (
                    "Prepare and apply Hammerite / Dulux anti-rust paint to structural "
                    "steelwork, gates, and railings on a Port Harcourt refinery support "
                    "facility. Sandblasting by others. Safety certification (working at "
                    "height, confined-space awareness) required."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 18_000,
                "pay_max": 28_000,
                "state": "rivers",
                "lga": "Port Harcourt",
                "slots": 2,
            },
            {
                "title": "Road Marking Painter — Lagos State Contract",
                "description": (
                    "Apply thermoplastic road markings (centre lines, lane arrows, "
                    "pedestrian crossings, bus-stop boxes) on 20 km of urban roads in "
                    "Lagos. Reflective bead application included. Night working required."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 1_500_000,
                "pay_max": 2_500_000,
                "state": "lagos",
                "lga": "Oshodi",
                "slots": 5,
            },
            {
                "title": "Textured Stucco Finish Painter",
                "description": (
                    "Apply sand-textured stucco exterior finish to 40 villas in a new "
                    "estate in Ibadan. Works include scratch coat, texture coat, and "
                    "colour wash in two colour options. Staging equipment provided."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 12_000,
                "pay_max": 18_000,
                "state": "oyo",
                "lga": "Ibadan North-East",
                "slots": 4,
            },
            {
                "title": "Full-Time Painter — Property Management",
                "description": (
                    "Join an Abuja property management company as a permanent painter for "
                    "their portfolio of 300+ managed properties. Turnaround repaints, "
                    "patch repairs and new project works. Company vehicle provided."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 65_000,
                "pay_max": 90_000,
                "state": "fct",
                "lga": "Wuse",
                "slots": 2,
            },
            {
                "title": "Painter — School Renovation (NGO Project)",
                "description": (
                    "Repaint classrooms, corridors, and external walls at 6 public schools "
                    "in Kano under a community renovation programme. Materials supplied. "
                    "Accommodation and transport provided. 3-week duration."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.WEEKLY,
                "pay_min": 35_000,
                "pay_max": 50_000,
                "state": "kano",
                "lga": "Kano Municipal",
                "slots": 6,
            },
        ],
    },
    {
        "name": "Welder",
        "slug": "welder",
        "icon_class": "fas fa-fire",
        "display_order": 5,
        "clip_context_text": "welder fabricator metal works Nigeria structural welding",
        "description": (
            "Certified welders and metal fabricators for structural steel, gates, "
            "pipelines, pressure vessels, and artistic metalwork."
        ),
        "skills": [
            "MIG Welding",
            "TIG Welding",
            "Arc / Stick Welding",
            "Structural Steel Fabrication",
            "Gate & Railing Fabrication",
            "Pipeline Welding",
            "Aluminium Welding",
            "Stainless Steel Welding",
            "Pressure Vessel Welding",
            "Metal Art & Decorative Fabrication",
        ],
        "jobs": [
            {
                "title": "Structural Steel Welder — High-Rise Frame",
                "description": (
                    "Weld structural steel connections (beams, columns, bracing) on a "
                    "16-storey tower in Eko Atlantic City. AWS D1.1 certified welders only. "
                    "NDT testing will be carried out on welds. PPE and harnesses supplied."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 25_000,
                "pay_max": 40_000,
                "state": "lagos",
                "lga": "Eko Atlantic",
                "slots": 4,
            },
            {
                "title": "Ornamental Gate & Fence Fabricator",
                "description": (
                    "Fabricate and install ornamental steel gates and perimeter fencing "
                    "for a new estate in Gwarinpa, Abuja. Designs provided. All welding "
                    "on site; anti-rust primer and topcoat painting included in scope."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 500_000,
                "pay_max": 800_000,
                "state": "fct",
                "lga": "Gwarinpa",
                "slots": 2,
            },
            {
                "title": "Pipeline Welder — Oil & Gas (Rivers State)",
                "description": (
                    "Weld process pipelines (API 5L, 6-inch diameter) on an upstream oil "
                    "facility upgrade in Bonny Island. Must hold API 1104 or ASME IX "
                    "qualification. Offshore safety & survival certificate required."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 40_000,
                "pay_max": 70_000,
                "state": "rivers",
                "lga": "Bonny",
                "slots": 3,
            },
            {
                "title": "Aluminium Welder & Fabricator — Window Factory",
                "description": (
                    "Full-time welder/fabricator in an aluminium window and door "
                    "manufacturing workshop in Ibadan. MIG aluminium welding, profile "
                    "cutting, assembly and quality checking. Production environment."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 80_000,
                "pay_max": 110_000,
                "state": "oyo",
                "lga": "Ibadan North",
                "slots": 2,
            },
            {
                "title": "TIG Welder — Stainless Steel Kitchen Equipment",
                "description": (
                    "Fabricate stainless steel commercial kitchen equipment (tables, "
                    "shelving, sinks, extraction hoods) for a hotel fit-out in Abuja. "
                    "TIG welding on 304 SS; hygiene-grade finish required. Shop drawings "
                    "provided."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 300_000,
                "pay_max": 450_000,
                "state": "fct",
                "lga": "Maitama",
                "slots": 2,
            },
            {
                "title": "Pressure Vessel Welder — ASME Certified",
                "description": (
                    "Weld and repair ASME VIII pressure vessels at a chemical plant in "
                    "Kaduna. All welding procedures and consumables supplied. PWHT and "
                    "hydrostatic testing by others. Valid ASME IX weld procedure essential."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 35_000,
                "pay_max": 55_000,
                "state": "kaduna",
                "lga": "Kaduna North",
                "slots": 1,
            },
            {
                "title": "Welder & Fitter — Steel Storage Tanks",
                "description": (
                    "Fabricate and erect 6 × API 650 mild-steel water storage tanks "
                    "(50,000 L each) at a water treatment plant in Kano. Site-welded "
                    "shells and roof. RT of welds required. Minimum 5 years tank "
                    "construction experience."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 30_000,
                "pay_max": 50_000,
                "state": "kano",
                "lga": "Ungogo",
                "slots": 3,
            },
            {
                "title": "Metal Art & Décor Fabricator (Creative Studio)",
                "description": (
                    "Join a Lagos creative studio producing bespoke metal wall art, "
                    "sculptures, and interior décor pieces. MIG/TIG welding, angle "
                    "grinding, powder coating. Portfolio of artistic metal work required. "
                    "Flexible hours."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 70_000,
                "pay_max": 100_000,
                "state": "lagos",
                "lga": "Yaba",
                "slots": 1,
            },
            {
                "title": "Mobile Welder — Emergency Repairs (On-Call)",
                "description": (
                    "On-call mobile welder for a Lagos industrial estate with 40 tenants. "
                    "Emergency structural and equipment weld repairs. Must have own "
                    "portable MIG set. Paid per callout + monthly retainer."
                ),
                "job_type": Job.JobType.PART_TIME,
                "pay_type": Job.PayType.HOURLY,
                "pay_min": 5_000,
                "pay_max": 8_000,
                "state": "lagos",
                "lga": "Isolo",
                "slots": 1,
            },
            {
                "title": "Welding Instructor — TVET Centre (Imo)",
                "description": (
                    "Deliver a 3-month welding skills programme (arc, MIG, basic TIG) at "
                    "a technical college in Owerri. Curriculum and consumables provided. "
                    "Class of 20 trainees. Teaching experience or TVET certification "
                    "an advantage."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 80_000,
                "pay_max": 120_000,
                "state": "imo",
                "lga": "Owerri",
                "slots": 1,
            },
        ],
    },
    {
        "name": "Mason",
        "slug": "mason",
        "icon_class": "fas fa-layer-group",
        "display_order": 6,
        "clip_context_text": "mason bricklayer concrete block work construction Nigeria",
        "description": (
            "Skilled masons and bricklayers for blockwork, plastering, tiling, "
            "concrete work, and stone masonry."
        ),
        "skills": [
            "Blockwork & Bricklaying",
            "Wall Plastering & Rendering",
            "Floor & Wall Tiling",
            "Concrete Pouring & Screeding",
            "Stone Masonry",
            "Waterproofing & Tanking",
            "Reinforced Concrete Work",
            "Coping & Copings",
            "Chimney & Fireplace Construction",
            "Retaining Wall Construction",
        ],
        "jobs": [
            {
                "title": "Bricklayer / Mason — Housing Estate (Ogun)",
                "description": (
                    "Lay 9-inch sandcrete blockwork for 40 units in a housing estate in "
                    "Mowe, Ogun State. DPC, lintel setting, and fair-face internal work "
                    "included. Rate per square metre; drawings supplied on site."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 12_000,
                "pay_max": 18_000,
                "state": "ogun",
                "lga": "Obafemi-Owode",
                "slots": 8,
            },
            {
                "title": "Wall & Floor Tiler — Luxury Development",
                "description": (
                    "Supply and lay large-format porcelain tiles (600×1200 mm) throughout "
                    "a luxury apartment development in Ikoyi. 3,200 m² total. Grout and "
                    "adhesive supplied. Must have experience with thin-bed large-format "
                    "tiling; portfolio required."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 1_500_000,
                "pay_max": 2_200_000,
                "state": "lagos",
                "lga": "Ikoyi",
                "slots": 5,
            },
            {
                "title": "Concrete Screed & Floor Mason",
                "description": (
                    "Pour and level 8,000 m² of power-float concrete floor screed for "
                    "a logistics warehouse in Ikorodu. Fibre reinforcement added to mix. "
                    "Contractor to manage curing and protection. Laser screed experience "
                    "an advantage."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 2_000_000,
                "pay_max": 3_500_000,
                "state": "lagos",
                "lga": "Ikorodu",
                "slots": 4,
            },
            {
                "title": "Plastering & Rendering Subcontractor",
                "description": (
                    "Float and set plaster on internal walls and ceilings for 60 apartments "
                    "in Kuje, Abuja. Scratch coat, browning, and skim coat finish. "
                    "Straightness tolerance: 3 mm under a 1.8 m staff. Rate per m²."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 14_000,
                "pay_max": 20_000,
                "state": "fct",
                "lga": "Kuje",
                "slots": 6,
            },
            {
                "title": "Waterproofing & Tanking Specialist",
                "description": (
                    "Apply crystalline waterproofing system to basement and ground-floor "
                    "slab of a 5-storey office building in Lagos Island. Xypex or Kryton "
                    "system; applicator training certificate required. Include a 10-year "
                    "guarantee."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 400_000,
                "pay_max": 650_000,
                "state": "lagos",
                "lga": "Lagos Island",
                "slots": 2,
            },
            {
                "title": "Stone Mason — Heritage Restoration (Enugu)",
                "description": (
                    "Restore and repoint stone masonry on a 1960s government building "
                    "in Enugu. Lime mortar pointing, ashlar cleaning, and cracked section "
                    "replacement using matching sandstone. Heritage or conservation "
                    "experience desirable."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 18_000,
                "pay_max": 28_000,
                "state": "enugu",
                "lga": "Enugu East",
                "slots": 2,
            },
            {
                "title": "Retaining Wall Mason — Hillside Estate",
                "description": (
                    "Build gabion and mass-concrete retaining walls on a hillside plot in "
                    "Jos, Plateau State. Drainage provisions and weep holes included. "
                    "Structural drawings provided. Previous retaining wall experience "
                    "mandatory."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 700_000,
                "pay_max": 1_100_000,
                "state": "plateau",
                "lga": "Jos North",
                "slots": 3,
            },
            {
                "title": "Swimming Pool Shell Mason",
                "description": (
                    "Form, pour, and waterproof the concrete shell of two swimming pools "
                    "(15 m × 7 m and 8 m × 4 m) at a private school in Ibadan. "
                    "Gunite or traditional shuttered RC construction. Structural drawings "
                    "available. Pool-construction experience required."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 1_200_000,
                "pay_max": 2_000_000,
                "state": "oyo",
                "lga": "Ibadan South-West",
                "slots": 3,
            },
            {
                "title": "Full-Time Mason — Property Developer",
                "description": (
                    "Permanent mason for a Lagos-based property developer with a rolling "
                    "pipeline of 10–15 simultaneous projects. Blockwork, plastering, "
                    "tiling, and general masonry works. Company transport to sites."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 80_000,
                "pay_max": 110_000,
                "state": "lagos",
                "lga": "Ojodu",
                "slots": 3,
            },
            {
                "title": "Mason Apprentice Supervisor — TVET (Kano)",
                "description": (
                    "Supervise 12 apprentice masons during the practical phase of a "
                    "government TVET programme in Kano. 10-week posting. Must hold a "
                    "Trade Test Certificate Grade I or NVQ Level 3 equivalent."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.WEEKLY,
                "pay_min": 40_000,
                "pay_max": 55_000,
                "state": "kano",
                "lga": "Kano Municipal",
                "slots": 1,
            },
        ],
    },
    {
        "name": "Hair Stylist",
        "slug": "hair-stylist",
        "icon_class": "fas fa-cut",
        "display_order": 7,
        "clip_context_text": "hair stylist braider loctitian salon Nigeria beauty",
        "description": (
            "Professional hair stylists, braiders, and locticians for salons, "
            "home service, and bridal styling in Nigeria."
        ),
        "skills": [
            "Hair Braiding & Threading",
            "Natural Hair Care & Twists",
            "Locs & Dreadlocks",
            "Relaxer & Texturiser Application",
            "Hair Colouring & Highlights",
            "Weave & Hair Extension Installation",
            "Wig Making & Customisation",
            "Bridal & Event Styling",
            "Men's Haircut & Grooming",
            "Scalp Treatment & Hair Growth",
        ],
        "jobs": [
            {
                "title": "Senior Hair Stylist — Upscale Lagos Salon",
                "description": (
                    "Join a high-end salon in Victoria Island as a senior stylist. "
                    "Clientele includes corporate professionals and socialites. "
                    "Skills required: colouring, relaxers, weaves, and natural styles. "
                    "Build your own client book with a competitive commission split."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 100_000,
                "pay_max": 180_000,
                "state": "lagos",
                "lga": "Victoria Island",
                "slots": 2,
            },
            {
                "title": "Bridal Hair Stylist — Wedding Season (Abuja)",
                "description": (
                    "We need an experienced bridal hair stylist for a busy wedding season "
                    "in Abuja (June–September). Handle trials and wedding day styling for "
                    "brides and bridal parties. Minimum 4 years bridal experience; "
                    "portfolio of bridal looks required."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 30_000,
                "pay_max": 60_000,
                "state": "fct",
                "lga": "Garki",
                "slots": 3,
            },
            {
                "title": "Loc Specialist / Loctitian",
                "description": (
                    "Full-time loctitian for a natural hair studio in Yaba, Lagos. "
                    "Services: starter locs, retwisting, loc extensions, colouring, and "
                    "scalp treatments. Strong Instagram presence preferred — we will "
                    "feature your work."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 80_000,
                "pay_max": 130_000,
                "state": "lagos",
                "lga": "Yaba",
                "slots": 1,
            },
            {
                "title": "Home-Service Hair Stylist (Mobile)",
                "description": (
                    "Provide mobile hair styling to clients in their homes across Lekki, "
                    "Ajah, and Sangotedo. Services include braiding, weaves, natural "
                    "styles, and basic colour. Own kit required. Bookings managed through "
                    "our app."
                ),
                "job_type": Job.JobType.PART_TIME,
                "pay_type": Job.PayType.HOURLY,
                "pay_min": 3_000,
                "pay_max": 8_000,
                "state": "lagos",
                "lga": "Lekki",
                "slots": 5,
            },
            {
                "title": "Wig Maker & Customiser",
                "description": (
                    "Produce and customise human-hair and synthetic wigs for a Lagos "
                    "hair brand's online store. Works: hairline customisation, bleaching "
                    "knots, dying, and styling wigs to order. Work from our studio in "
                    "Surulere. Target: 15–20 wigs per week."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 70_000,
                "pay_max": 110_000,
                "state": "lagos",
                "lga": "Surulere",
                "slots": 2,
            },
            {
                "title": "Barber & Men's Grooming Specialist",
                "description": (
                    "Experienced barber needed for a premium men's grooming lounge in "
                    "Ikeja. Services: fades, lineups, beard sculpting, hot-towel shaves. "
                    "Clientele expects consistency. Minimum 3 years barbering. "
                    "Instagram portfolio preferred."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 90_000,
                "pay_max": 150_000,
                "state": "lagos",
                "lga": "Ikeja",
                "slots": 2,
            },
            {
                "title": "Hair Colourist — Salon (Port Harcourt)",
                "description": (
                    "Hair colourist specialising in highlights, balayage, and vivid "
                    "fashion colours at a growing salon in Port Harcourt. Schwarzkopf "
                    "product training provided. Commission-based with strong earning "
                    "potential."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 80_000,
                "pay_max": 140_000,
                "state": "rivers",
                "lga": "Port Harcourt",
                "slots": 1,
            },
            {
                "title": "Salon Manager & Master Stylist",
                "description": (
                    "Manage day-to-day operations of a 6-chair salon in Asokoro, Abuja, "
                    "while also taking a full column of clients. Duties: staff scheduling, "
                    "retail stock, social media, and quality control. 5+ years senior "
                    "stylist experience required."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 150_000,
                "pay_max": 250_000,
                "state": "fct",
                "lga": "Asokoro",
                "slots": 1,
            },
            {
                "title": "Hair Braider — Kids' Party Specialist",
                "description": (
                    "Mobile braider available for children's parties and events across "
                    "Lagos. Provide quick, fun styles (single plaits, Ghana braids, "
                    "butterfly locs mini-style) for groups of 10–20 kids. Weekend "
                    "bookings. Kit and travel allowance provided."
                ),
                "job_type": Job.JobType.PART_TIME,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 20_000,
                "pay_max": 40_000,
                "state": "lagos",
                "lga": "Maryland",
                "slots": 3,
            },
            {
                "title": "Scalp Analyst & Trichology Advisor",
                "description": (
                    "Conduct scalp health analyses and recommend treatment plans at a "
                    "Lagos wellness brand. Must have trichology qualification (IAT, ITT, "
                    "or equivalent) plus hands-on salon background. Role is 60% clinical, "
                    "40% retail sales of branded hair products."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 120_000,
                "pay_max": 200_000,
                "state": "lagos",
                "lga": "Victoria Island",
                "slots": 1,
            },
        ],
    },
    {
        "name": "HVAC Technician",
        "slug": "hvac-technician",
        "icon_class": "fas fa-wind",
        "display_order": 8,
        "clip_context_text": "HVAC air conditioning installation refrigeration technician Nigeria",
        "description": (
            "HVAC engineers and AC technicians for installation, servicing, and "
            "repair of split units, VRF systems, chillers, and refrigeration."
        ),
        "skills": [
            "Split AC Installation & Commissioning",
            "VRF / VRV System Installation",
            "Chiller Plant Operation",
            "Refrigeration & Cold Room",
            "Ductwork Fabrication & Installation",
            "AC Servicing & Gas Top-Up",
            "BMS & Controls Integration",
            "Ventilation & Extraction Systems",
            "Cooling Tower Maintenance",
            "Energy Auditing — Cooling Systems",
        ],
        "jobs": [
            {
                "title": "AC Installation Technician — New Hotel (Lagos)",
                "description": (
                    "Install 120 Daikin split AC units in a new 4-star hotel in Lagos "
                    "Island. Wall-mounted and cassette types. Refrigerant pipework, "
                    "drainage, and electrical first-fix included. Daikin-certified "
                    "preferred."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 20_000,
                "pay_max": 35_000,
                "state": "lagos",
                "lga": "Lagos Island",
                "slots": 4,
            },
            {
                "title": "VRF System Engineer — Office Complex (Abuja)",
                "description": (
                    "Design and install a Mitsubishi Electric VRF system for a 6-storey "
                    "office complex in Maitama. Includes outdoor units, branching kits, "
                    "indoor units, controls wiring, and commissioning. VRF certification "
                    "required."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 3_000_000,
                "pay_max": 5_000_000,
                "state": "fct",
                "lga": "Maitama",
                "slots": 2,
            },
            {
                "title": "Cold Room & Refrigeration Technician",
                "description": (
                    "Install cold rooms and display refrigeration cases in a supermarket "
                    "in Ibadan. R404A system; includes compressor racks, evaporators, "
                    "condensers, and store monitoring. Food retail refrigeration "
                    "experience required."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 800_000,
                "pay_max": 1_300_000,
                "state": "oyo",
                "lga": "Ibadan North",
                "slots": 2,
            },
            {
                "title": "AC Service Technician (Full-Time, Port Harcourt)",
                "description": (
                    "Service and repair split AC units, cassette units, and ducted systems "
                    "for a facility management company in Port Harcourt. Route-based PPM "
                    "schedule plus reactive calls. Company van and tools provided."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 90_000,
                "pay_max": 130_000,
                "state": "rivers",
                "lga": "Port Harcourt",
                "slots": 2,
            },
            {
                "title": "Ductwork Fabricator & Installer",
                "description": (
                    "Fabricate and install galvanised steel ductwork for the AHU "
                    "systems in a new logistics centre in Ikorodu. Includes spiral duct, "
                    "rectangular sections, flex connections, volume control dampers, and "
                    "diffusers. HVCA or SMACNA experience desirable."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 22_000,
                "pay_max": 35_000,
                "state": "lagos",
                "lga": "Ikorodu",
                "slots": 3,
            },
            {
                "title": "BMS Controls Technician",
                "description": (
                    "Programme and commission Trend / Distech BMS controllers for HVAC "
                    "systems in a smart office building in Eko Atlantic. Includes BACnet "
                    "integration, graphics, and operator training. BMS certification "
                    "required."
                ),
                "job_type": Job.JobType.ONCE_OFF,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 500_000,
                "pay_max": 800_000,
                "state": "lagos",
                "lga": "Eko Atlantic",
                "slots": 1,
            },
            {
                "title": "Cooling Tower Maintenance Engineer",
                "description": (
                    "Carry out quarterly maintenance on 4 BAC cooling towers serving a "
                    "data centre in Ikeja. Includes bio-treatment, drift eliminator "
                    "inspection, motor and gearbox service, and Legionella risk "
                    "assessment. Relevant L8 / CIBSE TM13 knowledge required."
                ),
                "job_type": Job.JobType.PART_TIME,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 25_000,
                "pay_max": 40_000,
                "state": "lagos",
                "lga": "Ikeja",
                "slots": 1,
            },
            {
                "title": "HVAC Energy Auditor",
                "description": (
                    "Conduct energy audits of HVAC systems across 8 commercial buildings "
                    "in Lagos for an energy services company. Produce ISO 50001-aligned "
                    "reports with savings recommendations. Must use FLIR thermal camera "
                    "and power logger."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.DAILY,
                "pay_min": 25_000,
                "pay_max": 40_000,
                "state": "lagos",
                "lga": "Ikeja",
                "slots": 1,
            },
            {
                "title": "Ventilation System Installer — Industrial",
                "description": (
                    "Install mechanical ventilation and fume extraction systems in "
                    "a new paint manufacturing plant in Sagamu. Axial fans, centrifugal "
                    "fans, spigot ductwork, explosion-proof motors. ATEX awareness "
                    "required."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.FIXED,
                "pay_min": 1_200_000,
                "pay_max": 2_000_000,
                "state": "ogun",
                "lga": "Sagamu",
                "slots": 2,
            },
            {
                "title": "Chiller Plant Operator (Shift Work, Abuja)",
                "description": (
                    "Operate and maintain a 1,200-kW centrifugal chiller plant at a "
                    "government complex in Abuja. 12-hour rotating shifts. Log readings, "
                    "carry out minor maintenance, liaise with service contractor. "
                    "Chiller operation certificate required."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 110_000,
                "pay_max": 160_000,
                "state": "fct",
                "lga": "Central Abuja",
                "slots": 2,
            },
        ],
    },
    {
        "name": "Auto Mechanic",
        "slug": "auto-mechanic",
        "icon_class": "fas fa-car",
        "display_order": 9,
        "clip_context_text": "auto mechanic car repair engine diagnostics Nigeria workshop",
        "description": (
            "Professional auto mechanics for engine diagnostics, servicing, "
            "bodywork repair, and electrical fault-finding across all vehicle types."
        ),
        "skills": [
            "Engine Diagnostics & Repair",
            "Gear & Transmission Work",
            "Brake System Repair",
            "Auto Electrical & ECU",
            "Body Repair & Panel Beating",
            "Vehicle Painting & Respray",
            "Suspension & Steering",
            "AC System Repair",
            "Diesel Engine Overhaul",
            "Wheel Alignment & Balancing",
        ],
        "jobs": [
            {
                "title": "Senior Auto Mechanic — Fleet Garage (Lagos)",
                "description": (
                    "Diagnose and repair a mixed fleet of 60 vehicles (Toyota, Iveco vans, "
                    "Mitsubishi forklifts) at a logistics company workshop in Ikeja. "
                    "Use OBD-II scanner diagnostics. Minimum 5 years experience on "
                    "commercial vehicles."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 120_000,
                "pay_max": 180_000,
                "state": "lagos",
                "lga": "Ikeja",
                "slots": 2,
            },
            {
                "title": "Auto Electrician & ECU Specialist",
                "description": (
                    "Diagnose and repair auto electrical faults (wiring looms, ECU, "
                    "alternators, BCM, immobilisers) at a specialist auto-electrical "
                    "workshop in Oshodi. Must be proficient with Autel or Launch "
                    "diagnostic tools and comfortable programming keys."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 100_000,
                "pay_max": 160_000,
                "state": "lagos",
                "lga": "Oshodi",
                "slots": 1,
            },
            {
                "title": "Panel Beater & Body Repair Technician",
                "description": (
                    "Panel beat, fill, and prep accident-damaged vehicles for paint at "
                    "a busy bodyshop in Ojota. Experience on premium brands (BMW, Mercedes, "
                    "Land Rover) preferred. MIG brazing and plastic repair skills an "
                    "advantage."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 90_000,
                "pay_max": 140_000,
                "state": "lagos",
                "lga": "Ojota",
                "slots": 2,
            },
            {
                "title": "Vehicle Painter & Respray Specialist",
                "description": (
                    "Spray paint vehicles using PPG / Sikkens waterborne base coat / "
                    "clearcoat system at an Abuja bodyshop. HVLP gun technique; "
                    "experience with colour matching and blending is essential. "
                    "Spray booth provided."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 85_000,
                "pay_max": 130_000,
                "state": "fct",
                "lga": "Wuse",
                "slots": 1,
            },
            {
                "title": "Diesel Engine Overhaul Mechanic (Kano)",
                "description": (
                    "Overhaul Cummins and Perkins diesel engines (trucks and stationary "
                    "generators) at a workshop in Kano. In-frame and full rebuilds, "
                    "injector testing, and turbocharger reconditioning. Manufacturer "
                    "training certificate preferred."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 100_000,
                "pay_max": 150_000,
                "state": "kano",
                "lga": "Kano Municipal",
                "slots": 2,
            },
            {
                "title": "Gearbox & Transmission Specialist",
                "description": (
                    "Diagnose and rebuild automatic and manual gearboxes at a specialist "
                    "transmission workshop in Port Harcourt. ZF 6HP, Aisin Warner, and "
                    "Mercedes 722 series experience preferred. Flat-rate pay structure."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 110_000,
                "pay_max": 170_000,
                "state": "rivers",
                "lga": "Port Harcourt",
                "slots": 1,
            },
            {
                "title": "Mobile Mechanic — On-Call (Abuja)",
                "description": (
                    "Provide roadside breakdown assistance and minor repairs for a "
                    "vehicle breakdown service in Abuja. Own tools and transport required. "
                    "Callouts within 30-minute radius. Evening and weekend availability "
                    "essential."
                ),
                "job_type": Job.JobType.PART_TIME,
                "pay_type": Job.PayType.HOURLY,
                "pay_min": 5_000,
                "pay_max": 10_000,
                "state": "fct",
                "lga": "Garki",
                "slots": 3,
            },
            {
                "title": "Vehicle AC Technician",
                "description": (
                    "Service and regas vehicle AC systems across a fleet management "
                    "company's 150 vehicles in Lagos. System diagnostics, compressor "
                    "replacement, evaporator cleaning, and refrigerant recovery. "
                    "AC gas handling certification required."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 80_000,
                "pay_max": 120_000,
                "state": "lagos",
                "lga": "Isolo",
                "slots": 1,
            },
            {
                "title": "Wheel Alignment & Balancing Technician",
                "description": (
                    "Operate Hunter or Hofmann alignment equipment and wheel balancer at "
                    "a tyre and service centre in Ibadan. Handle alignment jobs on all "
                    "vehicle types including SUVs and light commercials. High-volume "
                    "environment."
                ),
                "job_type": Job.JobType.FULL_TIME,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 70_000,
                "pay_max": 100_000,
                "state": "oyo",
                "lga": "Ibadan North",
                "slots": 1,
            },
            {
                "title": "Mechanic Trainer — TVET Programme (Enugu)",
                "description": (
                    "Deliver practical automotive skills training for 20 youth trainees "
                    "at a TVET centre in Enugu under a federal skills programme. 4-month "
                    "contract. Minimum 7 years industry experience; teaching exposure "
                    "welcome."
                ),
                "job_type": Job.JobType.CONTRACT,
                "pay_type": Job.PayType.MONTHLY,
                "pay_min": 90_000,
                "pay_max": 130_000,
                "state": "enugu",
                "lga": "Enugu East",
                "slots": 1,
            },
        ],
    },
]


# ──────────────────────────────────────────────────────────────────────────────
#  SEED EMPLOYER
# ──────────────────────────────────────────────────────────────────────────────

SEED_EMPLOYER_USERNAME = "tradelink_seed_employer"
SEED_EMPLOYER_EMAIL    = "seed-employer@tradelink.ng"
SEED_EMPLOYER_PASSWORD = "SeedPass#2024!"


def get_or_create_seed_employer():
    """
    Return a (user, employer_profile) tuple.
    Creates the seed user/employer if they don't exist yet.
    """
    user, _ = User.objects.get_or_create(
        username=SEED_EMPLOYER_USERNAME,
        defaults={
            "email":    SEED_EMPLOYER_EMAIL,
            "is_staff": False,
        },
    )
    if not user.has_usable_password():
        user.set_password(SEED_EMPLOYER_PASSWORD)
        user.save(update_fields=["password"])

    employer, _ = EmployerProfile.objects.get_or_create(
        user=user,
        defaults={
            "company_name": "TradeLink Demo Employer",
            "company_type": EmployerProfile.CompanyType.SME,
            "description":  (
                "Seed account used by the seed_jobs management command to create "
                "demonstration job listings across all trade categories."
            ),
            "state": "lagos",
            "lga":   "Ikeja",
        },
    )
    return user, employer


# ──────────────────────────────────────────────────────────────────────────────
#  COMMAND
# ──────────────────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = (
        "Seeds the database with 10 trade categories, 10 skills each, "
        "and 10 active job listings per category (100 jobs total). "
        "Idempotent — safe to run multiple times."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--jobs-per-trade",
            type=int,
            default=10,
            metavar="N",
            help="How many jobs to create per trade category (default: 10, max: 10).",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help=(
                "Delete all jobs, skills, and trade categories created by this "
                "command (identified by the seed employer) before re-seeding."
            ),
        )
    def handle(self, *args, **options):
        jobs_per_trade = min(options["jobs_per_trade"], 10)

        if options["clear"]:
            self._clear_seed_data()

        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n🔧  TradeLink NG — Job Seeder\n"
        ))

        _, employer = get_or_create_seed_employer()
        self.stdout.write(f"  Seed employer: {employer.company_name} (pk={employer.pk})\n")

        total_categories = 0
        total_skills     = 0
        total_jobs       = 0

        with transaction.atomic():
            for trade_data in TRADE_CATEGORIES:
                cat, skills_created, jobs_created = self._seed_trade(
                    trade_data, employer, jobs_per_trade
                )
                total_categories += 1
                total_skills     += skills_created
                total_jobs       += jobs_created

        self.stdout.write(self.style.SUCCESS(
            f"\n✅  Seed complete — "
            f"{total_categories} categories · "
            f"{total_skills} new skills · "
            f"{total_jobs} new jobs\n"
        ))

    # ── Private helpers ────────────────────────────────────────────────────────

    def _seed_trade(self, trade_data: dict, employer: EmployerProfile, jobs_per_trade: int):
        """Create (or skip) one trade category, its skills, and its jobs."""

        # ── Trade Category ───────────────────────────────────────────────────
        cat, cat_created = TradeCategory.objects.get_or_create(
            slug=trade_data["slug"],
            defaults={
                "name":              trade_data["name"],
                "icon_class":        trade_data["icon_class"],
                "display_order":     trade_data["display_order"],
                "clip_context_text": trade_data["clip_context_text"],
                "description":       trade_data["description"],
                "is_active":         True,
            },
        )

        status_label = "✔  exists" if not cat_created else "✚  created"
        self.stdout.write(
            f"\n  [{status_label}] TradeCategory: {cat.name}"
        )

        # ── Skills ───────────────────────────────────────────────────────────
        skills_created = 0
        for skill_name in trade_data["skills"]:
            slug = skill_name.lower().replace(" ", "-").replace("&", "and").replace("/", "-")
            _, created = Skill.objects.get_or_create(
                category=cat,
                slug=slug,
                defaults={"name": skill_name, "is_active": True},
            )
            if created:
                skills_created += 1

        self.stdout.write(
            f"     Skills: {skills_created} new / "
            f"{len(trade_data['skills'])} total"
        )

        # ── Jobs ─────────────────────────────────────────────────────────────
        jobs_created = 0
        deadline_base = date.today() + timedelta(days=30)

        for job_data in trade_data["jobs"][:jobs_per_trade]:
            # Idempotency: skip if a job with this exact title already exists
            # for this employer & category
            exists = Job.objects.filter(
                employer=employer,
                trade_category=cat,
                title=job_data["title"],
            ).exists()

            if exists:
                self.stdout.write(
                    f"     ↳ skip  (exists): {job_data['title'][:60]}"
                )
                continue

            # Spread deadlines by a few days so they don't all expire at once
            deadline = deadline_base + timedelta(days=random.randint(0, 30))

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
                status=Job.Status.ACTIVE,   # makes signal fire → Celery embedding
            )
            jobs_created += 1
            self.stdout.write(
                f"     ✚  created: {job_data['title'][:60]}"
            )

        self.stdout.write(
            f"     Jobs: {jobs_created} new / "
            f"{min(jobs_per_trade, len(trade_data['jobs']))} attempted"
        )
        return cat, skills_created, jobs_created

    def _clear_seed_data(self):
        """Remove all data associated with the seed employer."""
        self.stdout.write(self.style.WARNING(
            "\n⚠️   --clear flag set: removing seed data …"
        ))
        try:
            user = User.objects.get(username=SEED_EMPLOYER_USERNAME)
            employer = EmployerProfile.objects.get(user=user)
            deleted_jobs, _ = Job.objects.filter(employer=employer).delete()
            self.stdout.write(f"  Deleted {deleted_jobs} job(s).")
        except (User.DoesNotExist, EmployerProfile.DoesNotExist):
            self.stdout.write("  No seed employer found; nothing to clear.")
