"""
marketplace/management/commands/seed_marketplace_products_expanded.py
======================================================================
Creates 220 realistic Nigerian tool & equipment marketplace listings:
  • 20 alternate listings across the original 10 categories (2 per category)
  • 20 brand-new categories with 10 products each (200 products)

Total: 220 new products across 30 categories (10 original + 20 new).

Usage
─────
    python manage.py seed_marketplace_products_expanded
    python manage.py seed_marketplace_products_expanded --seller <worker_profile_pk>
    python manage.py seed_marketplace_products_expanded --clear

Options
───────
  --seller PK   Assign all seeded products to a specific WorkerProfile (UUID or int pk).
                Defaults to the first verified WorkerProfile found.
  --clear       Delete all previously seeded products (identified by the
                SEEDED_TAG in their description) before creating new ones.
  --no-active   Create products in DRAFT status instead of ACTIVE.
"""

import random
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

SEEDED_TAG = '[SEEDED]'

# ──────────────────────────────────────────────────────────────────────────────
#  CATEGORY + PRODUCT DATA
# ──────────────────────────────────────────────────────────────────────────────

SEED_DATA = [

    # ══════════════════════════════════════════════════════════════════════════
    #  SECTION A — 20 ALTERNATE PRODUCTS ACROSS THE ORIGINAL 10 CATEGORIES
    #  (2 extra products per original category, same slugs so get_or_create
    #   attaches them to the existing category rows)
    # ══════════════════════════════════════════════════════════════════════════

    # ── A1. Power Tools (extras) ──────────────────────────────────────────────
    {
        'category': 'Power Tools',
        'slug': 'power-tools',
        'icon_class': 'fas fa-bolt',
        'description': 'Electric and battery-powered tools for professional trades.',
        'display_order': 1,
        'products': [
            {
                'title': 'Hilti TE 60-ATC/AVR Combihammer 1100W',
                'description': (
                    'Heavy-duty SDS-Max rotary hammer with active vibration reduction. '
                    'Used for drilling 50mm core holes on a hospital extension project. '
                    'All functions work: rotation-only, hammer-only, combo. '
                    'Comes with carry case and three SDS-Max bits. ' + SEEDED_TAG
                ),
                'brand': 'Hilti', 'model_number': 'TE 60-ATC/AVR',
                'condition': 'used_good', 'price': Decimal('185000'),
                'min_offer': Decimal('160000'),
                'state': 'Lagos', 'lga': 'Ikeja',
                'pickup_notes': 'Oregun industrial estate, weekdays.',
            },
            {
                'title': 'Milwaukee M18 FUEL 4-1/2" Angle Grinder (Bare Tool)',
                'description': (
                    'Brushless cordless grinder, compatible with all M18 batteries. '
                    'RAPID STOP brake, no lock-on switch for safety. '
                    'Purchased for a one-off job — barely used, guard and flange included. '
                    'Sold without battery. ' + SEEDED_TAG
                ),
                'brand': 'Milwaukee', 'model_number': '2780-20',
                'condition': 'used_good', 'price': Decimal('68000'),
                'min_offer': Decimal('58000'),
                'state': 'Abuja', 'lga': 'Wuse 2',
                'pickup_notes': 'Wuse 2, call before coming.',
            },
        ],
    },

    # ── A2. Hand Tools (extras) ───────────────────────────────────────────────
    {
        'category': 'Hand Tools',
        'slug': 'hand-tools',
        'icon_class': 'fas fa-tools',
        'description': 'Non-powered tools for skilled tradespeople.',
        'display_order': 2,
        'products': [
            {
                'title': 'Wera 900/9 Screwdriver Set — 9-Piece Kraftform',
                'description': (
                    'German-made ergonomic screwdriver set: 4× slotted, 3× Phillips, '
                    '2× Pozidriv. Hardened tips, colour-coded handles. '
                    'Used by an electrician for 18 months, tips show normal wear. '
                    'Stored in original wall holder rack. ' + SEEDED_TAG
                ),
                'brand': 'Wera', 'model_number': '900/9',
                'condition': 'used_good', 'price': Decimal('14500'),
                'min_offer': Decimal('12000'),
                'state': 'Lagos', 'lga': 'Surulere',
                'pickup_notes': 'Eric Moore area, evenings.',
            },
            {
                'title': 'Irwin Record 9" Quick-Grip F-Clamp Set (6 Pieces)',
                'description': (
                    'Six F-clamps with 225mm jaw opening and 75mm throat depth. '
                    'Rubber pads intact, quick-release trigger smooth on all six. '
                    'Used for gluing timber furniture panels. ' + SEEDED_TAG
                ),
                'brand': 'Irwin', 'model_number': 'Quick-Grip 225mm',
                'condition': 'used_good', 'price': Decimal('18000'),
                'state': 'Oyo', 'lga': 'Ibadan North',
                'pickup_notes': 'Challenge area, Ibadan.',
            },
        ],
    },

    # ── A3. Electrical Equipment (extras) ─────────────────────────────────────
    {
        'category': 'Electrical Equipment',
        'slug': 'electrical-equipment',
        'icon_class': 'fas fa-plug',
        'description': 'Wiring tools, test equipment, and electrical accessories.',
        'display_order': 3,
        'products': [
            {
                'title': 'Megger MIT410 Insulation & Continuity Tester',
                'description': (
                    'Professional insulation resistance tester, 50V–1000V test voltages. '
                    'Used for PAT testing and installation commissioning on 3 sites. '
                    'Auto discharge, PI and DAR calculations. Comes with leads and case. ' + SEEDED_TAG
                ),
                'brand': 'Megger', 'model_number': 'MIT410',
                'condition': 'used_good', 'price': Decimal('95000'),
                'min_offer': Decimal('82000'),
                'state': 'Lagos', 'lga': 'Victoria Island',
                'pickup_notes': 'VI, appointment only, serious buyers.',
            },
            {
                'title': 'Chint NXB-63 MCB Assorted Pack — 20 Pieces',
                'description': (
                    'Mixed pack: 5× 6A, 5× 10A, 5× 16A, 5× 32A — all Type B, 230V. '
                    'Brand new in original boxes. Surplus from a panel-building project. '
                    'Suitable for residential distribution boards. ' + SEEDED_TAG
                ),
                'brand': 'Chint',
                'condition': 'new', 'price': Decimal('22000'),
                'min_offer': Decimal('19000'),
                'state': 'Ogun', 'lga': 'Abeokuta South',
                'pickup_notes': 'Oke-Mosan area, Abeokuta.',
            },
        ],
    },

    # ── A4. Plumbing Supplies (extras) ────────────────────────────────────────
    {
        'category': 'Plumbing Supplies',
        'slug': 'plumbing-supplies',
        'icon_class': 'fas fa-faucet',
        'description': 'Pipe fittings, valves, and plumbing tools.',
        'display_order': 4,
        'products': [
            {
                'title': 'Ridgid 206 Inside/Outside Pipe Reamer',
                'description': (
                    'T-handle ratcheting pipe reamer for inside and outside burrs. '
                    'Fits 3/8"–2" pipe. Blades still sharp, ratchet clicks positively. '
                    'Used on a hotel refit — excellent tool at a fraction of new price. ' + SEEDED_TAG
                ),
                'brand': 'Ridgid', 'model_number': '206',
                'condition': 'used_good', 'price': Decimal('13500'),
                'state': 'Rivers', 'lga': 'Eleme',
                'pickup_notes': 'Eleme junction, near SPDC gate.',
            },
            {
                'title': 'Geberit Mepla Multilayer Pipe — 100m × 16mm Coil',
                'description': (
                    'MLCP (aluminium-lined) hot and cold water pipe, 16mm OD × 2mm wall. '
                    'Full 100m coil, unused. Offcut from a large underfloor heating job. '
                    'Compatible with standard Mepla press fittings. ' + SEEDED_TAG
                ),
                'brand': 'Geberit', 'model_number': 'Mepla 16mm',
                'condition': 'new', 'price': Decimal('48000'),
                'min_offer': Decimal('42000'),
                'state': 'Lagos', 'lga': 'Eti-Osa',
                'pickup_notes': 'Ajah, available daily.',
            },
        ],
    },

    # ── A5. Safety Gear (extras) ──────────────────────────────────────────────
    {
        'category': 'Safety Gear',
        'slug': 'safety-gear',
        'icon_class': 'fas fa-hard-hat',
        'description': 'PPE and safety equipment for trade professionals.',
        'display_order': 5,
        'products': [
            {
                'title': 'Uvex Pheos S Safety Spectacles — 30 Pairs (Clear)',
                'description': (
                    'Bulk pack of 30 clear-lens safety spectacles, EN166 rated. '
                    'Lightweight polycarbonate frame, anti-scratch coating. '
                    'Surplus from a construction site PPE resupply order. '
                    'All individually wrapped — brand new. ' + SEEDED_TAG
                ),
                'brand': 'Uvex', 'model_number': 'Pheos S',
                'condition': 'new', 'price': Decimal('15000'),
                'min_offer': Decimal('13000'),
                'state': 'Lagos', 'lga': 'Ogba-Ijaye-Onikan',
                'pickup_notes': 'Ogba, call ahead.',
            },
            {
                'title': 'Draeger X-am 2500 4-Gas Personal Monitor',
                'description': (
                    'Compact confined-space gas detector: O₂, CO, H₂S, LEL. '
                    'Used on refinery maintenance jobs. Calibrated 3 months ago. '
                    'Bump-test daily log attached. Comes with charging cradle. ' + SEEDED_TAG
                ),
                'brand': 'Draeger', 'model_number': 'X-am 2500',
                'condition': 'used_good', 'price': Decimal('145000'),
                'min_offer': Decimal('125000'),
                'state': 'Delta', 'lga': 'Warri South',
                'pickup_notes': 'PTI road, Effurun, Delta State.',
            },
        ],
    },

    # ── A6. Woodworking Tools (extras) ────────────────────────────────────────
    {
        'category': 'Woodworking Tools',
        'slug': 'woodworking-tools',
        'icon_class': 'fas fa-drafting-compass',
        'description': 'Saws, planes, routers, and carpentry equipment.',
        'display_order': 6,
        'products': [
            {
                'title': 'DeWalt DW735X 13" Thickness Planer with Stand',
                'description': (
                    '3-knife planer, 10,000 RPM cutter-head, 25mm max depth per pass. '
                    'Comes with factory stand. Used in a production furniture workshop '
                    'for 18 months. Knives turned once — still cutting clean. ' + SEEDED_TAG
                ),
                'brand': 'DeWalt', 'model_number': 'DW735X',
                'condition': 'used_good', 'price': Decimal('285000'),
                'min_offer': Decimal('255000'),
                'state': 'Lagos', 'lga': 'Alimosho',
                'pickup_notes': 'Idimu, workshop — large machine, bring transport.',
            },
            {
                'title': 'Axminster Trade AT254TS Table Saw 254mm — 230V',
                'description': (
                    'Cabinet table saw with extension wings and riving knife. '
                    '254mm blade, 82mm max depth. Fence still accurate. '
                    'Dust port fitted. Used for cabinet carcass work — very clean machine. ' + SEEDED_TAG
                ),
                'brand': 'Axminster', 'model_number': 'AT254TS',
                'condition': 'used_good', 'price': Decimal('220000'),
                'min_offer': Decimal('190000'),
                'state': 'Oyo', 'lga': 'Ibadan South-West',
                'pickup_notes': 'Dugbe industrial road.',
            },
        ],
    },

    # ── A7. Measuring Instruments (extras) ────────────────────────────────────
    {
        'category': 'Measuring Instruments',
        'slug': 'measuring-instruments',
        'icon_class': 'fas fa-ruler-combined',
        'description': 'Levels, distance meters, thermometers, and gauges.',
        'display_order': 7,
        'products': [
            {
                'title': 'Topcon RL-H5A Self-Levelling Rotary Laser Level',
                'description': (
                    'Outdoor-grade rotary laser, ±1.5mm/10m accuracy. '
                    'IP66 rated, 800m diameter range with supplied detector. '
                    'Used on drainage and slab levelling jobs for 2 years. '
                    'Self-levels within ±5°, carry case and tripod mount included. ' + SEEDED_TAG
                ),
                'brand': 'Topcon', 'model_number': 'RL-H5A',
                'condition': 'used_good', 'price': Decimal('245000'),
                'min_offer': Decimal('210000'),
                'state': 'Abuja', 'lga': 'Kubwa',
                'pickup_notes': 'Kubwa Phase 3, available weekends.',
            },
            {
                'title': 'Mitutoyo 500-196-30 Absolute Digital Caliper 150mm',
                'description': (
                    'IP67 coolant-resistant digital caliper, ±0.02mm accuracy. '
                    'ABS (absolute) system — no zeroing after power-off. '
                    'Used lightly in a fabrication shop. Jaw faces clean, no pitting. ' + SEEDED_TAG
                ),
                'brand': 'Mitutoyo', 'model_number': '500-196-30',
                'condition': 'used_good', 'price': Decimal('42000'),
                'state': 'Lagos', 'lga': 'Apapa',
                'pickup_notes': 'Apapa, call to confirm.',
            },
        ],
    },

    # ── A8. HVAC & Refrigeration (extras) ────────────────────────────────────
    {
        'category': 'HVAC & Refrigeration',
        'slug': 'hvac-refrigeration',
        'icon_class': 'fas fa-snowflake',
        'description': 'Air-conditioning tools, refrigerants, and HVAC equipment.',
        'display_order': 8,
        'products': [
            {
                'title': 'Testo 557 Digital Manifold (Bluetooth)',
                'description': (
                    'Digital manifold gauge for R22, R32, R134a, R404A, R407C, R410A. '
                    'Connects to Testo Smart app via Bluetooth. Used on 30+ AC services. '
                    'Hose set included, calibration valid to end of year. ' + SEEDED_TAG
                ),
                'brand': 'Testo', 'model_number': '557',
                'condition': 'used_good', 'price': Decimal('118000'),
                'min_offer': Decimal('100000'),
                'state': 'Lagos', 'lga': 'Ikeja',
                'pickup_notes': 'Near MMIA, flexible times.',
            },
            {
                'title': 'Rothenberger ROCUT 42 TC Pipe Cutter (6–42mm)',
                'description': (
                    'Ratchet pipe cutter for copper and thin-wall stainless up to 42mm. '
                    'Wheel still sharp, one-hand operation. Ideal for AC line-set installation. '
                    'Lightly used on a villa project. ' + SEEDED_TAG
                ),
                'brand': 'Rothenberger', 'model_number': 'ROCUT 42 TC',
                'condition': 'used_good', 'price': Decimal('19500'),
                'state': 'Rivers', 'lga': 'Obio-Akpor',
                'pickup_notes': 'Rumuola junction, PH.',
            },
        ],
    },

    # ── A9. Welding & Fabrication (extras) ───────────────────────────────────
    {
        'category': 'Welding & Fabrication',
        'slug': 'welding-fabrication',
        'icon_class': 'fas fa-fire',
        'description': 'Welding machines, plasma cutters, and metal fabrication tools.',
        'display_order': 9,
        'products': [
            {
                'title': 'Fronius TransSteel 2200 MIG/MAG Welder',
                'description': (
                    'Semi-professional MIG welder, 10–220A, 230V single phase. '
                    'Synergic line controls for wire and gas adjustment. '
                    'Used on light fabrication jobs. Gun and ground cable original. '
                    'Includes manual wire feeder and Euro connector. ' + SEEDED_TAG
                ),
                'brand': 'Fronius', 'model_number': 'TransSteel 2200',
                'condition': 'used_good', 'price': Decimal('225000'),
                'min_offer': Decimal('195000'),
                'state': 'Lagos', 'lga': 'Oshodi-Isale',
                'pickup_notes': 'Oshodi, heavy machine — bring transport.',
            },
            {
                'title': 'Speedglas 9100X Auto-Darkening Welding Helmet',
                'description': (
                    'Premium auto-dark helmet, shade 5–8 / 9–13, 0.1ms reaction time. '
                    'Used mainly for TIG welding stainless steel. Lens pristine. '
                    'Comes with grinding shield and replacement head-band. ' + SEEDED_TAG
                ),
                'brand': 'Speedglas', 'model_number': '9100X',
                'condition': 'used_good', 'price': Decimal('78000'),
                'min_offer': Decimal('68000'),
                'state': 'Kano', 'lga': 'Nassarawa',
                'pickup_notes': 'Kano Workshop Road, call ahead.',
            },
        ],
    },

    # ── A10. Materials & Supplies (extras) ───────────────────────────────────
    {
        'category': 'Materials & Supplies',
        'slug': 'materials-supplies',
        'icon_class': 'fas fa-boxes',
        'description': 'Raw materials, fixings, adhesives, and consumables.',
        'display_order': 10,
        'products': [
            {
                'title': 'Sika SikaFlex 252 Structural Adhesive — 12 × 300ml',
                'description': (
                    'Polyurethane structural adhesive for bonding metal, glass, and plastic. '
                    '12 × 300ml cartridges, all factory-sealed. '
                    'Suitable for vehicle body-repair, aluminium cladding, and GRP panels. '
                    'Best before 2027. ' + SEEDED_TAG
                ),
                'brand': 'Sika', 'model_number': 'SikaFlex 252',
                'condition': 'new', 'price': Decimal('32000'),
                'min_offer': Decimal('28000'),
                'state': 'Lagos', 'lga': 'Gbagada',
                'pickup_notes': 'Gbagada, contact for address.',
            },
            {
                'title': 'BRC A393 Steel Mesh Sheets — 5 Pieces (2.4 × 4.8m)',
                'description': (
                    'Heavy-gauge concrete reinforcement mesh, A393 grade. '
                    'Wire diameter 10mm, 200mm square grid. '
                    '5 sheets left over from a suspended slab pour. '
                    'Must collect with flatbed — no delivery. ' + SEEDED_TAG
                ),
                'condition': 'new', 'price': Decimal('95000'),
                'min_offer': Decimal('82000'),
                'state': 'Abuja', 'lga': 'Abuja Municipal',
                'pickup_notes': 'Construction depot, Lugbe road.',
            },
        ],
    },


    # ══════════════════════════════════════════════════════════════════════════
    #  SECTION B — 20 BRAND-NEW CATEGORIES (10 products each)
    # ══════════════════════════════════════════════════════════════════════════

    # ── B1. Scaffolding & Access ──────────────────────────────────────────────
    {
        'category': 'Scaffolding & Access',
        'slug': 'scaffolding-access',
        'icon_class': 'fas fa-layer-group',
        'description': 'Scaffolding systems, ladders, and elevated work platforms.',
        'display_order': 11,
        'products': [
            {
                'title': 'Youngman BoSS 3T Aluminium Tower — 4.2m Working Height',
                'description': (
                    'Folding aluminium mobile scaffold tower. Working height 4.2m, '
                    'platform height 2.2m. Used for painting a 2-storey building. '
                    'All locking pins and casters present. Clean and straight. ' + SEEDED_TAG
                ),
                'brand': 'Youngman', 'model_number': 'BoSS 3T',
                'condition': 'used_good', 'price': Decimal('185000'),
                'min_offer': Decimal('160000'),
                'state': 'Lagos', 'lga': 'Ikeja',
                'pickup_notes': 'Oregun, Ikeja — large item, bring van.',
            },
            {
                'title': 'Lyte Industrial Fibreglass Ladder 4.2m (14 Rung)',
                'description': (
                    'Class 1 fibreglass extension ladder. Electrician-safe — non-conductive. '
                    'Rubber feet intact, rungs clean with good anti-slip serration. '
                    'Used on commercial electrical fit-out for 1 year. ' + SEEDED_TAG
                ),
                'brand': 'Lyte', 'model_number': 'NELT425',
                'condition': 'used_good', 'price': Decimal('48000'),
                'state': 'Abuja', 'lga': 'Garki',
                'pickup_notes': 'Garki 2, flexible pickup.',
            },
            {
                'title': 'Haki Universal Scaffolding — 40m² System Set',
                'description': (
                    'Modular ringlock scaffolding system sufficient for approx 40m² facade. '
                    'Includes standards, ledgers, transoms, baseplates and planks. '
                    'Hot-dip galvanised — very low rust. Used on 4 projects. ' + SEEDED_TAG
                ),
                'brand': 'Haki',
                'condition': 'used_good', 'price': Decimal('580000'),
                'min_offer': Decimal('500000'),
                'state': 'Lagos', 'lga': 'Amuwo-Odofin',
                'pickup_notes': 'Mile 2, heavy load — buyer to arrange haulage.',
            },
            {
                'title': 'Werner MT-22 Multi-Position Ladder (Up to 6.7m)',
                'description': (
                    'Articulating ladder convertible to A-frame, extension, stairway '
                    'or scaffold position. 150kg rated. Used in a renovation business. '
                    'All locks engage firmly. ' + SEEDED_TAG
                ),
                'brand': 'Werner', 'model_number': 'MT-22',
                'condition': 'used_good', 'price': Decimal('65000'),
                'min_offer': Decimal('55000'),
                'state': 'Rivers', 'lga': 'Port Harcourt',
                'pickup_notes': 'GRA Phase 1, PH.',
            },
            {
                'title': 'Layher Allround Scaffolding — 6m × 2 Bay Starter Set',
                'description': (
                    '2-bay facade scaffold kit: 12 standards, 20 ledgers, 8 planks, '
                    'baseplates, and couplers. German-made Layher system. '
                    'Ready to erect. Bought from a liquidation — minimal use. ' + SEEDED_TAG
                ),
                'brand': 'Layher',
                'condition': 'used_good', 'price': Decimal('420000'),
                'min_offer': Decimal('370000'),
                'state': 'Lagos', 'lga': 'Agbado-Oke-Odo',
                'pickup_notes': 'Abule-Egba, large volume — lorry required.',
            },
            {
                'title': 'Step Stool 3-Tread — Hailo S60 ProfiLine Aluminium',
                'description': (
                    'Lightweight 3-step professional stool, 150kg rated. '
                    'Slip-resistant treads. Used in an electrical panel room for 8 months. '
                    'Perfect cosmetic condition. ' + SEEDED_TAG
                ),
                'brand': 'Hailo', 'model_number': 'S60 ProfiLine',
                'condition': 'used_good', 'price': Decimal('16500'),
                'state': 'Anambra', 'lga': 'Awka South',
                'pickup_notes': 'Awka town, call to arrange.',
            },
            {
                'title': 'Steel Scaffolding Tube (48.3mm × 3.2mm) — 6m, 20 Pieces',
                'description': (
                    '20 × 6m hot-dip galvanised BS 1139 scaffolding tube. '
                    'Grade S235, 48.3mm OD, 3.2mm wall. Used once, minimal rust. '
                    'Straight, no dents. Priced per job-lot. ' + SEEDED_TAG
                ),
                'condition': 'used_good', 'price': Decimal('180000'),
                'min_offer': Decimal('155000'),
                'state': 'Ogun', 'lga': 'Ota',
                'pickup_notes': 'Sango-Ota industrial area.',
            },
            {
                'title': 'Cuplock Scaffolding System — 100 Node Set',
                'description': (
                    '100 cuplock nodes with top and bottom cups plus mixed lengths of '
                    'standards and ledgers. Hot-galvanised, high-strength steel. '
                    'Suitable for multi-storey construction access. ' + SEEDED_TAG
                ),
                'condition': 'used_good', 'price': Decimal('650000'),
                'min_offer': Decimal('580000'),
                'state': 'Kano', 'lga': 'Fagge',
                'pickup_notes': 'Near Kano central mosque, call ahead.',
            },
            {
                'title': 'Painter\'s Trestle Set — 2 × Steel Trestles + Plank',
                'description': (
                    'Heavy-duty steel folding trestles (max 1.8m height) with 4m × 230mm '
                    'scaffold board. Used for interior painting on 3 projects. '
                    'Legs fold flat, locking pins all present. ' + SEEDED_TAG
                ),
                'condition': 'used_good', 'price': Decimal('24000'),
                'state': 'Lagos', 'lga': 'Mushin',
                'pickup_notes': 'Mushin, call to confirm.',
            },
            {
                'title': 'Zarges Z600 Aluminium Step Ladder 7-Tread (2.4m)',
                'description': (
                    'German professional stepladder, 150kg capacity. Safety shoes, '
                    'wide platform top step. Only used in a clean workshop environment. '
                    'Treads scratch-free, hinges tight. ' + SEEDED_TAG
                ),
                'brand': 'Zarges', 'model_number': 'Z600 42134',
                'condition': 'used_good', 'price': Decimal('38000'),
                'state': 'Lagos', 'lga': 'Victoria Island',
                'pickup_notes': 'VI, weekdays only.',
            },
        ],
    },

    # ── B2. Concrete & Masonry Equipment ─────────────────────────────────────
    {
        'category': 'Concrete & Masonry Equipment',
        'slug': 'concrete-masonry',
        'icon_class': 'fas fa-cubes',
        'description': 'Concrete mixers, vibrators, block-laying tools and masonry equipment.',
        'display_order': 12,
        'products': [
            {
                'title': 'Belle Minimix 150 Cement Mixer — 230V',
                'description': (
                    '150-litre drum, 120-litre batch capacity. 230V, 550W motor runs strong. '
                    'Used on a domestic extension project. Drum clean, bearings good. '
                    'Polyethylene drum with no cracks. ' + SEEDED_TAG
                ),
                'brand': 'Belle', 'model_number': 'Minimix 150',
                'condition': 'used_good', 'price': Decimal('95000'),
                'min_offer': Decimal('82000'),
                'state': 'Lagos', 'lga': 'Alimosho',
                'pickup_notes': 'Egbeda, bring van.',
            },
            {
                'title': 'Wacker Neuson IRFU 38 Poker Vibrator — 4m Hose',
                'description': (
                    'Integrated electric poker vibrator, 38mm head diameter. '
                    '230V, automatic restart after power loss. 4m hose included. '
                    'Used on slab pours for 6 months. Head runs true, no wobble. ' + SEEDED_TAG
                ),
                'brand': 'Wacker Neuson', 'model_number': 'IRFU 38',
                'condition': 'used_good', 'price': Decimal('68000'),
                'state': 'Abuja', 'lga': 'Bwari',
                'pickup_notes': 'Bwari, call to arrange pickup.',
            },
            {
                'title': 'Husqvarna TS 400 F Floor Saw — 400mm Blade',
                'description': (
                    'Petrol floor saw for cutting concrete, asphalt and tiles. '
                    '13HP Honda engine starts first pull. Blade guard intact. '
                    'Includes one diamond blade. Used on road reinstatement contracts. ' + SEEDED_TAG
                ),
                'brand': 'Husqvarna', 'model_number': 'TS 400 F',
                'condition': 'used_fair', 'price': Decimal('345000'),
                'min_offer': Decimal('295000'),
                'state': 'Lagos', 'lga': 'Apapa',
                'pickup_notes': 'Apapa, large machine — hire a vehicle.',
            },
            {
                'title': 'Screed Rail Set — 3m Aluminium, 4 Rails',
                'description': (
                    '4 × 3m anodised aluminium screed rails for levelling concrete floors. '
                    'H-profile, 60mm height. Adjustable feet on each. '
                    'Used on a warehouse slab — clean with no bends. ' + SEEDED_TAG
                ),
                'condition': 'used_good', 'price': Decimal('28000'),
                'state': 'Oyo', 'lga': 'Ibadan North',
                'pickup_notes': 'Apata area, Ibadan.',
            },
            {
                'title': 'Diamond Core Drill Bit Set — 6 Sizes (52–150mm)',
                'description': (
                    '6-piece wet diamond core set: 52, 68, 82, 102, 127, 150mm. '
                    'SDS-Plus shank, 300mm barrel depth. Used on a hospital MEP project. '
                    'Segments 60% remaining on average. ' + SEEDED_TAG
                ),
                'condition': 'used_good', 'price': Decimal('38000'),
                'min_offer': Decimal('32000'),
                'state': 'Rivers', 'lga': 'Port Harcourt',
                'pickup_notes': 'Trans-Amadi industrial, PH.',
            },
            {
                'title': 'Briggs & Stratton 6HP Petrol Cement Mixer — 350L',
                'description': (
                    'Large-capacity site mixer with 350L drum (280L batch). '
                    'Towable frame with road wheels. B&S petrol engine, pull-start. '
                    'Used on a block-work project for 4 months. Motor runs cleanly. ' + SEEDED_TAG
                ),
                'brand': 'Briggs & Stratton',
                'condition': 'used_good', 'price': Decimal('185000'),
                'min_offer': Decimal('160000'),
                'state': 'Enugu', 'lga': 'Enugu North',
                'pickup_notes': 'New Haven, Enugu — large load.',
            },
            {
                'title': 'Laser Screed Marker — Perimeter Kit for 5 × 5m Slab',
                'description': (
                    'Laser-level-compatible screed pin system. 20 height-adjustable pins '
                    'with base plates for marking slab target elevation. '
                    'New — purchased for a project that changed spec. ' + SEEDED_TAG
                ),
                'condition': 'new', 'price': Decimal('21000'),
                'state': 'Lagos', 'lga': 'Gbagada',
                'pickup_notes': 'Gbagada, call ahead.',
            },
            {
                'title': 'Masonry Trowel Set — Marshalltown, 5 Pieces',
                'description': (
                    '5-piece set: brick trowel 280mm, pointing trowel, margin trowel, '
                    'gauging trowel, and bucket trowel. Forged steel, cork handles. '
                    'Used for 2 years by a professional bricklayer, blades well maintained. ' + SEEDED_TAG
                ),
                'brand': 'Marshalltown',
                'condition': 'used_good', 'price': Decimal('18500'),
                'state': 'Ogun', 'lga': 'Sagamu',
                'pickup_notes': 'Sagamu, meet at express junction.',
            },
            {
                'title': 'Block-Making Machine — Manual 2-Block Mould Press',
                'description': (
                    'Manual hydraulic block moulding press, produces 2 × 9" hollow blocks '
                    'per cycle. Heavy-gauge steel frame. Used in a small block yard. '
                    'Dies clean, press cylinder seals good. ' + SEEDED_TAG
                ),
                'condition': 'used_good', 'price': Decimal('145000'),
                'min_offer': Decimal('125000'),
                'state': 'Kano', 'lga': 'Kano Municipal',
                'pickup_notes': 'Sharada industrial area, Kano.',
            },
            {
                'title': 'Siniat Speedskim Plastering Kit — Long Handle + 2 Blades',
                'description': (
                    'Speedskim ST 600mm rule plus short-handle set. Includes '
                    '600mm flexible blade and 600mm semi-flexible blade. '
                    'Barely used on one apartment skim project. Blades clean. ' + SEEDED_TAG
                ),
                'brand': 'Siniat', 'model_number': 'Speedskim ST',
                'condition': 'used_good', 'price': Decimal('12000'),
                'state': 'Lagos', 'lga': 'Lekki',
                'pickup_notes': 'Lekki Phase 1, evenings.',
            },
        ],
    },

    # ── B3. Generators & Power Supply ─────────────────────────────────────────
    {
        'category': 'Generators & Power Supply',
        'slug': 'generators-power-supply',
        'icon_class': 'fas fa-charging-station',
        'description': 'Petrol, diesel, and solar generators for site and workshop power.',
        'display_order': 13,
        'products': [
            {
                'title': 'Mikano MK6500E 5.5kVA Open-Frame Generator',
                'description': (
                    '5.5kVA single-phase open-frame generator, electric start. '
                    'OHV 4-stroke engine runs quiet and smooth. AVR fitted. '
                    'Used as backup for a small factory for 1 year. '
                    'Oil changed 2 months ago, starts first time. ' + SEEDED_TAG
                ),
                'brand': 'Mikano', 'model_number': 'MK6500E',
                'condition': 'used_good', 'price': Decimal('265000'),
                'min_offer': Decimal('235000'),
                'state': 'Lagos', 'lga': 'Ikeja',
                'pickup_notes': 'Oregun road, Ikeja.',
            },
            {
                'title': 'Elemax SH7600EX 6kVA Generator — Honda Engine',
                'description': (
                    'Reliable Honda GX390 powered generator, 6kVA. Electric and recoil '
                    'start. AVR for stable voltage. Used as office backup, well serviced. '
                    'Comes with original manual and remote start fob. ' + SEEDED_TAG
                ),
                'brand': 'Elemax', 'model_number': 'SH7600EX',
                'condition': 'used_good', 'price': Decimal('380000'),
                'min_offer': Decimal('340000'),
                'state': 'Abuja', 'lga': 'Garki',
                'pickup_notes': 'Area 10, Garki, Abuja.',
            },
            {
                'title': 'Perkins 20kVA Silent Diesel Generator — Soundproofed',
                'description': (
                    '20kVA three-phase silent generator, Perkins 404D-22 engine. '
                    'Low noise enclosure (<68dB at 7m). Used as bank branch backup. '
                    'Automatic transfer switch ready. Service history available. ' + SEEDED_TAG
                ),
                'brand': 'Perkins',
                'condition': 'used_good', 'price': Decimal('2800000'),
                'min_offer': Decimal('2500000'),
                'state': 'Lagos', 'lga': 'Victoria Island',
                'pickup_notes': 'VI — serious buyers with transport only.',
            },
            {
                'title': 'Inverter-Charger 5kVA — Luminous Cruze+ 10 VA',
                'description': (
                    'Off-grid inverter/charger unit, 5kVA / 4000W, 48V DC. '
                    'Solar-ready MPPT charge controller built in. '
                    'Used in a residential solar installation for 18 months. '
                    'Fans working, display clear, no fault codes. ' + SEEDED_TAG
                ),
                'brand': 'Luminous', 'model_number': 'Cruze+ 10 VA',
                'condition': 'used_good', 'price': Decimal('185000'),
                'state': 'Lagos', 'lga': 'Surulere',
                'pickup_notes': 'Bode Thomas, Surulere.',
            },
            {
                'title': 'Solar Panel — Jinko 400W Monocrystalline (4 Panels)',
                'description': (
                    '4 × Jinko JKM400M-72HL panels, MC4 connectors. '
                    'Used for 10 months in a hybrid residential system. '
                    'Power output checked — all within 3% of rated output. '
                    'Frames good, glass clean, no delamination. ' + SEEDED_TAG
                ),
                'brand': 'Jinko', 'model_number': 'JKM400M-72HL',
                'condition': 'used_good', 'price': Decimal('320000'),
                'min_offer': Decimal('285000'),
                'state': 'Oyo', 'lga': 'Ibadan North',
                'pickup_notes': 'Bodija, Ibadan.',
            },
            {
                'title': 'Automatic Voltage Regulator (AVR) — 5000VA Servo',
                'description': (
                    'Servo motor AVR, 5kVA, input 140–260V, output 220V ±2%. '
                    'Suitable for protecting sensitive equipment from mains fluctuations. '
                    'Used for 2 years on a printing machine. Voltage output stable. ' + SEEDED_TAG
                ),
                'condition': 'used_good', 'price': Decimal('55000'),
                'state': 'Kano', 'lga': 'Nasarawa',
                'pickup_notes': 'Farm Centre Road, Kano.',
            },
            {
                'title': 'Pramac GS7000 7kVA Generator — Yamaha Engine',
                'description': (
                    'Italian-branded generator with Yamaha MZ360 4-stroke OHV engine. '
                    '7kVA peak, 6kVA continuous. AVR stabilised output. '
                    'Used at a catering event twice — barely run in. '
                    'Electric start, remote panel capable. ' + SEEDED_TAG
                ),
                'brand': 'Pramac', 'model_number': 'GS7000',
                'condition': 'used_good', 'price': Decimal('420000'),
                'min_offer': Decimal('375000'),
                'state': 'Rivers', 'lga': 'Eleme',
                'pickup_notes': 'Eleme, call before coming.',
            },
            {
                'title': '200Ah AGM Deep-Cycle Battery — Ritar DC12-200',
                'description': (
                    '12V 200Ah sealed AGM battery, M8 bolt terminals. '
                    'Used in a solar storage bank for 14 months, maintained at float. '
                    'Load-tested at 185Ah — still strong. '
                    'Ideal for inverter backup systems. ' + SEEDED_TAG
                ),
                'brand': 'Ritar', 'model_number': 'DC12-200',
                'condition': 'used_good', 'price': Decimal('85000'),
                'state': 'Abuja', 'lga': 'Mabushi',
                'pickup_notes': 'Mabushi district, Abuja.',
            },
            {
                'title': 'Victron MultiPlus-II 48/5000/70-50 Inverter/Charger',
                'description': (
                    'Premium European 5000VA inverter/charger, 48V bank, 70A charge current. '
                    'Remote panel, Venus GX compatible. '
                    'Removed from a premium solar installation during a system upgrade. '
                    'Firmware up to date, no faults. ' + SEEDED_TAG
                ),
                'brand': 'Victron', 'model_number': 'MultiPlus-II 48/5000',
                'condition': 'used_good', 'price': Decimal('680000'),
                'min_offer': Decimal('600000'),
                'state': 'Lagos', 'lga': 'Ikoyi',
                'pickup_notes': 'Ikoyi, appointment only.',
            },
            {
                'title': 'Distribution Board — 18-Way DP Metal Enclosure (New)',
                'description': (
                    '18-way double-pole consumer unit in steel enclosure with DIN rail, '
                    'neutral bar, earth bar, and blanks. Brand new, unbuilt. '
                    'Suitable for 3-phase distribution at small commercial sites. '
                    'Supplied without MCBs — buyer adds own breakers. ' + SEEDED_TAG
                ),
                'condition': 'new', 'price': Decimal('28000'),
                'state': 'Lagos', 'lga': 'Mushin',
                'pickup_notes': 'Mushin market area.',
            },
        ],
    },

    # ── B4. Painting & Decorating ─────────────────────────────────────────────
    {
        'category': 'Painting & Decorating',
        'slug': 'painting-decorating',
        'icon_class': 'fas fa-paint-roller',
        'description': 'Airless sprayers, rollers, mixers, and paint trade equipment.',
        'display_order': 14,
        'products': [
            {
                'title': 'Graco Magnum X5 Airless Paint Sprayer',
                'description': (
                    'Airless sprayer, 0.27 HP motor, up to 125m of 1/4" hose. '
                    'RAC V tip included. Used for interior emulsion spray on 2 sites. '
                    'Pump seals replaced 6 months ago. Includes suction hose and filter. ' + SEEDED_TAG
                ),
                'brand': 'Graco', 'model_number': 'Magnum X5',
                'condition': 'used_good', 'price': Decimal('120000'),
                'min_offer': Decimal('100000'),
                'state': 'Lagos', 'lga': 'Ikeja',
                'pickup_notes': 'Allen Avenue, Ikeja.',
            },
            {
                'title': 'Wagner W 950 Flexio Paint Sprayer — HVLP',
                'description': (
                    'HVLP turbine sprayer for interior surfaces. Adjustable spray width '
                    'and flow. Used for lacquering furniture. All cups and nozzles included. '
                    'Fully cleaned and tested before sale. ' + SEEDED_TAG
                ),
                'brand': 'Wagner', 'model_number': 'W 950 Flexio',
                'condition': 'used_good', 'price': Decimal('38000'),
                'state': 'Oyo', 'lga': 'Ibadan South-West',
                'pickup_notes': 'Dugbe area, Ibadan.',
            },
            {
                'title': 'Faithfull Paint Mixing Paddle 80mm × 500mm — 10-Pack',
                'description': (
                    '10 new mixing paddles, 80mm diameter, for use with 13mm drill chuck. '
                    'Heavy-gauge steel wire, powder-coated. Suitable for paint, plaster, '
                    'and adhesive mixing. Surplus from a painting contract. ' + SEEDED_TAG
                ),
                'brand': 'Faithfull',
                'condition': 'new', 'price': Decimal('8500'),
                'state': 'Rivers', 'lga': 'Port Harcourt',
                'pickup_notes': 'NTA Road area, PH.',
            },
            {
                'title': '9" Roller Frame Set + 20 Sleeves (Polyester, Short Pile)',
                'description': (
                    'Heavy-duty cage frame with 10mm nap roller. Set includes 20 short-pile '
                    'polyester sleeve refills. New — bulk-ordered for a contract, '
                    'surplus after job scaled down. ' + SEEDED_TAG
                ),
                'condition': 'new', 'price': Decimal('12000'),
                'state': 'Lagos', 'lga': 'Agege',
                'pickup_notes': 'Agege motor road.',
            },
            {
                'title': 'Festool PLANEX LHS 225 Drywall Sander',
                'description': (
                    'Long-neck drywall sander with LED ring lighting and self-levelling '
                    'head. Integrated Bluetooth connection to dust extractor. '
                    'Used for skim-coat finishing on 2 apartment blocks. '
                    'Pads 40% life remaining, motor strong. ' + SEEDED_TAG
                ),
                'brand': 'Festool', 'model_number': 'PLANEX LHS 225',
                'condition': 'used_good', 'price': Decimal('285000'),
                'min_offer': Decimal('245000'),
                'state': 'Lagos', 'lga': 'Victoria Island',
                'pickup_notes': 'VI — serious trade buyers only.',
            },
            {
                'title': 'Paint Bucket Lids — 5L Gamma Seal, 50-Pack',
                'description': (
                    '50 × Gamma Seal screw-on lids for standard 5L paint buckets. '
                    'Airtight and re-openable — no dried skins. '
                    'New in box, surplus from a bulk order. ' + SEEDED_TAG
                ),
                'condition': 'new', 'price': Decimal('18000'),
                'state': 'Abuja', 'lga': 'Lugbe',
                'pickup_notes': 'Lugbe, near airport.',
            },
            {
                'title': 'Bosch GTR 30 CE Random Orbital Sander 125mm',
                'description': (
                    'Professional ROS with 5mm orbit, 125mm pad. 300W motor. '
                    'Used for furniture sanding. Pad in good condition, '
                    'dust bag clean, variable speed works. ' + SEEDED_TAG
                ),
                'brand': 'Bosch', 'model_number': 'GTR 30 CE',
                'condition': 'used_good', 'price': Decimal('22000'),
                'state': 'Anambra', 'lga': 'Nnewi North',
                'pickup_notes': 'Nnewi, call before coming.',
            },
            {
                'title': 'Stanley SurForm Block Plane Set — 4 Pieces',
                'description': (
                    'Four SurForm tools: standard plane, pocket plane, round file, '
                    'and half-round file. Ideal for shaping fibreglass, hardboard, or timber. '
                    'Light use, blades serviceable. ' + SEEDED_TAG
                ),
                'brand': 'Stanley',
                'condition': 'used_good', 'price': Decimal('7500'),
                'state': 'Lagos', 'lga': 'Yaba',
                'pickup_notes': 'Yaba Tech area.',
            },
            {
                'title': 'Nap Roller Extension Pole — 1.8–3m Telescoping Steel',
                'description': (
                    '3m maximum extension aluminium telescoping handle for paint rollers. '
                    'Universal 3/4" threaded end. New — 3 left from a contract order. '
                    'Price is per pole. ' + SEEDED_TAG
                ),
                'condition': 'new', 'price': Decimal('4500'),
                'slots': 3,
                'state': 'Delta', 'lga': 'Uvwie',
                'pickup_notes': 'Effurun, Delta State.',
            },
            {
                'title': 'Blue Spot 40-Piece Masking Tape Bulk Pack (48mm × 50m)',
                'description': (
                    '40 rolls of professional painter\'s masking tape, 48mm wide, '
                    '50m per roll. Clean release up to 30 days. '
                    'New — full sealed case from a trade wholesaler. ' + SEEDED_TAG
                ),
                'brand': 'Blue Spot',
                'condition': 'new', 'price': Decimal('22000'),
                'min_offer': Decimal('19000'),
                'state': 'Lagos', 'lga': 'Ojo',
                'pickup_notes': 'Trade Fair area.',
            },
        ],
    },

    # ── B5. Automotive Workshop Tools ─────────────────────────────────────────
    {
        'category': 'Automotive Workshop Tools',
        'slug': 'automotive-workshop-tools',
        'icon_class': 'fas fa-car-mechanic',
        'description': 'Lifts, diagnostic tools, and workshop equipment for mechanics.',
        'display_order': 15,
        'products': [
            {
                'title': 'Bosch KTS 560 OBD Diagnostic Scanner',
                'description': (
                    'Professional diagnostic tool for all OBD2 vehicles. '
                    'Reads and clears fault codes, live data, coding, and adaptations. '
                    'Used by an independent workshop for 2 years. '
                    'Software subscription still active for 8 months. ' + SEEDED_TAG
                ),
                'brand': 'Bosch', 'model_number': 'KTS 560',
                'condition': 'used_good', 'price': Decimal('480000'),
                'min_offer': Decimal('420000'),
                'state': 'Lagos', 'lga': 'Mushin',
                'pickup_notes': 'Mushin workshop, call ahead.',
            },
            {
                'title': 'Snap-on ATECH3F250 1/2" Drive Torque Wrench 250Nm',
                'description': (
                    'Industry-standard torque wrench, ±3% accuracy. '
                    '20–250Nm range, click-type with lockable collar. '
                    'Calibration certificate available on request. '
                    'Kept in case, used only for wheel torqueing. ' + SEEDED_TAG
                ),
                'brand': 'Snap-on', 'model_number': 'ATECH3F250',
                'condition': 'used_good', 'price': Decimal('165000'),
                'min_offer': Decimal('145000'),
                'state': 'Abuja', 'lga': 'Gudu',
                'pickup_notes': 'Gudu, Abuja, call to arrange.',
            },
            {
                'title': '4-Post Vehicle Lift — 4-Tonne Hydraulic (240V)',
                'description': (
                    'Four-post drive-on car lift, 4,000kg capacity. Electric-hydraulic. '
                    'Runway length 4.6m. Installed in a private garage, 240V supply. '
                    'Seals tight, no leak. Disassembly and transport by buyer. ' + SEEDED_TAG
                ),
                'condition': 'used_good', 'price': Decimal('1850000'),
                'min_offer': Decimal('1600000'),
                'state': 'Lagos', 'lga': 'Lekki',
                'pickup_notes': 'Lekki Phase 2 — substantial item, buyer dismantles.',
            },
            {
                'title': 'Milwaukee M12 Fuel Ratchet 3/8" — 2 Batteries',
                'description': (
                    'Compact cordless ratchet, 81Nm breakaway torque. '
                    'Comes with 2 × M12 2.0Ah batteries and charger. '
                    'Used in a light-vehicle workshop for 14 months. Mechanism smooth. ' + SEEDED_TAG
                ),
                'brand': 'Milwaukee', 'model_number': 'M12 FRAC38-202',
                'condition': 'used_good', 'price': Decimal('88000'),
                'min_offer': Decimal('76000'),
                'state': 'Rivers', 'lga': 'Port Harcourt',
                'pickup_notes': 'Trans-Amadi, PH.',
            },
            {
                'title': 'Tyre Changer Machine — Manual Bead Breaker + Rim Arm',
                'description': (
                    'Heavy-duty manual tyre changer. Handles 13"–21" rims. '
                    'Steel swing arm, rubber bumpers. Used in a roadside tyre shop '
                    'for 3 years. Paintwork worn but structurally sound. ' + SEEDED_TAG
                ),
                'condition': 'used_fair', 'price': Decimal('65000'),
                'state': 'Kano', 'lga': 'Fagge',
                'pickup_notes': 'Kantin Kwari market area, Kano.',
            },
            {
                'title': 'GS Caltex 5W-30 Fully Synthetic Engine Oil — 20L Drum',
                'description': (
                    '20-litre drum of GS Caltex Kixx G1 5W-30 SP/CF fully synthetic oil. '
                    'Suitable for petrol and light diesel engines. '
                    'New and sealed — surplus from a fleet order. ' + SEEDED_TAG
                ),
                'brand': 'GS Caltex', 'model_number': 'Kixx G1 5W-30',
                'condition': 'new', 'price': Decimal('58000'),
                'state': 'Lagos', 'lga': 'Amuwo-Odofin',
                'pickup_notes': 'Festac Town.',
            },
            {
                'title': 'Chicago Pneumatic CP7775 Pneumatic Impact Wrench 1/2"',
                'description': (
                    '880Nm max torque air impact wrench. Hog-ring anvil for fast '
                    'socket changes. Used in a busy workshop for 2 years. '
                    'Rotor vanes freshly replaced — feels like new. ' + SEEDED_TAG
                ),
                'brand': 'Chicago Pneumatic', 'model_number': 'CP7775',
                'condition': 'used_good', 'price': Decimal('42000'),
                'state': 'Lagos', 'lga': 'Ikeja',
                'pickup_notes': 'Ladipo market area.',
            },
            {
                'title': 'Coats 5060A Wheel Balancer — Semi-Automatic',
                'description': (
                    'Semi-automatic wheel balancer, handles 10"–26" wheels up to 70kg. '
                    'Used in a tyre fitting business for 4 years. '
                    'Self-calibration function works. LCD readout clear. ' + SEEDED_TAG
                ),
                'brand': 'Coats', 'model_number': '5060A',
                'condition': 'used_fair', 'price': Decimal('380000'),
                'min_offer': Decimal('320000'),
                'state': 'Abuja', 'lga': 'Wuse',
                'pickup_notes': 'Zone 5, Wuse — large machine.',
            },
            {
                'title': 'Draper Expert 200-Piece Socket Set 1/4" 3/8" 1/2"',
                'description': (
                    '200-piece professional socket and wrench set in blow-moulded case. '
                    'Metric and imperial sockets, extensions, universal joints, '
                    'spark plug sockets. Used lightly for 1 year. All pieces accounted for. ' + SEEDED_TAG
                ),
                'brand': 'Draper Expert',
                'condition': 'used_good', 'price': Decimal('48000'),
                'state': 'Oyo', 'lga': 'Ibadan North-East',
                'pickup_notes': 'Ojoo area, Ibadan.',
            },
            {
                'title': 'OTC Tools 6780 Stinger Strut Spring Compressor Set',
                'description': (
                    'MacPherson strut spring compressor — saddle type for coil spring '
                    'removal and installation. Max 175mm coil diameter. '
                    'Used on Honda and Toyota suspension work. Threads and hooks sound. ' + SEEDED_TAG
                ),
                'brand': 'OTC Tools', 'model_number': '6780',
                'condition': 'used_good', 'price': Decimal('28000'),
                'state': 'Lagos', 'lga': 'Mushin',
                'pickup_notes': 'Ladipo, Mushin.',
            },
        ],
    },

    # ── B6. Cleaning & Janitorial Equipment ───────────────────────────────────
    {
        'category': 'Cleaning & Janitorial Equipment',
        'slug': 'cleaning-janitorial',
        'icon_class': 'fas fa-broom',
        'description': 'Industrial cleaning machines, vacuum cleaners, and janitorial supplies.',
        'display_order': 16,
        'products': [
            {
                'title': 'Kärcher K 7 Premium Pressure Washer 160 Bar',
                'description': (
                    '160 bar, 600 l/h flow, Full Control gun. Onboard hose storage. '
                    'Used for post-construction site cleaning on 3 projects. '
                    'Pump has no leaks, O-rings recently serviced. '
                    '20m hose, dirt blaster and T-Racer included. ' + SEEDED_TAG
                ),
                'brand': 'Kärcher', 'model_number': 'K 7 Premium',
                'condition': 'used_good', 'price': Decimal('185000'),
                'min_offer': Decimal('160000'),
                'state': 'Lagos', 'lga': 'Ikeja',
                'pickup_notes': 'GRA Ikeja, call ahead.',
            },
            {
                'title': 'Nilfisk GD 930 S2 Industrial Wet/Dry Vacuum',
                'description': (
                    '30L stainless steel tank, 1200W motor. Handles debris, liquids, '
                    'and plaster dust. HEPA filtration system. '
                    'Used in a commercial cleaning company for 18 months. '
                    'Filter recently replaced. ' + SEEDED_TAG
                ),
                'brand': 'Nilfisk', 'model_number': 'GD 930 S2',
                'condition': 'used_good', 'price': Decimal('95000'),
                'min_offer': Decimal('80000'),
                'state': 'Abuja', 'lga': 'Central Business District',
                'pickup_notes': 'CBD Abuja, business hours.',
            },
            {
                'title': 'Tennant 5700 Walk-Behind Floor Scrubber-Dryer',
                'description': (
                    'Battery-powered 56cm disc scrubber. 30L solution tank, 28L recovery. '
                    'Used in a 1,500m² warehouse. Batteries replaced 4 months ago. '
                    'Squeegee blade 60% remaining. ' + SEEDED_TAG
                ),
                'brand': 'Tennant', 'model_number': '5700',
                'condition': 'used_good', 'price': Decimal('780000'),
                'min_offer': Decimal('680000'),
                'state': 'Lagos', 'lga': 'Apapa',
                'pickup_notes': 'Apapa — large item, van required.',
            },
            {
                'title': 'Dry Ice Blasting Gun — Icetech Compact Nozzle Kit',
                'description': (
                    'Industrial dry ice blasting nozzle with hose adapter for CO₂ tanks. '
                    'Removes mould, paint, and grease without water. '
                    'Used for machinery cleaning in a food plant. ' + SEEDED_TAG
                ),
                'brand': 'Icetech',
                'condition': 'used_good', 'price': Decimal('145000'),
                'state': 'Rivers', 'lga': 'Eleme',
                'pickup_notes': 'Eleme, near Indorama plant.',
            },
            {
                'title': 'Kärcher FC 5 Cordless Floor Cleaner',
                'description': (
                    'Hard-floor cordless cleaner: spray and suction in one pass. '
                    '20-minute run-time per charge. Self-cleaning roller system. '
                    'Used in a serviced apartment block for 6 months. '
                    'Battery holds charge well. ' + SEEDED_TAG
                ),
                'brand': 'Kärcher', 'model_number': 'FC 5 Cordless',
                'condition': 'used_good', 'price': Decimal('55000'),
                'state': 'Lagos', 'lga': 'Victoria Island',
                'pickup_notes': 'VI area, evenings.',
            },
            {
                'title': 'Microfibre Flat Mop System — 60cm with 5 Pads',
                'description': (
                    'Commercial 60cm frame flat mop with telescoping handle (1–1.7m). '
                    'Includes 5 microfibre refill pads — machine washable to 60°C. '
                    'New — surplus from a hotel contract order. ' + SEEDED_TAG
                ),
                'condition': 'new', 'price': Decimal('14000'),
                'state': 'Lagos', 'lga': 'Gbagada',
                'pickup_notes': 'Gbagada Phase 1.',
            },
            {
                'title': '5-Piece Colour-Coded Cleaning Bucket Set (HACCP)',
                'description': (
                    '5 × 10L buckets in red, yellow, blue, green, white. '
                    'Food hygiene HACCP compliant. Each with press wringer insert. '
                    'New in original packaging — bought in bulk for a hospital. ' + SEEDED_TAG
                ),
                'condition': 'new', 'price': Decimal('18500'),
                'state': 'Oyo', 'lga': 'Ibadan North',
                'pickup_notes': 'Bodija, Ibadan.',
            },
            {
                'title': 'Makita DVC860LZ 18V × 2 Brushless Backpack Vacuum',
                'description': (
                    '36V (2× 18V) backpack vacuum with HEPA H13 filter. '
                    'Used for post-concrete-cut cleanup on two projects. '
                    'Sold as bare tool — compatible with Makita 18V LXT batteries. '
                    'Tank clean, HEPA filter clean. ' + SEEDED_TAG
                ),
                'brand': 'Makita', 'model_number': 'DVC860LZ',
                'condition': 'used_good', 'price': Decimal('165000'),
                'state': 'Abuja', 'lga': 'Jabi',
                'pickup_notes': 'Jabi district, Abuja.',
            },
            {
                'title': 'Steam Cleaner — Kärcher SG 4/4 Steamer (1.6 Bar)',
                'description': (
                    'Professional steam generator for grease and germ removal. '
                    '1.6 bar, 130°C steam temperature. '
                    'Accessories: nozzle kit, floor tool, fabric steam cap. '
                    'Used in a commercial kitchen. Scale filter recently cleaned. ' + SEEDED_TAG
                ),
                'brand': 'Kärcher', 'model_number': 'SG 4/4',
                'condition': 'used_good', 'price': Decimal('72000'),
                'state': 'Lagos', 'lga': 'Lekki',
                'pickup_notes': 'Lekki Phase 1.',
            },
            {
                'title': 'Window Cleaning Kit — Unger Professional (6-Piece)',
                'description': (
                    '6-piece Unger kit: 45cm squeegee, S-channel, 35cm applicator, '
                    '2× replacement rubber, telescoping handle 1.5–3m. '
                    'New — bought for a high-rise clean that was outsourced. ' + SEEDED_TAG
                ),
                'brand': 'Unger',
                'condition': 'new', 'price': Decimal('32000'),
                'state': 'Lagos', 'lga': 'Eti-Osa',
                'pickup_notes': 'Ajah, available daily.',
            },
        ],
    },

    # ── B7. Lifting & Material Handling ───────────────────────────────────────
    {
        'category': 'Lifting & Material Handling',
        'slug': 'lifting-material-handling',
        'icon_class': 'fas fa-dolly',
        'description': 'Chain hoists, pallet jacks, forklifts, and lifting accessories.',
        'display_order': 17,
        'products': [
            {
                'title': 'Kito ER2 Electric Chain Hoist 1-Tonne 6m Lift',
                'description': (
                    '1000kg capacity electric chain hoist, 230V single phase. '
                    '6m chain travel, 4m/min lift speed. '
                    'Used in a fabrication workshop to lift steel sections. '
                    'Limit switches work, hand chain smooth. ' + SEEDED_TAG
                ),
                'brand': 'Kito', 'model_number': 'ER2 010 M',
                'condition': 'used_good', 'price': Decimal('285000'),
                'min_offer': Decimal('250000'),
                'state': 'Lagos', 'lga': 'Apapa',
                'pickup_notes': 'Apapa — heavy item.',
            },
            {
                'title': '2.5-Tonne Hydraulic Pallet Truck — Vulcan MS25',
                'description': (
                    '2500kg capacity manual pallet jack, standard 1150mm forks. '
                    'Pump action clean, forks level, wheels good. '
                    'Used in a warehouse for 3 years, recently serviced. ' + SEEDED_TAG
                ),
                'brand': 'Vulcan', 'model_number': 'MS25',
                'condition': 'used_good', 'price': Decimal('58000'),
                'state': 'Ogun', 'lga': 'Ado-Odo/Ota',
                'pickup_notes': 'Ota industrial area.',
            },
            {
                'title': 'Yale 3-Tonne Manual Chain Block — 3m Drop',
                'description': (
                    'Heavy-duty hand chain hoist, 3000kg WLL, grade 80 chain. '
                    'Load chain smooth with no kinks. Hooks and safety latches intact. '
                    'Used for equipment rigging on 4 projects. ' + SEEDED_TAG
                ),
                'brand': 'Yale', 'model_number': 'YaleHoist 3000',
                'condition': 'used_good', 'price': Decimal('72000'),
                'min_offer': Decimal('62000'),
                'state': 'Rivers', 'lga': 'Port Harcourt',
                'pickup_notes': 'Trans-Amadi, PH.',
            },
            {
                'title': 'Flat Bed Trolley (600kg) — Folding Handle, Steel Platform',
                'description': (
                    'Heavy-duty platform trolley, 1200×600mm deck, 600kg rated. '
                    'Folding handle, 4 × 160mm swivel castors (2 with brake). '
                    'Used in a distribution centre. Deck has scuff marks, fully functional. ' + SEEDED_TAG
                ),
                'condition': 'used_good', 'price': Decimal('35000'),
                'state': 'Lagos', 'lga': 'Mushin',
                'pickup_notes': 'Mushin warehouse, weekdays.',
            },
            {
                'title': 'Engine Crane (Hoist) — 2-Tonne Hydraulic Folding',
                'description': (
                    '2-tonne hydraulic engine crane. Folds flat for storage. '
                    'Boom extends in 4 positions (730–1320mm). '
                    'Used by a mechanic for engine swaps. Ram seals tight. ' + SEEDED_TAG
                ),
                'condition': 'used_good', 'price': Decimal('85000'),
                'state': 'Lagos', 'lga': 'Mushin',
                'pickup_notes': 'Ladipo market area.',
            },
            {
                'title': 'Tirfor TU-16 Wire Rope Hoist — 1.6-Tonne',
                'description': (
                    'Hand-operated wire rope puller/hoist, 1600kg capacity. '
                    'Includes 10m × 9mm wire rope and safety hook. '
                    'Used for pulling plant into a building. Rope clean, no kinks. ' + SEEDED_TAG
                ),
                'brand': 'Tractel', 'model_number': 'Tirfor TU-16',
                'condition': 'used_good', 'price': Decimal('95000'),
                'state': 'Abuja', 'lga': 'Kubwa',
                'pickup_notes': 'Kubwa, call ahead.',
            },
            {
                'title': 'Stainless Steel Lifting Slings — 2m × 5-Tonne, 4-Pack',
                'description': (
                    '4 × 2m flat webbing slings, polyester, 5-tonne WLL in choke hitch. '
                    'Stitched eyes, rated tags present. Used on crane lifting work. '
                    'No cuts or abrasions, colours still bright. ' + SEEDED_TAG
                ),
                'condition': 'used_good', 'price': Decimal('28000'),
                'state': 'Delta', 'lga': 'Warri',
                'pickup_notes': 'DSC Road, Warri.',
            },
            {
                'title': 'Sack Barrow (300kg) — Aluminium with Stair Climbers',
                'description': (
                    'Professional sack truck with 3-wheel stair climbing attachment. '
                    '300kg load capacity. Pneumatic tyres. '
                    'Used for appliance delivery and stair work. All wheels hold air. ' + SEEDED_TAG
                ),
                'condition': 'used_good', 'price': Decimal('42000'),
                'state': 'Lagos', 'lga': 'Ikeja',
                'pickup_notes': 'Airport road, Ikeja.',
            },
            {
                'title': 'Prolift Electric Scissor Lift Table — 500kg / 1m Rise',
                'description': (
                    'Single-scissor electric table lift, 500kg capacity, rises to 1m. '
                    'Platform 1200×800mm. Used in a packaging line for 2 years. '
                    'Hydraulic seals replaced recently. Operates smoothly. ' + SEEDED_TAG
                ),
                'brand': 'Prolift',
                'condition': 'used_good', 'price': Decimal('520000'),
                'min_offer': Decimal('450000'),
                'state': 'Ogun', 'lga': 'Ado-Odo/Ota',
                'pickup_notes': 'Sango-Ota industrial estate.',
            },
            {
                'title': 'Beam Trolley — 1-Tonne I-Beam Pusher Trolley',
                'description': (
                    '1000kg capacity manual push trolley for I-beams and H-sections. '
                    'Adjustable flange width 50–220mm. Combo with a chain block makes '
                    'a complete gantry system. Wheels spin freely, no seized bolts. ' + SEEDED_TAG
                ),
                'condition': 'used_good', 'price': Decimal('28000'),
                'state': 'Rivers', 'lga': 'Eleme',
                'pickup_notes': 'Eleme industrial zone, PH.',
            },
        ],
    },

    # ── B8. Survey & Civil Engineering Equipment ───────────────────────────────
    {
        'category': 'Survey & Civil Engineering Equipment',
        'slug': 'survey-civil-engineering',
        'icon_class': 'fas fa-map-marked-alt',
        'description': 'Total stations, theodolites, GPS, and civil survey instruments.',
        'display_order': 18,
        'products': [
            {
                'title': 'Leica TC407 Total Station — 7" Accuracy',
                'description': (
                    '7 arc-second total station with reflectorless EDM up to 80m. '
                    'Includes tribrach, standard prism pole, and carry case. '
                    'Used on a road construction project for 1 season. '
                    'Collimation recently adjusted. ' + SEEDED_TAG
                ),
                'brand': 'Leica', 'model_number': 'TC407',
                'condition': 'used_good', 'price': Decimal('580000'),
                'min_offer': Decimal('500000'),
                'state': 'Abuja', 'lga': 'Garki',
                'pickup_notes': 'Area 2, Garki, Abuja — appointment only.',
            },
            {
                'title': 'Nikon C-100 Automatic Level — 32× Magnification',
                'description': (
                    'Self-levelling automatic level. 32× magnification, circular vial. '
                    'Used on site levelling and drainage surveys. '
                    'Comes with wooden tripod and 4m telescopic staff. '
                    'Compensator verified — reads flat on calibrated surface. ' + SEEDED_TAG
                ),
                'brand': 'Nikon', 'model_number': 'C-100',
                'condition': 'used_good', 'price': Decimal('145000'),
                'min_offer': Decimal('120000'),
                'state': 'Rivers', 'lga': 'Port Harcourt',
                'pickup_notes': 'GRA Phase 2, PH.',
            },
            {
                'title': 'Trimble R8s GNSS RTK Rover',
                'description': (
                    'Multi-constellation GNSS rover (GPS, GLONASS, BeiDou). '
                    'Used for topographic survey and setting-out work. '
                    'Includes controller, pole, range radio, and base station adapter. '
                    'Valid subscription to RTK correction network until Dec 2026. ' + SEEDED_TAG
                ),
                'brand': 'Trimble', 'model_number': 'R8s',
                'condition': 'used_good', 'price': Decimal('2500000'),
                'min_offer': Decimal('2200000'),
                'state': 'Lagos', 'lga': 'Victoria Island',
                'pickup_notes': 'VI office — serious buyers only.',
            },
            {
                'title': 'Wild T1A Theodolite — 1\' Resolution',
                'description': (
                    'Classic optical theodolite, 1 arc-minute resolution. '
                    'Used for teaching and simple angle measurements. '
                    'Optics clear. Horizontal and vertical circles move smoothly. '
                    'Original Kern carry case. ' + SEEDED_TAG
                ),
                'brand': 'Wild Heerbrugg', 'model_number': 'T1A',
                'condition': 'used_good', 'price': Decimal('85000'),
                'state': 'Enugu', 'lga': 'Enugu East',
                'pickup_notes': 'Independence Layout, Enugu.',
            },
            {
                'title': 'Staff Rod — 5m Telescoping Aluminium (E-Type Face)',
                'description': (
                    'Standard 5m folding staff with E-type metric face. '
                    'Sections lock positively, bubble vial accurate. '
                    'Used on levelling surveys. Markings clear throughout. ' + SEEDED_TAG
                ),
                'condition': 'used_good', 'price': Decimal('18000'),
                'state': 'Oyo', 'lga': 'Ibadan North',
                'pickup_notes': 'Challenge area, Ibadan.',
            },
            {
                'title': 'Prism Pole Set — 2m Fixed + 1.8m Extension (Leica Compatible)',
                'description': (
                    'Aluminium prism pole, 2m fixed, with 1.8m push-button extension. '
                    'Leica-style tip. Bubble vial accurate. '
                    'Used with total station survey. Comes with bipod. ' + SEEDED_TAG
                ),
                'condition': 'used_good', 'price': Decimal('22000'),
                'state': 'Lagos', 'lga': 'Ikeja',
                'pickup_notes': 'Oregun, Ikeja.',
            },
            {
                'title': 'Heavy-Duty Aluminium Survey Tripod — Leica/Topcon',
                'description': (
                    'Aluminium adjustable-height tripod with wing-nut clamping legs. '
                    'Flat head with universal mount compatible with Leica, Topcon, Sokkia. '
                    'Light surface scuffs. Height range 1–1.65m. ' + SEEDED_TAG
                ),
                'condition': 'used_good', 'price': Decimal('25000'),
                'state': 'Abuja', 'lga': 'Wuse 2',
                'pickup_notes': 'Wuse 2, call before visit.',
            },
            {
                'title': 'DJI Phantom 4 RTK Drone — Survey Payload',
                'description': (
                    'RTK-enabled survey drone, 1-cm horizontal accuracy. '
                    'Multi-spectral and mechanical shutter camera included. '
                    'Used on 5 topographic and infrastructure surveys. '
                    '3 batteries, all hold charge. '
                    'Logged flight hours: 62. ' + SEEDED_TAG
                ),
                'brand': 'DJI', 'model_number': 'Phantom 4 RTK',
                'condition': 'used_good', 'price': Decimal('2800000'),
                'min_offer': Decimal('2400000'),
                'state': 'Lagos', 'lga': 'Victoria Island',
                'pickup_notes': 'VI — appointment only, serious inquiries.',
            },
            {
                'title': 'Sokkia B30 Automatic Level — 28× with Rain Cover',
                'description': (
                    '28× magnification auto level with magnetic compensator. '
                    'Rubber rain cover and tripod shoe included. '
                    'Used on drainage and road survey for 2 years. '
                    'Optics pristine, compensator tested fine. ' + SEEDED_TAG
                ),
                'brand': 'Sokkia', 'model_number': 'B30',
                'condition': 'used_good', 'price': Decimal('115000'),
                'min_offer': Decimal('95000'),
                'state': 'Rivers', 'lga': 'Obio-Akpor',
                'pickup_notes': 'Rumuola area, PH.',
            },
            {
                'title': 'Measuring Wheel — Keson RR318 Road Runner Pro (300m)',
                'description': (
                    '3-digit counter measuring wheel, 300m range. One-click reset. '
                    'Used for road and perimeter measurements. '
                    'Tyre clean, counter clicks accurately to 0.1m. Folds for transport. ' + SEEDED_TAG
                ),
                'brand': 'Keson', 'model_number': 'RR318',
                'condition': 'used_good', 'price': Decimal('16000'),
                'state': 'Kano', 'lga': 'Kano Municipal',
                'pickup_notes': 'Bello Road area, Kano.',
            },
        ],
    },

    # ── B9. Pumps & Water Management ──────────────────────────────────────────
    {
        'category': 'Pumps & Water Management',
        'slug': 'pumps-water-management',
        'icon_class': 'fas fa-water',
        'description': 'Submersible pumps, surface pumps, and water treatment equipment.',
        'display_order': 19,
        'products': [
            {
                'title': 'Grundfos CM3-4 Surface Centrifugal Pump — 0.5 HP',
                'description': (
                    'Stainless steel multi-stage pump, 0.5HP, 230V. '
                    '3m³/h flow at 4-bar pressure. Used for domestic water boosting. '
                    'Motor runs cool, no vibration. Impeller clean. ' + SEEDED_TAG
                ),
                'brand': 'Grundfos', 'model_number': 'CM3-4',
                'condition': 'used_good', 'price': Decimal('68000'),
                'min_offer': Decimal('58000'),
                'state': 'Lagos', 'lga': 'Gbagada',
                'pickup_notes': 'Gbagada Phase 2.',
            },
            {
                'title': 'DAB Feka 750 M-A Submersible Sewage Pump',
                'description': (
                    '750W submersible pump for sewage and dirty water. '
                    '24mm max particle size, 10m delivery head. '
                    'Used on a basement drainage contract. '
                    'Impeller free, seals dry — ready for reuse. ' + SEEDED_TAG
                ),
                'brand': 'DAB', 'model_number': 'Feka 750 M-A',
                'condition': 'used_good', 'price': Decimal('88000'),
                'state': 'Abuja', 'lga': 'Lugbe',
                'pickup_notes': 'Lugbe, near Abuja airport.',
            },
            {
                'title': 'Pedrollo NKm 4/6 1HP Centrifugal Pump (3-Phase)',
                'description': (
                    '3-phase, 1HP monoblock centrifugal pump, 50Hz. '
                    '4.5m³/h flow, compatible with Pedrollo MEC-E panel. '
                    'Used in a booster station for 1 year. Shaft seal recently replaced. ' + SEEDED_TAG
                ),
                'brand': 'Pedrollo', 'model_number': 'NKm 4/6',
                'condition': 'used_good', 'price': Decimal('55000'),
                'state': 'Lagos', 'lga': 'Apapa',
                'pickup_notes': 'Apapa, call before visit.',
            },
            {
                'title': 'Wilo Stratos Maxo 25/0.5-10 Circulator Pump',
                'description': (
                    'Variable-speed smart circulator pump for heating and chilled-water systems. '
                    'Replaced during a system upgrade — hours logged: 4,200. '
                    'Built-in communication, fits standard 25mm compression unions. ' + SEEDED_TAG
                ),
                'brand': 'Wilo', 'model_number': 'Stratos Maxo 25/0.5-10',
                'condition': 'used_good', 'price': Decimal('95000'),
                'state': 'Lagos', 'lga': 'Victoria Island',
                'pickup_notes': 'VI, appointment only.',
            },
            {
                'title': 'Honda WB20XT 2" Water Transfer Pump — Petrol',
                'description': (
                    '2" clear-water pump, Honda GX120 engine, 600 l/min flow. '
                    'Used on construction dewatering for 1 rainy season. '
                    'Carburettor cleaned. New spark plug fitted. Starts second pull. ' + SEEDED_TAG
                ),
                'brand': 'Honda', 'model_number': 'WB20XT',
                'condition': 'used_good', 'price': Decimal('72000'),
                'min_offer': Decimal('62000'),
                'state': 'Rivers', 'lga': 'Port Harcourt',
                'pickup_notes': 'Rumuola, PH.',
            },
            {
                'title': 'Sprinkler Irrigation System — 50m × 1" Main Line Kit',
                'description': (
                    'Complete drip/sprinkler kit: 50m 1" polypipe, 6 pop-up heads, '
                    'timer valve, filter, and pressure regulator. '
                    'New, unpacked — designed for a garden that was not built. ' + SEEDED_TAG
                ),
                'condition': 'new', 'price': Decimal('45000'),
                'state': 'Lagos', 'lga': 'Eti-Osa',
                'pickup_notes': 'Ajah area.',
            },
            {
                'title': '1000L IBC Water Tank — UN-Certified Food Grade',
                'description': (
                    'Food-grade intermediate bulk container, UN31HA1/Y rated. '
                    'Galvanised steel cage, HDPE inner bottle. '
                    'Used once for water storage, professionally cleaned. '
                    'Outlet valve operates cleanly. ' + SEEDED_TAG
                ),
                'condition': 'used_good', 'price': Decimal('38000'),
                'state': 'Ogun', 'lga': 'Ifo',
                'pickup_notes': 'Ifo industrial area.',
            },
            {
                'title': 'Atlas Copco WEDA 30L Submersible Dewatering Pump',
                'description': (
                    '230V submersible dewatering pump, 3m³/h, 11m max head. '
                    'Solids handling 5mm. Used for foundation dewatering on 2 sites. '
                    'Motor insulation resistance tested — passed. Float switch included. ' + SEEDED_TAG
                ),
                'brand': 'Atlas Copco', 'model_number': 'WEDA 30L',
                'condition': 'used_good', 'price': Decimal('98000'),
                'state': 'Ogun', 'lga': 'Sagamu',
                'pickup_notes': 'Sagamu expressway exit.',
            },
            {
                'title': 'Varem 60L Vertical Pressure Tank — Bladder Type',
                'description': (
                    '60L vertical bladder pressure tank, pre-charge 1.5 bar. '
                    'BSP 1" inlet/outlet. Bladder integrity verified. '
                    'Used in a domestic booster pump set for 3 years. '
                    'No corrosion, no leaks at ports. ' + SEEDED_TAG
                ),
                'brand': 'Varem',
                'condition': 'used_good', 'price': Decimal('32000'),
                'state': 'Abuja', 'lga': 'Garki',
                'pickup_notes': 'Area 3, Garki, Abuja.',
            },
            {
                'title': 'UV Water Steriliser — Watts Resin-X 15W (1m³/hr)',
                'description': (
                    '15-watt UV steriliser for potable water, 1m³/hr flow capacity. '
                    '1" BSP connections. Lamp replaced 2 months ago. '
                    'Used in a drinking water treatment plant. '
                    'SS chamber and quartz sleeve clean. ' + SEEDED_TAG
                ),
                'brand': 'Watts', 'model_number': 'Resin-X 15W',
                'condition': 'used_good', 'price': Decimal('28000'),
                'state': 'Enugu', 'lga': 'Enugu South',
                'pickup_notes': 'Trans-Ekulu, Enugu.',
            },
        ],
    },

    # ── B10. Roofing & Cladding Materials ─────────────────────────────────────
    {
        'category': 'Roofing & Cladding Materials',
        'slug': 'roofing-cladding',
        'icon_class': 'fas fa-home',
        'description': 'Roofing sheets, insulation, cladding systems, and roofing tools.',
        'display_order': 20,
        'products': [
            {
                'title': 'Longspan Aluminium Roofing Sheets — 0.5mm, 20 Sheets',
                'description': (
                    '20 × 0.55mm aluminium longspan roofing sheets, 3m length, Sandstone colour. '
                    'Grade 3003-H16. Unused — project cancelled after delivery. '
                    'Bundled and covered, no scratches or dents. ' + SEEDED_TAG
                ),
                'condition': 'new', 'price': Decimal('185000'),
                'min_offer': Decimal('165000'),
                'state': 'Lagos', 'lga': 'Amuwo-Odofin',
                'pickup_notes': 'Trade Fair, Mile 2 — bring truck.',
            },
            {
                'title': 'Galvanised Steel Roofing Screws — 5,000-Pack (50mm)',
                'description': (
                    '5000 × 50mm hex-washer-head self-drilling roofing screws, '
                    'Type 10 drill tip. Zinc-plated. Suitable for metal-to-purlin fixing. '
                    'New, factory pack. Surplus from a stadium roofing contract. ' + SEEDED_TAG
                ),
                'condition': 'new', 'price': Decimal('28000'),
                'state': 'Abuja', 'lga': 'Nyanya',
                'pickup_notes': 'Nyanya, near bus terminal.',
            },
            {
                'title': 'Steel Roof Truss — 5-Span @ 4.5m, 5 Sets',
                'description': (
                    '5 × complete 4.5m-span cold-formed steel roof trusses (kingpost design). '
                    '1.2mm cold-rolled galvanised steel. Designed for residential use. '
                    'Pre-fab from a cancelled project. All connectors included. ' + SEEDED_TAG
                ),
                'condition': 'new', 'price': Decimal('320000'),
                'min_offer': Decimal('280000'),
                'state': 'Ogun', 'lga': 'Ado-Odo/Ota',
                'pickup_notes': 'Ota, bring heavy vehicle.',
            },
            {
                'title': 'Gerard Stone-Coat Metal Tiles — 40m² (Sand Brown)',
                'description': (
                    '40m² of Gerard stone-coated steel roofing tiles, sand brown colour. '
                    'Stone coating intact, no chips. Removed from a roof during renovation. '
                    'Same batch, uniform colour. Ideal for a re-roof. ' + SEEDED_TAG
                ),
                'brand': 'Gerard',
                'condition': 'used_good', 'price': Decimal('280000'),
                'min_offer': Decimal('245000'),
                'state': 'Lagos', 'lga': 'Lekki',
                'pickup_notes': 'Lekki Phase 1, call ahead.',
            },
            {
                'title': 'DPC (Damp Proof Course) Roll — 300mm × 20m, 10 Rolls',
                'description': (
                    '10 rolls of standard polythene DPC, 300mm wide, 20m per roll. '
                    '250 micron. Suitable for wall-plate and foundation DPC applications. '
                    'New, still wrapped. Surplus from a block-work schedule. ' + SEEDED_TAG
                ),
                'condition': 'new', 'price': Decimal('18000'),
                'state': 'Oyo', 'lga': 'Ibadan North',
                'pickup_notes': 'Apata, Ibadan.',
            },
            {
                'title': 'Dow Corning 995 Structural Glazing Silicone — 12 × 310ml',
                'description': (
                    '12 cartridges of DC 995 structural silicone, grey. '
                    'Suitable for structural bonding of glass, aluminium curtain wall. '
                    'Factory-sealed. Best before 2027. ' + SEEDED_TAG
                ),
                'brand': 'Dow Corning', 'model_number': '995',
                'condition': 'new', 'price': Decimal('48000'),
                'state': 'Lagos', 'lga': 'Ikeja',
                'pickup_notes': 'Allen Avenue area.',
            },
            {
                'title': 'Velux GGL 2 SK02 Fixed Roof Window — Double Glazed',
                'description': (
                    '780 × 550mm fixed timber roof window, centre-pivot-ready frame. '
                    'Removed from a remodelled loft — double-glazed unit intact. '
                    'Flashing kit included (type EDW). '
                    'Ideal for a studio or workshop roof light. ' + SEEDED_TAG
                ),
                'brand': 'Velux', 'model_number': 'GGL 2 SK02',
                'condition': 'used_good', 'price': Decimal('75000'),
                'state': 'Lagos', 'lga': 'Victoria Island',
                'pickup_notes': 'VI, appointment only.',
            },
            {
                'title': 'Roofing Felt — Breathable Membrane 50m × 1.5m Roll',
                'description': (
                    'Vapour-permeable roofing underlay, 50m roll, 1.5m wide. '
                    'BS 4016 Type 1F equivalent. New in sealed polythene wrapper. '
                    'Ideal for use under metal roofing and interlocking tiles. ' + SEEDED_TAG
                ),
                'condition': 'new', 'price': Decimal('24000'),
                'state': 'Abuja', 'lga': 'Bwari',
                'pickup_notes': 'Bwari, near FCT boundary.',
            },
            {
                'title': 'Fibre Cement Soffit Board — 9mm × 1200×600mm, 25 Sheets',
                'description': (
                    '25 × 1200×600mm (9mm) compressed fibre-cement sheets for soffits, '
                    'sills and cladding. Impact-resistant, rot-proof, paintable. '
                    'Unused, removed from a warehouse by mistake. ' + SEEDED_TAG
                ),
                'condition': 'new', 'price': Decimal('62000'),
                'state': 'Lagos', 'lga': 'Alimosho',
                'pickup_notes': 'Abule-Egba, bring pick-up truck.',
            },
            {
                'title': 'Guttering System — UPVC Half-Round 50m Run (Brown)',
                'description': (
                    '50m run of brown UPVC half-round guttering: 12 × 4m lengths, '
                    '6 union clips, 4 stop ends, 6 outlets, 4 running outlets, downpipe. '
                    'New, sealed packs. Surplus from a housing estate fit-out. ' + SEEDED_TAG
                ),
                'condition': 'new', 'price': Decimal('48000'),
                'min_offer': Decimal('42000'),
                'state': 'Ogun', 'lga': 'Sagamu',
                'pickup_notes': 'Sagamu ring road.',
            },
        ],
    },

    # ── B11. Flooring Tools & Materials ──────────────────────────────────────
    {
        'category': 'Flooring Tools & Materials',
        'slug': 'flooring-tools-materials',
        'icon_class': 'fas fa-border-all',
        'description': 'Tiling tools, floor sanders, levelling compounds, and flooring materials.',
        'display_order': 21,
        'products': [
            {
                'title': 'Bosch PFZ 500 E Flooring Saw (Parquet Saw)',
                'description': (
                    '500W jab saw for parquet, laminate and strip flooring. '
                    'Scrolling blade for tight turning. Used on a hardwood floor install. '
                    'Blade still sharp, base plate flat. ' + SEEDED_TAG
                ),
                'brand': 'Bosch', 'model_number': 'PFZ 500 E',
                'condition': 'used_good', 'price': Decimal('22000'),
                'state': 'Lagos', 'lga': 'Lekki',
                'pickup_notes': 'Lekki Phase 1, evenings.',
            },
            {
                'title': 'Lagler Hummel Drum Floor Sander — 230V',
                'description': (
                    'Professional belt-drive drum sander for hardwood floor refinishing. '
                    '200mm drum. Used on 4 floor restoration projects. '
                    'Dust bag system works. Belt change lever smooth. '
                    'Comes with 3 rolls of 36g, 60g, and 80g abrasive. ' + SEEDED_TAG
                ),
                'brand': 'Lagler', 'model_number': 'Hummel',
                'condition': 'used_good', 'price': Decimal('380000'),
                'min_offer': Decimal('330000'),
                'state': 'Lagos', 'lga': 'Victoria Island',
                'pickup_notes': 'VI — serious buyers.',
            },
            {
                'title': 'Tile Cutter — Sigma 3B4M 52cm Manual',
                'description': (
                    'Manual tile cutter for porcelain and ceramic up to 52cm. '
                    'Used on a kitchen tiling contract. '
                    'Tungsten carbide wheel still sharp, rail clean, all clips present. ' + SEEDED_TAG
                ),
                'brand': 'Sigma', 'model_number': '3B4M',
                'condition': 'used_good', 'price': Decimal('48000'),
                'state': 'Abuja', 'lga': 'Wuse',
                'pickup_notes': 'Wuse 2, Abuja.',
            },
            {
                'title': 'Rubi Speed-N 65cm Electric Tile Cutter — Wet',
                'description': (
                    'Wet-cut bench tile saw, 650mm cutting capacity. '
                    '1100W motor, diamond blade included. Water tray fitted. '
                    'Used on 2 large bathroom tiling jobs. Blade 60% remaining. ' + SEEDED_TAG
                ),
                'brand': 'Rubi', 'model_number': 'Speed-N 65',
                'condition': 'used_good', 'price': Decimal('120000'),
                'min_offer': Decimal('100000'),
                'state': 'Rivers', 'lga': 'Port Harcourt',
                'pickup_notes': 'GRA PH, call ahead.',
            },
            {
                'title': 'SDS Tile Removing Chisel Set — 5 Sizes (Bosch Compatible)',
                'description': (
                    '5-piece SDS-Plus tile removal chisel set: '
                    'flat, pointed, spade, scraper, and grooving types. '
                    'New — bought for a project that used an alternative method. '
                    'Compatible with any SDS-Plus rotary hammer. ' + SEEDED_TAG
                ),
                'condition': 'new', 'price': Decimal('9500'),
                'state': 'Lagos', 'lga': 'Surulere',
                'pickup_notes': 'Eric Moore area.',
            },
            {
                'title': 'Floor Levelling Compound — Mapei Ultraplan, 25kg × 4 Bags',
                'description': (
                    '4 × 25kg bags of Mapei Ultraplan self-levelling floor compound. '
                    '3–20mm depth, 12hr walk-on time. '
                    'Unopened, stored dry. Batch date within use. '
                    'Suitable for tile, parquet, or vinyl overlay. ' + SEEDED_TAG
                ),
                'brand': 'Mapei', 'model_number': 'Ultraplan',
                'condition': 'new', 'price': Decimal('38000'),
                'state': 'Lagos', 'lga': 'Gbagada',
                'pickup_notes': 'Gbagada area.',
            },
            {
                'title': 'Grout Float + Squeegee + Grout Saw — 3-Piece Kit',
                'description': (
                    'Trade tiling kit: rubber grout float (280mm), '
                    'notched grout squeegee, and manual grout saw. '
                    'Barely used — float head still square. ' + SEEDED_TAG
                ),
                'condition': 'used_good', 'price': Decimal('6500'),
                'state': 'Oyo', 'lga': 'Ibadan North',
                'pickup_notes': 'Bodija, Ibadan.',
            },
            {
                'title': 'Weber.floor 4310 Underfloor Heating Screed — 25kg × 6',
                'description': (
                    '6 × 25kg bags of Weber calcium sulphate flowing screed for UFH. '
                    '30–80mm depth range, 24hr light traffic. '
                    'New and factory-sealed. Suitable for warm-water UFH systems. ' + SEEDED_TAG
                ),
                'brand': 'Weber', 'model_number': 'floor 4310',
                'condition': 'new', 'price': Decimal('55000'),
                'state': 'Lagos', 'lga': 'Ikeja',
                'pickup_notes': 'Allen Avenue area.',
            },
            {
                'title': 'Tile Levelling Clip System — 2000 Clips + 200 Wedges',
                'description': (
                    '2000 × 1.5mm tile levelling clips plus 200 wedges. '
                    'Suitable for large-format tiles up to 30mm joint. '
                    'New in original buckets. Surplus from a hotel fit-out. ' + SEEDED_TAG
                ),
                'condition': 'new', 'price': Decimal('18000'),
                'state': 'Abuja', 'lga': 'Garki',
                'pickup_notes': 'Garki Area 11, Abuja.',
            },
            {
                'title': 'Amtico Spacia Luxury Vinyl Tiles — 18m² (Pale Limed Oak)',
                'description': (
                    'Amtico Spacia 4mm LVT, 18m² in Pale Limed Oak. '
                    'New in unopened boxes — colour discontinued, selling surplus. '
                    'Click-fit system, suitable for underfloor heating. '
                    'Unused, stable in a cool dry room. ' + SEEDED_TAG
                ),
                'brand': 'Amtico', 'model_number': 'Spacia SS5W2652',
                'condition': 'new', 'price': Decimal('85000'),
                'min_offer': Decimal('72000'),
                'state': 'Lagos', 'lga': 'Victoria Island',
                'pickup_notes': 'VI, available weekdays.',
            },
        ],
    },

    # ── B12. CCTV & Security Installation ─────────────────────────────────────
    {
        'category': 'CCTV & Security Installation',
        'slug': 'cctv-security',
        'icon_class': 'fas fa-video',
        'description': 'IP cameras, NVRs, access control systems, and security cabling.',
        'display_order': 22,
        'products': [
            {
                'title': 'Hikvision DS-2CD2T47G2-L 4MP AcuSense Bullet Camera',
                'description': (
                    '4MP ColorVu turret camera, 2.8mm lens, 40m white light range. '
                    'Used for 1 year in a residential compound. Image crisp, IR range good. '
                    'PoE powered, weatherproof IP67. ' + SEEDED_TAG
                ),
                'brand': 'Hikvision', 'model_number': 'DS-2CD2T47G2-L',
                'condition': 'used_good', 'price': Decimal('38000'),
                'state': 'Lagos', 'lga': 'Ikeja',
                'pickup_notes': 'Oregun area, Ikeja.',
            },
            {
                'title': 'Dahua NVR4208-8P-EI 8-Channel NVR with 4TB HDD',
                'description': (
                    '8-channel PoE NVR, supports 4K output, AI functions. '
                    'Pre-loaded with 4TB Western Digital Purple surveillance HDD. '
                    'Used in an office complex for 2 years. '
                    'Remote viewing via DMSS app works. ' + SEEDED_TAG
                ),
                'brand': 'Dahua', 'model_number': 'NVR4208-8P-EI',
                'condition': 'used_good', 'price': Decimal('95000'),
                'min_offer': Decimal('82000'),
                'state': 'Abuja', 'lga': 'Garki',
                'pickup_notes': 'Area 2, Garki — bring drive.',
            },
            {
                'title': 'Cat6 UTP Network Cable — 305m Box (Grey)',
                'description': (
                    'Full 305m box of CCA Cat6 UTP cable, 23AWG, grey PVC jacket. '
                    'New, factory sealed. Suitable for CCTV and data installations. '
                    'Surplus from a project that switched to fibre. ' + SEEDED_TAG
                ),
                'condition': 'new', 'price': Decimal('28000'),
                'state': 'Lagos', 'lga': 'Mushin',
                'pickup_notes': 'Mushin market.',
            },
            {
                'title': 'ZKTeco F18 Fingerprint Access Controller',
                'description': (
                    'Standalone access control with fingerprint + password + RFID. '
                    '1000 fingerprint capacity, stores 100,000 events. '
                    'Used on one office door for 18 months. '
                    'Includes power supply, door strike, and exit button. ' + SEEDED_TAG
                ),
                'brand': 'ZKTeco', 'model_number': 'F18',
                'condition': 'used_good', 'price': Decimal('42000'),
                'state': 'Rivers', 'lga': 'Port Harcourt',
                'pickup_notes': 'D/Line area, PH.',
            },
            {
                'title': 'PoE Network Switch — TP-Link TL-SG1016PE 16-Port',
                'description': (
                    '16-port gigabit PoE+ switch, 802.3at, 150W total budget. '
                    'Used in a hotel CCTV rack for 2 years. '
                    'All ports functional — checked with cable tester before sale. ' + SEEDED_TAG
                ),
                'brand': 'TP-Link', 'model_number': 'TL-SG1016PE',
                'condition': 'used_good', 'price': Decimal('55000'),
                'state': 'Lagos', 'lga': 'Victoria Island',
                'pickup_notes': 'VI, call to arrange.',
            },
            {
                'title': 'Cable Trunking — 100mm × 60mm PVC, 30 × 2m Lengths',
                'description': (
                    '30 lengths of 2m × 100mm × 60mm white PVC cable management trunking. '
                    'Includes 6 × 90° flat bends. New, unused. '
                    'Suitable for CCTV, data, or electrical cabling along walls. ' + SEEDED_TAG
                ),
                'condition': 'new', 'price': Decimal('24000'),
                'state': 'Lagos', 'lga': 'Agege',
                'pickup_notes': 'Agege motor road.',
            },
            {
                'title': 'Uniview IPC3618SE-ADF28KM-WL 8MP Fixed Dome Camera',
                'description': (
                    '8MP full-colour AI dome camera, 2.8mm, IP67. '
                    'Deep learning-based person and vehicle detection. '
                    'Used at a school gate for 1 year. Image quality excellent. ' + SEEDED_TAG
                ),
                'brand': 'Uniview', 'model_number': 'IPC3618SE-ADF28KM-WL',
                'condition': 'used_good', 'price': Decimal('48000'),
                'state': 'Abuja', 'lga': 'Wuse 2',
                'pickup_notes': 'Wuse 2, Abuja.',
            },
            {
                'title': 'Electric Magnetic Lock 600lb + Access Control Kit',
                'description': (
                    '600lb holding-force EM lock with fail-safe operation. '
                    'Kit includes: 12V power supply, push-to-exit button, '
                    'door sensor, mounting bracket. New in box. ' + SEEDED_TAG
                ),
                'condition': 'new', 'price': Decimal('28000'),
                'state': 'Lagos', 'lga': 'Gbagada',
                'pickup_notes': 'Gbagada, call ahead.',
            },
            {
                'title': 'HIKVISION DS-3E0105P-E/M 4-Port PoE Unmanaged Switch',
                'description': (
                    '4-port PoE Fast Ethernet switch, 1 uplink, 55W PoE budget. '
                    '802.3af/at. Ideal for small CCTV clusters. '
                    'New in original box — excess stock from installation contractor. '
                    'Selling 5 units — price per unit. ' + SEEDED_TAG
                ),
                'brand': 'Hikvision', 'model_number': 'DS-3E0105P-E/M',
                'condition': 'new', 'price': Decimal('12000'),
                'slots': 5,
                'state': 'Lagos', 'lga': 'Lekki',
                'pickup_notes': 'Lekki Phase 1.',
            },
            {
                'title': 'Fibreglass Cable Rod Set — 10m, 30-Piece Rods',
                'description': (
                    '30 × 330mm fibreglass cable rods with screw-together joints. '
                    'Includes fish-eye, hook, and threaded adapters. '
                    'Used for routing cables through conduit and wall cavities. '
                    'All joints solid, rods straight. ' + SEEDED_TAG
                ),
                'condition': 'used_good', 'price': Decimal('8500'),
                'state': 'Oyo', 'lga': 'Ibadan North',
                'pickup_notes': 'Challenge area, Ibadan.',
            },
        ],
    },

    # ── B13. Compressed Air Tools ──────────────────────────────────────────────
    {
        'category': 'Compressed Air & Pneumatic Tools',
        'slug': 'compressed-air-pneumatic',
        'icon_class': 'fas fa-wind',
        'description': 'Air compressors, pneumatic tools, and pressure accessories.',
        'display_order': 23,
        'products': [
            {
                'title': 'Atlas Copco GA11+ 11kW Industrial Rotary Screw Compressor',
                'description': (
                    '11kW oil-injected rotary screw compressor. 1.4 m³/min at 8 bar. '
                    '3-phase 380V. Fully enclosed canopy, air-cooled. '
                    'Used in a metalworking factory. '
                    'Service history available. Oil changed 3 months ago. ' + SEEDED_TAG
                ),
                'brand': 'Atlas Copco', 'model_number': 'GA11+',
                'condition': 'used_good', 'price': Decimal('1850000'),
                'min_offer': Decimal('1600000'),
                'state': 'Lagos', 'lga': 'Apapa',
                'pickup_notes': 'Apapa industrial — serious buyers with lorry.',
            },
            {
                'title': 'Ingersoll Rand 2475F14GH 5HP Reciprocating Compressor',
                'description': (
                    'Two-stage, 5HP, 240V single-phase air compressor. '
                    'Twin 60-gallon horizontal tanks, 175 PSI max. '
                    'Used in a tyre workshop for 2 years. Valves recently serviced. '
                    'Starts well, no oil in air — tank drain works. ' + SEEDED_TAG
                ),
                'brand': 'Ingersoll Rand', 'model_number': '2475F14GH',
                'condition': 'used_good', 'price': Decimal('380000'),
                'min_offer': Decimal('330000'),
                'state': 'Ogun', 'lga': 'Ota',
                'pickup_notes': 'Ota industrial area.',
            },
            {
                'title': 'Fini Cube 2.2 Portable 50L Air Compressor 230V',
                'description': (
                    'Compact 2.2 HP oil-free compressor with 50L horizontal tank. '
                    '8 bar, 230V single phase. Very portable at 30kg. '
                    'Used for inflation and spray painting. Quiet for its size. ' + SEEDED_TAG
                ),
                'brand': 'Fini', 'model_number': 'Cube 2.2',
                'condition': 'used_good', 'price': Decimal('95000'),
                'state': 'Abuja', 'lga': 'Jabi',
                'pickup_notes': 'Jabi district.',
            },
            {
                'title': 'Chicago Pneumatic CP737 Air Die Grinder 6mm Collet',
                'description': (
                    '6mm collet die grinder, 25,000 RPM, 0.3HP. '
                    'Used for port polishing on engine heads. '
                    'Collet tight, no spindle play. Comes with 5 assorted burs. ' + SEEDED_TAG
                ),
                'brand': 'Chicago Pneumatic', 'model_number': 'CP737',
                'condition': 'used_good', 'price': Decimal('18000'),
                'state': 'Lagos', 'lga': 'Mushin',
                'pickup_notes': 'Ladipo, Mushin.',
            },
            {
                'title': 'Bostitch MIIIFN 3" Pneumatic Framing Nailer',
                'description': (
                    '3" clipped-head framing nail gun, 70–120 PSI. '
                    '21° coil magazine. Used on roof truss assembly. '
                    'Fires consistently, no jamming. Comes with 1 coil of nails. ' + SEEDED_TAG
                ),
                'brand': 'Bostitch', 'model_number': 'MIIIFN',
                'condition': 'used_good', 'price': Decimal('72000'),
                'state': 'Lagos', 'lga': 'Alimosho',
                'pickup_notes': 'Idimu area.',
            },
            {
                'title': 'Brad Nailer — Dewalt DWFP12231 18GA 2" Finish Nailer',
                'description': (
                    '18-gauge finish nailer, 5/8" to 2" nail length. '
                    'Jam-resistant drive guide. Used for architrave and skirting fitting. '
                    'No misfires. Comes with one pack of 18G nails. ' + SEEDED_TAG
                ),
                'brand': 'DeWalt', 'model_number': 'DWFP12231',
                'condition': 'used_good', 'price': Decimal('38000'),
                'state': 'Oyo', 'lga': 'Ibadan North',
                'pickup_notes': 'Challenge area, Ibadan.',
            },
            {
                'title': 'Parker Hannifin FRL Unit — Filter/Regulator/Lubricator 1/2"',
                'description': (
                    '1/2" BSP air preparation unit: filter (40 micron), regulator '
                    '(0–10 bar), and oil mist lubricator. '
                    'New — surplus from a pneumatic panel assembly. '
                    'Bowls and seals included. ' + SEEDED_TAG
                ),
                'brand': 'Parker Hannifin',
                'condition': 'new', 'price': Decimal('24000'),
                'state': 'Abuja', 'lga': 'Wuse 2',
                'pickup_notes': 'Wuse 2.',
            },
            {
                'title': 'Polyurethane Air Hose — 10m × 8mm, 10-Pack',
                'description': (
                    '10 × 10m coils of 8mm bore PU air hose with 1/4" BSP ends. '
                    '20 bar rated, kink-resistant. New in sealed bags. '
                    'Bulk-bought for a compressor showroom. ' + SEEDED_TAG
                ),
                'condition': 'new', 'price': Decimal('65000'),
                'min_offer': Decimal('55000'),
                'state': 'Lagos', 'lga': 'Oshodi-Isale',
                'pickup_notes': 'Oshodi market.',
            },
            {
                'title': 'Pneumatic Impact Wrench — Ingersoll Rand 2135TiMAX 1/2"',
                'description': (
                    '1170Nm max reverse torque. Lightweight titanium hammer case. '
                    'Used in a tyre shop for 1.5 years. Recently serviced with '
                    'new vanes. Trigger smooth, forward/reverse crisp. ' + SEEDED_TAG
                ),
                'brand': 'Ingersoll Rand', 'model_number': '2135TiMAX',
                'condition': 'used_good', 'price': Decimal('65000'),
                'state': 'Kano', 'lga': 'Fagge',
                'pickup_notes': 'Sabon Gari market, Kano.',
            },
            {
                'title': 'Compressed Air Duster — 90° Blow Gun (5-Pack)',
                'description': (
                    '5 × right-angle safety blow guns, 1/4" BSP male. '
                    'Rubber tip, all-metal body. Suitable for workshop and machine cleaning. '
                    'New in retail blister packs. Surplus stock. ' + SEEDED_TAG
                ),
                'condition': 'new', 'price': Decimal('8500'),
                'state': 'Lagos', 'lga': 'Ikeja',
                'pickup_notes': 'Oregun industrial area.',
            },
        ],
    },

    # ── B14. Drainage & Groundworks Equipment ─────────────────────────────────
    {
        'category': 'Drainage & Groundworks Equipment',
        'slug': 'drainage-groundworks',
        'icon_class': 'fas fa-route',
        'description': 'Trench supports, drainage pipes, compaction equipment, and groundwork tools.',
        'display_order': 24,
        'products': [
            {
                'title': 'Wacker Neuson VP1550 Petrol Plate Compactor',
                'description': (
                    'Honda GX160 petrol vibratory plate, 65kg, 5400 vpm. '
                    'Used for sub-base compaction on a residential drive project. '
                    'Plate edges in good condition, engine starts first pull. ' + SEEDED_TAG
                ),
                'brand': 'Wacker Neuson', 'model_number': 'VP1550',
                'condition': 'used_good', 'price': Decimal('265000'),
                'min_offer': Decimal('230000'),
                'state': 'Lagos', 'lga': 'Alimosho',
                'pickup_notes': 'Idimu, Lagos.',
            },
            {
                'title': 'Trench Strut — Mechanical Aluminum Hydraulic, 900–1500mm',
                'description': (
                    'Aluminium hydraulic trench strut, extends 900–1500mm. '
                    'Load-rated, suitable for shallow utility trenches. '
                    '4 struts available, price per pair. '
                    'Used on water main replacement works. ' + SEEDED_TAG
                ),
                'condition': 'used_good', 'price': Decimal('48000'),
                'slots': 4,
                'state': 'Lagos', 'lga': 'Apapa',
                'pickup_notes': 'Apapa, weekdays.',
            },
            {
                'title': 'Husqvarna DM 200 Electric Diamond Core Drill Rig',
                'description': (
                    'Bench-mounted core drilling rig with column, feed arm, '
                    'and vacuum base plate. Motor unit 2000W. '
                    'Used for 100mm core holes through reinforced concrete slabs. '
                    'Column and feed mechanism tight. ' + SEEDED_TAG
                ),
                'brand': 'Husqvarna', 'model_number': 'DM 200',
                'condition': 'used_good', 'price': Decimal('485000'),
                'min_offer': Decimal('420000'),
                'state': 'Rivers', 'lga': 'Obio-Akpor',
                'pickup_notes': 'Rumuola junction, PH.',
            },
            {
                'title': 'MDPE Blue Water Pipe — 63mm × 50m Coil (SDR11)',
                'description': (
                    '63mm OD MDPE blue water service pipe, SDR11, 12.5 bar rated. '
                    '50m coil, unused. PE100 grade, suitable for underground mains. '
                    'New — excess from a housing scheme supply contract. ' + SEEDED_TAG
                ),
                'condition': 'new', 'price': Decimal('55000'),
                'min_offer': Decimal('48000'),
                'state': 'Ogun', 'lga': 'Sagamu',
                'pickup_notes': 'Sagamu, large coil.',
            },
            {
                'title': 'Safety Trench Boxes — Steel Slide Rail, 2m × 1.2m (2 Sets)',
                'description': (
                    '2 × steel slide-rail trench box panels (2000mm × 1200mm each). '
                    'Heavy-gauge, hot-dip galvanised. With 2 adjustable spreaders. '
                    'Used on a sewage reticulation project. Plates straight, no welds cracked. ' + SEEDED_TAG
                ),
                'condition': 'used_good', 'price': Decimal('420000'),
                'min_offer': Decimal('360000'),
                'state': 'Lagos', 'lga': 'Amuwo-Odofin',
                'pickup_notes': 'Mile 2, Lagos — heavy load.',
            },
            {
                'title': 'Precast Manhole Cover Class B125 — 600 × 600mm',
                'description': (
                    '600mm × 600mm ductile iron manhole cover and frame, B125 rated. '
                    '5 covers available — price per unit. '
                    'New and uninstalled, surplus from a housing estate. ' + SEEDED_TAG
                ),
                'condition': 'new', 'price': Decimal('22000'),
                'slots': 5,
                'state': 'Lagos', 'lga': 'Gbagada',
                'pickup_notes': 'Gbagada Phase 2.',
            },
            {
                'title': 'Geofabric Weed Membrane — 4.5m × 100m, 130gsm',
                'description': (
                    '100m roll of heavy-duty woven geotextile membrane, 130g/m². '
                    'For sub-base separation, road-building, and drainage filtration. '
                    'New, still in shrink-wrap. ' + SEEDED_TAG
                ),
                'condition': 'new', 'price': Decimal('42000'),
                'state': 'Abuja', 'lga': 'Bwari',
                'pickup_notes': 'Bwari, near FCT boundary.',
            },
            {
                'title': 'Petrol Breaker — Makita HM1812 70J Class',
                'description': (
                    'Heavyweight demolition breaker, 1750W petrol equivalent, 70J impact. '
                    'SDS-Max chisel included. Used for breaking concrete footings. '
                    'Vibration dampening intact. Serviced 2 months ago. ' + SEEDED_TAG
                ),
                'brand': 'Makita', 'model_number': 'HM1812',
                'condition': 'used_good', 'price': Decimal('285000'),
                'min_offer': Decimal('245000'),
                'state': 'Oyo', 'lga': 'Ibadan North',
                'pickup_notes': 'Apata area, Ibadan.',
            },
            {
                'title': 'Land Drain Coil — 60mm Perforated, 50m (Socketed)',
                'description': (
                    '50m coil of 60mm corrugated perforated land drain pipe '
                    'pre-sleeved in filter sock. PE, suitable for french drains. '
                    'New, still in plastic wrap. ' + SEEDED_TAG
                ),
                'condition': 'new', 'price': Decimal('18000'),
                'state': 'Lagos', 'lga': 'Alimosho',
                'pickup_notes': 'Egbeda area.',
            },
            {
                'title': 'Spirit Level Laser Line — Bosch GCL 2-50 G (Green Beam)',
                'description': (
                    'Green cross-line laser, ±0.2mm/m accuracy. '
                    'Self-levelling within ±4°. Projects horizontal + vertical + plumb dot. '
                    'Used for drainage setting-out. Comes with mount, receiver, and case. ' + SEEDED_TAG
                ),
                'brand': 'Bosch', 'model_number': 'GCL 2-50 G',
                'condition': 'used_good', 'price': Decimal('88000'),
                'state': 'Abuja', 'lga': 'Garki',
                'pickup_notes': 'Area 3, Garki.',
            },
        ],
    },

    # ── B15. Solar & Renewable Energy ─────────────────────────────────────────
    {
        'category': 'Solar & Renewable Energy',
        'slug': 'solar-renewable-energy',
        'icon_class': 'fas fa-solar-panel',
        'description': 'Solar panels, inverters, batteries, charge controllers, and EV equipment.',
        'display_order': 25,
        'products': [
            {
                'title': 'Growatt SPF 6000T DVM-MPV Off-Grid Inverter 6kW',
                'description': (
                    '6000W pure sine wave off-grid inverter/charger. '
                    '48V, dual MPPT, 120A max charge. 230V output. '
                    'Used in a large residential solar install for 1 year. '
                    'All AC/DC terminals tight. No fault codes in log. ' + SEEDED_TAG
                ),
                'brand': 'Growatt', 'model_number': 'SPF 6000T DVM-MPV',
                'condition': 'used_good', 'price': Decimal('580000'),
                'min_offer': Decimal('510000'),
                'state': 'Lagos', 'lga': 'Ikeja',
                'pickup_notes': 'Allen Avenue, Ikeja.',
            },
            {
                'title': 'Canadian Solar CS6R 440W HiKu Mono Panel (10 Panels)',
                'description': (
                    '10 × 440W Mono PERC panels. 21.3% efficiency. '
                    'Used on a commercial rooftop system for 14 months. '
                    'Each panel independently flash-tested — all within 2% of rated output. '
                    'Frames undamaged, glass clean. ' + SEEDED_TAG
                ),
                'brand': 'Canadian Solar', 'model_number': 'CS6R-440MS',
                'condition': 'used_good', 'price': Decimal('850000'),
                'min_offer': Decimal('740000'),
                'state': 'Abuja', 'lga': 'Kubwa',
                'pickup_notes': 'Kubwa, bring open truck.',
            },
            {
                'title': 'Pylontech US3000C 3.5kWh Lithium Battery (48V)',
                'description': (
                    '48V 74Ah lithium iron phosphate (LiFePO4) rack battery. '
                    'Compatible with Victron, SMA, Goodwe, and most hybrid inverters. '
                    'Cycle count: 248. BMS healthy — no cell imbalance alarms. '
                    'Comes with CAN cable. ' + SEEDED_TAG
                ),
                'brand': 'Pylontech', 'model_number': 'US3000C',
                'condition': 'used_good', 'price': Decimal('680000'),
                'min_offer': Decimal('600000'),
                'state': 'Lagos', 'lga': 'Victoria Island',
                'pickup_notes': 'VI — appointment only.',
            },
            {
                'title': 'Epever MPPT 60A Charge Controller — Tracer 6415AN',
                'description': (
                    'MPPT solar charge controller, 60A, 12/24/36/48V auto-detect. '
                    '150V max PV input. MT50 remote meter included. '
                    'Used in a 5kW solar system for 1 year. Works flawlessly. ' + SEEDED_TAG
                ),
                'brand': 'Epever', 'model_number': 'Tracer 6415AN',
                'condition': 'used_good', 'price': Decimal('95000'),
                'state': 'Oyo', 'lga': 'Ibadan North',
                'pickup_notes': 'Bodija, Ibadan.',
            },
            {
                'title': 'SMA Sunny Boy 3.0 Grid-Tie Inverter 3kW',
                'description': (
                    '3kW single-phase grid-tie inverter. 97.2% CEC efficiency. '
                    'Webconnect data logging built in. Removed from a system upgrade. '
                    'Log shows 2 years, 6 months operation, no faults. ' + SEEDED_TAG
                ),
                'brand': 'SMA', 'model_number': 'SB 3.0-1AV-41',
                'condition': 'used_good', 'price': Decimal('285000'),
                'min_offer': Decimal('245000'),
                'state': 'Lagos', 'lga': 'Ikoyi',
                'pickup_notes': 'Ikoyi, appointment only.',
            },
            {
                'title': 'Renogy 40A DC-DC On-Board Battery Charger',
                'description': (
                    'MPPT DC-DC charger for charging lithium or AGM auxiliary batteries '
                    'from alternator or solar. 40A, 12V/24V. New in box. '
                    'Surplus from a fleet vehicle electrification project. ' + SEEDED_TAG
                ),
                'brand': 'Renogy', 'model_number': 'DCC50S',
                'condition': 'new', 'price': Decimal('48000'),
                'state': 'Abuja', 'lga': 'Garki',
                'pickup_notes': 'Area 10, Garki.',
            },
            {
                'title': 'MC4 Solar Connector Kit — 50 Pairs (Male + Female)',
                'description': (
                    '50 pairs of UV-resistant MC4 connectors, IP67 rated. '
                    'Crimping tool not included. '
                    'New, factory bags. Surplus from a 50kW rooftop project. ' + SEEDED_TAG
                ),
                'condition': 'new', 'price': Decimal('18000'),
                'state': 'Lagos', 'lga': 'Ikeja',
                'pickup_notes': 'Oregun area.',
            },
            {
                'title': 'Solar Cable — 6mm² Red + Black, 50m Each Roll',
                'description': (
                    '2 × 50m rolls of TÜV-approved 6mm² single-core solar DC cable. '
                    'UV and heat resistant, -40°C to 90°C. New. '
                    'Suitable for PV string wiring and battery interconnects. ' + SEEDED_TAG
                ),
                'condition': 'new', 'price': Decimal('28000'),
                'state': 'Rivers', 'lga': 'Port Harcourt',
                'pickup_notes': 'Trans-Amadi, PH.',
            },
            {
                'title': 'Goodwe GW5000-ES 5kW Hybrid Inverter',
                'description': (
                    '5kW single-phase hybrid inverter, 2 MPPT, 20A max charge. '
                    'Compatible with lead-acid and lithium batteries. '
                    'Used in a residential system for 8 months. '
                    'No faults; SEMS portal logging intact. ' + SEEDED_TAG
                ),
                'brand': 'Goodwe', 'model_number': 'GW5000-ES',
                'condition': 'used_good', 'price': Decimal('420000'),
                'min_offer': Decimal('365000'),
                'state': 'Ogun', 'lga': 'Abeokuta South',
                'pickup_notes': 'Oke-Mosan, Abeokuta.',
            },
            {
                'title': 'Solar Panel Mounting Rail — 4.4m Aluminium, 20 Pieces',
                'description': (
                    '20 × 4.4m T-slot aluminium rails for rooftop solar mounting. '
                    'Includes end clamps, mid clamps and splice plates. '
                    'New — surplus from a commercial solar project. '
                    'Compatible with most 35–40mm framed panels. ' + SEEDED_TAG
                ),
                'condition': 'new', 'price': Decimal('65000'),
                'min_offer': Decimal('55000'),
                'state': 'Lagos', 'lga': 'Lekki',
                'pickup_notes': 'Lekki Phase 1.',
            },
        ],
    },

    # ── B16. Laboratory & Scientific Equipment ────────────────────────────────
    {
        'category': 'Laboratory & Testing Equipment',
        'slug': 'laboratory-testing-equipment',
        'icon_class': 'fas fa-microscope',
        'description': 'Testing instruments, lab equipment, and quality control tools.',
        'display_order': 26,
        'products': [
            {
                'title': 'Mettler Toledo ML3002E Analytical Balance 3200g / 0.01g',
                'description': (
                    '3200g capacity, 0.01g readability precision balance. '
                    'Internal calibration (FACT). RS232 and USB output. '
                    'Used in a quality control lab for 2 years. '
                    'Calibration certificate available. ' + SEEDED_TAG
                ),
                'brand': 'Mettler Toledo', 'model_number': 'ML3002E',
                'condition': 'used_good', 'price': Decimal('280000'),
                'min_offer': Decimal('240000'),
                'state': 'Lagos', 'lga': 'Victoria Island',
                'pickup_notes': 'VI office — by appointment.',
            },
            {
                'title': 'Hanna HI9813-6 pH / EC / TDS / Temperature Meter',
                'description': (
                    'Portable multi-parameter water quality meter. '
                    'pH ±0.1, EC ±2%, TDS ±2%. Used in a fish farm for 18 months. '
                    'Electrode recently replaced. Reads stable in buffer solutions. ' + SEEDED_TAG
                ),
                'brand': 'Hanna', 'model_number': 'HI9813-6',
                'condition': 'used_good', 'price': Decimal('65000'),
                'state': 'Oyo', 'lga': 'Ibadan North',
                'pickup_notes': 'University area, Ibadan.',
            },
            {
                'title': 'Elcometer 456 Coating Thickness Gauge (Magnetic + Eddy)',
                'description': (
                    'Dual-principle DFT gauge for steel and aluminium substrates. '
                    '±1% accuracy, 0–3000 micron range. USB data output. '
                    'Used for paint inspection on structural steel. Probe clean. ' + SEEDED_TAG
                ),
                'brand': 'Elcometer', 'model_number': '456 BFC1',
                'condition': 'used_good', 'price': Decimal('185000'),
                'min_offer': Decimal('160000'),
                'state': 'Lagos', 'lga': 'Apapa',
                'pickup_notes': 'Apapa, call first.',
            },
            {
                'title': 'Shore A Durometer — ASTM D2240 Digital, 0–100 HA',
                'description': (
                    'Digital Shore A hardness tester for rubber, silicone, and flexible plastics. '
                    'ASTM D2240 standard. Auto-peak hold. '
                    'Used in a rubber product factory. Indenter and spring clean. ' + SEEDED_TAG
                ),
                'condition': 'used_good', 'price': Decimal('42000'),
                'state': 'Ogun', 'lga': 'Ado-Odo/Ota',
                'pickup_notes': 'Ota industrial estate.',
            },
            {
                'title': 'Particle Counter — Fluke 985 6-Channel Airborne',
                'description': (
                    '6-channel particle counter (0.3–10.0 μm), prints ISO class report. '
                    'Used for HVAC duct and cleanroom air quality validation. '
                    'Pump flow calibrated 6 months ago. Comes with carry case and printer. ' + SEEDED_TAG
                ),
                'brand': 'Fluke', 'model_number': '985',
                'condition': 'used_good', 'price': Decimal('580000'),
                'min_offer': Decimal('500000'),
                'state': 'Lagos', 'lga': 'Ikeja',
                'pickup_notes': 'GRA Ikeja, appointment only.',
            },
            {
                'title': 'Olympus BX53 Trinocular Compound Microscope',
                'description': (
                    'Research-grade trinocular microscope, 4×/10×/40×/100× objectives. '
                    'Koehler illumination LED base. Camera port available. '
                    'Used in a microbiology lab for 3 years. Optics clean, stage moves smoothly. ' + SEEDED_TAG
                ),
                'brand': 'Olympus', 'model_number': 'BX53',
                'condition': 'used_good', 'price': Decimal('1850000'),
                'min_offer': Decimal('1600000'),
                'state': 'Lagos', 'lga': 'Surulere',
                'pickup_notes': 'LUTH area, appointment only.',
            },
            {
                'title': 'Extech SDL400 Sound Level Meter with Datalogger',
                'description': (
                    'Type 2 sound level meter, 30–130 dB, A/C weighting. '
                    'SD card datalogger. Used for occupational noise assessment. '
                    'Mic calibrated with Extech 407766 calibrator 4 months ago. ' + SEEDED_TAG
                ),
                'brand': 'Extech', 'model_number': 'SDL400',
                'condition': 'used_good', 'price': Decimal('88000'),
                'state': 'Abuja', 'lga': 'Garki',
                'pickup_notes': 'Area 2, Garki.',
            },
            {
                'title': 'Instron 3343 Universal Testing Machine — 1kN',
                'description': (
                    'Tabletop tensile/compression testing machine, 1kN load cell. '
                    'Bluehill 3 software licence included. '
                    'Used in a polymer research lab for 2 years. '
                    'Load cell calibration cert valid until Oct 2026. ' + SEEDED_TAG
                ),
                'brand': 'Instron', 'model_number': '3343',
                'condition': 'used_good', 'price': Decimal('2200000'),
                'min_offer': Decimal('1900000'),
                'state': 'Lagos', 'lga': 'Yaba',
                'pickup_notes': 'UNILAG area, appointment only.',
            },
            {
                'title': 'PCE-CT 55 Non-Destructive Concrete Tester',
                'description': (
                    'Rebound hammer (Schmidt type) for in-situ concrete strength estimate. '
                    'Impact energy 2.207J. 16 readings for automatic average. '
                    'Calibrated on test anvil — reads within ±10% on known strength. ' + SEEDED_TAG
                ),
                'brand': 'PCE Instruments', 'model_number': 'CT 55',
                'condition': 'used_good', 'price': Decimal('65000'),
                'state': 'Rivers', 'lga': 'Port Harcourt',
                'pickup_notes': 'GRA Phase 1, PH.',
            },
            {
                'title': 'Digital Refractometer — ATAGO PAL-1 Brix 0–53%',
                'description': (
                    'Pocket digital refractometer for sugar concentration, Brix 0–53%. '
                    '±0.2% accuracy. ATC automatic temperature compensation. '
                    'Used in a beverage factory for QC. Prism clean. '
                    'Comes with distilled water sample bottles. ' + SEEDED_TAG
                ),
                'brand': 'Atago', 'model_number': 'PAL-1',
                'condition': 'used_good', 'price': Decimal('38000'),
                'state': 'Lagos', 'lga': 'Oshodi-Isale',
                'pickup_notes': 'Oshodi area.',
            },
        ],
    },

    # ── B17. Catering & Food Service Equipment ────────────────────────────────
    {
        'category': 'Catering & Food Service Equipment',
        'slug': 'catering-food-service',
        'icon_class': 'fas fa-utensils',
        'description': 'Commercial kitchen equipment, refrigeration, and food preparation tools.',
        'display_order': 27,
        'products': [
            {
                'title': 'Hobart A200 20-Quart Commercial Stand Mixer',
                'description': (
                    '20-quart bowl-lift commercial mixer. 3 speeds. '
                    'Includes dough hook, flat beater, and wire whip. '
                    'Used in a bakery for 3 years. Gearbox quiet, no oil leaks. '
                    'Bowl in good shape — no dents. ' + SEEDED_TAG
                ),
                'brand': 'Hobart', 'model_number': 'A200-10',
                'condition': 'used_good', 'price': Decimal('680000'),
                'min_offer': Decimal('580000'),
                'state': 'Lagos', 'lga': 'Surulere',
                'pickup_notes': 'Bode Thomas area.',
            },
            {
                'title': 'Rational SCC WE 61 6-Tray Combi Oven (3-Phase)',
                'description': (
                    'Self-cleaning combi steamer, 6× GN1/1 trays. '
                    'Used in a hotel kitchen for 2 years. '
                    'SelfCooking Control programming intact. '
                    'Recently professionally serviced. 3-phase 380V. ' + SEEDED_TAG
                ),
                'brand': 'Rational', 'model_number': 'SCC WE 61',
                'condition': 'used_good', 'price': Decimal('2800000'),
                'min_offer': Decimal('2400000'),
                'state': 'Lagos', 'lga': 'Victoria Island',
                'pickup_notes': 'VI — large item, serious buyers only.',
            },
            {
                'title': 'Anvil MKA1003 15L Commercial Bench Mixer',
                'description': (
                    '15-litre planetary bench mixer, 3 speeds + pulse. '
                    'Bowl guard fitted. Used in a small restaurant for 1 year. '
                    'All 3 attachments included. Timer works accurately. ' + SEEDED_TAG
                ),
                'brand': 'Anvil', 'model_number': 'MKA1003',
                'condition': 'used_good', 'price': Decimal('185000'),
                'min_offer': Decimal('158000'),
                'state': 'Abuja', 'lga': 'Wuse 2',
                'pickup_notes': 'Wuse 2, Abuja.',
            },
            {
                'title': 'True TWT-27F Under-Counter Commercial Freezer',
                'description': (
                    '27" under-counter freezer, 3 drawers, -18°C operating temp. '
                    'R290 hydrocarbon refrigerant. Used in a hotel galley kitchen. '
                    'Compressor quiet, seals excellent, interior clean. ' + SEEDED_TAG
                ),
                'brand': 'True', 'model_number': 'TWT-27F',
                'condition': 'used_good', 'price': Decimal('480000'),
                'min_offer': Decimal('420000'),
                'state': 'Lagos', 'lga': 'Ikeja',
                'pickup_notes': 'Oregun road, Ikeja.',
            },
            {
                'title': 'Waring WCG75 Commercial Grinder 12-Cup',
                'description': (
                    'Heavy-duty commercial coffee grinder, 12-cup capacity. '
                    'Stainless steel burrs. Used in a café for 18 months. '
                    'Grind consistency still excellent on all settings. '
                    'Hopper and ground-coffee container included. ' + SEEDED_TAG
                ),
                'brand': 'Waring', 'model_number': 'WCG75',
                'condition': 'used_good', 'price': Decimal('95000'),
                'state': 'Lagos', 'lga': 'Lekki',
                'pickup_notes': 'Lekki Phase 1.',
            },
            {
                'title': 'GN 1/1 Stainless Steel Gastronorm Pans — 20-Piece Set',
                'description': (
                    'Full set of GN 1/1 gastronorm pans: 4 depths (20mm, 40mm, 65mm, 100mm). '
                    '5 pans per depth. 18/10 stainless, commercial grade. '
                    'Used in a catering company for 2 years, washed in commercial dishwasher. '
                    'No serious dents. ' + SEEDED_TAG
                ),
                'condition': 'used_good', 'price': Decimal('85000'),
                'state': 'Oyo', 'lga': 'Ibadan North',
                'pickup_notes': 'Challenge area, Ibadan.',
            },
            {
                'title': 'Vollrath 40735 Commercial Immersion Blender 7-Speed',
                'description': (
                    '7-speed immersion blender with 600W motor. '
                    'S/S shaft and blade, 460mm stick depth. '
                    'Used in a soup production kitchen. Blade still sharp. '
                    'Whisk attachment also included. ' + SEEDED_TAG
                ),
                'brand': 'Vollrath', 'model_number': '40735',
                'condition': 'used_good', 'price': Decimal('68000'),
                'state': 'Rivers', 'lga': 'Port Harcourt',
                'pickup_notes': 'D/Line, PH.',
            },
            {
                'title': 'Commercial Food Warmer Bain Marie — 4-Pan GN 1/4',
                'description': (
                    '4-pan bain marie hot hold unit, GN 1/4 inserts, hinged lid. '
                    '1200W element with thermostat. Stainless steel throughout. '
                    'Used at buffet events for 2 years. Element heats evenly, no rust. ' + SEEDED_TAG
                ),
                'condition': 'used_good', 'price': Decimal('75000'),
                'state': 'Lagos', 'lga': 'Gbagada',
                'pickup_notes': 'Gbagada, call to arrange.',
            },
            {
                'title': 'Merrychef eikon e2s High-Speed Oven',
                'description': (
                    'Countertop high-speed combination oven: microwave + convection + impingement. '
                    'Cook 8× faster than conventional. Used in a hotel lounge. '
                    'Cavity liner clean, magnetron healthy. Programmes intact on touchscreen. ' + SEEDED_TAG
                ),
                'brand': 'Merrychef', 'model_number': 'eikon e2s',
                'condition': 'used_good', 'price': Decimal('1250000'),
                'min_offer': Decimal('1050000'),
                'state': 'Lagos', 'lga': 'Victoria Island',
                'pickup_notes': 'VI, appointment only.',
            },
            {
                'title': 'Hoshizaki IM-45NE-Q Cube Ice Machine — 45kg/24hr',
                'description': (
                    '45kg/24hr production, 25kg storage bin. R134a refrigerant. '
                    'Used in an upscale bar for 18 months. '
                    'Scale cleaned 2 months ago, production rate verified at 42kg/day. ' + SEEDED_TAG
                ),
                'brand': 'Hoshizaki', 'model_number': 'IM-45NE-Q',
                'condition': 'used_good', 'price': Decimal('650000'),
                'min_offer': Decimal('570000'),
                'state': 'Lagos', 'lga': 'Ikeja',
                'pickup_notes': 'Oregun area, GRA.',
            },
        ],
    },

    # ── B18. IT & Networking Infrastructure ───────────────────────────────────
    {
        'category': 'IT & Networking Infrastructure',
        'slug': 'it-networking-infrastructure',
        'icon_class': 'fas fa-network-wired',
        'description': 'Servers, networking gear, rack cabinets, and cable management.',
        'display_order': 28,
        'products': [
            {
                'title': 'Dell PowerEdge R440 1U Server — 2× Xeon Silver 4114',
                'description': (
                    'Dual-socket 1U rack server. 2× Intel Xeon Silver 4114 (10C/20T each). '
                    '64GB DDR4 RAM. 2× 1.2TB SAS 10k HDD. iDRAC9 Enterprise. '
                    'Used as a virtualisation host for 2 years. '
                    'Enterprise warranty expired. No hardware faults in logs. ' + SEEDED_TAG
                ),
                'brand': 'Dell', 'model_number': 'PowerEdge R440',
                'condition': 'used_good', 'price': Decimal('1250000'),
                'min_offer': Decimal('1050000'),
                'state': 'Lagos', 'lga': 'Victoria Island',
                'pickup_notes': 'VI data centre, appointment only.',
            },
            {
                'title': 'Cisco Catalyst 2960X-48FPD-L 48-Port PoE+ Switch',
                'description': (
                    '48-port PoE+ Gigabit switch with 2× SFP+ uplinks. '
                    '740W PoE budget. VLAN, QoS, Cisco IOS feature set. '
                    'Used in an office LAN for 3 years. All ports functional. '
                    'Running IOS 15.2(7)E5. ' + SEEDED_TAG
                ),
                'brand': 'Cisco', 'model_number': 'WS-C2960X-48FPD-L',
                'condition': 'used_good', 'price': Decimal('580000'),
                'min_offer': Decimal('500000'),
                'state': 'Lagos', 'lga': 'Ikeja',
                'pickup_notes': 'Allen Avenue area.',
            },
            {
                'title': 'APC Smart-UPS SRT 3000VA Online Tower UPS',
                'description': (
                    '3000VA / 2700W pure sine wave online UPS. '
                    'Runtime: ~12 min at full load. Batteries replaced 8 months ago. '
                    'Used to protect servers in an IT room. '
                    'Management card installed — SNMP logging. ' + SEEDED_TAG
                ),
                'brand': 'APC', 'model_number': 'SRT3000XLI',
                'condition': 'used_good', 'price': Decimal('580000'),
                'min_offer': Decimal('500000'),
                'state': 'Abuja', 'lga': 'Garki',
                'pickup_notes': 'Area 2, Garki — heavy item, bring help.',
            },
            {
                'title': 'Ubiquiti UniFi 48-Port POE Network Switch USW-Pro-48-POE',
                'description': (
                    '48× GbE PoE/PoE+ + 4× SFP+ uplinks. 600W PoE budget. '
                    'Used in a hospitality WiFi network for 2 years. '
                    'Firmware 6.6.61. Full management via UniFi controller. '
                    'All ports tested — no dead ports. ' + SEEDED_TAG
                ),
                'brand': 'Ubiquiti', 'model_number': 'USW-Pro-48-POE',
                'condition': 'used_good', 'price': Decimal('420000'),
                'min_offer': Decimal('370000'),
                'state': 'Lagos', 'lga': 'Lekki',
                'pickup_notes': 'Lekki Phase 1.',
            },
            {
                'title': '22U Wall-Mount Network Rack Cabinet — Closed, Lockable',
                'description': (
                    '22U 600×450mm closed wall-mount rack with fan tray and shelf. '
                    'Glass front door, side panels removable. '
                    'Removed from an office relocation. Minor cabinet surface scuffs only. '
                    'Cage nuts and mounting screws included. ' + SEEDED_TAG
                ),
                'condition': 'used_good', 'price': Decimal('85000'),
                'state': 'Lagos', 'lga': 'Gbagada',
                'pickup_notes': 'Gbagada, call ahead.',
            },
            {
                'title': 'Fortinet FortiGate 60E Next-Gen Firewall',
                'description': (
                    '10× GbE ports, 3Gbps firewall throughput, 400Mbps NGFW. '
                    'Used to protect a 150-user SME network. '
                    'Licence expired — basic firewall still fully functional. '
                    'Comes with PSU, admin credentials reset. ' + SEEDED_TAG
                ),
                'brand': 'Fortinet', 'model_number': 'FortiGate 60E',
                'condition': 'used_good', 'price': Decimal('220000'),
                'state': 'Lagos', 'lga': 'Ikeja',
                'pickup_notes': 'Allen Avenue, Ikeja.',
            },
            {
                'title': 'Patch Panel — 24-Port Cat6 Keystone (Loaded)',
                'description': (
                    '24-port 1U Cat6 loaded keystone patch panel. '
                    'All 24 ports punched and tested — certified to 250MHz. '
                    'Used in a structured cabling installation for 4 years. '
                    'Labels still readable; ports click cleanly. ' + SEEDED_TAG
                ),
                'condition': 'used_good', 'price': Decimal('18000'),
                'state': 'Abuja', 'lga': 'Wuse 2',
                'pickup_notes': 'Wuse 2.',
            },
            {
                'title': 'TP-Link TL-WA901ND Ceiling-Mount Access Point',
                'description': (
                    '450Mbps 802.11n 2.4GHz ceiling-mount AP. '
                    '6 units available — price per unit. Passive PoE powered. '
                    'Used in a school network. Range excellent indoors. ' + SEEDED_TAG
                ),
                'brand': 'TP-Link', 'model_number': 'TL-WA901ND',
                'condition': 'used_good', 'price': Decimal('12000'),
                'slots': 6,
                'state': 'Oyo', 'lga': 'Ibadan North',
                'pickup_notes': 'UI area, Ibadan.',
            },
            {
                'title': 'NetAlly AirCheck G3 Pro WiFi Analyser + Spectrum',
                'description': (
                    'Handheld WiFi 6 spectrum analyser and site survey tool. '
                    'Discovers rogue APs, tests throughput, maps heatmaps. '
                    '12-month subscription still active. '
                    'Used by a network contractor. Screen protector on — display pristine. ' + SEEDED_TAG
                ),
                'brand': 'NetAlly', 'model_number': 'AirCheck G3 Pro',
                'condition': 'used_good', 'price': Decimal('980000'),
                'min_offer': Decimal('850000'),
                'state': 'Lagos', 'lga': 'Victoria Island',
                'pickup_notes': 'VI — serious buyers only.',
            },
            {
                'title': 'Cable Labeller — Brady BMP41 Industrial Label Printer',
                'description': (
                    'Industrial label printer for wiring, patch panels, and asset tags. '
                    'Prints on cartridges up to 38mm wide. USB connectivity. '
                    'Comes with 2 full cartridges (white general-purpose). '
                    'Used in a data-centre build project. ' + SEEDED_TAG
                ),
                'brand': 'Brady', 'model_number': 'BMP41',
                'condition': 'used_good', 'price': Decimal('165000'),
                'min_offer': Decimal('140000'),
                'state': 'Lagos', 'lga': 'Ikeja',
                'pickup_notes': 'Allen Avenue.',
            },
        ],
    },

    # ── B19. Agricultural & Farm Equipment ────────────────────────────────────
    {
        'category': 'Agricultural & Farm Equipment',
        'slug': 'agricultural-farm-equipment',
        'icon_class': 'fas fa-tractor',
        'description': 'Tractors, irrigation, crop processing, and general farm tools.',
        'display_order': 29,
        'products': [
            {
                'title': 'Massey Ferguson MF 375 Tractor — 75HP 4WD',
                'description': (
                    '75HP 4WD utility tractor. Perkins 1004.4 engine. '
                    'Used on a 20-hectare rice farm. '
                    'Engine runs cleanly, hydraulic lift works. '
                    'Rear tyres 60% tread remaining. Service log available. ' + SEEDED_TAG
                ),
                'brand': 'Massey Ferguson', 'model_number': 'MF 375',
                'condition': 'used_good', 'price': Decimal('5800000'),
                'min_offer': Decimal('5200000'),
                'state': 'Kano', 'lga': 'Kano Municipal',
                'pickup_notes': 'Kano farm road — buyer arranges trailer.',
            },
            {
                'title': 'Knapsack Sprayer — Honda 4-Stroke 20L',
                'description': (
                    '20-litre motorised knapsack sprayer, Honda GX25 engine. '
                    'Used for herbicide application on 2 maize seasons. '
                    'Nozzle set includes flat fan and adjustable cone. '
                    'Tank seal good — no leaks. ' + SEEDED_TAG
                ),
                'brand': 'Honda',
                'condition': 'used_good', 'price': Decimal('58000'),
                'state': 'Kano', 'lga': 'Tofa',
                'pickup_notes': 'Tofa, Kano State — call before coming.',
            },
            {
                'title': 'Drip Irrigation Kit — 1-Hectare Layout (16mm)',
                'description': (
                    'Complete 1-hectare drip system: 1" main, 16mm lateral, '
                    '1000 button drippers (4 L/hr), valves, filter and fertigation injector. '
                    'Used for 1 tomato season. Drippers tested — 90% unblocked. '
                    'Manifold and fittings all present. ' + SEEDED_TAG
                ),
                'condition': 'used_good', 'price': Decimal('185000'),
                'min_offer': Decimal('158000'),
                'state': 'Kaduna', 'lga': 'Kaduna North',
                'pickup_notes': 'Kawo area, Kaduna.',
            },
            {
                'title': 'Threshing Machine — Petrol Rice/Groundnut Thresher 5HP',
                'description': (
                    'Portable motorised thresher for rice and groundnuts. '
                    '5HP Honda clone engine, 600kg/hr throughput. '
                    'Used for 2 harvests on a family farm. '
                    'Screen and beater bars checked — no broken bars. ' + SEEDED_TAG
                ),
                'condition': 'used_good', 'price': Decimal('145000'),
                'min_offer': Decimal('125000'),
                'state': 'Niger', 'lga': 'Bida',
                'pickup_notes': 'Bida town, call to arrange collection.',
            },
            {
                'title': 'Poultry Layer Cage — 4-Tier Galvanised, 120-Bird (Flat-Pack)',
                'description': (
                    'A-frame 4-tier cage system for 120 layers. '
                    'Hot-dip galvanised wire mesh, egg roll tray, feed trough, water pipe. '
                    'Used for 2 production cycles. Galvanising intact — no rust on inner frames. ' + SEEDED_TAG
                ),
                'condition': 'used_good', 'price': Decimal('420000'),
                'min_offer': Decimal('370000'),
                'state': 'Oyo', 'lga': 'Akinyele',
                'pickup_notes': 'Moniya farm road, Ibadan.',
            },
            {
                'title': 'Catfish Fingerling Sorting Machine — Motorised Grader',
                'description': (
                    'Motorised fish fingerling grader with 3 interchangeable size bars. '
                    'Grades 1–5cm, 5–10cm, and 10–15cm catfish in seconds. '
                    'Used on a 5-pond catfish farm. Motor quiet, bars clean. ' + SEEDED_TAG
                ),
                'condition': 'used_good', 'price': Decimal('85000'),
                'state': 'Ogun', 'lga': 'Sagamu',
                'pickup_notes': 'Sagamu ring road area.',
            },
            {
                'title': 'Chaff Cutter — Electric 1.5HP Motor, 200kg/hr',
                'description': (
                    'Electric chaff cutter for maize stalks and dry grass. '
                    '1.5HP, 240V, adjustable cut length (10/20/30mm). '
                    'Used in livestock feeding on a cattle farm. '
                    'Blades recently sharpened. Hopper intact. ' + SEEDED_TAG
                ),
                'condition': 'used_good', 'price': Decimal('68000'),
                'state': 'Benue', 'lga': 'Makurdi',
                'pickup_notes': 'Makurdi farm road.',
            },
            {
                'title': 'Rain Gauge — Davis 7852M Tipping-Bucket Rain Sensor',
                'description': (
                    'Professional tipping-bucket rain gauge, 0.2mm per tip resolution. '
                    'Stainless steel collector ring, filtered inlet. '
                    'Used on an agricultural weather station for 3 years. '
                    'Tip mechanism clean, funnel screen clear. ' + SEEDED_TAG
                ),
                'brand': 'Davis Instruments', 'model_number': '7852M',
                'condition': 'used_good', 'price': Decimal('38000'),
                'state': 'Abuja', 'lga': 'Bwari',
                'pickup_notes': 'Research institute campus, Bwari.',
            },
            {
                'title': 'Greenhouse Frame Kit — 6m × 12m Galvanised Single Span',
                'description': (
                    'Single-span galvanised steel greenhouse frame kit. '
                    '6m wide × 12m long × 3m gutter height. '
                    'Complete with ridges, rafters, vent frames, and door frames. '
                    'New — polythene cover not included. Easy assembly. ' + SEEDED_TAG
                ),
                'condition': 'new', 'price': Decimal('580000'),
                'min_offer': Decimal('510000'),
                'state': 'Kaduna', 'lga': 'Igabi',
                'pickup_notes': 'Kaduna South, bring truck.',
            },
            {
                'title': 'Borehole Pump — Grundfos SP5A-25 Submersible 1HP',
                'description': (
                    '1HP Grundfos borehole pump, 6" slim-line for 4" bore. '
                    '25m³/hr flow at 25m head. Used on a 3-hectare irrigation scheme. '
                    'Motor rewound 6 months ago — insulation resistance 200MΩ. '
                    'Impellers all spinning freely. ' + SEEDED_TAG
                ),
                'brand': 'Grundfos', 'model_number': 'SP5A-25',
                'condition': 'used_good', 'price': Decimal('145000'),
                'min_offer': Decimal('125000'),
                'state': 'Sokoto', 'lga': 'Sokoto North',
                'pickup_notes': 'Sokoto irrigation project office, call ahead.',
            },
        ],
    },

    # ── B20. Printing & Signage Equipment ─────────────────────────────────────
    {
        'category': 'Printing & Signage Equipment',
        'slug': 'printing-signage-equipment',
        'icon_class': 'fas fa-print',
        'description': 'Wide-format printers, plotters, laminators, and vinyl cutters.',
        'display_order': 30,
        'products': [
            {
                'title': 'Roland SOLJET Pro 4 XR-640 64" Eco-Solvent Printer/Cutter',
                'description': (
                    '64" wide-format print-and-cut machine. 8-colour eco-solvent ink. '
                    'Print speed 52.3 m²/hr. Used in an outdoor signage company for 2 years. '
                    'Heads recently cleaned and tested — banding free. '
                    'Includes Roland DG print manager. ' + SEEDED_TAG
                ),
                'brand': 'Roland', 'model_number': 'XR-640',
                'condition': 'used_good', 'price': Decimal('4200000'),
                'min_offer': Decimal('3700000'),
                'state': 'Lagos', 'lga': 'Ikeja',
                'pickup_notes': 'Oregun road — large machine, specialist transport.',
            },
            {
                'title': 'Graphtec CE7000-60 24" Vinyl Cutter Plotter',
                'description': (
                    '24" professional vinyl cutter, 500mm/s max speed, 400g blade force. '
                    'ARMS optical registration. Used with sign-making vinyl for 2 years. '
                    'Cutting carriage smooth, sensor clean. Comes with GRAPHTEC Studio software. ' + SEEDED_TAG
                ),
                'brand': 'Graphtec', 'model_number': 'CE7000-60',
                'condition': 'used_good', 'price': Decimal('380000'),
                'min_offer': Decimal('330000'),
                'state': 'Abuja', 'lga': 'Wuse 2',
                'pickup_notes': 'Wuse 2, Abuja.',
            },
            {
                'title': 'Epson SureColor SC-T5400 36" CAD/GIS Plotter',
                'description': (
                    '36" large-format plotter, 4-colour PrecisionCore. '
                    '35 sec per A1. Used in an engineering firm for 18 months. '
                    'Print head nozzle check 100%. 2 ink sets remaining. ' + SEEDED_TAG
                ),
                'brand': 'Epson', 'model_number': 'SC-T5400',
                'condition': 'used_good', 'price': Decimal('1250000'),
                'min_offer': Decimal('1050000'),
                'state': 'Lagos', 'lga': 'Victoria Island',
                'pickup_notes': 'VI, appointment only.',
            },
            {
                'title': 'Mefu MF1700-M1 Thermal Laminator 1600mm',
                'description': (
                    '1600mm hot-roll laminator, 0–180°C, 0–8m/min. '
                    'Used for encapsulating large-format prints. '
                    'Top and bottom rollers clean, no creases in test run. '
                    'Silicone roller set recently replaced. ' + SEEDED_TAG
                ),
                'brand': 'Mefu', 'model_number': 'MF1700-M1',
                'condition': 'used_good', 'price': Decimal('480000'),
                'min_offer': Decimal('420000'),
                'state': 'Lagos', 'lga': 'Mushin',
                'pickup_notes': 'Mushin industrial area.',
            },
            {
                'title': 'LED UV Flatbed Printer — Mimaki UJF-6042 MkII',
                'description': (
                    'A2 format flatbed UV printer for rigid substrates up to 153mm thick. '
                    '1440 dpi, white ink enabled. Used for acrylic and phone case printing. '
                    'UV lamps at 60% life. Heads test excellent. ' + SEEDED_TAG
                ),
                'brand': 'Mimaki', 'model_number': 'UJF-6042 MkII',
                'condition': 'used_good', 'price': Decimal('6500000'),
                'min_offer': Decimal('5800000'),
                'state': 'Lagos', 'lga': 'Ikeja',
                'pickup_notes': 'Oregun, Ikeja — specialist transport required.',
            },
            {
                'title': 'Heat Transfer Press — Sword 38×38cm Swing-Away',
                'description': (
                    '38cm × 38cm swing-away heat press. 0–250°C digital control, '
                    'timer 0–999s. Used for T-shirt and mug transfers in a small print shop. '
                    'Platen clean, pressure spring uniform. ' + SEEDED_TAG
                ),
                'brand': 'Sword',
                'condition': 'used_good', 'price': Decimal('48000'),
                'state': 'Oyo', 'lga': 'Ibadan North',
                'pickup_notes': 'Challenge area, Ibadan.',
            },
            {
                'title': 'Ricoh SG 3110DN Sublimation Printer (Modified)',
                'description': (
                    'A4 GelJet printer modified for dye-sublimation printing. '
                    'Sublimation ink set installed. '
                    'Used for photo and sportswear transfer printing. '
                    'Prints clean with no streaking. ' + SEEDED_TAG
                ),
                'brand': 'Ricoh', 'model_number': 'SG 3110DN',
                'condition': 'used_good', 'price': Decimal('38000'),
                'state': 'Abuja', 'lga': 'Kubwa',
                'pickup_notes': 'Kubwa, Phase 3.',
            },
            {
                'title': '4-Colour DTG Printer — Epson F2100 Direct-to-Garment',
                'description': (
                    'Direct-to-garment printer for cotton T-shirts and hoodies. '
                    '4-colour (CMYK) + white. Garment platen included. '
                    'Print head nozzle check passed 100%. '
                    'Used in a custom merchandise business for 1 year. ' + SEEDED_TAG
                ),
                'brand': 'Epson', 'model_number': 'SC-F2100',
                'condition': 'used_good', 'price': Decimal('1800000'),
                'min_offer': Decimal('1580000'),
                'state': 'Lagos', 'lga': 'Surulere',
                'pickup_notes': 'Bode Thomas, Surulere.',
            },
            {
                'title': 'Sign Board Channel Letters — Illuminated Acrylic Mould Set',
                'description': (
                    'Set of channel letter moulds A–Z and 0–9, 150mm height. '
                    'Used for forming backlit LED acrylic letters. '
                    'All 36 moulds in good shape, no cracks. '
                    'Ideal for a sign-making business. ' + SEEDED_TAG
                ),
                'condition': 'used_good', 'price': Decimal('85000'),
                'state': 'Lagos', 'lga': 'Ikeja',
                'pickup_notes': 'Allen Avenue area.',
            },
            {
                'title': 'Flex Solvent Banner Media — 510g, 3.2m × 50m Roll',
                'description': (
                    '3.2m wide × 50m printable flex banner, 510g/m² with weld-able edges. '
                    'Suitable for eco-solvent, solvent, and UV inks. '
                    'New, sealed in original core tube. '
                    '3 rolls available at this price. ' + SEEDED_TAG
                ),
                'condition': 'new', 'price': Decimal('55000'),
                'slots': 3,
                'state': 'Lagos', 'lga': 'Mushin',
                'pickup_notes': 'Mushin printing road.',
            },
        ],
    },

]

