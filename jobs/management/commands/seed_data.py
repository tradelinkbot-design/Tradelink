"""
jobs/management/commands/seed_data.py
======================================
Management command that seeds the database with realistic Nigerian trade
marketplace data for development and testing.

Usage:
    python manage.py seed_data
    python manage.py seed_data --flush     # wipe existing seed data first

What it creates
───────────────
  • 4  TradeCategory rows   (Electrician, Plumber, Solar Installer, Carpenter)
  • 16 Skill rows           (4 per trade)
  • 5  Employer users       + EmployerProfile
  • 15 Worker  users        + WorkerProfile  (3 per trade)
  • 20 Job listings         (5 per trade, ACTIVE)
  • 15 WorkerSkill rows     (skills linked to workers)
  • 10 Review rows          (workers reviewing employers & vice-versa)

All accounts share the password:  TradeLink@2025

Login emails follow the pattern:
  Workers  → chukwuemeka.obi@tradelink.test
  Employers→ dangote.builders@tradelink.test
"""

import random
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction

# ── Models ───────────────────────────────────────────────────────────────────
from django.contrib.auth import get_user_model
from jobs.models import (
    TradeCategory,
    Skill,
    WorkerProfile,
    WorkerSkill,
    EmployerProfile,
    Job,
    Review,
)

User = get_user_model()

SEED_PASSWORD = "TradeLink@2025"

# ─────────────────────────────────────────────────────────────────────────────
#  RAW DATA
# ─────────────────────────────────────────────────────────────────────────────

TRADE_DATA = [
    {
        "name": "Electrician",
        "slug": "electrician",
        "icon_class": "fas fa-bolt",
        "description": (
            "Licensed electricians covering residential wiring, industrial "
            "installations, CCTV, solar integration, and generator maintenance."
        ),
        "clip_context_text": "expert electrician wiring installation Lagos Nigeria",
        "skills": [
            {"name": "Residential Wiring",       "slug": "residential-wiring"},
            {"name": "Solar Panel Integration",   "slug": "solar-panel-integration"},
            {"name": "CCTV & Security Systems",   "slug": "cctv-security-systems"},
            {"name": "Generator Maintenance",     "slug": "generator-maintenance"},
        ],
    },
    {
        "name": "Plumber",
        "slug": "plumber",
        "icon_class": "fas fa-wrench",
        "description": (
            "Skilled plumbers for pipe installation, borehole systems, "
            "bathroom fittings, and drainage repairs across Nigeria."
        ),
        "clip_context_text": "professional plumber pipe installation borehole Nigeria",
        "skills": [
            {"name": "Pipe Installation & Repair", "slug": "pipe-installation-repair"},
            {"name": "Borehole & Water Systems",   "slug": "borehole-water-systems"},
            {"name": "Bathroom Fitting",           "slug": "bathroom-fitting"},
            {"name": "Drainage & Sewage",          "slug": "drainage-sewage"},
        ],
    },
    {
        "name": "Solar Installer",
        "slug": "solar-installer",
        "icon_class": "fas fa-solar-panel",
        "description": (
            "Certified solar installers specialising in rooftop PV systems, "
            "inverter setup, battery storage, and off-grid solutions for homes "
            "and businesses across Nigeria."
        ),
        "clip_context_text": "certified solar panel installer rooftop PV Nigeria",
        "skills": [
            {"name": "Rooftop PV Installation",   "slug": "rooftop-pv-installation"},
            {"name": "Inverter & Battery Setup",  "slug": "inverter-battery-setup"},
            {"name": "Off-Grid System Design",    "slug": "off-grid-system-design"},
            {"name": "Solar Maintenance & Repair","slug": "solar-maintenance-repair"},
        ],
    },
    {
        "name": "Carpenter",
        "slug": "carpenter",
        "icon_class": "fas fa-hammer",
        "description": (
            "Expert carpenters for furniture making, door and window fitting, "
            "roofing, and bespoke interior woodwork across Nigeria."
        ),
        "clip_context_text": "expert carpenter furniture woodwork interior Nigeria",
        "skills": [
            {"name": "Furniture Making",          "slug": "furniture-making"},
            {"name": "Door & Window Fitting",     "slug": "door-window-fitting"},
            {"name": "Roof Carpentry",            "slug": "roof-carpentry"},
            {"name": "Interior Woodwork & Decor", "slug": "interior-woodwork-decor"},
        ],
    },
]


# ── Employer data ─────────────────────────────────────────────────────────────
EMPLOYER_DATA = [
    {
        "first_name": "Adewale",   "last_name": "Ogundimu",
        "username":   "adewale_ogundimu",
        "email":      "adewale.ogundimu@tradelink.test",
        "phone":      "+2348031001001",
        "company_name":  "Ogundimu Properties Ltd",
        "company_type":  EmployerProfile.CompanyType.SME,
        "industry":      "Real Estate & Construction",
        "about": (
            "Ogundimu Properties Ltd is a mid-size Lagos developer building "
            "residential estates in Lekki, Ajah, and Epe. We hire verified "
            "tradespeople for every project stage — from groundwork to finishing."
        ),
        "state": "lagos",  "lga": "Lekki",
        "website": "https://ogundimuproperties.ng",
        "is_verified": True,
    },
    {
        "first_name": "Ngozi",     "last_name": "Eze",
        "username":   "ngozi_eze",
        "email":      "ngozi.eze@tradelink.test",
        "phone":      "+2348031001002",
        "company_name":  "Eze Facility Services",
        "company_type":  EmployerProfile.CompanyType.SME,
        "industry":      "Facilities Management",
        "about": (
            "Eze Facility Services manages commercial and residential buildings "
            "in Abuja FCT. We regularly need electricians, plumbers, and general "
            "maintenance workers on short-notice contracts."
        ),
        "state": "fct",   "lga": "Wuse 2",
        "website": "",
        "is_verified": True,
    },
    {
        "first_name": "Emeka",     "last_name": "Dike",
        "username":   "emeka_dike",
        "email":      "emeka.dike@tradelink.test",
        "phone":      "+2348031001003",
        "company_name":  "GreenPower Solutions NG",
        "company_type":  EmployerProfile.CompanyType.SME,
        "industry":      "Renewable Energy",
        "about": (
            "GreenPower Solutions NG installs and maintains solar energy systems "
            "for homes and SMEs across Rivers State and the South-South region. "
            "We are expanding rapidly and always need skilled solar installers."
        ),
        "state": "rivers", "lga": "Port Harcourt",
        "website": "https://greenpowerng.com",
        "is_verified": True,
    },
    {
        "first_name": "Fatima",    "last_name": "Musa",
        "username":   "fatima_musa",
        "email":      "fatima.musa@tradelink.test",
        "phone":      "+2348031001004",
        "company_name":  "Al-Amin Construction",
        "company_type":  EmployerProfile.CompanyType.SME,
        "industry":      "Construction",
        "about": (
            "Al-Amin Construction is a Kano-based building firm specialising in "
            "residential and commercial projects. We value reliability, quality "
            "craftsmanship, and on-time delivery."
        ),
        "state": "kano",  "lga": "Nassarawa",
        "website": "",
        "is_verified": False,
    },
    {
        "first_name": "Taiwo",     "last_name": "Adeyemi",
        "username":   "taiwo_adeyemi",
        "email":      "taiwo.adeyemi@tradelink.test",
        "phone":      "+2348031001005",
        "company_name":  "Adeyemi Interiors",
        "company_type":  EmployerProfile.CompanyType.INDIVIDUAL,
        "industry":      "Interior Design",
        "about": (
            "I am an interior designer based in Ibadan. I hire skilled carpenters "
            "and woodwork artisans for bespoke furniture and fitted wardrobe "
            "projects for high-end residential clients."
        ),
        "state": "oyo",   "lga": "Ibadan North",
        "website": "",
        "is_verified": False,
    },
]


