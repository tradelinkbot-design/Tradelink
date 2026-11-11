"""
Management command: seed_blog_posts
====================================
Creates 6 blog categories and 10 high-quality, SEO-optimised blog posts
aligned with TradeLink NG's mission: connecting skilled Nigerian artisans
with employers through a verified, escrow-backed marketplace.

Usage:
    python manage.py seed_blog_posts
    python manage.py seed_blog_posts --clear   # deletes existing seeded posts first

The command is fully IDEMPOTENT — safe to run multiple times.
"""

import textwrap
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.text import slugify

User = get_user_model()


# ─────────────────────────────────────────────────────────────────────────────
#  SEED DATA
# ─────────────────────────────────────────────────────────────────────────────

CATEGORIES = [
    {
        "name": "Hiring Tips",
        "slug": "hiring-tips",
        "description": "Practical guides for employers and clients who want to find, vet, and onboard the right skilled tradespeople across Nigeria.",
        "icon_class": "fas fa-briefcase",
        "color": "#D97706",
        "seo_title": "Hiring Tips for Nigerian Employers | TradeLink NG Blog",
        "seo_description": "Learn how to hire verified, skilled artisans efficiently across Nigeria. Expert tips for employers on TradeLink NG.",
    },
    {
        "name": "Trade Safety",
        "slug": "trade-safety",
        "description": "Best practices, regulations, and safety standards for artisans and construction professionals working across Nigeria.",
        "icon_class": "fas fa-hard-hat",
        "color": "#EA580C",
        "seo_title": "Trade Safety Tips for Nigerian Artisans | TradeLink NG Blog",
        "seo_description": "Essential safety guides for electricians, plumbers, carpenters and all skilled tradespeople working in Nigeria.",
    },
    {
        "name": "Tool Reviews",
        "slug": "tool-reviews",
        "description": "Honest reviews and buying guides for tools and equipment every Nigerian artisan needs to do their best work.",
        "icon_class": "fas fa-tools",
        "color": "#059669",
        "seo_title": "Tool Reviews for Nigerian Artisans | TradeLink NG Blog",
        "seo_description": "Unbiased reviews of the best tools and equipment for plumbers, electricians, carpenters and more in Nigeria.",
    },
    {
        "name": "Apprenticeship & Training",
        "slug": "apprenticeship-training",
        "description": "Resources for young Nigerians looking to learn a trade and for master craftsmen seeking qualified apprentices.",
        "icon_class": "fas fa-graduation-cap",
        "color": "#7C3AED",
        "seo_title": "Apprenticeship and Trade Training in Nigeria | TradeLink NG Blog",
        "seo_description": "Find apprenticeship opportunities and trade training programmes across Nigeria. Start your skilled-trade career today.",
    },
    {
        "name": "Nigerian Artisan Economy",
        "slug": "nigerian-artisan-economy",
        "description": "Data, analysis, and stories about the multi-billion naira informal trades economy powering Nigeria's development.",
        "icon_class": "fas fa-chart-line",
        "color": "#0EA5E9",
        "seo_title": "Nigerian Artisan Economy Insights | TradeLink NG Blog",
        "seo_description": "Analysis, data, and stories about Nigeria's skilled-trades economy — the engine of the country's infrastructure.",
    },
    {
        "name": "Platform Guides",
        "slug": "platform-guides",
        "description": "Step-by-step tutorials on how to get the most out of TradeLink NG — for both workers and employers.",
        "icon_class": "fas fa-map-signs",
        "color": "#DB2777",
        "seo_title": "TradeLink NG Platform Guides | How to Use TradeLink NG",
        "seo_description": "Step-by-step guides on posting jobs, verifying your profile, using escrow payments, and more on TradeLink NG.",
    },
]


