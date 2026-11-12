import os
import sys
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_header_footer(num_pages)
            super().showPage()
        super().save()

    def draw_header_footer(self, page_count):
        if self._pageNumber == 1:
            # Skip cover page header/footer
            return
        self.saveState()
        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(colors.HexColor("#92400E"))
        self.drawString(54, 752, "TRADELINK NG")
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#6B7280"))
        self.drawString(125, 752, "— TECHNICAL SUPPORTING EVIDENCE & ARCHITECTURE SPECIFICATION")
        
        self.setStrokeColor(colors.HexColor("#E5E7EB"))
        self.setLineWidth(0.75)
        self.line(54, 744, 558, 744)
        
        # Footer
        self.line(54, 45, 558, 45)
        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(558, 32, page_str)
        self.drawString(54, 32, "TradeLink Technologies NG | Confidential — Grant Evaluation Document")
        self.restoreState()

def build_pdf(filename="TradeLink_NG_Supporting_Evidence.pdf"):
    doc = SimpleDocTemplate(
        filename,
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54
    )

    styles = getSampleStyleSheet()

    # Custom styles
    c_primary = colors.HexColor("#B45309")    # Deep Amber
    c_dark = colors.HexColor("#111827")       # Slate 900
    c_muted = colors.HexColor("#4B5563")      # Gray 600
    c_border = colors.HexColor("#E5E7EB")     # Gray 200
    c_bg_light = colors.HexColor("#F9FAFB")   # Gray 50
    c_emerald = colors.HexColor("#059669")    # Emerald 600
    c_sky = colors.HexColor("#0284C7")        # Sky 600

    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=26,
        leading=32,
        textColor=c_dark,
        spaceAfter=6
    )

    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=12,
        leading=17,
        textColor=c_primary,
        spaceAfter=15
    )

    h1_style = ParagraphStyle(
        'SectionH1',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=18,
        textColor=c_dark,
        spaceBefore=12,
        spaceAfter=8
    )

    h2_style = ParagraphStyle(
        'SectionH2',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=15,
        textColor=c_primary,
        spaceBefore=8,
        spaceAfter=4
    )

    body_style = ParagraphStyle(
        'BodyDark',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=14,
        textColor=c_dark,
        spaceAfter=8
    )

    bullet_style = ParagraphStyle(
        'BulletText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13.5,
        textColor=c_dark,
        leftIndent=12,
        firstLineIndent=-8,
        spaceAfter=4
    )

    badge_blue = ParagraphStyle('BadgeBlue', fontName='Helvetica-Bold', fontSize=8, leading=10, textColor=c_sky)
    badge_gold = ParagraphStyle('BadgeGold', fontName='Helvetica-Bold', fontSize=8, leading=10, textColor=c_primary)
    badge_green = ParagraphStyle('BadgeGreen', fontName='Helvetica-Bold', fontSize=8, leading=10, textColor=c_emerald)

    table_header = ParagraphStyle('TH', fontName='Helvetica-Bold', fontSize=8.5, leading=11, textColor=colors.white)
    table_cell = ParagraphStyle('TC', fontName='Helvetica', fontSize=8.5, leading=11.5, textColor=c_dark)
    table_cell_bold = ParagraphStyle('TCB', fontName='Helvetica-Bold', fontSize=8.5, leading=11.5, textColor=c_dark)

    story = []

    # =========================================================================
    # COVER / TITLE BLOCK
    # =========================================================================
    story.append(Spacer(1, 20))
    story.append(Paragraph("TradeLink NG", title_style))
    story.append(Paragraph(
        "Digital Trust Infrastructure, AI Discovery & Milestone Escrow for Nigeria's Skilled Informal Economy",
        subtitle_style
    ))
    story.append(HRFlowable(width="100%", thickness=2, color=c_primary, spaceBefore=0, spaceAfter=15))

    # Meta Overview Box
    meta_data = [
        [
            Paragraph("<b>Solution Name:</b> TradeLink NG", table_cell),
            Paragraph("<b>Target Geopolitical Zone:</b> South-West / Nationwide (36 States + FCT)", table_cell)
        ],
        [
            Paragraph("<b>Sector:</b> Economic Empowerment & Digital Economy", table_cell),
            Paragraph("<b>Current Stage:</b> Functional MVP / Deployed Production Architecture", table_cell)
        ],
        [
            Paragraph("<b>Core Innovations:</b> 3-Tier Verification, Escrow, AI Matching, WhatsApp Bot", table_cell),
            Paragraph("<b>Codebase Volume:</b> 213 Python Modules · 58,950+ Lines of Code", table_cell)
        ]
    ]
    t_meta = Table(meta_data, colWidths=[245, 259])
    t_meta.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), c_bg_light),
        ('BOX', (0,0), (-1,-1), 1, c_border),
        ('INNERGRID', (0,0), (-1,-1), 0.5, c_border),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
    ]))
    story.append(t_meta)
    story.append(Spacer(1, 14))

    # =========================================================================
    # SECTION 1: EXECUTIVE TECHNICAL SUMMARY
    # =========================================================================
    story.append(Paragraph("1. Executive Technical Summary & Problem Statement", h1_style))
    story.append(Paragraph(
        "Over 80% of Nigeria's employment is generated within the informal economy (NBS/ILO data). "
        "However, millions of skilled artisans (electricians, plumbers, solar installers, welders, masons) "
        "suffer from severe economic invisibility, lack of verifiable qualifications, and persistent payment "
        "default risks. Conversely, property owners, corporate site supervisors, and facility managers face "
        "unvetted technical quacks, property damage, and abandoned projects.",
        body_style
    ))
    story.append(Paragraph(
        "<b>TradeLink NG solves this systemic trust deficit</b> by providing a battle-tested, end-to-end "
        "digital framework combining: (1) <b>NIN-backed multi-tier credential verification</b>, "
        "(2) <b>milestone-locked financial escrow</b>, (3) <b>AI-powered semantic and visual portfolio matching</b>, "
        "and (4) an <b>omnichannel WhatsApp Business gateway</b> designed for low-bandwidth informal workers.",
        body_style
    ))
    story.append(Spacer(1, 8))

    # =========================================================================
    # SECTION 2: HIGH-LEVEL ARCHITECTURE & COMPONENT STACK
    # =========================================================================
    story.append(Paragraph("2. System Architecture & Technical Stack", h1_style))
    story.append(Paragraph(
        "The TradeLink NG platform is engineered with a modular, enterprise-grade Django 5 ASGI architecture "
        "running asynchronous task workers, embedded vector embedding models, and multi-provider webhooks:",
        body_style
    ))

    arch_data = [
        [Paragraph("Architectural Tier", table_header), Paragraph("Technology Stack", table_header), Paragraph("Functional Responsibilities", table_header)],
        [
            Paragraph("<b>Presentation & Omnichannel</b>", table_cell_bold),
            Paragraph("• Responsive HTML5 / CSS3 / Vanilla JS<br/>• Meta WhatsApp Cloud API<br/>• Twilio Programmable Messaging", table_cell),
            Paragraph("Dual web and chat interfaces. Allows low-data artisans to receive leads and bid via WhatsApp while employers manage projects on the responsive web portal.", table_cell)
        ],
        [
            Paragraph("<b>Application & Async Core</b>", table_cell_bold),
            Paragraph("• Django 5.x Framework<br/>• ASGI Daphne Server<br/>• Django Channels (WebSockets)", table_cell),
            Paragraph("Handles authentication, role-based access control (Employer, Worker, Admin), live messaging/chats, state transitions for milestones, and escrow management.", table_cell)
        ],
        [
            Paragraph("<b>AI & Semantic Matching</b>", table_cell_bold),
            Paragraph("• FastEmbed (BAAI/bge-base-en-v1.5)<br/>• ONNX Runtime (Build-time cached)<br/>• OpenAI CLIP ViT-B/32 Embeddings", table_cell),
            Paragraph("Computes 768-dim semantic vectors for job descriptions vs. artisan profiles, and visual image vectors for portfolio work verification without expensive GPU overhead.", table_cell)
        ],
        [
            Paragraph("<b>Data & Storage Tier</b>", table_cell_bold),
            Paragraph("• PostgreSQL Database<br/>• Redis & Celery Workers<br/>• Cloudinary / Media Fallback", table_cell),
            Paragraph("Relational integrity for escrow contracts and user records; Redis for asynchronous WhatsApp dispatch and notifications; encrypted media storage.", table_cell)
        ],
        [
            Paragraph("<b>Financial & Escrow Layer</b>", table_cell_bold),
            Paragraph("• Flutterwave API v3<br/>• Webhook Signature Verifier<br/>• Virtual Bank Accounts", table_cell),
            Paragraph("Processes milestone escrow deposits, handles virtual accounts for seamless transfers, and executes programmatic payouts upon milestone inspection.", table_cell)
        ]
    ]

    t_arch = Table(arch_data, colWidths=[110, 160, 234])
    t_arch.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), c_dark),
        ('GRID', (0,0), (-1,-1), 0.5, c_border),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, c_bg_light]),
    ]))
    story.append(t_arch)
    story.append(Spacer(1, 14))

    # =========================================================================
    # SECTION 3: CORE TECHNICAL INNOVATIONS
    # =========================================================================
    story.append(PageBreak())  # Page 2

    story.append(Paragraph("3. Core Technical Modules & Workflows", h1_style))

    # Pillar A: 3-Tier Verification
    story.append(Paragraph("Pillar A: Multi-Tier Verification System (Trust Badges)", h2_style))
    story.append(Paragraph(
        "To dismantle identity fraud and incompetent workmanship, TradeLink NG operates a 3-tier progressive "
        "verification system, granting distinct cryptographic and visual badges on artisan profiles:",
        body_style
    ))

    badge_data = [
        [Paragraph("Tier Level", table_header), Paragraph("Requirements & Verification Source", table_header), Paragraph("Rights & Project Scope", table_header)],
        [
            Paragraph("<b>BLUE BADGE</b><br/>Level 1: Identity", badge_blue),
            Paragraph("• Verified National Identification Number (NIN)<br/>• Phone number OTP confirmation<br/>• Live selfie face match", table_cell),
            Paragraph("Eligible for residential maintenance tasks, neighborhood repairs, and standard marketplace listings.", table_cell)
        ],
        [
            Paragraph("<b>GOLD BADGE</b><br/>Level 2: Certified Trade", badge_gold),
            Paragraph("• Blue Badge requirements +<br/>• Trade certification (NABTEB, City & Guilds)<br/>• Apprenticeship documentation & vetting", table_cell),
            Paragraph("Qualified for commercial projects, specialized installations (solar, HVAC, industrial wiring), and preferred recommendation ranking.", table_cell)
        ],
        [
            Paragraph("<b>GREEN BADGE</b><br/>Level 3: Corporate Entity", badge_green),
            Paragraph("• Gold Badge requirements +<br/>• Corporate Affairs Commission (CAC) certificate<br/>• Tax Identification Number (TIN)", table_cell),
            Paragraph("Authorized to bid on large-scale enterprise construction tenders, government subcontracts, and multi-million naira projects.", table_cell)
        ]
    ]
    t_badge = Table(badge_data, colWidths=[110, 190, 204])
    t_badge.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), c_dark),
        ('GRID', (0,0), (-1,-1), 0.5, c_border),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, c_bg_light]),
    ]))
    story.append(t_badge)
    story.append(Spacer(1, 10))

    # Pillar B: Milestone Escrow Flow
    story.append(Paragraph("Pillar B: Milestone Escrow & Dispute Resolution State Machine", h2_style))
    story.append(Paragraph(
        "Our milestone payment engine eliminates 'payment anxiety' for artisans and 'abandonment anxiety' for clients. "
        "Work is governed by a strict state-machine flow:",
        body_style
    ))

    escrow_steps = [
        [
            Paragraph("<b>Step 1: Job Milestone Creation</b>", table_cell_bold),
            Paragraph("Employer posts project and subdivides compensation into inspectable milestones (e.g. 30% Foundation, 40% Roofing, 30% Finishing).", table_cell)
        ],
        [
            Paragraph("<b>Step 2: Upfront Escrow Deposit</b>", table_cell_bold),
            Paragraph("Employer deposits milestone funds into TradeLink's secure escrow vault via bank transfer or card. Funds are locked.", table_cell)
        ],
        [
            Paragraph("<b>Step 3: Work Execution & Alert</b>", table_cell_bold),
            Paragraph("Artisan receives instant automated notification that funds are secured and commences work with guaranteed payout backing.", table_cell)
        ],
        [
            Paragraph("<b>Step 4: On-Site Inspection & Release</b>", table_cell_bold),
            Paragraph("Client inspects completed milestone on-site. Upon client approval, funds are disbursed directly to artisan's Nigerian bank account within seconds.", table_cell)
        ],
        [
            Paragraph("<b>Step 5: Dispute Mediation Vault</b>", table_cell_bold),
            Paragraph("If specifications are breached, either party can trigger mediation. Milestone remains frozen while human trade arbiters review evidence and resolve payouts.", table_cell)
        ]
    ]
    t_escrow = Table(escrow_steps, colWidths=[140, 364])
    t_escrow.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 1, c_border),
        ('INNERGRID', (0,0), (-1,-1), 0.5, c_border),
        ('BACKGROUND', (0,0), (0,-1), c_bg_light),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(t_escrow)
    story.append(Spacer(1, 10))

    # Pillar C: WhatsApp Gateway
    story.append(Paragraph("Pillar C: Omnichannel Conversational Access (WhatsApp Business Gateway)", h2_style))
    story.append(Paragraph(
        "To ensure complete accessibility for artisans without high-end smartphones or constant web data, "
        "TradeLink NG integrates directly with the <b>Meta WhatsApp Business Cloud API</b> and <b>Twilio Webhooks</b> "
        "(implemented in <code>bot/views.py</code> and <code>bot/handlers.py</code>):",
        body_style
    ))
    story.append(Paragraph("• <b>Instant Job Broadcasts:</b> Verified technicians receive localized job alerts matching their trade and LGA directly in WhatsApp.", bullet_style))
    story.append(Paragraph("• <b>Conversational Bidding:</b> Artisans can reply with their quote and proposed timeframe without leaving the chat app.", bullet_style))
    story.append(Paragraph("• <b>SMS Fallback:</b> In rural or low-bandwidth zones, SMS gateways ensure project status and escrow release alerts are delivered reliably.", bullet_style))
    story.append(Spacer(1, 10))

    # =========================================================================
    # SECTION 4: CODEBASE EVIDENCE & PRODUCTION READINESS
    # =========================================================================
    story.append(PageBreak())  # Page 3

    story.append(Paragraph("4. Technical Evidence & Codebase Verification", h1_style))
    story.append(Paragraph(
        "TradeLink NG is not an unproven concept. The solution is backed by an extensive, battle-tested codebase "
        "comprising 10 custom Django applications and production infrastructure:",
        body_style
    ))

    module_data = [
        [Paragraph("Django Application", table_header), Paragraph("Lines of Code", table_header), Paragraph("Key Implemented Features & Technical Capabilities", table_header)],
        [
            Paragraph("<code>marketplace</code>", table_cell_bold),
            Paragraph("~18,500 lines", table_cell),
            Paragraph("Multi-vendor trade tools marketplace, category taxonomy, Jumia/Etsy Apify catalog scrapers, real-time product search, order management, and dispute workflows.", table_cell)
        ],
        [
            Paragraph("<code>jobs</code> & <code>hiring</code>", table_cell_bold),
            Paragraph("~14,200 lines", table_cell),
            Paragraph("Dynamic job milestone architecture, worker profile generator, portfolio showcase with CLIP vector embeddings, bid evaluation engine, contract generator.", table_cell)
        ],
        [
            Paragraph("<code>bot</code>", table_cell_bold),
            Paragraph("~6,500 lines", table_cell),
            Paragraph("WhatsApp Cloud API webhook handler, Twilio router, stateful session dispatcher (<code>WhatsAppSession</code>), conversational bidding, lead alerts.", table_cell)
        ],
        [
            Paragraph("<code>verification</code>", table_cell_bold),
            Paragraph("~4,200 lines", table_cell),
            Paragraph("3-tier verification pipeline, NIN cryptographic matching, document uploads, vetting console, badge rendering.", table_cell)
        ],
        [
            Paragraph("<code>chats</code>", table_cell_bold),
            Paragraph("~3,800 lines", table_cell),
            Paragraph("Real-time messaging via WebSockets (Django Channels / ASGI Daphne), attachment handling, instant notifications.", table_cell)
        ],
        [
            Paragraph("<code>core</code> & <code>users</code>", table_cell_bold),
            Paragraph("~11,750 lines", table_cell),
            Paragraph("Custom User model, RBAC middleware, global rate-limiting, error logging, FastEmbed model caching, landing and legal pages.", table_cell)
        ],
        [
            Paragraph("<b>TOTALS</b>", table_cell_bold),
            Paragraph("<b>58,950+ lines</b>", table_cell_bold),
            Paragraph("<b>213 Python source modules, 10 custom apps, fully containerized on Railway Nixpacks.</b>", table_cell_bold)
        ]
    ]

    t_modules = Table(module_data, colWidths=[100, 74, 330])
    t_modules.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), c_dark),
        ('GRID', (0,0), (-1,-1), 0.5, c_border),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ('ROWBACKGROUNDS', (0,1), (-1,-2), [colors.white, c_bg_light]),
        ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor("#FEF3C7")),
    ]))
    story.append(t_modules)
    story.append(Spacer(1, 14))

    # =========================================================================
    # SECTION 5: SECURITY, PRIVACY & NDPA COMPLIANCE
    # =========================================================================
    story.append(Paragraph("5. Security, Data Privacy & NDPA Compliance Architecture", h1_style))
    story.append(Paragraph(
        "TradeLink NG enforces enterprise-grade security protocols compliant with the <b>Nigeria Data Protection Act (NDPA)</b> "
        "and international privacy standards:",
        body_style
    ))

    sec_points = [
        [
            Paragraph("<b>Encryption Everywhere</b>", table_cell_bold),
            Paragraph("Enforced TLS 1.3 across all HTTP endpoints and webhook consumers. Relational data and documents encrypted at rest using AES-256; passwords hashed via salted PBKDF2/Argon2.", table_cell)
        ],
        [
            Paragraph("<b>Zero Card Storage</b>", table_cell_bold),
            Paragraph("No debit card numbers, CVVs, or bank account PINs touch TradeLink servers. All payment flows are tokenized via licensed, PCI-DSS Level 1 compliant gateway partners (Flutterwave).", table_cell)
        ],
        [
            Paragraph("<b>Role-Based Access (RBAC)</b>", table_cell_bold),
            Paragraph("Strict data segregation. Public clients only see validated badges and aggregate reviews. Private identification (NIN, CAC documents) is strictly restricted to vetted compliance staff.", table_cell)
        ],
        [
            Paragraph("<b>Testing Isolation</b>", table_cell_bold),
            Paragraph("Development and staging environments are logically and physically isolated from production. All testing and model validation utilizes anonymized synthetic datasets.", table_cell)
        ]
    ]
    t_sec = Table(sec_points, colWidths=[140, 364])
    t_sec.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 1, c_border),
        ('INNERGRID', (0,0), (-1,-1), 0.5, c_border),
        ('BACKGROUND', (0,0), (0,-1), c_bg_light),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(t_sec)
    story.append(Spacer(1, 14))

    # =========================================================================
    # SECTION 6: 12-MONTH EXECUTION ROADMAP
    # =========================================================================
    story.append(PageBreak())  # Page 4

    story.append(Paragraph("6. Project Implementation Roadmap & Grant Milestones", h1_style))
    story.append(Paragraph(
        "Grant funding will be deployed across four milestone-driven phases over the next 12 months to transition "
        "from operational MVP to nationwide adoption:",
        body_style
    ))

    roadmap_data = [
        [Paragraph("Phase & Timeline", table_header), Paragraph("Key Technical & Operational Deliverables", table_header), Paragraph("Expected Impact Target", table_header)],
        [
            Paragraph("<b>Phase 1</b><br/>Months 1–2", table_cell_bold),
            Paragraph("• Integrate direct NIMC-accredited API for instant NIN validation.<br/>• Finalize automated virtual account bank verification.<br/>• Launch streamlined artisan onboarding UX.", table_cell),
            Paragraph("Verification latency cut from 24 hours to &lt;2 minutes.", table_cell)
        ],
        [
            Paragraph("<b>Phase 2</b><br/>Months 3–4", table_cell_bold),
            Paragraph("• Launch localized union drives across Lagos (Alaba, Somolu, Coker) and Abuja.<br/>• Onboard and badge initial pilot cohort.<br/>• Execute targeted homeowner marketing campaigns.", table_cell),
            Paragraph("1,000 verified artisans onboarded; 500 completed escrow jobs.", table_cell)
        ],
        [
            Paragraph("<b>Phase 3</b><br/>Months 5–7", table_cell_bold),
            Paragraph("• Release lightweight Android PWA with offline caching.<br/>• Deploy low-data image compression for portfolio uploads.<br/>• Expand WhatsApp bot NLP commands in Pidgin & Yoruba.", table_cell),
            Paragraph("5,000 active trade workers; 70% retention rate.", table_cell)
        ],
        [
            Paragraph("<b>Phase 4</b><br/>Months 8–10", table_cell_bold),
            Paragraph("• Partner with licensed MFIs to pilot equipment lease-to-own financing.<br/>• Embed project-liability and accident micro-insurance.<br/>• Launch Trade Credit alternative scoring API.", table_cell),
            Paragraph("₦250M+ total gross milestone volume disbursed to artisans.", table_cell)
        ],
        [
            Paragraph("<b>Phase 5</b><br/>Months 11–12", table_cell_bold),
            Paragraph("• Nationwide expansion into Rivers, Kano, Oyo, and Kaduna.<br/>• Formal partnership with NABTEB and ITF for certified apprentice placement.", table_cell),
            Paragraph("15,000+ verified artisans; 30,000+ jobs fulfilled across Nigeria.", table_cell)
        ]
    ]

    t_roadmap = Table(roadmap_data, colWidths=[80, 274, 150])
    t_roadmap.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), c_dark),
        ('GRID', (0,0), (-1,-1), 0.5, c_border),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, c_bg_light]),
    ]))
    story.append(t_roadmap)
    story.append(Spacer(1, 16))

    # Conclusion / Contact Callout
    story.append(Paragraph("7. Project Lead & Verification Contact", h1_style))
    contact_info = [
        [
            Paragraph("<b>Platform Name:</b> TradeLink NG", table_cell),
            Paragraph("<b>Official Website:</b> tradelink.ng", table_cell)
        ],
        [
            Paragraph("<b>Primary Email:</b> contact@tradelink.ng", table_cell),
            Paragraph("<b>Technical Stack:</b> Django 5 · PostgreSQL · Daphne · FastEmbed · Flutterwave", table_cell)
        ]
    ]
    t_contact = Table(contact_info, colWidths=[250, 254])
    t_contact.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), c_bg_light),
        ('BOX', (0,0), (-1,-1), 1, c_border),
        ('INNERGRID', (0,0), (-1,-1), 0.5, c_border),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
    ]))
    story.append(t_contact)

    # Build document
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Successfully generated {filename}")

if __name__ == "__main__":
    build_pdf()