# ── Worker data ───────────────────────────────────────────────────────────────
WORKER_DATA = [
    # ── ELECTRICIANS ──────────────────────────────────────────────────────────
    {
        "first_name": "Chukwuemeka", "last_name": "Obi",
        "username":   "chukwuemeka_obi",
        "email":      "chukwuemeka.obi@tradelink.test",
        "phone":      "+2348041001001",
        "trade": "electrician",
        "experience_level": WorkerProfile.ExperienceLevel.EXPERIENCED,
        "years_experience": 8,
        "bio": (
            "I am a certified electrician with 8 years of experience working on "
            "residential estates and commercial buildings across Lagos and Ogun State. "
            "I specialise in residential wiring, CCTV installation, and solar panel "
            "integration. I have completed over 200 wiring projects and hold a COREN "
            "technician certificate. I am meticulous, safety-conscious, and always "
            "deliver clean, regulation-compliant installations."
        ),
        "state": "lagos", "lga": "Yaba",
        "hourly_rate": 4500,  "daily_rate": 32000,
        "availability": WorkerProfile.Availability.AVAILABLE,
        "is_verified": True,
        "skills": ["residential-wiring", "cctv-security-systems", "solar-panel-integration"],
    },
    {
        "first_name": "Babatunde",  "last_name": "Fashola",
        "username":   "babatunde_fashola",
        "email":      "babatunde.fashola@tradelink.test",
        "phone":      "+2348041001002",
        "trade": "electrician",
        "experience_level": WorkerProfile.ExperienceLevel.INTERMEDIATE,
        "years_experience": 4,
        "bio": (
            "Electrician based in Abuja with 4 years of experience in generator "
            "installation and maintenance, inverter systems, and general electrical "
            "repairs for homes and offices. I am quick, professional, and available "
            "for urgent call-outs. I cover FCT and nearby Nasarawa State."
        ),
        "state": "fct", "lga": "Garki",
        "hourly_rate": 3500,  "daily_rate": 25000,
        "availability": WorkerProfile.Availability.AVAILABLE,
        "is_verified": False,
        "skills": ["generator-maintenance", "residential-wiring"],
    },
    {
        "first_name": "Olumide",    "last_name": "Adeyinka",
        "username":   "olumide_adeyinka",
        "email":      "olumide.adeyinka@tradelink.test",
        "phone":      "+2348041001003",
        "trade": "electrician",
        "experience_level": WorkerProfile.ExperienceLevel.EXPERT,
        "years_experience": 12,
        "bio": (
            "Master electrician with 12 years of experience across industrial, "
            "commercial, and residential sectors. I lead wiring projects from "
            "load calculation and panel installation to final testing. Past clients "
            "include Shoprite, GTBank branches, and several Lekki Phase 1 estates. "
            "Available for contract and full-time roles in Lagos."
        ),
        "state": "lagos", "lga": "Surulere",
        "hourly_rate": 6000,  "daily_rate": 45000,
        "availability": WorkerProfile.Availability.AVAILABLE_SOON,
        "is_verified": True,
        "skills": ["residential-wiring", "cctv-security-systems", "generator-maintenance", "solar-panel-integration"],
    },

    # ── PLUMBERS ──────────────────────────────────────────────────────────────
    {
        "first_name": "Uche",       "last_name": "Nwosu",
        "username":   "uche_nwosu",
        "email":      "uche.nwosu@tradelink.test",
        "phone":      "+2348041001004",
        "trade": "plumber",
        "experience_level": WorkerProfile.ExperienceLevel.EXPERIENCED,
        "years_experience": 7,
        "bio": (
            "Professional plumber with 7 years of experience in pipe installation, "
            "borehole water systems, and bathroom fittings. I have worked on housing "
            "projects in Rivers State, Delta, and Bayelsa. I use quality materials "
            "and guarantee my work for 12 months. Available for site visits within "
            "48 hours notice in the South-South region."
        ),
        "state": "rivers", "lga": "Port Harcourt",
        "hourly_rate": 3800,  "daily_rate": 28000,
        "availability": WorkerProfile.Availability.AVAILABLE,
        "is_verified": True,
        "skills": ["pipe-installation-repair", "borehole-water-systems", "bathroom-fitting"],
    },
    {
        "first_name": "Suleiman",   "last_name": "Garba",
        "username":   "suleiman_garba",
        "email":      "suleiman.garba@tradelink.test",
        "phone":      "+2348041001005",
        "trade": "plumber",
        "experience_level": WorkerProfile.ExperienceLevel.INTERMEDIATE,
        "years_experience": 5,
        "bio": (
            "Kano-based plumber specialising in drainage, sewage systems, and "
            "pipe repair for residential buildings. I have completed over 150 "
            "plumbing jobs in Kano, Kaduna, and Katsina. Fluent in Hausa and "
            "English. Honest, punctual, and reliable."
        ),
        "state": "kano", "lga": "Kano Municipal",
        "hourly_rate": 2500,  "daily_rate": 18000,
        "availability": WorkerProfile.Availability.AVAILABLE,
        "is_verified": False,
        "skills": ["drainage-sewage", "pipe-installation-repair"],
    },
    {
        "first_name": "Akinwale",   "last_name": "Bello",
        "username":   "akinwale_bello",
        "email":      "akinwale.bello@tradelink.test",
        "phone":      "+2348041001006",
        "trade": "plumber",
        "experience_level": WorkerProfile.ExperienceLevel.EXPERT,
        "years_experience": 11,
        "bio": (
            "Senior plumber with 11 years of experience in large-scale borehole "
            "projects, elevated water tank installation, and complete estate "
            "plumbing systems. I have led crews on 3 Lekki residential estate "
            "projects and a 10-storey office block in VI. I work with a team "
            "of 4 and can handle large projects independently."
        ),
        "state": "lagos", "lga": "Victoria Island",
        "hourly_rate": 5500,  "daily_rate": 40000,
        "availability": WorkerProfile.Availability.BUSY,
        "is_verified": True,
        "skills": ["borehole-water-systems", "pipe-installation-repair", "bathroom-fitting", "drainage-sewage"],
    },

    # ── SOLAR INSTALLERS ──────────────────────────────────────────────────────
    {
        "first_name": "Ifeanyi",    "last_name": "Okafor",
        "username":   "ifeanyi_okafor",
        "email":      "ifeanyi.okafor@tradelink.test",
        "phone":      "+2348041001007",
        "trade": "solar-installer",
        "experience_level": WorkerProfile.ExperienceLevel.EXPERIENCED,
        "years_experience": 6,
        "bio": (
            "Solar energy technician with 6 years of experience installing rooftop "
            "PV systems, inverters, and lithium battery banks for homes and small "
            "businesses. I hold a NABCEP-equivalent certificate from NAERLS. I "
            "have completed over 80 solar installations in Rivers, Imo, and Enugu "
            "States. I offer a 2-year workmanship warranty on all my installations."
        ),
        "state": "rivers", "lga": "Obio-Akpor",
        "hourly_rate": 4000,  "daily_rate": 30000,
        "availability": WorkerProfile.Availability.AVAILABLE,
        "is_verified": True,
        "skills": ["rooftop-pv-installation", "inverter-battery-setup", "solar-maintenance-repair"],
    },
    {
        "first_name": "Amina",      "last_name": "Yusuf",
        "username":   "amina_yusuf",
        "email":      "amina.yusuf@tradelink.test",
        "phone":      "+2348041001008",
        "trade": "solar-installer",
        "experience_level": WorkerProfile.ExperienceLevel.INTERMEDIATE,
        "years_experience": 3,
        "bio": (
            "Solar installer based in Abuja with 3 years of hands-on experience "
            "in off-grid and hybrid solar system installations. I have worked "
            "with GreenTech NG and SolarMax Africa on residential projects across "
            "FCT and Niger State. I am passionate about clean energy and provide "
            "detailed system sizing reports before every installation."
        ),
        "state": "fct", "lga": "Maitama",
        "hourly_rate": 3200,  "daily_rate": 22000,
        "availability": WorkerProfile.Availability.AVAILABLE,
        "is_verified": False,
        "skills": ["off-grid-system-design", "inverter-battery-setup"],
    },
    {
        "first_name": "Rotimi",     "last_name": "Adeleke",
        "username":   "rotimi_adeleke",
        "email":      "rotimi.adeleke@tradelink.test",
        "phone":      "+2348041001009",
        "trade": "solar-installer",
        "experience_level": WorkerProfile.ExperienceLevel.EXPERT,
        "years_experience": 10,
        "bio": (
            "I am a senior solar energy engineer with 10 years of experience "
            "designing and installing utility-scale and commercial rooftop PV "
            "systems. My portfolio includes a 50kW system for a Lagos hospital, "
            "a 30kW system for a Lekki mall, and dozens of home installations. "
            "I offer full EPC services: design, supply, installation, and "
            "commissioning. Based in Lagos, willing to travel nationwide."
        ),
        "state": "lagos", "lga": "Lekki",
        "hourly_rate": 7000,  "daily_rate": 55000,
        "availability": WorkerProfile.Availability.AVAILABLE_SOON,
        "is_verified": True,
        "skills": ["rooftop-pv-installation", "inverter-battery-setup", "off-grid-system-design", "solar-maintenance-repair"],
    },

    # ── CARPENTERS ────────────────────────────────────────────────────────────
    {
        "first_name": "Biodun",     "last_name": "Adelaja",
        "username":   "biodun_adelaja",
        "email":      "biodun.adelaja@tradelink.test",
        "phone":      "+2348041001010",
        "trade": "carpenter",
        "experience_level": WorkerProfile.ExperienceLevel.EXPERIENCED,
        "years_experience": 9,
        "bio": (
            "Furniture carpenter with 9 years of experience making custom "
            "wardrobes, kitchen cabinets, beds, and office desks. I work in "
            "Ibadan and deliver across Oyo, Ogun, and Lagos. I use quality "
            "hardwood and marine board. My work is clean, precise, and durable. "
            "I offer free measurement visits within Ibadan."
        ),
        "state": "oyo", "lga": "Ibadan South-West",
        "hourly_rate": 3000,  "daily_rate": 22000,
        "availability": WorkerProfile.Availability.AVAILABLE,
        "is_verified": False,
        "skills": ["furniture-making", "interior-woodwork-decor"],
    },
    {
        "first_name": "Tunde",      "last_name": "Olatunji",
        "username":   "tunde_olatunji",
        "email":      "tunde.olatunji@tradelink.test",
        "phone":      "+2348041001011",
        "trade": "carpenter",
        "experience_level": WorkerProfile.ExperienceLevel.INTERMEDIATE,
        "years_experience": 4,
        "bio": (
            "Carpenter specialising in door and window installations, frame "
            "repair, and roof carpentry. I have worked on new builds and "
            "renovation projects in Kano, Kaduna, and Abuja over the last "
            "4 years. I work fast without compromising on quality and I "
            "provide a one-year guarantee on all fittings."
        ),
        "state": "kano", "lga": "Fagge",
        "hourly_rate": 2800,  "daily_rate": 20000,
        "availability": WorkerProfile.Availability.AVAILABLE,
        "is_verified": False,
        "skills": ["door-window-fitting", "roof-carpentry"],
    },
    {
        "first_name": "Seun",       "last_name": "Ogunleye",
        "username":   "seun_ogunleye",
        "email":      "seun.ogunleye@tradelink.test",
        "phone":      "+2348041001012",
        "trade": "carpenter",
        "experience_level": WorkerProfile.ExperienceLevel.EXPERT,
        "years_experience": 15,
        "bio": (
            "Master carpenter and woodwork artisan with 15 years of experience. "
            "I specialise in bespoke luxury furniture, custom-built wardrobes, "
            "ceiling work, and high-end interior woodwork for premium residential "
            "and hospitality clients. Past projects include a Banana Island "
            "mansion, a Victoria Island hotel lobby, and several Ikoyi penthouses. "
            "I run a workshop in Lagos Island with 3 assistants."
        ),
        "state": "lagos", "lga": "Lagos Island",
        "hourly_rate": 6500,  "daily_rate": 50000,
        "availability": WorkerProfile.Availability.AVAILABLE,
        "is_verified": True,
        "skills": ["furniture-making", "interior-woodwork-decor", "door-window-fitting", "roof-carpentry"],
    },

    # ── EXTRA WORKERS (for richer match data) ─────────────────────────────────
    {
        "first_name": "Musa",       "last_name": "Ibrahim",
        "username":   "musa_ibrahim",
        "email":      "musa.ibrahim@tradelink.test",
        "phone":      "+2348041001013",
        "trade": "electrician",
        "experience_level": WorkerProfile.ExperienceLevel.ENTRY,
        "years_experience": 1,
        "bio": (
            "Junior electrician with 1 year of on-site training under a master "
            "electrician in Kano. I can handle basic wiring, socket installations, "
            "and lighting fixtures. I am hardworking, eager to learn, and willing "
            "to work under supervision on larger projects."
        ),
        "state": "kano", "lga": "Tarauni",
        "hourly_rate": 1500,  "daily_rate": 10000,
        "availability": WorkerProfile.Availability.AVAILABLE,
        "is_verified": False,
        "skills": ["residential-wiring"],
    },
    {
        "first_name": "Grace",      "last_name": "Okonkwo",
        "username":   "grace_okonkwo",
        "email":      "grace.okonkwo@tradelink.test",
        "phone":      "+2348041001014",
        "trade": "solar-installer",
        "experience_level": WorkerProfile.ExperienceLevel.INTERMEDIATE,
        "years_experience": 4,
        "bio": (
            "Solar technician and off-grid system designer based in Enugu. "
            "I have 4 years of experience sizing and installing solar home "
            "systems for rural communities and urban homes without reliable "
            "grid power. I am also trained in solar water pumping systems."
        ),
        "state": "enugu", "lga": "Enugu East",
        "hourly_rate": 3000,  "daily_rate": 22000,
        "availability": WorkerProfile.Availability.AVAILABLE,
        "is_verified": False,
        "skills": ["off-grid-system-design", "rooftop-pv-installation"],
    },
    {
        "first_name": "Haruna",     "last_name": "Abdullahi",
        "username":   "haruna_abdullahi",
        "email":      "haruna.abdullahi@tradelink.test",
        "phone":      "+2348041001015",
        "trade": "plumber",
        "experience_level": WorkerProfile.ExperienceLevel.INTERMEDIATE,
        "years_experience": 5,
        "bio": (
            "Experienced plumber covering Abuja FCT and satellite towns. "
            "Specialises in bathroom renovations, geyser and water heater "
            "installations, and pipe leak detection using modern diagnostic "
            "tools. I respond to emergency call-outs within 2 hours in FCT."
        ),
        "state": "fct", "lga": "Kuje",
        "hourly_rate": 3000,  "daily_rate": 21000,
        "availability": WorkerProfile.Availability.AVAILABLE,
        "is_verified": False,
        "skills": ["bathroom-fitting", "pipe-installation-repair"],
    },
]


