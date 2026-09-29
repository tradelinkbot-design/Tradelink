"""
marketplace/management/commands/seed_marketplace_products.py
=============================================================
Creates 50 realistic Nigerian tool & equipment marketplace listings spread
across 10 categories, each linked to a randomly selected verified WorkerProfile.

Usage
─────
    python manage.py seed_marketplace_products
    python manage.py seed_marketplace_products --seller <worker_profile_pk>
    python manage.py seed_marketplace_products --clear

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
    # ── 1. Power Tools ───────────────────────────────────────────────────────
    {
        'category': 'Power Tools',
        'slug': 'power-tools',
        'icon_class': 'fas fa-bolt',
        'description': 'Electric and battery-powered tools for professional trades.',
        'display_order': 1,
        'products': [
            {
                'title': 'Bosch GBH 2-26 DRE Rotary Hammer Drill',
                'description': (
                    'Powerful 800W SDS-Plus rotary hammer, ideal for concrete and masonry. '
                    'Used on two site jobs, still has original chuck and bits. '
                    'No vibration issues, motor runs smooth. ' + SEEDED_TAG
                ),
                'brand': 'Bosch', 'model_number': 'GBH 2-26 DRE',
                'condition': 'used_good', 'price': Decimal('42000'),
                'min_offer': Decimal('36000'),
                'state': 'Lagos', 'lga': 'Ikeja',
                'pickup_notes': 'Available weekends in Ikeja.',
            },
            {
                'title': 'DeWalt DCD778 18V Brushless Cordless Drill',
                'description': (
                    'Barely used cordless drill with 2 Li-Ion batteries and charger included. '
                    'Purchased 6 months ago for a renovation project that ended early. '
                    'Comes in original carry case. ' + SEEDED_TAG
                ),
                'brand': 'DeWalt', 'model_number': 'DCD778',
                'condition': 'used_good', 'price': Decimal('55000'),
                'min_offer': Decimal('48000'),
                'state': 'Abuja', 'lga': 'Garki',
                'pickup_notes': 'Garki Area 2, any weekday after 5pm.',
            },
            {
                'title': 'Makita 9565CVL Variable-Speed Angle Grinder 9"',
                'description': (
                    '2,200W angle grinder with variable speed dial. Used for cutting '
                    'reinforcement bars on a construction project. Disc guard intact, '
                    'comes with one grinding disc and one cutting disc. ' + SEEDED_TAG
                ),
                'brand': 'Makita', 'model_number': '9565CVL',
                'condition': 'used_fair', 'price': Decimal('28000'),
                'state': 'Rivers', 'lga': 'Port Harcourt',
                'pickup_notes': 'Trans-Amadi area, call ahead.',
            },
            {
                'title': 'Ingco Circular Saw 185mm 1200W — Brand New',
                'description': (
                    'Never used Ingco circular saw still in original packaging. '
                    'Bought as spare but the project got cancelled. '
                    'Includes rip fence, blade wrench, and carbide-tipped blade. ' + SEEDED_TAG
                ),
                'brand': 'Ingco', 'model_number': 'CS18528',
                'condition': 'new', 'price': Decimal('18500'),
                'min_offer': Decimal('16500'),
                'state': 'Oyo', 'lga': 'Ibadan North',
                'pickup_notes': 'Bodija market area.',
            },
            {
                'title': 'Krisbow Jigsaw 650W with 5 Blades',
                'description': (
                    'Corded jigsaw used for cutting plywood on a furniture project. '
                    'Orbital action switch works perfectly. Includes 5 assorted blades '
                    '(wood and metal). Minor scuff on housing, nothing functional. ' + SEEDED_TAG
                ),
                'brand': 'Krisbow', 'model_number': 'KW0600370',
                'condition': 'used_good', 'price': Decimal('12000'),
                'state': 'Lagos', 'lga': 'Lekki',
                'pickup_notes': 'Lekki Phase 1, evenings only.',
            },
        ],
    },

    # ── 2. Hand Tools ─────────────────────────────────────────────────────────
    {
        'category': 'Hand Tools',
        'slug': 'hand-tools',
        'icon_class': 'fas fa-tools',
        'description': 'Non-powered tools for skilled tradespeople.',
        'display_order': 2,
        'products': [
            {
                'title': 'Stanley FatMax 26" Hand Saw — Very Sharp',
                'description': (
                    'High-tensile steel blade, 11 TPI, barely used. Tried it once on '
                    'hardwood, switched to circular saw. Blade still has factory set. '
                    'Great for joiners or carpenters. ' + SEEDED_TAG
                ),
                'brand': 'Stanley', 'model_number': '20-526',
                'condition': 'new', 'price': Decimal('5500'),
                'state': 'Kano', 'lga': 'Kano Municipal',
                'pickup_notes': 'Kurmi market, call before coming.',
            },
            {
                'title': 'Bahco Combination Spanner Set (8–22mm, 8-piece)',
                'description': (
                    'Professional chrome-vanadium spanner set. Used by a mechanic for '
                    '3 years, all spanners in good shape with no rounding. '
                    'Stored in original roll pouch. ' + SEEDED_TAG
                ),
                'brand': 'Bahco', 'model_number': 'SB-6SET-5',
                'condition': 'used_good', 'price': Decimal('9800'),
                'min_offer': Decimal('8500'),
                'state': 'Lagos', 'lga': 'Mushin',
                'pickup_notes': 'Mushin market, Monday to Saturday, 8am–5pm.',
            },
            {
                'title': 'Pliers Set — Knipex + 2 Others, 3-piece',
                'description': (
                    'Includes one Knipex long-nose pliers (180mm), one Knipex '
                    'combination pliers, and a Chinese diagonal cutter. '
                    'Knipex pair in excellent condition. ' + SEEDED_TAG
                ),
                'brand': 'Knipex',
                'condition': 'used_good', 'price': Decimal('7500'),
                'state': 'Abuja', 'lga': 'Wuse',
                'pickup_notes': 'Wuse Zone 5 workshop.',
            },
            {
                'title': 'Roughneck Cold Chisels Set — 5 Pieces',
                'description': (
                    'Octagonal-shank cold chisels for concrete and masonry work. '
                    'Sizes: 12mm, 16mm, 19mm, 25mm, 32mm. '
                    'Tips have been resharpened once, still in good working order. ' + SEEDED_TAG
                ),
                'brand': 'Roughneck',
                'condition': 'used_fair', 'price': Decimal('4200'),
                'state': 'Enugu', 'lga': 'Enugu North',
                'pickup_notes': 'New Haven hardware market.',
            },
            {
                'title': 'Tape Measure 10m × 25mm — Stanley PowerLock',
                'description': (
                    'Classic PowerLock with blade lock and Belt clip. '
                    'Used on multiple sites, blade clean and readable throughout. '
                    'Hook still square. Selling because I switched to digital. ' + SEEDED_TAG
                ),
                'brand': 'Stanley', 'model_number': '33-425',
                'condition': 'used_good', 'price': Decimal('3200'),
                'state': 'Lagos', 'lga': 'Yaba',
                'pickup_notes': 'Yaba Tech area, evenings.',
            },
        ],
    },

    # ── 3. Electrical Equipment ───────────────────────────────────────────────
    {
        'category': 'Electrical Equipment',
        'slug': 'electrical-equipment',
        'icon_class': 'fas fa-plug',
        'description': 'Wiring tools, test equipment, and electrical accessories.',
        'display_order': 3,
        'products': [
            {
                'title': 'Fluke 117 True-RMS Digital Multimeter',
                'description': (
                    'Electrician-grade multimeter with non-contact voltage detection. '
                    'Accurate to ±0.5% on DC. Comes with original leads, thermocouple '
                    'adapter, and holster. Purchased 2022, used on residential wiring jobs. ' + SEEDED_TAG
                ),
                'brand': 'Fluke', 'model_number': '117',
                'condition': 'used_good', 'price': Decimal('62000'),
                'min_offer': Decimal('55000'),
                'state': 'Lagos', 'lga': 'Victoria Island',
                'pickup_notes': 'VI by appointment only.',
            },
            {
                'title': 'Klein Tools Wire Stripper / Cutter 10–18 AWG',
                'description': (
                    'Self-adjusting wire stripper, barely used. Works on 10–18 AWG '
                    'solid and stranded wire. Comfortable dual-material handles. ' + SEEDED_TAG
                ),
                'brand': 'Klein Tools', 'model_number': '11061',
                'condition': 'new', 'price': Decimal('8900'),
                'state': 'Abuja', 'lga': 'Maitama',
                'pickup_notes': 'Maitama, call to arrange.',
            },
            {
                'title': 'Ridgid 300 Compact Threading Machine (230V)',
                'description': (
                    'Compact pipe threader, 230V Nigerian plug, cuts ½" to 2" pipe. '
                    'Includes die head 811A, pipe cutter, reamer and stand. '
                    'Used on two plumbing contracts. Needs one new die segment. ' + SEEDED_TAG
                ),
                'brand': 'Ridgid', 'model_number': '300 Compact',
                'condition': 'used_fair', 'price': Decimal('185000'),
                'min_offer': Decimal('160000'),
                'state': 'Lagos', 'lga': 'Apapa',
                'pickup_notes': 'Apapa, large item — buyer to arrange transport.',
            },
            {
                'title': 'Lutron LM-80 Lux Light Meter',
                'description': (
                    'Digital lux / foot-candle meter for lighting design and safety checks. '
                    'Accurate from 0.1 to 200,000 Lux. Used for electrical certification jobs. '
                    'Comes with carrying case and 9V battery. ' + SEEDED_TAG
                ),
                'brand': 'Lutron', 'model_number': 'LM-80',
                'condition': 'used_good', 'price': Decimal('14500'),
                'state': 'Ogun', 'lga': 'Sagamu',
                'pickup_notes': 'Sagamu, can meet at express exit.',
            },
            {
                'title': 'Conduit Bender 20mm EMT — Greenlee',
                'description': (
                    'Hand conduit bender for 20mm (¾") EMT. Hook, rim, and arrow markings '
                    'still clearly visible. Good for electricians doing surface wiring. '
                    'Priced to sell quickly. ' + SEEDED_TAG
                ),
                'brand': 'Greenlee',
                'condition': 'used_good', 'price': Decimal('7200'),
                'state': 'Rivers', 'lga': 'Obio-Akpor',
                'pickup_notes': 'Rumuola junction.',
            },
        ],
    },

    # ── 4. Plumbing Supplies ──────────────────────────────────────────────────
    {
        'category': 'Plumbing Supplies',
        'slug': 'plumbing-supplies',
        'icon_class': 'fas fa-faucet',
        'description': 'Pipe fittings, valves, and plumbing tools.',
        'display_order': 4,
        'products': [
            {
                'title': 'Rothenberger ROMAX Compact Press Tool Set',
                'description': (
                    'Battery-powered press tool for copper and stainless push-fit fittings. '
                    'Includes V15, V18, V22 jaws. Battery and charger included. '
                    'About 200 presses done — barely run in. ' + SEEDED_TAG
                ),
                'brand': 'Rothenberger', 'model_number': 'ROMAX Compact',
                'condition': 'used_good', 'price': Decimal('320000'),
                'min_offer': Decimal('280000'),
                'state': 'Lagos', 'lga': 'Ikorodu',
                'pickup_notes': 'Ikorodu town, Saturday mornings.',
            },
            {
                'title': 'Toledo Pipe Cutter Set (Sizes 3mm–50mm)',
                'description': (
                    '3-piece set: tube cutter for mini copper (3–16mm), standard (15–32mm), '
                    'and large (28–50mm). All three cutters in good shape, wheels sharp. '
                    'Stored in canvas roll bag. ' + SEEDED_TAG
                ),
                'brand': 'Toledo',
                'condition': 'used_good', 'price': Decimal('11500'),
                'state': 'Delta', 'lga': 'Warri',
                'pickup_notes': 'DSC road, Warri.',
            },
            {
                'title': 'Pressure Test Pump — Manual Hydraulic 60 Bar',
                'description': (
                    'Used for pressure-testing water and heating systems. '
                    'Tests up to 60 Bar (870 PSI). Includes 2m hose and gauge. '
                    'Gauge has been calibrated and reads accurately. ' + SEEDED_TAG
                ),
                'condition': 'used_good', 'price': Decimal('22000'),
                'state': 'Abuja', 'lga': 'Lugbe',
                'pickup_notes': 'Lugbe, near airport road.',
            },
            {
                'title': 'Push-Fit Speedfit Plumbing Kit — Assorted 15mm & 22mm',
                'description': (
                    'Approx 80 push-fit fittings: equal tees, elbows, couplers, end stops '
                    'in 15mm and 22mm. Leftover from a refit. All brand new in original bags. ' + SEEDED_TAG
                ),
                'brand': 'JG Speedfit',
                'condition': 'new', 'price': Decimal('16800'),
                'min_offer': Decimal('14000'),
                'state': 'Lagos', 'lga': 'Surulere',
                'pickup_notes': 'Bode Thomas street.',
            },
            {
                'title': 'Fernox TF1 Magnetic System Filter 22mm',
                'description': (
                    'Magnetic filter for central heating systems. Used for one heating season, '
                    'cleaned and refitted. Includes 22mm gate valves and mounting bracket. ' + SEEDED_TAG
                ),
                'brand': 'Fernox', 'model_number': 'TF1',
                'condition': 'used_good', 'price': Decimal('38000'),
                'state': 'Lagos', 'lga': 'Gbagada',
                'pickup_notes': 'Gbagada Phase 2 estate.',
            },
        ],
    },

    # ── 5. Safety Gear ────────────────────────────────────────────────────────
    {
        'category': 'Safety Gear',
        'slug': 'safety-gear',
        'icon_class': 'fas fa-hard-hat',
        'description': 'PPE and safety equipment for trade professionals.',
        'display_order': 5,
        'products': [
            {
                'title': '3M Full-Face Respirator with P100 + OV Cartridges (Size M)',
                'description': (
                    'Series 6000 full-face air-purifying respirator, size medium. '
                    'Used for painting and solvent work. Lens clean, seal good. '
                    'Comes with 2 pairs of P100 + organic vapour cartridges (unused). ' + SEEDED_TAG
                ),
                'brand': '3M', 'model_number': '6800',
                'condition': 'used_good', 'price': Decimal('28500'),
                'min_offer': Decimal('24000'),
                'state': 'Lagos', 'lga': 'Amuwo-Odofin',
                'pickup_notes': 'Festac Town, Mile 2 area.',
            },
            {
                'title': 'MSA V-Gard Safety Helmets — 10 Units (Yellow)',
                'description': (
                    'Ten brand-new V-Gard polycarbonate helmets, yellow. '
                    'Pinlock suspension inside, adjustable 51–63cm. '
                    'Removed from site stock — surplus from a construction contract. ' + SEEDED_TAG
                ),
                'brand': 'MSA', 'model_number': 'V-Gard',
                'condition': 'new', 'price': Decimal('38000'),
                'min_offer': Decimal('34000'),
                'state': 'Abuja', 'lga': 'Kubwa',
                'pickup_notes': 'Kubwa, contact for address.',
            },
            {
                'title': 'Bolle Safety Glasses Assorted Pack (20 pairs)',
                'description': (
                    'Mixed pack of 20 pairs of clear and tinted safety glasses. '
                    'Anti-scratch coating, CE EN166 rated. New in box. '
                    'Perfect for site foremen issuing to workers. ' + SEEDED_TAG
                ),
                'brand': 'Bolle',
                'condition': 'new', 'price': Decimal('12000'),
                'state': 'Lagos', 'lga': 'Agege',
                'pickup_notes': 'Agege, call first.',
            },
            {
                'title': 'Fall Arrest Harness — Honeywell Miller, Size L/XL',
                'description': (
                    'Class A full-body harness for working at height. '
                    'Used for scaffolding erection on two commercial projects. '
                    'Stitching intact, no shock loading history — comes with inspection tag. ' + SEEDED_TAG
                ),
                'brand': 'Honeywell Miller', 'model_number': 'T4500/L/XL',
                'condition': 'used_good', 'price': Decimal('21000'),
                'state': 'Rivers', 'lga': 'Port Harcourt',
                'pickup_notes': 'Rumuola, PH.',
            },
            {
                'title': 'Anti-Vibration Leather Gloves — 3 Pairs (Size L)',
                'description': (
                    'New anti-vibration gloves for use with grinders and jackhammers. '
                    'Padded palm with gel insert. EN ISO 10819 rated. '
                    'Size Large, 3 pairs never used. ' + SEEDED_TAG
                ),
                'condition': 'new', 'price': Decimal('6500'),
                'state': 'Anambra', 'lga': 'Awka North',
                'pickup_notes': 'Awka, weekdays.',
            },
        ],
    },

    # ── 6. Woodworking Tools ──────────────────────────────────────────────────
    {
        'category': 'Woodworking Tools',
        'slug': 'woodworking-tools',
        'icon_class': 'fas fa-drafting-compass',
        'description': 'Saws, planes, routers, and carpentry equipment.',
        'display_order': 6,
        'products': [
            {
                'title': 'Festool TS 55 REQ Track Saw with 1.4m Rail',
                'description': (
                    'Premium plunge-cut track saw with 1.4m guide rail. Used for precision '
                    'sheet goods cutting on a high-end joinery contract. '
                    'Dust port works, blade still good, rail connection smooth. ' + SEEDED_TAG
                ),
                'brand': 'Festool', 'model_number': 'TS 55 REQ',
                'condition': 'used_good', 'price': Decimal('195000'),
                'min_offer': Decimal('175000'),
                'state': 'Lagos', 'lga': 'Victoria Island',
                'pickup_notes': 'VI, serious buyers only please.',
            },
            {
                'title': 'Triton MOF001 Router Table Combo 1400W',
                'description': (
                    'Plunge router with full-size router table kit. '
                    '1/2" and 1/4" collets included. 12 speed settings. '
                    'Used on a fitted wardrobe project. Table top has light tooling marks. ' + SEEDED_TAG
                ),
                'brand': 'Triton', 'model_number': 'MOF001',
                'condition': 'used_good', 'price': Decimal('75000'),
                'min_offer': Decimal('65000'),
                'state': 'Lagos', 'lga': 'Badagry',
                'pickup_notes': 'Badagry expressway.',
            },
            {
                'title': 'Record Power BS350S 350mm Bandsaw — 230V',
                'description': (
                    'Floor-standing bandsaw with 350mm throat depth, 160mm cutting height. '
                    'Fitted with a fresh Starrett blade. Table tilts 0–45°. '
                    'Used in a small furniture workshop, very well maintained. ' + SEEDED_TAG
                ),
                'brand': 'Record Power', 'model_number': 'BS350S',
                'condition': 'used_good', 'price': Decimal('145000'),
                'min_offer': Decimal('125000'),
                'state': 'Oyo', 'lga': 'Egbeda',
                'pickup_notes': 'Workshop in Egbeda — large item, bring van.',
            },
            {
                'title': 'Narex 6-Piece Mortise Chisel Set (6–20mm)',
                'description': (
                    'Professional mortise chisels, A2 steel. Never commercially used — '
                    'bought for a hobby project that did not happen. All edges factory sharp. '
                    'Stored in original wooden box. ' + SEEDED_TAG
                ),
                'brand': 'Narex',
                'condition': 'new', 'price': Decimal('22000'),
                'state': 'Abuja', 'lga': 'Asokoro',
                'pickup_notes': 'Asokoro, appointment only.',
            },
            {
                'title': 'Veritas Bevel-Up Jack Plane',
                'description': (
                    'Premium hand plane for truing and flattening lumber. '
                    'PM-V11 blade holds an edge for hours. '
                    'Used on two furniture builds, blade freshly honed. '
                    'Sole flat within 0.01mm. ' + SEEDED_TAG
                ),
                'brand': 'Veritas', 'model_number': '05P29.01',
                'condition': 'used_good', 'price': Decimal('48000'),
                'min_offer': Decimal('42000'),
                'state': 'Lagos', 'lga': 'Magodo',
                'pickup_notes': 'Magodo Phase 2.',
            },
        ],
    },

    # ── 7. Measuring Instruments ──────────────────────────────────────────────
    {
        'category': 'Measuring Instruments',
        'slug': 'measuring-instruments',
        'icon_class': 'fas fa-ruler-combined',
        'description': 'Levels, distance meters, thermometers, and gauges.',
        'display_order': 7,
        'products': [
            {
                'title': 'Leica Disto D2 Laser Distance Meter',
                'description': (
                    'Accurate to ±1.5mm up to 60m. Bluetooth to iOS/Android. '
                    'Used for quantity surveying and MEP layouts. '
                    'Screen has minor surface scratch — readings unaffected. '
                    'Original case and lanyard included. ' + SEEDED_TAG
                ),
                'brand': 'Leica', 'model_number': 'Disto D2',
                'condition': 'used_good', 'price': Decimal('58000'),
                'min_offer': Decimal('50000'),
                'state': 'Lagos', 'lga': 'Lekki',
                'pickup_notes': 'Lekki Phase 1 office.',
            },
            {
                'title': 'Stabila 96-2 Spirit Level 120cm',
                'description': (
                    'Professional aluminium spirit level with 3 vials (horizontal, '
                    'vertical, 45°). Accurate to 0.029°/m. Only surface marks, '
                    'accuracy verified with reversal test. ' + SEEDED_TAG
                ),
                'brand': 'Stabila', 'model_number': '96-2',
                'condition': 'used_good', 'price': Decimal('16500'),
                'state': 'Rivers', 'lga': 'Port Harcourt',
                'pickup_notes': 'GRA Phase 2, PH.',
            },
            {
                'title': 'Flir TG165-X Thermal Camera + Spot Meter',
                'description': (
                    'Handheld thermal imaging camera used for electrical inspection and '
                    'HVAC diagnostics. 80×60 IR resolution, -25°C to 300°C range. '
                    'Comes with USB cable and carry pouch. ' + SEEDED_TAG
                ),
                'brand': 'Flir', 'model_number': 'TG165-X',
                'condition': 'used_good', 'price': Decimal('89000'),
                'min_offer': Decimal('78000'),
                'state': 'Abuja', 'lga': 'Central Business District',
                'pickup_notes': 'CBD, Abuja.',
            },
            {
                'title': 'Supatool Combination Square Set — 300mm',
                'description': (
                    'Three-piece set: combination square, protractor head, centre head. '
                    'Hardened blade, readable markings. Used for metalwork marking. '
                    'Blade still straight. ' + SEEDED_TAG
                ),
                'brand': 'Supatool',
                'condition': 'used_good', 'price': Decimal('9500'),
                'state': 'Lagos', 'lga': 'Alimosho',
                'pickup_notes': 'Iyana-Ipaja area.',
            },
            {
                'title': 'Silverline Digital Angle Finder — 4-way 400mm',
                'description': (
                    'Digital inclinometer / angle finder, ±0.1° accuracy. '
                    'Four 100mm hinged arms, hold function, magnetic base. '
                    'Used for staircase and roof pitch work. Battery still good. ' + SEEDED_TAG
                ),
                'brand': 'Silverline',
                'condition': 'used_good', 'price': Decimal('7800'),
                'state': 'Ogun', 'lga': 'Ifo',
                'pickup_notes': 'Ifo town.',
            },
        ],
    },

    # ── 8. HVAC & Refrigeration ───────────────────────────────────────────────
    {
        'category': 'HVAC & Refrigeration',
        'slug': 'hvac-refrigeration',
        'icon_class': 'fas fa-snowflake',
        'description': 'Air-conditioning tools, refrigerants, and HVAC equipment.',
        'display_order': 8,
        'products': [
            {
                'title': 'Robinair AC300 Pro Refrigerant Recovery Machine',
                'description': (
                    'Push-pull recovery machine for R22, R134a, R407C, R410A. '
                    'Used professionally on residential AC jobs for 2 years. '
                    'Motor strong, gauge accurate, hoses included. ' + SEEDED_TAG
                ),
                'brand': 'Robinair', 'model_number': 'AC300 Pro',
                'condition': 'used_good', 'price': Decimal('210000'),
                'min_offer': Decimal('185000'),
                'state': 'Lagos', 'lga': 'Oshodi-Isale',
                'pickup_notes': 'Oshodi, large equipment — call first.',
            },
            {
                'title': 'Yellow Jacket 4-Valve Manifold Gauge Set (R22/R410A)',
                'description': (
                    'Dual-reading gauges for R22 and R410A. High and low side with '
                    '3 × 60" colour-coded hoses. Used on about 50 AC service jobs. '
                    'Gauges calibrated, no leaks in hoses. ' + SEEDED_TAG
                ),
                'brand': 'Yellow Jacket',
                'condition': 'used_good', 'price': Decimal('45000'),
                'state': 'Kano', 'lga': 'Fagge',
                'pickup_notes': 'Sabon Gari, Kano.',
            },
            {
                'title': 'Fieldpiece HR2 Rechargeable Refrigerant Leak Detector',
                'description': (
                    'Heated diode leak detector, sensitivity <0.1 oz/yr. '
                    'Audible and visual alerts. Comes with charging dock. '
                    'Sensor replaced 4 months ago — still fully functional. ' + SEEDED_TAG
                ),
                'brand': 'Fieldpiece', 'model_number': 'HR2',
                'condition': 'used_good', 'price': Decimal('32000'),
                'state': 'Lagos', 'lga': 'Ikeja',
                'pickup_notes': 'Computer Village area.',
            },
            {
                'title': 'Appion G5 Twin Refrigerant Recovery Machine',
                'description': (
                    'Dual-cylinder high-speed recovery machine, handles all common '
                    'refrigerants. Very fast — 2 lbs/min. '
                    'Used on 12-split-unit commercial job. Good condition. ' + SEEDED_TAG
                ),
                'brand': 'Appion', 'model_number': 'G5 Twin',
                'condition': 'used_good', 'price': Decimal('280000'),
                'min_offer': Decimal('250000'),
                'state': 'Abuja', 'lga': 'Jabi',
                'pickup_notes': 'Jabi, call before visit.',
            },
            {
                'title': 'Fluke 971 Temperature & Humidity Meter',
                'description': (
                    'Precise HVAC air quality tool. Measures temp (-20 to 60°C) '
                    'and relative humidity (0–99.9%). Used for commissioning 3 hotel '
                    'HVAC systems. Calibration sticker valid till 2025. ' + SEEDED_TAG
                ),
                'brand': 'Fluke', 'model_number': '971',
                'condition': 'used_good', 'price': Decimal('38000'),
                'state': 'Lagos', 'lga': 'Ikoyi',
                'pickup_notes': 'Ikoyi.',
            },
        ],
    },

    # ── 9. Welding & Fabrication ──────────────────────────────────────────────
    {
        'category': 'Welding & Fabrication',
        'slug': 'welding-fabrication',
        'icon_class': 'fas fa-fire',
        'description': 'Welding machines, plasma cutters, and metal fabrication tools.',
        'display_order': 9,
        'products': [
            {
                'title': 'Lincoln Electric POWER MIG 180C MIG Welder',
                'description': (
                    'Industrial MIG welder, 30–180A, 230V. Feeds .023"–.035" wire. '
                    'Used for mild steel structural welding on a warehouse project. '
                    'Drive rolls, gun, and ground cable all original. ' + SEEDED_TAG
                ),
                'brand': 'Lincoln Electric', 'model_number': 'POWER MIG 180C',
                'condition': 'used_good', 'price': Decimal('165000'),
                'min_offer': Decimal('148000'),
                'state': 'Lagos', 'lga': 'Apapa',
                'pickup_notes': 'Apapa — heavy item, bring help.',
            },
            {
                'title': 'ESAB Rogue ES 180i ARC / MMA Inverter Welder',
                'description': (
                    'Portable stick welder, 10–180A. Comes with electrode holder, '
                    'earth clamp and shoulder strap carry bag. '
                    'Ideal for site work and repair welding. Only 30hrs on it. ' + SEEDED_TAG
                ),
                'brand': 'ESAB', 'model_number': 'Rogue ES 180i',
                'condition': 'used_good', 'price': Decimal('68000'),
                'min_offer': Decimal('60000'),
                'state': 'Rivers', 'lga': 'Port Harcourt',
                'pickup_notes': 'Rumuola PH, flexible times.',
            },
            {
                'title': 'Hypertherm Powermax 45 XP Plasma Cutter',
                'description': (
                    'Cuts up to 16mm mild steel, severs up to 22mm. '
                    '45A, 240V. Used for plate cutting on two fabrication contracts. '
                    'Torch consumables recently replaced. Includes drag shield. ' + SEEDED_TAG
                ),
                'brand': 'Hypertherm', 'model_number': 'Powermax 45 XP',
                'condition': 'used_good', 'price': Decimal('310000'),
                'min_offer': Decimal('280000'),
                'state': 'Ogun', 'lga': 'Ota',
                'pickup_notes': 'Ota industrial area.',
            },
            {
                'title': 'Welding Helmet — Miller Digital Elite Black/Gold',
                'description': (
                    'Auto-darkening helmet, shades 3–13. 1/25,000s switching speed. '
                    'Solar + lithium power. Used on TIG welding work. '
                    'Headgear ratchet works perfectly, lens clean. ' + SEEDED_TAG
                ),
                'brand': 'Miller', 'model_number': 'Digital Elite',
                'condition': 'used_good', 'price': Decimal('52000'),
                'state': 'Lagos', 'lga': 'Oshodi-Isale',
                'pickup_notes': 'Oshodi.',
            },
            {
                'title': 'Victor Journeyman Oxy-Acetylene Torch Set',
                'description': (
                    'Professional cutting and welding torch set. Includes regulators, '
                    '3m hoses, cutting torch, welding torch, and tips (0–5). '
                    'Sold without gas cylinders. All valves seal properly. ' + SEEDED_TAG
                ),
                'brand': 'Victor', 'model_number': 'Journeyman G350',
                'condition': 'used_good', 'price': Decimal('88000'),
                'min_offer': Decimal('78000'),
                'state': 'Kano', 'lga': 'Nassarawa',
                'pickup_notes': 'Kano, Workshop Road.',
            },
        ],
    },

    # ── 10. Materials & Supplies ──────────────────────────────────────────────
    {
        'category': 'Materials & Supplies',
        'slug': 'materials-supplies',
        'icon_class': 'fas fa-boxes',
        'description': 'Raw materials, fixings, adhesives, and consumables.',
        'display_order': 10,
        'products': [
            {
                'title': '50kg Bag — Dangote Portland Cement 3X (5 Bags)',
                'description': (
                    '5 × 50kg bags of Dangote 3X Portland cement, purchased last week. '
                    'Stored undercover on pallets — completely dry. '
                    'Selling because the concrete pour was cancelled. ' + SEEDED_TAG
                ),
                'brand': 'Dangote',
                'condition': 'new', 'price': Decimal('9500'),
                'min_offer': Decimal('8500'),
                'state': 'Abuja', 'lga': 'Bwari',
                'pickup_notes': 'Bwari — bring your own vehicle for 5 bags.',
            },
            {
                'title': 'Hilti HIT-HY 200-R Adhesive Anchor — Box of 10',
                'description': (
                    '10 × 330ml foil packs of Hilti epoxy adhesive for anchoring rebar '
                    'and threaded rods into concrete. '
                    'Unexpired (batch exp. 2026). Left over from a structural project. ' + SEEDED_TAG
                ),
                'brand': 'Hilti', 'model_number': 'HIT-HY 200-R',
                'condition': 'new', 'price': Decimal('78000'),
                'min_offer': Decimal('70000'),
                'state': 'Lagos', 'lga': 'Gbagada',
                'pickup_notes': 'Gbagada, contact for address.',
            },
            {
                'title': 'Araldite 2011 Structural Adhesive — 24 × 400ml Cartridges',
                'description': (
                    'Full case of 24 × 400ml Araldite 2011 A+B epoxy adhesive. '
                    'Used for bonding metal, fibreglass, and concrete. '
                    'Case opened, all 24 cartridges sealed. Best before 2026. ' + SEEDED_TAG
                ),
                'brand': 'Araldite', 'model_number': '2011',
                'condition': 'new', 'price': Decimal('145000'),
                'state': 'Lagos', 'lga': 'Apapa',
                'pickup_notes': 'Apapa, can deliver within Lagos for fee.',
            },
            {
                'title': '50m Reel — 2.5mm² Twin & Earth Cable (100m available)',
                'description': (
                    'British Standard BS 6004 twin & earth cable, grey sheath. '
                    '50m reels available. Ideal for domestic wiring. '
                    'Priced per reel — can sell multiples. ' + SEEDED_TAG
                ),
                'condition': 'new', 'price': Decimal('8200'),
                'state': 'Lagos', 'lga': 'Alimosho',
                'slots': 2,
                'pickup_notes': 'Iyana-Ipaja, electrical store.',
            },
            {
                'title': 'Quanex Silicone Sealant — Trade Pack (24 × 300ml, Clear)',
                'description': (
                    '24-piece trade pack of neutral-cure clear silicone sealant. '
                    'Paintable, suitable for kitchens, bathrooms, and general glazing. '
                    'Box opened, all tubes untouched. 12 months to expiry. ' + SEEDED_TAG
                ),
                'condition': 'new', 'price': Decimal('22000'),
                'min_offer': Decimal('19000'),
                'state': 'Oyo', 'lga': 'Ibadan South-West',
                'pickup_notes': 'Dugbe area, Ibadan.',
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
        'Seeds the marketplace with 50 realistic product listings across 10 '
        'categories. Requires at least one verified WorkerProfile to exist.'
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
                    'Tip: python manage.py seed_marketplace_products --seller <pk>'
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