NIGERIAN_STATES = [
    'Abia', 'Adamawa', 'Akwa Ibom', 'Anambra', 'Bauchi', 'Bayelsa', 'Benue',
    'Borno', 'Cross River', 'Delta', 'Ebonyi', 'Edo', 'Ekiti', 'Enugu', 'FCT',
    'Gombe', 'Imo', 'Jigawa', 'Kaduna', 'Kano', 'Katsina', 'Kebbi', 'Kogi',
    'Kwara', 'Lagos', 'Nasarawa', 'Niger', 'Ogun', 'Ondo', 'Osun', 'Oyo',
    'Plateau', 'Rivers', 'Sokoto', 'Taraba', 'Yobe', 'Zamfara',
]


class Command(BaseCommand):
    help = (
        'Seeds the marketplace with 220 additional realistic product listings: '
        '20 extras across the original 10 categories + 20 brand-new categories '
        'with 10 products each.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--seller',
            type=str,
            default=None,
            metavar='PK',
            help='UUID of the WorkerProfile to assign all products to. '
                 'Defaults to the first verified WorkerProfile found.',
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            default=False,
            help=f'Remove all products tagged "{SEEDED_TAG}" before seeding.',
        )
        parser.add_argument(
            '--no-active',
            action='store_true',
            default=False,
            help='Create products in DRAFT status instead of ACTIVE.',
        )

    def handle(self, *args, **options):
        from marketplace.models import MarketplaceCategory, Product
        from jobs.models import WorkerProfile

        # ── 0. Optional clear ─────────────────────────────────────────────────
        if options['clear']:
            deleted, _ = Product.objects.filter(
                description__contains=SEEDED_TAG
            ).delete()
            self.stdout.write(self.style.WARNING(
                f'Cleared {deleted} previously seeded product(s).'
            ))

        # ── 1. Resolve seller(s) ──────────────────────────────────────────────
        if options['seller']:
            try:
                sellers = [WorkerProfile.objects.get(pk=options['seller'])]
            except WorkerProfile.DoesNotExist:
                raise CommandError(
                    f"WorkerProfile with pk='{options['seller']}' not found."
                )
        else:
            sellers = list(WorkerProfile.objects.all()[:10])
            if not sellers:
                raise CommandError(
                    'No WorkerProfile found. '
                    'Create at least one worker profile before seeding products.\n'
                    'Tip: python manage.py seed_marketplace_products_expanded --seller <pk>'
                )
            self.stdout.write(
                f'Found {len(sellers)} seller(s). Products will be distributed '
                f'across them randomly.'
            )

        # ── 2. Determine product status ───────────────────────────────────────
        status = (
            Product.Status.DRAFT
            if options['no_active']
            else Product.Status.ACTIVE
        )

        # ── 3. Seed categories + products ─────────────────────────────────────
        created_categories = 0
        created_products   = 0

        with transaction.atomic():
            for cat_data in SEED_DATA:
                category, cat_created = MarketplaceCategory.objects.get_or_create(
                    slug=cat_data['slug'],
                    defaults={
                        'name':          cat_data['category'],
                        'icon_class':    cat_data.get('icon_class', ''),
                        'description':   cat_data.get('description', ''),
                        'display_order': cat_data.get('display_order', 0),
                        'is_active':     True,
                    },
                )
                if cat_created:
                    created_categories += 1
                    self.stdout.write(f'  ✦ Category created: {category.name}')
                else:
                    self.stdout.write(f'  · Category exists:  {category.name}')

                for p in cat_data['products']:
                    seller = random.choice(sellers)

                    Product.objects.create(
                        seller          = seller,
                        category        = category,
                        title           = p['title'],
                        description     = p['description'],
                        condition       = p.get('condition', Product.Condition.USED_GOOD),
                        brand           = p.get('brand', ''),
                        model_number    = p.get('model_number', ''),
                        price           = p['price'],
                        min_offer       = p.get('min_offer'),
                        offers_allowed  = True,
                        state           = p.get('state', random.choice(NIGERIAN_STATES)),
                        lga             = p.get('lga', ''),
                        pickup_only     = True,
                        pickup_notes    = p.get('pickup_notes', ''),
                        status          = status,
                        slots           = p.get('slots', 1),
                        platform_fee_pct= Decimal('5.00'),
                    )
                    created_products += 1
                    self.stdout.write(f'      + {p["title"][:70]}')

        # ── 4. Summary ────────────────────────────────────────────────────────
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Done. Created {created_categories} new category(ies) and '
            f'{created_products} product(s) with status="{status}".'
        ))
        if status == Product.Status.ACTIVE:
            self.stdout.write(self.style.SUCCESS(
                'Embedding tasks will be queued automatically by the post_save signal '
                'if Celery is running.'
            ))
        else:
            self.stdout.write(self.style.WARNING(
                'Products created as DRAFT. Set status to ACTIVE when ready to publish.'
            ))