# ── Job data ──────────────────────────────────────────────────────────────────
# Each job references employer by index into EMPLOYER_DATA and trade by slug.
JOB_DATA = [
    # ── ELECTRICIAN JOBS (5) ──────────────────────────────────────────────────
    {
        "employer_idx": 0,
        "trade": "electrician",
        "title": "Residential Electrician — Lekki Phase 1 Estate (20 Units)",
        "description": (
            "Ogundimu Properties is completing a 20-unit terrace development in "
            "Lekki Phase 1 and requires an experienced electrician to handle all "
            "internal wiring, socket and switch installation, distribution board "
            "setup, and final testing for each unit.\n\n"
            "Scope of work:\n"
            "• Complete internal wiring for 20 x 3-bedroom terrace houses\n"
            "• Install DB boards, circuit breakers, and earthing systems\n"
            "• Fit all sockets, switches, light fittings (supplied by client)\n"
            "• CCTV conduit runs in each unit\n"
            "• Testing and commissioning before handover\n\n"
            "Timeline: 8 weeks. Candidate must have COREN or NECA certification."
        ),
        "job_type": Job.JobType.CONTRACT,
        "pay_type": Job.PayType.FIXED,
        "pay_min": 1800000,  "pay_max": 2500000,
        "state": "lagos",    "lga": "Lekki",
        "is_remote": False,
        "slots": 2,
        "skills": ["residential-wiring", "cctv-security-systems"],
        "deadline_days": 14,
    },
    {
        "employer_idx": 1,
        "trade": "electrician",
        "title": "Electrician for Office Block Maintenance Contract — Abuja",
        "description": (
            "Eze Facility Services manages a portfolio of 12 commercial office "
            "buildings in Abuja and requires a reliable electrician on a monthly "
            "retainer to handle routine maintenance, fault finding, and emergency "
            "repairs across all properties.\n\n"
            "Responsibilities:\n"
            "• Monthly inspection of electrical systems in all 12 buildings\n"
            "• Emergency call-outs within 2 hours (24/7 availability required)\n"
            "• Generator maintenance and servicing (4 generators)\n"
            "• Replacement of failed components — DB breakers, sockets, wiring\n"
            "• Monthly maintenance report\n\n"
            "Ideal candidate has experience with 3-phase systems and generators."
        ),
        "job_type": Job.JobType.CONTRACT,
        "pay_type": Job.PayType.MONTHLY,
        "pay_min": 180000,  "pay_max": 250000,
        "state": "fct",     "lga": "Wuse 2",
        "is_remote": False,
        "slots": 1,
        "skills": ["generator-maintenance", "residential-wiring"],
        "deadline_days": 10,
    },
    {
        "employer_idx": 0,
        "trade": "electrician",
        "title": "CCTV & Access Control Installer — Ajah Gated Community",
        "description": (
            "We need a specialist to install a complete CCTV and electronic access "
            "control system for a new 50-unit gated community in Ajah, Lagos.\n\n"
            "Scope:\n"
            "• 24 x outdoor IP cameras (equipment supplied)\n"
            "• 8 x indoor cameras in common areas\n"
            "• 2 x NVR systems with remote viewing setup\n"
            "• Electronic boom gate and intercom at main entrance\n"
            "• Structured cabling and conduit installation\n\n"
            "Experience with Hikvision and Dahua systems is required."
        ),
        "job_type": Job.JobType.ONCE_OFF,
        "pay_type": Job.PayType.FIXED,
        "pay_min": 800000,  "pay_max": 1200000,
        "state": "lagos",   "lga": "Ajah",
        "is_remote": False,
        "slots": 1,
        "skills": ["cctv-security-systems"],
        "deadline_days": 7,
    },
    {
        "employer_idx": 1,
        "trade": "electrician",
        "title": "Generator Installation Technician — Wuse 2, Abuja",
        "description": (
            "We require a technician to install and commission a 60 KVA Perkins "
            "generator for a 5-storey office building in Wuse 2, Abuja.\n\n"
            "The job includes:\n"
            "• Mounting and housing preparation (civil work done separately)\n"
            "• ATS (Automatic Transfer Switch) installation and wiring\n"
            "• Cable runs from generator to main panel\n"
            "• Load testing and commissioning\n"
            "• Training building maintenance staff on operation\n\n"
            "Must have experience with industrial generators above 40 KVA."
        ),
        "job_type": Job.JobType.ONCE_OFF,
        "pay_type": Job.PayType.FIXED,
        "pay_min": 350000,  "pay_max": 500000,
        "state": "fct",     "lga": "Wuse 2",
        "is_remote": False,
        "slots": 1,
        "skills": ["generator-maintenance"],
        "deadline_days": 5,
    },
    {
        "employer_idx": 2,
        "trade": "electrician",
        "title": "Solar-Electrical Integration Specialist — Port Harcourt",
        "description": (
            "GreenPower Solutions requires an electrician with solar integration "
            "experience to work alongside our solar team on hybrid system "
            "installations for residential clients in Port Harcourt.\n\n"
            "You will be responsible for:\n"
            "• AC-side wiring from inverter to distribution boards\n"
            "• Load analysis and circuit balancing\n"
            "• Change-over switch installation\n"
            "• Final electrical sign-off on all systems\n\n"
            "This is a 6-month contract with possibility of permanent hire. "
            "Experience with Luminous, Felicity, or Victron inverters is a plus."
        ),
        "job_type": Job.JobType.CONTRACT,
        "pay_type": Job.PayType.MONTHLY,
        "pay_min": 150000,  "pay_max": 200000,
        "state": "rivers",  "lga": "Port Harcourt",
        "is_remote": False,
        "slots": 2,
        "skills": ["solar-panel-integration", "residential-wiring"],
        "deadline_days": 21,
    },

    # ── PLUMBER JOBS (5) ──────────────────────────────────────────────────────
    {
        "employer_idx": 0,
        "trade": "plumber",
        "title": "Plumber for 20-Unit Estate — Full Plumbing & Sewage Works",
        "description": (
            "We need a senior plumber (or team lead) to handle complete plumbing "
            "works for our 20-unit terrace development in Lekki Phase 1.\n\n"
            "Scope:\n"
            "• Hot and cold water pipe installation for all 20 units\n"
            "• Bathroom and kitchen fitting (toilets, basins, showers)\n"
            "• Sewage and drainage system — main stack and branches\n"
            "• Overhead tank connections and ballcock installation\n"
            "• Pressure testing before tiling commences\n\n"
            "Timeline: 10 weeks parallel with electrical team. "
            "Candidate must supply own hand tools."
        ),
        "job_type": Job.JobType.CONTRACT,
        "pay_type": Job.PayType.FIXED,
        "pay_min": 2000000,  "pay_max": 2800000,
        "state": "lagos",    "lga": "Lekki",
        "is_remote": False,
        "slots": 2,
        "skills": ["pipe-installation-repair", "bathroom-fitting", "drainage-sewage"],
        "deadline_days": 14,
    },
    {
        "employer_idx": 1,
        "trade": "plumber",
        "title": "Emergency Plumber — Commercial Buildings Portfolio, Abuja",
        "description": (
            "Eze Facility Services needs a dependable plumber available for "
            "emergency call-outs and routine maintenance across 12 commercial "
            "buildings in Abuja FCT.\n\n"
            "Key responsibilities:\n"
            "• Respond to burst pipes and water leaks within 2 hours\n"
            "• Monthly plumbing inspection across all properties\n"
            "• Toilet, tap, and basin repair and replacement\n"
            "• Overhead tank cleaning and float valve service\n\n"
            "Monthly retainer with additional payment per emergency call-out."
        ),
        "job_type": Job.JobType.CONTRACT,
        "pay_type": Job.PayType.MONTHLY,
        "pay_min": 120000,  "pay_max": 160000,
        "state": "fct",     "lga": "Wuse",
        "is_remote": False,
        "slots": 1,
        "skills": ["pipe-installation-repair", "bathroom-fitting"],
        "deadline_days": 8,
    },
    {
        "employer_idx": 3,
        "trade": "plumber",
        "title": "Borehole & Water System Installer — Kano Residential Project",
        "description": (
            "Al-Amin Construction requires a plumber with borehole and water "
            "system experience for a new estate project in Kano.\n\n"
            "Work includes:\n"
            "• Borehole casing, pump installation (submersible, 2HP)\n"
            "• Overhead water tank (10,000L polyethylene) installation\n"
            "• Distribution pipe network to 15 housing units\n"
            "• All necessary valves, pressure gauges, and fittings\n\n"
            "Material cost is covered by the employer. Candidate should have "
            "experience with Northern Nigeria groundwater depths (30–60m)."
        ),
        "job_type": Job.JobType.ONCE_OFF,
        "pay_type": Job.PayType.FIXED,
        "pay_min": 600000,  "pay_max": 900000,
        "state": "kano",    "lga": "Nassarawa",
        "is_remote": False,
        "slots": 1,
        "skills": ["borehole-water-systems", "pipe-installation-repair"],
        "deadline_days": 12,
    },
    {
        "employer_idx": 4,
        "trade": "plumber",
        "title": "Bathroom Renovation Plumber — Ibadan Duplex",
        "description": (
            "I am renovating 3 bathrooms in my duplex in Ibadan and need a "
            "skilled plumber to handle the full plumbing works alongside the "
            "tiler and electrician.\n\n"
            "Scope:\n"
            "• Remove and dispose of old bathroom fittings\n"
            "• Install new wall-hung WC, vanity basin, and shower enclosure\n"
            "• Re-run concealed pipe work before tiling\n"
            "• Install towel rails, soap dishes (supplied by client)\n"
            "• Test all fixtures before sign-off\n\n"
            "Expected duration: 4–5 days per bathroom."
        ),
        "job_type": Job.JobType.ONCE_OFF,
        "pay_type": Job.PayType.FIXED,
        "pay_min": 280000,  "pay_max": 380000,
        "state": "oyo",     "lga": "Ibadan North",
        "is_remote": False,
        "slots": 1,
        "skills": ["bathroom-fitting"],
        "deadline_days": 5,
    },
    {
        "employer_idx": 3,
        "trade": "plumber",
        "title": "Drainage & Sewage Engineer — New Construction, Kano",
        "description": (
            "Al-Amin Construction needs a drainage specialist for a commercial "
            "plaza currently under construction in Kano.\n\n"
            "Works include:\n"
            "• Design and installation of main sewer line (150mm PVC)\n"
            "• Branch connections from 8 toilet blocks\n"
            "• Grease trap installation for restaurant units\n"
            "• Soak-away pit construction\n"
            "• Connection to municipal sewer (municipal approval in place)\n\n"
            "Must have experience with commercial drainage systems."
        ),
        "job_type": Job.JobType.CONTRACT,
        "pay_type": Job.PayType.FIXED,
        "pay_min": 450000,  "pay_max": 700000,
        "state": "kano",    "lga": "Fagge",
        "is_remote": False,
        "slots": 1,
        "skills": ["drainage-sewage", "pipe-installation-repair"],
        "deadline_days": 18,
    },

    # ── SOLAR INSTALLER JOBS (5) ──────────────────────────────────────────────
    {
        "employer_idx": 2,
        "trade": "solar-installer",
        "title": "Solar Installer — 20 Residential Systems, Port Harcourt",
        "description": (
            "GreenPower Solutions is executing a 20-home solar rollout in the "
            "Trans-Amadi and GRA areas of Port Harcourt. We need experienced "
            "solar installers to join our team for this 3-month project.\n\n"
            "Each installation includes:\n"
            "• 6–10 x 400W monocrystalline panels\n"
            "• 5 kVA inverter (Felicity or Luminous)\n"
            "• 2 x 200Ah lithium or gel batteries\n"
            "• Mounting structures (ground-fixed tiltable frames)\n"
            "• DC wiring, charge controller, and AC distribution\n\n"
            "You must be able to complete 1 full system every 2 days."
        ),
        "job_type": Job.JobType.CONTRACT,
        "pay_type": Job.PayType.FIXED,
        "pay_min": 2500000,  "pay_max": 3500000,
        "state": "rivers",   "lga": "Port Harcourt",
        "is_remote": False,
        "slots": 3,
        "skills": ["rooftop-pv-installation", "inverter-battery-setup"],
        "deadline_days": 10,
    },
    {
        "employer_idx": 2,
        "trade": "solar-installer",
        "title": "Off-Grid Solar Designer — Community Electrification Project",
        "description": (
            "GreenPower Solutions is partnering with an NGO on a rural "
            "electrification project in Ogoniland, Rivers State. We need "
            "a solar designer who can conduct site surveys, design the system, "
            "and oversee installation.\n\n"
            "Project scope:\n"
            "• Power 50 households and a health clinic\n"
            "• Design mini-grid or individual SHS systems\n"
            "• Prepare BoQ and procurement list\n"
            "• Supervise installation team (team supplied)\n"
            "• Commission and hand over to community\n\n"
            "Experience with mini-grid projects is highly preferred."
        ),
        "job_type": Job.JobType.CONTRACT,
        "pay_type": Job.PayType.FIXED,
        "pay_min": 1200000,  "pay_max": 1800000,
        "state": "rivers",   "lga": "Eleme",
        "is_remote": False,
        "slots": 1,
        "skills": ["off-grid-system-design", "rooftop-pv-installation"],
        "deadline_days": 20,
    },
    {
        "employer_idx": 0,
        "trade": "solar-installer",
        "title": "Solar Installer for Estate Common Areas — Ajah, Lagos",
        "description": (
            "Ogundimu Properties is installing solar power for street lighting "
            "and the clubhouse of our Ajah estate. We need a solar installer "
            "to design and execute the full installation.\n\n"
            "Scope:\n"
            "• 20 x solar street lights (10W integrated LED)\n"
            "• Clubhouse: 8 kW hybrid system (grid-tied with battery backup)\n"
            "• Panels to be roof-mounted on clubhouse\n"
            "• All wiring, conduit, and earthing\n\n"
            "Turnkey supply-and-install contract preferred."
        ),
        "job_type": Job.JobType.ONCE_OFF,
        "pay_type": Job.PayType.FIXED,
        "pay_min": 3500000,  "pay_max": 5000000,
        "state": "lagos",    "lga": "Ajah",
        "is_remote": False,
        "slots": 1,
        "skills": ["rooftop-pv-installation", "inverter-battery-setup", "off-grid-system-design"],
        "deadline_days": 15,
    },
    {
        "employer_idx": 1,
        "trade": "solar-installer",
        "title": "Solar System Maintenance Technician — Abuja (Retainer)",
        "description": (
            "Eze Facility Services has solar installations on 4 of our managed "
            "buildings and needs a maintenance technician on a monthly retainer.\n\n"
            "Duties:\n"
            "• Monthly inspection of all 4 systems\n"
            "• Panel cleaning and yield monitoring\n"
            "• Battery health checks and electrolyte top-up (where applicable)\n"
            "• Inverter fault diagnosis and repair\n"
            "• Written monthly report per site\n\n"
            "Must be based in Abuja or willing to relocate."
        ),
        "job_type": Job.JobType.PART_TIME,
        "pay_type": Job.PayType.MONTHLY,
        "pay_min": 80000,   "pay_max": 120000,
        "state": "fct",     "lga": "Wuse 2",
        "is_remote": False,
        "slots": 1,
        "skills": ["solar-maintenance-repair"],
        "deadline_days": 7,
    },
    {
        "employer_idx": 2,
        "trade": "solar-installer",
        "title": "Solar Sales & Installation Rep — Rivers & Bayelsa",
        "description": (
            "GreenPower Solutions is expanding into Bayelsa State and needs "
            "a motivated solar technician who can also do client consultation "
            "and basic system sizing for residential customers.\n\n"
            "Role:\n"
            "• Visit potential clients, assess power needs, recommend system\n"
            "• Prepare quotation with guidance from head office\n"
            "• Lead installation once sale is confirmed\n"
            "• Provide after-sales support and warranty visits\n\n"
            "Commission-based earnings on top of base salary. "
            "Motorbike or car access is required."
        ),
        "job_type": Job.JobType.FULL_TIME,
        "pay_type": Job.PayType.MONTHLY,
        "pay_min": 100000,  "pay_max": 180000,
        "state": "rivers",  "lga": "Obio-Akpor",
        "is_remote": False,
        "slots": 2,
        "skills": ["rooftop-pv-installation", "inverter-battery-setup"],
        "deadline_days": 25,
    },

    # ── CARPENTER JOBS (5) ────────────────────────────────────────────────────
    {
        "employer_idx": 4,
        "trade": "carpenter",
        "title": "Bespoke Furniture Carpenter — Ibadan (4 Rooms)",
        "description": (
            "I am furnishing a newly built 4-bedroom duplex in Ibadan and need "
            "a skilled carpenter to produce custom furniture for all rooms.\n\n"
            "Items required:\n"
            "• 4 x fitted wardrobes with sliding doors (measurements supplied)\n"
            "• 1 x kitchen cabinet set (L-shape, 12 units upper and lower)\n"
            "• 2 x TV console units\n"
            "• Study desk and bookshelf for home office\n\n"
            "Materials: marine board and melamine finish (client supplies). "
            "Carpenter supplies fittings, hinges, and labour."
        ),
        "job_type": Job.JobType.ONCE_OFF,
        "pay_type": Job.PayType.FIXED,
        "pay_min": 650000,  "pay_max": 900000,
        "state": "oyo",     "lga": "Ibadan North",
        "is_remote": False,
        "slots": 1,
        "skills": ["furniture-making", "interior-woodwork-decor"],
        "deadline_days": 10,
    },
    {
        "employer_idx": 0,
        "trade": "carpenter",
        "title": "Roof Carpenter — 20-Unit Terrace Development, Lekki",
        "description": (
            "Ogundimu Properties needs an experienced roof carpenter for the "
            "roofing works on our 20-unit terrace development in Lekki Phase 1.\n\n"
            "Scope:\n"
            "• Rafter and purlin installation for 20 terrace roofs\n"
            "• Hip and ridge construction\n"
            "• Fascia and barge board fitting\n"
            "• Preparation for roof tile contractor\n\n"
            "Timeline: 6 weeks. Must be able to work at height safely. "
            "Team of 2–3 carpenters required."
        ),
        "job_type": Job.JobType.CONTRACT,
        "pay_type": Job.PayType.FIXED,
        "pay_min": 1500000,  "pay_max": 2200000,
        "state": "lagos",    "lga": "Lekki",
        "is_remote": False,
        "slots": 3,
        "skills": ["roof-carpentry"],
        "deadline_days": 12,
    },
    {
        "employer_idx": 3,
        "trade": "carpenter",
        "title": "Door & Window Installer — Commercial Plaza, Kano",
        "description": (
            "Al-Amin Construction requires a carpenter to handle all door and "
            "window installations for a 3-storey commercial plaza in Kano.\n\n"
            "Works include:\n"
            "• Fitting 40 x solid wood internal doors and frames\n"
            "• Installation of 25 x aluminium-clad wood window frames\n"
            "• Skirting board and architrave installation throughout\n"
            "• Storeroom shelving (6 storerooms)\n\n"
            "Materials supplied by client. Duration approximately 3 weeks."
        ),
        "job_type": Job.JobType.CONTRACT,
        "pay_type": Job.PayType.FIXED,
        "pay_min": 400000,  "pay_max": 600000,
        "state": "kano",    "lga": "Nassarawa",
        "is_remote": False,
        "slots": 2,
        "skills": ["door-window-fitting"],
        "deadline_days": 8,
    },
    {
        "employer_idx": 4,
        "trade": "carpenter",
        "title": "Interior Woodwork Artisan — High-End Residence, Ibadan",
        "description": (
            "I am an interior designer working on a high-end residence in "
            "Bodija, Ibadan and I need an experienced woodwork artisan for "
            "bespoke interior carpentry.\n\n"
            "Scope:\n"
            "• Coffered ceiling panels in living and dining areas\n"
            "• Wall panelling in master bedroom and study\n"
            "• Custom floating shelves and display niches\n"
            "• Decorative wood cladding on staircase feature wall\n\n"
            "This is a prestige project. Only craftspeople with a strong "
            "portfolio of similar work should apply. Sample images required."
        ),
        "job_type": Job.JobType.ONCE_OFF,
        "pay_type": Job.PayType.FIXED,
        "pay_min": 900000,  "pay_max": 1400000,
        "state": "oyo",     "lga": "Ibadan North-East",
        "is_remote": False,
        "slots": 1,
        "skills": ["interior-woodwork-decor", "furniture-making"],
        "deadline_days": 6,
    },
    {
        "employer_idx": 1,
        "trade": "carpenter",
        "title": "Maintenance Carpenter — Commercial Buildings Portfolio, Abuja",
        "description": (
            "Eze Facility Services needs a part-time maintenance carpenter "
            "across our 12 managed commercial buildings in Abuja.\n\n"
            "Regular duties:\n"
            "• Door, window, and lock repairs\n"
            "• Warped door planing and re-hanging\n"
            "• Furniture repair and touch-ups\n"
            "• Emergency boarding-up after break-ins\n"
            "• Monthly condition report\n\n"
            "Approximately 10–15 days of work per month. Retainer fee + "
            "material costs covered."
        ),
        "job_type": Job.JobType.PART_TIME,
        "pay_type": Job.PayType.MONTHLY,
        "pay_min": 80000,   "pay_max": 120000,
        "state": "fct",     "lga": "Wuse",
        "is_remote": False,
        "slots": 1,
        "skills": ["door-window-fitting"],
        "deadline_days": 30,
    },
]