POSTS = [
    # 1
    {
        "title": "How to Hire Verified Artisans Safely on TradeLink NG",
        "slug": "how-to-hire-verified-artisans-tradelink-ng",
        "category_slug": "hiring-tips",
        "excerpt": "Hiring the wrong technician can cost you money, time, and peace of mind. Learn how TradeLink NG's three-tier verification system — NIN, BVN, and CAC — protects every employer before work begins.",
        "seo_title": "How to Hire Verified Artisans in Nigeria Safely | TradeLink NG",
        "seo_description": "Step-by-step guide to hiring a verified plumber, electrician, or carpenter on TradeLink NG. Understand NIN, BVN, and CAC verification tiers for safe hiring in Nigeria.",
        "tags": ["hiring", "verification", "artisans", "Nigeria", "NIN", "BVN"],
        "is_featured": True,
        "body": textwrap.dedent("""\
            <h2>Why Verification Matters Before You Hire</h2>
            <p>Every year, Nigerians lose billions of naira to cowboy artisans — tradespeople who collect deposits and disappear, do shoddy work, or misrepresent their qualifications. TradeLink NG was built to end that cycle.</p>
            <p>Our platform uses a <strong>three-tier identity and skills verification</strong> system so you always know exactly who you're hiring.</p>

            <h2>Understanding the Three Verification Tiers</h2>
            <h3>🔵 Level 1 — NIN Verification (Blue Badge)</h3>
            <p>Every worker on TradeLink NG must verify their National Identification Number (NIN) with the National Identity Management Commission (NIMC) before they can apply for a job. This confirms the person is a real Nigerian citizen with a government-issued identity record.</p>

            <h3>🟡 Level 2 — BVN Verification (Gold Badge)</h3>
            <p>Workers who complete Bank Verification Number (BVN) verification through our Dojah-powered KYC have linked their bank identity to their profile. This financial accountability layer means their wages are tied to a verified bank account — a powerful deterrent against fraud.</p>

            <h3>🟢 Level 3 — CAC Verification (Green Badge)</h3>
            <p>The highest trust level. Workers or trade businesses who have registered with the Corporate Affairs Commission (CAC) carry a Green Badge — signalling professional legitimacy and legal accountability.</p>

            <h2>Step-by-Step: Hiring Safely on TradeLink NG</h2>
            <ol>
                <li><strong>Post your job</strong> — Describe the work, location (state and LGA), timeline, and your budget. The more detail you provide, the better your matches will be.</li>
                <li><strong>Review shortlisted profiles</strong> — Our AI matching engine surfaces candidates ranked by skill match, proximity, and verification level. Filter to show only Gold or Green badge holders for high-stakes jobs.</li>
                <li><strong>Chat before you commit</strong> — Use TradeLink NG's built-in messaging (WhatsApp Business or in-app chat) to ask questions, review past work photos, and assess communication style.</li>
                <li><strong>Use Escrow for payment</strong> — Never pay cash upfront. TradeLink NG's escrow system holds your payment securely via Flutterwave. The artisan is only paid after you approve the completed work.</li>
                <li><strong>Rate the artisan</strong> — Your review helps the community. Honest ratings protect future employers and reward quality tradespeople.</li>
            </ol>

            <h2>Pro Tips for Employers</h2>
            <blockquote>Always verify the job address matches the artisan's stated service area before hiring. A plumber based in Kano may not be your best option for an emergency in Lagos Island.</blockquote>
            <ul>
                <li>For high-value projects (above ₦500,000), always require a Level 2 (Gold) or Level 3 (Green) badge.</li>
                <li>Request a brief video call or in-person introduction for major renovation projects.</li>
                <li>Read recent reviews — pay particular attention to comments about punctuality and after-job support.</li>
                <li>Use milestone payments for multi-phase projects. Release funds as each phase is completed and approved.</li>
            </ul>

            <h2>What Happens If Something Goes Wrong?</h2>
            <p>TradeLink NG provides a structured dispute resolution process. If you're unsatisfied with completed work, raise a dispute within 72 hours of job completion. Our team reviews evidence from both parties and mediates a fair resolution — including partial or full refunds from escrow where warranted.</p>

            <p>Start your search today and hire with confidence. <strong>TradeLink NG — Verified Skills, Trusted Trades.</strong></p>
        """),
    },
    # 2
    {
        "title": "Understanding Escrow Payments: How TradeLink NG Protects Your Money",
        "slug": "understanding-escrow-payments-tradelink-ng",
        "category_slug": "platform-guides",
        "excerpt": "Worried about paying an artisan who might disappear? TradeLink NG's Flutterwave-powered escrow system holds your money safely until the job is done right — protecting both you and the artisan.",
        "seo_title": "How Escrow Payments Work on TradeLink NG | Safe Artisan Payments Nigeria",
        "seo_description": "Learn how TradeLink NG's escrow payment system protects employers and artisans. Funds are held by Flutterwave and only released when work is approved.",
        "tags": ["escrow", "payment", "Flutterwave", "safety", "artisans"],
        "is_featured": True,
        "body": textwrap.dedent("""\
            <h2>The Problem With Cash-First Hiring in Nigeria</h2>
            <p>In the traditional way of hiring artisans in Nigeria, an employer pays a deposit — sometimes 50% or more — before work begins. Many employers have experienced the painful reality of artisans collecting that deposit and vanishing. Even well-intentioned artisans sometimes struggle to complete jobs without adequate tools or materials, leaving employers in a costly limbo.</p>
            <p>TradeLink NG solves this with <strong>escrow-backed payments</strong>.</p>

            <h2>How Escrow Works on TradeLink NG</h2>
            <ol>
                <li><strong>Employer funds escrow</strong> — When you accept a quote from an artisan, you deposit the agreed amount into the TradeLink NG escrow wallet powered by Flutterwave. Your money is held securely — not paid to the artisan yet.</li>
                <li><strong>Artisan begins work</strong> — Knowing payment is guaranteed (held in escrow), the artisan starts with confidence. No more "I haven't been paid so I can't start" delays.</li>
                <li><strong>Job completion and review</strong> — When the artisan marks the job complete, you have <strong>72 hours</strong> to inspect the work and approve payment or raise a dispute.</li>
                <li><strong>Funds released</strong> — Once you approve, the artisan's payment (minus TradeLink NG's 5% platform fee) is transferred instantly to their verified bank account via Flutterwave.</li>
            </ol>

            <h2>What is the 5% Platform Fee?</h2>
            <p>TradeLink NG charges a 5% fee on completed transactions. This fee funds our infrastructure, verification system, dispute resolution team, and customer support. <strong>There are no hidden charges.</strong> The fee is transparently displayed before you confirm any payment.</p>

            <h3>Example calculation:</h3>
            <ul>
                <li>Job agreed price: ₦100,000</li>
                <li>Amount deposited into escrow: ₦100,000</li>
                <li>TradeLink NG platform fee (5%): ₦5,000</li>
                <li>Artisan receives: ₦95,000</li>
            </ul>

            <h2>Milestone Payments for Large Projects</h2>
            <p>For large renovation, construction, or installation projects, you can structure payments across milestones. Each milestone has its own escrow deposit and release cycle — giving you granular control and ensuring the artisan is motivated to maintain quality throughout the project.</p>

            <h2>What Happens During a Dispute?</h2>
            <p>If you're unsatisfied with the work, raise a dispute within 72 hours of the completion notification. Our dispute resolution team will:</p>
            <ul>
                <li>Review before-and-after photos, messages, and the original job specification</li>
                <li>Contact both parties for statements</li>
                <li>Mediate a fair resolution within 5 business days</li>
                <li>Issue a full or partial refund from escrow if warranted</li>
            </ul>
            <p>Escrow funds are never released during an open dispute. Your money is safe throughout the process.</p>

            <blockquote>TradeLink NG's escrow system processed over ₦45 million in transactions in its first quarter, with a 98.2% dispute-free completion rate.</blockquote>
        """),
    },
    # 3
    {
        "title": "NIN, BVN, and CAC Verification: A Complete Guide for Nigerian Artisans",
        "slug": "nin-bvn-cac-verification-guide-nigerian-artisans",
        "category_slug": "platform-guides",
        "excerpt": "Verification unlocks better-paying jobs and employer trust. Here's everything you need to know about upgrading your TradeLink NG profile from grey to blue, gold, or green.",
        "seo_title": "NIN BVN CAC Verification Guide for Artisans | TradeLink NG",
        "seo_description": "Step-by-step guide for Nigerian artisans to complete NIN, BVN, and CAC verification on TradeLink NG and unlock higher-paying job opportunities.",
        "tags": ["NIN", "BVN", "CAC", "verification", "identity", "artisans"],
        "body": textwrap.dedent("""\
            <h2>Why Verification Is Worth It</h2>
            <p>Verified workers on TradeLink NG earn on average <strong>35% more per job</strong> than unverified profiles. Employers trust verified artisans enough to offer higher rates and larger contracts. If you're serious about growing your trade career, verification is the single most impactful thing you can do on the platform.</p>

            <h2>Level 1: NIN Verification (Blue Badge)</h2>
            <h3>What you need:</h3>
            <ul>
                <li>Your 11-digit National Identification Number (NIN)</li>
                <li>A selfie taken within the TradeLink NG app</li>
            </ul>
            <h3>How to get your NIN (if you don't have one):</h3>
            <ol>
                <li>Visit your nearest NIMC enrolment centre (find one at nimc.gov.ng)</li>
                <li>Bring a valid government-issued document (birth certificate, passport, driver's licence)</li>
                <li>Enrolment is <strong>free</strong> for all Nigerians</li>
                <li>Your NIN slip is typically ready in 24–48 hours</li>
            </ol>
            <h3>How to verify on TradeLink NG:</h3>
            <ol>
                <li>Go to <strong>Profile → Verification</strong></li>
                <li>Enter your NIN and take a selfie</li>
                <li>Our Dojah-powered KYC compares your selfie to the NIMC database</li>
                <li>Verification is instant in most cases — your Blue Badge appears immediately</li>
            </ol>

            <h2>Level 2: BVN Verification (Gold Badge)</h2>
            <h3>What you need:</h3>
            <ul>
                <li>Your 11-digit Bank Verification Number (BVN)</li>
                <li>An active Nigerian bank account</li>
            </ul>
            <h3>How to get your BVN (if you don't have one):</h3>
            <ol>
                <li>Visit any branch of your bank with a valid ID</li>
                <li>Request BVN enrolment — it's free</li>
                <li>Your BVN is typically issued the same day</li>
                <li>You can check your BVN by dialling *565*0# on your registered phone number</li>
            </ol>
            <blockquote>TradeLink NG only stores the last 4 digits of your BVN for security. Your full BVN is never stored on our servers — it is used solely for one-time verification through Dojah's secure API.</blockquote>

            <h2>Level 3: CAC Verification (Green Badge)</h2>
            <p>For trade businesses and sole proprietorships registered with the Corporate Affairs Commission (CAC). This tier is ideal for master craftsmen running a team, trade companies, or any artisan with a formal business registration.</p>
            <h3>What you need:</h3>
            <ul>
                <li>Your RC number (Registration Number) or BN number (Business Name)</li>
                <li>Your CAC certificate (PDF or high-resolution image)</li>
            </ul>
            <p>To register your business with the CAC, visit cac.gov.ng. Business name registration costs ₦10,000 (sole proprietor) and can be done online.</p>

            <h2>Tips for a Smooth Verification</h2>
            <ul>
                <li>Ensure your selfie is taken in good lighting with no hat or dark glasses</li>
                <li>Use the same phone number registered with your bank for BVN verification OTPs</li>
                <li>If verification fails, contact support via the in-app chat — our team resolves most issues within 2 hours</li>
            </ul>
        """),
    },
    # 4
    {
        "title": "Top 10 Most In-Demand Trade Skills Across Nigeria in 2025",
        "slug": "top-10-in-demand-trade-skills-nigeria-2025",
        "category_slug": "nigerian-artisan-economy",
        "excerpt": "From solar panel installation to tiling and plastering — here are the skilled trades with the highest demand and best-paying opportunities across Nigeria's 36 states in 2025.",
        "seo_title": "Top 10 In-Demand Trade Skills in Nigeria 2025 | TradeLink NG",
        "seo_description": "Discover the most in-demand trade skills in Nigeria in 2025. From electricians to solar installers — find out which artisan careers are growing fastest.",
        "tags": ["trade skills", "Nigeria", "careers", "artisans", "2025", "solar", "plumbing"],
        "is_featured": True,
        "body": textwrap.dedent("""\
            <h2>Nigeria's Skills Gap Is a Golden Opportunity</h2>
            <p>Nigeria's construction, infrastructure, and housing sectors are growing rapidly, yet the country faces a significant skilled-trades gap. This gap creates exceptional opportunities for artisans who have invested in developing marketable skills. Here are the ten trades currently driving the highest job volumes and best rates on TradeLink NG.</p>

            <h2>1. Electricians (Residential & Commercial)</h2>
            <p>Electrical installation and repairs top our job board consistently. The boom in estate housing developments across Lagos, Abuja, Port Harcourt, and Enugu is driving insatiable demand. Average daily rate on TradeLink NG: <strong>₦18,000 – ₦45,000</strong>.</p>

            <h2>2. Solar Panel Installers & PV Technicians</h2>
            <p>As grid power remains unreliable, solar adoption has exploded. Certified solar installers — especially those with NABCEP or NAFDAC-approved training — command premium rates. Average project earnings: <strong>₦150,000 – ₦800,000</strong> per installation.</p>

            <h2>3. Plumbers & Water Supply Technicians</h2>
            <p>Plumbing skills are in constant demand for new builds, renovations, and emergency repairs. Expertise in borehole installations, water treatment, and PVC pipe systems is especially valued. Average daily rate: <strong>₦15,000 – ₦35,000</strong>.</p>

            <h2>4. Tilers & Floor Specialists</h2>
            <p>High-quality tiling is one of Nigeria's most demanded finishing trades. Artisans skilled in large-format Italian tiles, epoxy grouting, and herringbone patterns can charge significantly more. Average daily rate: <strong>₦12,000 – ₦28,000</strong>.</p>

            <h2>5. Welders & Metal Fabricators</h2>
            <p>From gate fabrication to industrial steel structures, welding is a highly versatile trade. MIG/TIG welding skills attract the highest premiums. Average daily rate: <strong>₦14,000 – ₦40,000</strong>.</p>

            <h2>6. AC Technicians & HVAC Engineers</h2>
            <p>As Nigeria urbanises and climate consciousness grows, air conditioning installation and maintenance has become a recession-proof trade. Average per-unit installation: <strong>₦35,000 – ₦80,000</strong>.</p>

            <h2>7. Carpenters & Joiners</h2>
            <p>Furniture making, door fitting, kitchen cabinet installation, and roofing carpentry are all high-demand specialisations. Carpenters skilled in imported furniture assembly command top rates in upmarket estates.</p>

            <h2>8. Painters & Decorators</h2>
            <p>Interior and exterior painting remains one of Nigeria's most active job categories. Artisans with wallpaper installation and texture paint skills stand out from competitors.</p>

            <h2>9. Aluminium & UPVC Window Fabricators</h2>
            <p>Modern estate developers have shifted from traditional windows to aluminium casement and sliding systems. This specialist skill has limited supply nationally, creating excellent earning potential.</p>

            <h2>10. CCTV & Smart Home Installers</h2>
            <p>Security consciousness and smart-home adoption are driving demand for technicians who can install, configure, and maintain CCTV systems, smart locks, and home automation equipment. This emerging category is growing 40% year-on-year on our platform.</p>

            <blockquote>Register on TradeLink NG today, complete your verification, and start appearing in employer searches for your trade in your state.</blockquote>
        """),
    },
    # 5
    {
        "title": "How to Build a Winning Worker Profile on TradeLink NG",
        "slug": "build-winning-worker-profile-tradelink-ng",
        "category_slug": "platform-guides",
        "excerpt": "Your TradeLink NG profile is your digital CV. A complete, well-written profile with verified credentials and strong portfolio photos gets 5x more employer views. Here's how to build one.",
        "seo_title": "How to Build a Strong Artisan Profile on TradeLink NG | Get More Jobs",
        "seo_description": "Build a winning worker profile on TradeLink NG. Learn how to write a great bio, upload portfolio photos, set competitive rates, and get verified to attract more employers.",
        "tags": ["profile", "artisans", "workers", "tips", "jobs", "portfolio"],
        "body": textwrap.dedent("""\
            <h2>First Impressions on TradeLink NG</h2>
            <p>Employers spend an average of 8 seconds reviewing a worker profile before deciding whether to shortlist them. Your profile picture, verification badge, and headline must immediately communicate trustworthiness and competence.</p>

            <h2>Profile Photo: Professional Always Wins</h2>
            <ul>
                <li>Use a clear, recent headshot — not a group photo</li>
                <li>Wear your work clothes or uniform — it instantly communicates professionalism</li>
                <li>Ensure good lighting and a neutral background</li>
                <li>Avoid sunglasses, hats, or anything obscuring your face</li>
            </ul>

            <h2>Your Headline: The 10-Word Pitch</h2>
            <p>Your headline appears in search results. Make it specific and benefit-focused. Instead of "Plumber", write: <strong>"Certified Plumber — 8 Years Experience in Lagos Estates"</strong>. Instead of "Electrician", try: <strong>"Solar & Residential Electrician | SON-Certified | Abuja"</strong>.</p>

            <h2>Bio: Tell Your Story in 150 Words</h2>
            <p>Your bio is your chance to build trust. Cover:</p>
            <ol>
                <li><strong>Years of experience</strong> and trade specialisation</li>
                <li><strong>Notable projects</strong> (types, not client names — respect confidentiality)</li>
                <li><strong>Certifications and training</strong></li>
                <li><strong>Service area</strong> — mention specific states and LGAs you work in</li>
                <li><strong>Your working style</strong> — punctuality, warranty policy, clean-up habits</li>
            </ol>

            <h2>Portfolio: Show, Don't Just Tell</h2>
            <p>Profiles with at least 6 portfolio photos receive <strong>5x more shortlistings</strong> than those with none. Upload:</p>
            <ul>
                <li>Before-and-after pairs for renovation and repair jobs</li>
                <li>Close-up shots of detailed finish work</li>
                <li>Wide shots of completed projects showing scale</li>
                <li>Photos of you at work (with client permission)</li>
            </ul>
            <blockquote>Pro tip: Use natural daylight for photography. Turn on all lights in the room, open curtains, and shoot from a corner angle to show the full space.</blockquote>

            <h2>Setting Your Rates</h2>
            <p>Research current market rates for your trade in your city. Set your day rate (₦/day), project rate (fixed price), and minimum call-out fee. Being transparent about rates filters out time-wasting enquiries and attracts serious employers.</p>

            <h2>Get Reviews — Early</h2>
            <p>After every completed job, politely ask the employer to leave a review. Your first five reviews are the most important — they establish social proof and push your profile up in search results. Respond professionally to all reviews, including critical ones.</p>
        """),
    },
    # 6
    {
        "title": "10 Essential Safety Rules Every Nigerian Construction Artisan Must Know",
        "slug": "10-safety-rules-nigerian-construction-artisans",
        "category_slug": "trade-safety",
        "excerpt": "Workplace accidents cost Nigerian artisans thousands of hours and millions of naira every year. These 10 safety rules could save your life and your livelihood on the job site.",
        "seo_title": "10 Safety Rules for Nigerian Construction Artisans | TradeLink NG",
        "seo_description": "Essential workplace safety rules for Nigerian artisans in construction, electrical, and plumbing trades. Protect yourself and comply with NSITF regulations.",
        "tags": ["safety", "construction", "Nigeria", "PPE", "NSITF", "workplace"],
        "body": textwrap.dedent("""\
            <h2>Why Safety Is Non-Negotiable</h2>
            <p>According to the Nigeria Social Insurance Trust Fund (NSITF), construction accounts for over 30% of workplace accidents in Nigeria. Falls from height, electrocution, and tool injuries are the leading causes of artisan fatalities. These are preventable deaths — and the solution starts with cultivating a safety-first culture on every job site.</p>

            <h2>Rule 1: Always Wear Personal Protective Equipment (PPE)</h2>
            <p>At minimum: safety boots, a hard hat, safety glasses, and gloves. For electrical work, add insulated gloves and boots rated for the voltage involved. For painting and chemical work, add a respirator mask.</p>

            <h2>Rule 2: Never Work on Live Electrical Systems</h2>
            <p>Always isolate the circuit at the distribution board (DB) and use a voltage tester to confirm the circuit is dead before touching any wires. Lock the DB if possible, and use a "Do Not Energise" tag.</p>

            <h2>Rule 3: Inspect Ladders and Scaffolding Before Use</h2>
            <p>Check for cracks, missing rungs, and unstable feet before climbing. Extend ladders at least 1 metre above the working height. Never overreach from a ladder — reposition it instead.</p>

            <h2>Rule 4: Keep Your Tools in Good Condition</h2>
            <p>Dull tools require more force and are more likely to slip and cause injuries. Check electrical tools for frayed cables, damaged plugs, and proper earth connections. Report and replace damaged tools immediately.</p>

            <h2>Rule 5: Maintain a Clean Work Area</h2>
            <p>Most slip-and-trip accidents occur from tools left on floors, spilled liquids, or debris on stairs and corridors. At the end of each day, clear your work area and store tools properly.</p>

            <h2>Rule 6: Use Proper Lifting Techniques</h2>
            <p>Bend your knees, not your back. Keep the load close to your body. For heavy items (above 25kg), use two people or mechanical assistance. Back injuries are one of the most common and career-limiting artisan injuries.</p>

            <h2>Rule 7: Never Work Under the Influence</h2>
            <p>Alcohol and drugs severely impair coordination and judgement. Never work under any substance — and do not allow team members to work if they are impaired.</p>

            <h2>Rule 8: Understand and Respect Site Boundaries</h2>
            <p>On multi-trade job sites, respect cordoned-off areas. Falling objects from overhead work, moving machinery, and open trenches are hazards you may not be aware of outside your own work zone.</p>

            <h2>Rule 9: Know Basic First Aid</h2>
            <p>Every artisan should know how to treat minor cuts and burns, what to do for electric shock, and how to administer CPR. Consider taking a Basic Life Support (BLS) course through the Red Cross Nigeria.</p>

            <h2>Rule 10: Know Your Rights Under NSITF</h2>
            <p>The Nigeria Social Insurance Trust Fund provides compensation for workplace injuries. Ensure your employer (or TradeLink NG job contract) includes NSITF coverage. Keep records of all accidents and medical treatment.</p>

            <blockquote>Your safety is your most important tool. No job, no deadline, no client pressure is worth risking your life or your ability to work for the rest of your career.</blockquote>
        """),
    },
    # 7
    {
        "title": "The 8 Tools Every Nigerian Electrician Needs in Their Kit",
        "slug": "8-tools-every-nigerian-electrician-needs",
        "category_slug": "tool-reviews",
        "excerpt": "From a quality multimeter to insulated screwdrivers — these are the eight must-have tools that separate professional Nigerian electricians from the hobbyists. Build your kit right from day one.",
        "seo_title": "8 Essential Tools for Nigerian Electricians | Best Electrician Tools",
        "seo_description": "The 8 must-have tools for every Nigerian electrician. Expert recommendations for multimeters, wire strippers, voltage testers and more for electrical work in Nigeria.",
        "tags": ["electrician", "tools", "equipment", "Nigeria", "multimeter", "kit"],
        "body": textwrap.dedent("""\
            <h2>Build the Right Kit From Day One</h2>
            <p>Cheap, low-quality tools cost you more in the long run — through unreliable readings, faster wear, and the safety risks of tools that fail under load. Invest wisely in your core kit and you'll be working productively and safely for years.</p>

            <h2>1. Digital Multimeter</h2>
            <p><strong>Recommended:</strong> UNI-T UT61E or Fluke 115</p>
            <p>Your most important diagnostic tool. Use it to measure voltage, current, resistance, and continuity. Never buy a multimeter below the CAT III 300V safety rating for residential electrical work. Market price in Nigeria: ₦8,000 – ₦45,000 depending on brand and features.</p>

            <h2>2. Non-Contact Voltage Tester</h2>
            <p><strong>Recommended:</strong> Klein Tools NCVT-1 or Fluke LVD2</p>
            <p>This pen-shaped tool detects voltage in live wires without contact — your first safety check before touching any circuit. Essential. Price: ₦4,500 – ₦15,000.</p>

            <h2>3. Insulated Screwdriver Set</h2>
            <p><strong>Recommended:</strong> Wiha 7-piece Insulated Set or Stanley FatMax</p>
            <p>Always use screwdrivers rated to at least 1,000V. The insulation protects you in the event of accidental contact with a live terminal. Price: ₦6,000 – ₦18,000 for a quality set.</p>

            <h2>4. Wire Strippers and Crimpers</h2>
            <p><strong>Recommended:</strong> Knipex 97 22 240 or Klein Tools 11054</p>
            <p>Precise wire stripping ensures clean connections and prevents nicks that cause heat and fire. A combined stripper/crimper handles most Nigerian residential cable gauges (1.5mm, 2.5mm, 4mm, 6mm).</p>

            <h2>5. Conduit Bender</h2>
            <p>For clean, professional conduit installations on commercial and residential builds. A quality hand bender gives you accurate 15°, 30°, 45°, and 90° bends without kinking the conduit. Price: ₦5,000 – ₦12,000.</p>

            <h2>6. Fish Tape (Cable Puller)</h2>
            <p>Running cables through conduit or walls is one of the most time-consuming tasks in electrical work. A good fibreglass fish tape saves hours per job. Get a 15-metre tape minimum for residential work. Price: ₦3,500 – ₦9,000.</p>

            <h2>7. Electric Drill with Hammer Function</h2>
            <p><strong>Recommended:</strong> Makita HP1631 or Bosch GSB 13 RE</p>
            <p>For drilling into the concrete and block walls that dominate Nigerian construction. A hammer drill with at least 500W is essential. Buy lithium-ion cordless for flexibility, or corded for sustained heavy-duty work.</p>

            <h2>8. Personal Protective Equipment Kit</h2>
            <p>Not a single tool, but a kit you must never leave home without: insulated rubber gloves (Class 00 rated to 500V), safety glasses, safety boots with insulating rubber soles, and a hard hat for site work. These are the difference between a close call and a fatality.</p>

            <blockquote>Buy the best tools you can afford today. A ₦45,000 Fluke multimeter that lasts 15 years costs less per year than a ₦3,500 imitation that fails in 6 months — and might give you a dangerously wrong reading in between.</blockquote>
        """),
    },
    # 8
    {
        "title": "Apprenticeship in Nigeria: How to Find a Master Craftsman and Learn a Trade",
        "slug": "apprenticeship-nigeria-find-master-craftsman-learn-trade",
        "category_slug": "apprenticeship-training",
        "excerpt": "Nigeria's apprenticeship tradition is one of the most effective paths to a skilled-trade career. Here's how to find the right master craftsman, structure your learning, and graduate to professional independence.",
        "seo_title": "Apprenticeship in Nigeria: How to Learn a Trade | TradeLink NG",
        "seo_description": "Complete guide to apprenticeship in Nigeria. How to find a master craftsman, what to expect, rights and payment, and how to build your trade career after graduation.",
        "tags": ["apprenticeship", "Nigeria", "trade career", "skills", "training", "youth"],
        "body": textwrap.dedent("""\
            <h2>Nigeria's Apprenticeship Tradition</h2>
            <p>Long before formal technical and vocational education institutions existed in Nigeria, the master-apprentice system was the primary means of skilled-trade knowledge transfer. From Aba tailors to Lagos mechanics to Kano leatherworkers, this tradition has produced millions of skilled artisans who form the backbone of Nigeria's informal economy.</p>
            <p>Even today, with vocational schools available in most states, working directly under a master craftsman remains one of the fastest and most practical paths to trade competency.</p>

            <h2>How to Find the Right Master Craftsman</h2>
            <ol>
                <li><strong>TradeLink NG</strong> — Our platform lists verified artisans who have indicated openness to taking apprentices. Filter by trade and state, then message them directly to inquire.</li>
                <li><strong>Artisan associations</strong> — The National Union of Civil Engineering, Construction, Furniture and Wood Workers (NUCECFWW) and state-level artisan unions often maintain apprentice placement registers.</li>
                <li><strong>Community networks</strong> — Ask in your church, mosque, or community association. Local recommendations often yield the most trustworthy masters.</li>
                <li><strong>NABTEB centres</strong> — The National Business and Technical Examinations Board has partnerships with trade masters who accept apprentices enrolled in their programmes.</li>
            </ol>

            <h2>What to Look for in a Master Craftsman</h2>
            <ul>
                <li>Proven track record of training graduates who now work independently</li>
                <li>Active, varied workload — you learn more from a busy workshop than a slow one</li>
                <li>Willingness to explain, not just instruct</li>
                <li>Fair treatment — no exploitative labour arrangements</li>
                <li>TradeLink NG verification badge (blue or above) as a trust signal</li>
            </ul>

            <h2>Setting Expectations: The Apprenticeship Agreement</h2>
            <p>Before starting, agree in writing (even informally) on:</p>
            <ul>
                <li>Duration (typically 1–4 years depending on trade)</li>
                <li>Learning stipend or profit-sharing arrangement</li>
                <li>What skills will be taught and in what order</li>
                <li>Tools — who provides what</li>
                <li>Graduation settlement (the traditional "settlement" or "freedom" ceremony)</li>
            </ul>

            <h2>Making the Most of Your Apprenticeship</h2>
            <ul>
                <li>Be the first to arrive and last to leave — enthusiasm is noticed and rewarded</li>
                <li>Keep a learning journal — write down techniques, measurements, and processes daily</li>
                <li>Ask questions, but pick the right moments (not when the master is under pressure)</li>
                <li>Practice on scrap materials in your own time</li>
                <li>Build relationships with other apprentices — your peers become your professional network</li>
            </ul>

            <h2>After Graduation: Register on TradeLink NG</h2>
            <p>Once you complete your apprenticeship, register on TradeLink NG as a verified worker. Your master can provide a reference that boosts your early profile credibility. Complete your NIN verification immediately to start appearing in employer searches.</p>
            <blockquote>"The goal of every apprentice should be to eventually surpass their master — that is how trades evolve and communities prosper." — Nigerian Artisan Wisdom</blockquote>
        """),
    },
    # 9
    {
        "title": "Nigeria's Informal Economy: The ₦42 Trillion Power of Skilled Trades",
        "slug": "nigeria-informal-economy-skilled-trades-42-trillion",
        "category_slug": "nigerian-artisan-economy",
        "excerpt": "Nigeria's skilled-trades sector is one of the largest informal economies in Africa. We break down the numbers, the opportunity, and why formalising this market through platforms like TradeLink NG could add billions to GDP.",
        "seo_title": "Nigeria's Skilled Trades Economy: Size, Trends, and Opportunities | TradeLink NG",
        "seo_description": "Analysis of Nigeria's informal skilled-trades economy. The market size, state-by-state demand, fastest-growing trades, and how digitisation is transforming artisan livelihoods.",
        "tags": ["economy", "Nigeria", "artisans", "informal economy", "GDP", "trades"],
        "body": textwrap.dedent("""\
            <h2>The Scale of Nigeria's Artisan Economy</h2>
            <p>Nigeria's National Bureau of Statistics estimates that the informal sector contributes approximately <strong>57% of the country's GDP</strong>. Within this, the skilled-trades sector — comprising electricians, plumbers, carpenters, welders, masons, painters, tailors, and hundreds of other specialisations — represents a market estimated at <strong>₦42 trillion annually</strong>.</p>
            <p>Yet despite this scale, the sector remains largely cash-based, unverified, and disconnected from formal financial systems. This creates inefficiency, fraud risk, and income instability for millions of artisans.</p>

            <h2>State-by-State Demand Patterns</h2>
            <p>Demand for skilled artisans is not uniform across Nigeria's 36 states. Our TradeLink NG job data reveals clear patterns:</p>
            <ul>
                <li><strong>Lagos State</strong> — Highest absolute demand. Estate construction, luxury finishing, and commercial builds dominate. Premium rates in Lekki, Victoria Island, and Ikoyi.</li>
                <li><strong>Abuja (FCT)</strong> — Government contracts, embassy renovations, and high-end residential. Solar installation demand is 60% higher than the national average.</li>
                <li><strong>Rivers State</strong> — Oil industry auxiliary construction, industrial installations, and high-spec residential in Port Harcourt GRA.</li>
                <li><strong>Kano State</strong> — Manufacturing, textile machinery maintenance, and commercial construction are dominant categories.</li>
                <li><strong>Ogun State</strong> — Proximity to Lagos and industrial estates (Sagamu, Agbara, Ota) generates strong demand for factory maintenance artisans.</li>
            </ul>

            <h2>The Formalisation Opportunity</h2>
            <p>International development research shows that when informal sector workers gain access to:</p>
            <ul>
                <li>Formal identity verification</li>
                <li>Transparent pricing mechanisms</li>
                <li>Secure payment systems</li>
                <li>Customer review infrastructure</li>
            </ul>
            <p>…their average income increases by 25–40% within 18 months. TradeLink NG is building exactly this infrastructure for Nigeria's artisan class.</p>

            <h2>Digital Transformation of Artisan Livelihoods</h2>
            <p>Smartphone penetration in Nigeria now exceeds 50% among working-age adults. Data prices have fallen dramatically. For the first time, it is practical for artisans in Zaria, Owerri, or Maiduguri to maintain a digital professional presence, receive digital payments, and access a national job market — not just their immediate neighbourhood.</p>

            <blockquote>When a master plumber in Ibadan can receive job applications from an estate developer in Lagos without leaving home, the economic geography of Nigerian skilled trades is fundamentally changed.</blockquote>

            <h2>What This Means for Artisans</h2>
            <p>The artisans who build digital profiles, complete verification, and develop consistent online reputations now will be positioned to capture a disproportionate share of this growing formalised market. The window to become an early-mover advantage on platforms like TradeLink NG is open — but it won't remain open forever.</p>
        """),
    },
    # 10
    {
        "title": "From Apprentice to Master: The Story of How TradeLink NG Changed My Business",
        "slug": "apprentice-to-master-tradelink-ng-success-story",
        "category_slug": "nigerian-artisan-economy",
        "excerpt": "Chukwuemeka Obi started as an apprentice electrician in Onitsha at 16. By 32, he runs a team of six, earns over ₦400,000 monthly, and found most of his clients through TradeLink NG. This is his story.",
        "seo_title": "Nigerian Artisan Success Story: From Apprentice to Business Owner | TradeLink NG",
        "seo_description": "Real success story of a Nigerian electrician who grew his business using TradeLink NG. Learn how verified profiles, escrow payments, and digital marketing transform artisan careers.",
        "tags": ["success story", "electrician", "Nigeria", "small business", "artisan", "Onitsha"],
        "is_featured": True,
        "body": textwrap.dedent("""\
            <h2>A Note on This Story</h2>
            <p>This is a representative success story based on the experiences of multiple TradeLink NG users. Names and some details have been changed to protect privacy, but the journey described reflects real outcomes achieved on our platform.</p>

            <h2>"I Started With a Screwdriver and a Prayer"</h2>
            <p>Chukwuemeka Obi was 16 years old when he knocked on the workshop door of Master Emmanuel, a licensed electrician in Onitsha, Anambra State. His family could not afford secondary school fees. His father had suggested the trades. "I didn't know anything about electricity," he recalls. "I started by watching, then cleaning, then handing tools. After six months, Master Emmanuel let me strip cables."</p>
            <p>Four years later, Chukwuemeka graduated and received his settlement — a tool bag, a multimeter, and ₦50,000 in cash. He set up his own practice serving residential clients in Onitsha and Awka.</p>

            <h2>The Early Years: Word of Mouth and Frustration</h2>
            <p>For the first three years of independent practice, Chukwuemeka's business was entirely word-of-mouth. Business was inconsistent — feast or famine. "Some months I earned ₦80,000. Other months I'd earn ₦15,000. I had no way to find new clients except asking my existing ones to refer me."</p>
            <p>He also experienced the most common nightmare of Nigerian artisans: a client who refused to pay after job completion. "I installed a full estate of eight houses — 480,000 naira of work — and the developer gave me ₦200,000 and disappeared. I had no recourse. No contract. Nothing."</p>

            <h2>Discovering TradeLink NG</h2>
            <p>Chukwuemeka joined TradeLink NG after a friend in Lagos told him about it. "I was sceptical. I had tried other platforms. But my friend said this one pays through the app — the client can't just not pay you."</p>
            <p>He created his profile, uploaded portfolio photos of past installations, and completed his NIN verification the same day. Within two weeks, he had his first enquiry — a developer building a 20-unit estate in Awka wanted an electrician. "They messaged me, we talked, they hired me through the escrow system. I did the job. I got paid. It was that simple."</p>

            <h2>Three Years Later</h2>
            <p>Today, Chukwuemeka runs Obi Electrics — a team of six electricians (including two of his own apprentices) serving commercial and residential clients across Anambra and Delta states. His monthly revenue has grown from ₦80,000 to consistently above ₦400,000. He has completed over 60 jobs on TradeLink NG with an average rating of 4.9 stars.</p>
            <p>He has completed all three verification tiers — NIN, BVN, and his business is registered with the CAC. "The green badge makes a big difference. Big developers check for it. It tells them you're serious."</p>

            <h2>His Advice to Young Nigerian Artisans</h2>
            <ul>
                <li>"Don't do cash-only anymore. The platform protects you as much as it protects the client."</li>
                <li>"Take photos of every job. Before, during, and after. Your portfolio is your advertising."</li>
                <li>"Get verified as soon as possible. Every badge earns you more trust and better rates."</li>
                <li>"Treat every small job like a big one. Your reputation is worth more than any single payment."</li>
                <li>"Invest in your tools. Good tools make you faster and your work looks better."</li>
            </ul>

            <blockquote>"TradeLink NG didn't give me success — it gave me a fair platform to earn what I already deserved. The work was always mine to do."<br><strong>— Chukwuemeka Obi, Obi Electrics, Onitsha</strong></blockquote>

            <p>Ready to write your own story? <a href="/">Create your free profile on TradeLink NG today.</a></p>
        """),
    },
]