# ─────────────────────────────────────────────────────────────────────────────
#  COMMAND
# ─────────────────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = (
        "Seed the database with 5 employer accounts, 15 worker accounts, "
        "4 trade categories, 16 skills, and 20 realistic job listings. "
        "All accounts use the password: TradeLink@2025"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Delete all existing seed data before creating fresh records.",
        )

    def handle(self, *args, **options):
        if options["flush"]:
            self._flush()

        with transaction.atomic():
            trades  = self._create_trades()
            skills  = self._create_skills(trades)
            employers, employer_profiles = self._create_employers()
            workers,  worker_profiles   = self._create_workers(trades, skills)
            jobs = self._create_jobs(trades, skills, employer_profiles)
            self._create_reviews(employer_profiles, worker_profiles, jobs)

        self.stdout.write(self.style.SUCCESS(
            "\n✅  Seed complete!\n"
            f"   Trades:    {len(trades)}\n"
            f"   Skills:    {len(skills)}\n"
            f"   Employers: {len(employer_profiles)}\n"
            f"   Workers:   {len(worker_profiles)}\n"
            f"   Jobs:      {len(jobs)}\n"
            f"\n   🔑  All accounts password: {SEED_PASSWORD}\n"
            "\n   Sample logins:\n"
            "   chukwuemeka.obi@tradelink.test   (electrician worker)\n"
            "   ifeanyi.okafor@tradelink.test    (solar worker)\n"
            "   adewale.ogundimu@tradelink.test  (employer)\n"
            "   ngozi.eze@tradelink.test         (employer)\n"
        ))

    # ── Flush ─────────────────────────────────────────────────────────────────

    def _flush(self):
        self.stdout.write("  Flushing existing seed data…")
        # Delete users whose emails end with @tradelink.test
        deleted, _ = User.objects.filter(email__endswith="@tradelink.test").delete()
        # Delete trade categories created by seed (cascades to skills & jobs)
        tc_deleted, _ = TradeCategory.objects.filter(
            slug__in=[t["slug"] for t in TRADE_DATA]
        ).delete()
        self.stdout.write(f"  Deleted {deleted} users, {tc_deleted} trade categories.")

    # ── Trades ────────────────────────────────────────────────────────────────

    def _create_trades(self):
        self.stdout.write("  Creating trade categories…")
        trades = {}
        for i, td in enumerate(TRADE_DATA):
            obj, created = TradeCategory.objects.get_or_create(
                slug=td["slug"],
                defaults={
                    "name":              td["name"],
                    "icon_class":        td["icon_class"],
                    "description":       td["description"],
                    "clip_context_text": td["clip_context_text"],
                    "is_active":         True,
                    "display_order":     i,
                },
            )
            trades[td["slug"]] = obj
            status = "created" if created else "exists"
            self.stdout.write(f"    [{status}] {obj.name}")
        return trades

    # ── Skills ────────────────────────────────────────────────────────────────

    def _create_skills(self, trades):
        self.stdout.write("  Creating skills…")
        skills = {}
        for td in TRADE_DATA:
            trade_obj = trades[td["slug"]]
            for sk in td["skills"]:
                obj, created = Skill.objects.get_or_create(
                    category=trade_obj,
                    slug=sk["slug"],
                    defaults={"name": sk["name"], "is_active": True},
                )
                skills[sk["slug"]] = obj
                status = "created" if created else "exists"
                self.stdout.write(f"    [{status}] {obj}")
        return skills

    # ── Employers ─────────────────────────────────────────────────────────────

    def _create_employers(self):
        self.stdout.write("  Creating employer users & profiles…")
        users, profiles = [], []
        for ed in EMPLOYER_DATA:
            try:
                user = User.objects.get(email=ed["email"])
                created = False
            except User.DoesNotExist:
                user = User.objects.create_user(
                    username=ed["username"],
                    email=ed["email"],
                    phone_number=ed["phone"],
                    password=SEED_PASSWORD,
                    first_name=ed["first_name"],
                    last_name=ed["last_name"],
                    is_active=True,
                )
                created = True

            profile, _ = EmployerProfile.objects.get_or_create(
                user=user,
                defaults={
                    "company_name":  ed["company_name"],
                    "company_type":  ed["company_type"],
                    "industry":      ed["industry"],
                    "about":         ed["about"],
                    "state":         ed["state"],
                    "lga":           ed["lga"],
                    "website":       ed["website"],
                    "is_verified":   ed["is_verified"],
                },
            )
            users.append(user)
            profiles.append(profile)
            status = "created" if created else "exists"
            self.stdout.write(f"    [{status}] {user.email}")
        return users, profiles

    # ── Workers ───────────────────────────────────────────────────────────────

    def _create_workers(self, trades, skills):
        self.stdout.write("  Creating worker users & profiles…")
        users, profiles = [], []

        # Map trade slug → TradeCategory object
        # Workers reference trade by slug stored in WORKER_DATA
        trade_slug_map = {
            "electrician":    "electrician",
            "plumber":        "plumber",
            "solar-installer":"solar-installer",
            "carpenter":      "carpenter",
        }

        for wd in WORKER_DATA:
            try:
                user = User.objects.get(email=wd["email"])
                created = False
            except User.DoesNotExist:
                user = User.objects.create_user(
                    username=wd["username"],
                    email=wd["email"],
                    phone_number=wd["phone"],
                    password=SEED_PASSWORD,
                    first_name=wd["first_name"],
                    last_name=wd["last_name"],
                    is_active=True,
                )
                created = True

            trade_obj = trades.get(wd["trade"])
            profile, p_created = WorkerProfile.objects.get_or_create(
                user=user,
                defaults={
                    "trade_category":    trade_obj,
                    "experience_level":  wd["experience_level"],
                    "years_experience":  wd["years_experience"],
                    "bio":               wd["bio"],
                    "state":             wd["state"],
                    "lga":               wd["lga"],
                    "hourly_rate":       wd["hourly_rate"],
                    "daily_rate":        wd["daily_rate"],
                    "availability":      wd["availability"],
                    "is_verified":       wd["is_verified"],
                    "is_featured":       wd.get("is_featured", False),
                    "profile_completion": self._estimate_completion(wd),
                },
            )

            # Attach skills
            if p_created:
                for sk_slug in wd.get("skills", []):
                    skill_obj = skills.get(sk_slug)
                    if skill_obj:
                        WorkerSkill.objects.get_or_create(
                            worker=profile,
                            skill=skill_obj,
                            defaults={
                                "proficiency":      "proficient",
                                "years_experience": min(wd["years_experience"], 5),
                            },
                        )

            users.append(user)
            profiles.append(profile)
            status = "created" if created else "exists"
            self.stdout.write(f"    [{status}] {user.email} ({wd['trade']})")
        return users, profiles

    def _estimate_completion(self, wd):
        score = 0
        if wd.get("bio"):              score += 30
        if wd.get("trade"):            score += 20
        if wd.get("state"):            score += 15
        if wd.get("hourly_rate"):      score += 10
        if wd.get("daily_rate"):       score += 10
        if wd.get("skills"):           score += 15
        return min(score, 100)

    # ── Jobs ──────────────────────────────────────────────────────────────────

    def _create_jobs(self, trades, skills, employer_profiles):
        self.stdout.write("  Creating job listings…")
        jobs = []
        for jd in JOB_DATA:
            employer = employer_profiles[jd["employer_idx"]]
            trade    = trades[jd["trade"]]
            deadline = date.today() + timedelta(days=jd["deadline_days"])

            job, created = Job.objects.get_or_create(
                title=jd["title"],
                employer=employer,
                defaults={
                    "trade_category": trade,
                    "description":    jd["description"],
                    "job_type":       jd["job_type"],
                    "pay_type":       jd["pay_type"],
                    "pay_min":        jd["pay_min"],
                    "pay_max":        jd["pay_max"],
                    "state":          jd["state"],
                    "lga":            jd["lga"],
                    "is_remote":      jd["is_remote"],
                    "slots":          jd["slots"],
                    "status":         Job.Status.ACTIVE,
                    "deadline":       deadline,
                },
            )

            # Attach required skills
            if created:
                for sk_slug in jd.get("skills", []):
                    skill_obj = skills.get(sk_slug)
                    if skill_obj:
                        job.required_skills.add(skill_obj)

            jobs.append(job)
            status = "created" if created else "exists"
            self.stdout.write(f"    [{status}] {job.title[:60]}")
        return jobs

    # ── Reviews ───────────────────────────────────────────────────────────────

    def _create_reviews(self, employer_profiles, worker_profiles, jobs):
        """
        Create a handful of realistic reviews to populate the rating UI.
        Employer → Worker reviews on completed jobs.
        """
        self.stdout.write("  Creating reviews…")

        review_data = [
            # (employer_idx, worker_idx, job_idx, rating, comment)
            (0, 0, 0,  5, "Chukwuemeka did outstanding wiring work across all 20 units. Clean, safe, and on schedule. Highly recommended."),
            (0, 2, 0,  5, "Olumide brought expert knowledge to our project. Panel setup was immaculate. Will use again."),
            (1, 1, 1,  4, "Babatunde responded quickly to every call-out and fixed issues the same day. Good communicator."),
            (1, 4, 5,  4, "Suleiman did solid plumbing work. A couple of small snags fixed promptly. Generally happy."),
            (2, 6, 10, 5, "Ifeanyi's solar installations were excellent. Every system commissioned perfectly first time."),
            (2, 8, 11, 5, "Rotimi designed a clever system for our community project. Very professional and knowledgeable."),
            (0, 9, 15, 4, "Biodun made great wardrobes. Finish was very clean. Slight delay on final room but quality compensates."),
            (3, 10, 17, 3, "Tunde got the doors fitted but needed supervision on the window frames. Acceptable for the price."),
            (4, 11, 15, 5, "Seun's woodwork is exceptional. Our clients were blown away by the quality. Premium artisan."),
            (1, 12, 1,  4, "Musa was helpful and worked hard under our senior electrician's guidance. Good attitude."),
        ]

        count = 0
        for emp_idx, wkr_idx, job_idx, rating, comment in review_data:
            # Guard against index out of range
            if (emp_idx >= len(employer_profiles) or
                    wkr_idx >= len(worker_profiles) or
                    job_idx >= len(jobs)):
                continue

            employer_profile = employer_profiles[emp_idx]
            worker_profile   = worker_profiles[wkr_idx]
            job              = jobs[job_idx]

            _, created = Review.objects.get_or_create(
                job=job,
                reviewer=employer_profile.user,
                review_type=Review.ReviewType.EMPLOYER_TO_WORKER,
                defaults={
                    "reviewee":   worker_profile.user,
                    "rating":     rating,
                    "comment":    comment,
                    "is_visible": True,
                },
            )
            if created:
                count += 1
                self.stdout.write(
                    f"    [created] {employer_profile.user.username} → "
                    f"{worker_profile.user.username} ({rating}★)"
                )
        self.stdout.write(f"  {count} reviews created.")