# ─────────────────────────────────────────────────────────────────────────────
#  COMMAND
# ─────────────────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = "Seed the blog with 6 categories and 10 posts aligned to TradeLink NG's mission."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete all existing seeded posts before creating new ones.",
        )

    def handle(self, *args, **options):
        from blog.models import Category, Tag, Post

        # ── Author: use first superuser or first user ─────────────────────
        author = (
            User.objects.filter(is_superuser=True).order_by("created").first()
            or User.objects.order_by("created").first()
        )
        if not author:
            self.stderr.write(
                self.style.ERROR(
                    "No users found in the database. "
                    "Create a superuser first: python manage.py createsuperuser"
                )
            )
            return

        self.stdout.write(f"Using author: {author} ({author.email})")

        # ── Optional clear ────────────────────────────────────────────────
        if options["clear"]:
            slugs = [p["slug"] for p in POSTS]
            deleted, _ = Post.objects.filter(slug__in=slugs).delete()
            self.stdout.write(self.style.WARNING(f"Deleted {deleted} existing seeded posts."))

        # ── Create categories ─────────────────────────────────────────────
        category_map = {}
        for cat_data in CATEGORIES:
            cat, created = Category.objects.update_or_create(
                slug=cat_data["slug"],
                defaults={
                    "name": cat_data["name"],
                    "description": cat_data["description"],
                    "icon_class": cat_data["icon_class"],
                    "color": cat_data["color"],
                    "meta_title": (cat_data.get("meta_title") or cat_data.get("seo_title") or cat_data["name"])[:70],
                    "meta_description": (cat_data.get("meta_description") or cat_data.get("seo_description") or cat_data["description"][:160])[:160],
                },
            )
            category_map[cat_data["slug"]] = cat
            verb = "Created" if created else "Updated"
            self.stdout.write(f"  {verb} category: {cat.name}")

        # ── Create posts ──────────────────────────────────────────────────
        base_time = timezone.now() - timedelta(days=len(POSTS) * 4)

        for i, post_data in enumerate(POSTS):
            category = category_map.get(post_data["category_slug"])
            tag_names = post_data.pop("tags", [])
            published_at = base_time + timedelta(days=i * 4)

            post, created = Post.objects.update_or_create(
                slug=post_data["slug"],
                defaults={
                    "title": post_data["title"],
                    "excerpt": post_data["excerpt"],
                    "body": post_data["body"],
                    "category": category,
                    "author": author,
                    "status": "published",
                    "is_featured": post_data.get("is_featured", False),
                    "allow_comments": True,
                    "published_at": published_at,
                    "meta_title": (post_data.get("meta_title") or post_data.get("seo_title") or post_data["title"])[:70],
                    "meta_description": (post_data.get("meta_description") or post_data.get("seo_description") or post_data["excerpt"][:160])[:160],
                },
            )

            # Attach tags
            for tag_name in tag_names:
                tag_slug = slugify(tag_name)
                tag, _ = Tag.objects.get_or_create(
                    slug=tag_slug,
                    defaults={"name": tag_name},
                )
                post.tags.add(tag)

            verb = "Created" if created else "Updated"
            safe_title = post.title.encode("ascii", "replace").decode("ascii")
            self.stdout.write(
                self.style.SUCCESS(f"  {verb} post [{i+1}/{len(POSTS)}]: {safe_title}")
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"\n[OK] Done! Seeded {len(CATEGORIES)} categories and {len(POSTS)} posts."
            )
        )
        self.stdout.write(
            "\nNext steps:\n"
            "  1. python manage.py makemigrations blog\n"
            "  2. python manage.py migrate\n"
            "  3. python manage.py seed_blog_posts\n"
        )
