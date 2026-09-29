"""
hiring/cv_generator.py
======================
Executive PDF resume generator for TradeLink NG WorkerProfiles.

Features:
  - Corporate header card with worker avatar (circular crop) or initials badge
  - Verified technician pill and trade specialisation
  - Contact row: Email, Phone, LGA / State location, Hourly / Daily rate
  - 4-metric stat cards (Rating, Verified jobs completed, Experience, Availability)
  - Professional summary & employment preferences
  - Skill chips in a structured multi-column pill grid
  - Work history in a two-column timeline layout
  - Certifications with verified credentials tags
  - Featured Portfolio Showcase (4:3 rounded thumbnails, trade category tags,
    clean captions, and clickable YouTube demo links)
  - Live Verification QR code in the footer linking to the worker's public profile
  - NumberedCanvas for page numbers ("Page X of Y") and running headers on multi-page CVs
  - 100% clean typography (no missing glyphs or black tofu boxes)
"""

import io
import os
from datetime import date

from django.db.models import Count, Avg

try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm, mm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, HRFlowable,
        Table, TableStyle, KeepTogether, Image
    )
    from reportlab.platypus.flowables import Flowable
    from reportlab.pdfgen import canvas
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

try:
    import qrcode
    import qrcode.image.pil
    QRCODE_AVAILABLE = True
except ImportError:
    QRCODE_AVAILABLE = False

try:
    from PIL import Image as PILImage, ImageDraw
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


# ── Color Palette ─────────────────────────────────────────────────────────────
_NAVY_DARK   = colors.HexColor('#0b1f3a')   # Deep corporate navy (header top)
_NAVY_STRIP  = colors.HexColor('#132a4a')   # Mid-navy contact strip
_BLUE_ACCENT = colors.HexColor('#1d4ed8')   # Primary action blue
_BLUE_LIGHT  = colors.HexColor('#eff6ff')   # Stat card & chip fill
_BLUE_BORDER = colors.HexColor('#bfdbfe')   # Chip & card border
_TEXT_MAIN   = colors.HexColor('#1e293b')   # Dark slate for body text
_TEXT_MUTED  = colors.HexColor('#64748b')   # Slate 500 for subtext / metadata
_BORDER_LINE = colors.HexColor('#e2e8f0')   # Section dividers
_GREEN_BG    = colors.HexColor('#16a34a')   # Verified pill green
_WHITE       = colors.HexColor('#ffffff')


# ── Typography Sanitizer ──────────────────────────────────────────────────────

def _clean(text: str) -> str:
    """
    Sanitize text to guarantee zero unprintable/missing characters in Helvetica.
    Replaces special unicode dashes, quotes, and symbols with clean ASCII equivalents.
    """
    if not text:
        return ''
    replacements = {
        '\u2013': '-',   # en-dash
        '\u2014': '-',   # em-dash
        '\u2018': "'",   # left single quote
        '\u2019': "'",   # right single quote
        '\u201c': '"',   # left double quote
        '\u201d': '"',   # right double quote
        '\u2022': '*',   # bullet
        '\u2026': '...', # ellipsis
        '\u20a6': 'NGN ',# Naira symbol
        '\ufffd': '-',   # replacement character
        '₦': 'NGN ',
        '⭐': '',
        '🟢': '',
        '✅': '',
        '✓': '',
        '▶': '>>',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    # Filter to printable characters
    return text.encode('ascii', 'replace').decode('ascii').replace('?', '-')


# ── Decorative Flowables ──────────────────────────────────────────────────────

class _ColorRect(Flowable):
    """A clean filled vertical accent pill for section headers."""
    def __init__(self, width, height, fill_color):
        super().__init__()
        self.width  = width
        self.height = height
        self._fill  = fill_color

    def draw(self):
        self.canv.setFillColor(self._fill)
        self.canv.roundRect(0, 0, self.width, self.height, radius=1.5, fill=1, stroke=0)


class NumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas that computes the total page count and stamps
    running headers (Page 2+) and 'Page X of Y' footers across all pages.
    """
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
            self._draw_page_chrome(num_pages)
            super().showPage()
        super().save()

    def _draw_page_chrome(self, total_pages):
        self.saveState()
        self.setFont("Helvetica", 7.5)
        self.setFillColor(_TEXT_MUTED)

        # Running header on page 2 onwards
        if self._pageNumber > 1:
            self.setStrokeColor(_BORDER_LINE)
            self.setLineWidth(0.5)
            self.line(36, 842 - 25, 595 - 36, 842 - 25)
            self.drawString(36, 842 - 20, "TradeLink NG  |  Professional Verified Resume")
            self.drawRightString(595 - 36, 842 - 20, "tradelinkng.com")

        # Bottom running page number
        page_str = f"Page {self._pageNumber} of {total_pages}"
        self.drawRightString(595 - 36, 16, page_str)
        self.drawString(36, 16, "TradeLink NG  -  Official Verified Professional Profile")
        self.restoreState()


# ── Image Processors ──────────────────────────────────────────────────────────

def _build_qr_image(url: str, size_cm: float = 2.4):
    """Generate high-contrast QR code as a ReportLab Image."""
    if not QRCODE_AVAILABLE or not url:
        return None
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=1,
    )
    qr.add_data(url)
    qr.make(fit=True)
    pil_img = qr.make_image(fill_color='black', back_color='white')
    buf = io.BytesIO()
    pil_img.save(buf, format='PNG')
    buf.seek(0)
    size = size_cm * cm
    return Image(buf, width=size, height=size)


def _build_avatar_image(user, size_pt: float = 52):
    """
    Return a circular cropped avatar for the worker's user.image,
    or a stylish circular initials badge if no image is uploaded.
    """
    if not PIL_AVAILABLE:
        return None

    size_px = 160
    has_image = False

    if hasattr(user, 'image') and user.image:
        try:
            # Supports both local and remote storages via open()
            with user.image.open('rb') as f:
                with PILImage.open(f) as src_img:
                    src_img = src_img.convert('RGB')
                    w, h = src_img.size
                    min_dim = min(w, h)
                    left = (w - min_dim) // 2
                    top = (h - min_dim) // 2
                    src_img = src_img.crop((left, top, left + min_dim, top + min_dim))
                    img = src_img.resize((size_px, size_px), PILImage.LANCZOS)
                    has_image = True
        except Exception:
            has_image = False

    if has_image:
        mask = PILImage.new('L', (size_px, size_px), 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, size_px, size_px), fill=255)
        avatar = PILImage.new('RGBA', (size_px, size_px), (0, 0, 0, 0))
        avatar.paste(img, (0, 0), mask=mask)
        # White border ring
        draw_ring = ImageDraw.Draw(avatar)
        draw_ring.ellipse((1, 1, size_px - 2, size_px - 2), outline=(255, 255, 255, 220), width=4)
    else:
        # Generate clean initials badge
        avatar = PILImage.new('RGBA', (size_px, size_px), (0, 0, 0, 0))
        draw = ImageDraw.Draw(avatar)
        draw.ellipse((0, 0, size_px, size_px), fill=(29, 78, 216))  # blue 700
        draw.ellipse((1, 1, size_px - 2, size_px - 2), outline=(255, 255, 255, 200), width=4)
        raw_name = user.get_full_name() or user.username
        initials = ''.join([p[0].upper() for p in raw_name.split() if p][:2]) or 'TL'
        
        # Load bold font with cross-platform fallbacks
        font = None
        for font_candidate in ['arialbd.ttf', 'arial.ttf', 'DejaVuSans-Bold.ttf', 'FreeSansBold.ttf']:
            try:
                from PIL import ImageFont
                font = ImageFont.truetype(font_candidate, 56)
                break
            except Exception:
                continue
        try:
            draw.text((size_px // 2, size_px // 2), initials, fill=(255, 255, 255), font=font, anchor='mm')
        except Exception:
            try:
                draw.text((size_px // 2, size_px // 2), initials, fill=(255, 255, 255), anchor='mm')
            except Exception:
                pass

    buf = io.BytesIO()
    avatar.save(buf, format='PNG')
    buf.seek(0)
    return Image(buf, width=size_pt, height=size_pt)


def _build_portfolio_thumbnail(item, target_w: float, target_h: float):
    """
    Crop portfolio photo to 4:3 ratio, apply subtle rounded corners,
    and return as a ReportLab Image.
    """
    if not PIL_AVAILABLE or not item.image:
        return None
    try:
        with item.image.open('rb') as f:
            with PILImage.open(f) as img:
                img = img.convert('RGB')
                w, h = img.size
                aspect = target_w / target_h
                if w / h > aspect:
                    new_w = int(h * aspect)
                    left = (w - new_w) // 2
                    img = img.crop((left, 0, left + new_w, h))
                else:
                    new_h = int(w / aspect)
                    top = (h - new_h) // 2
                    img = img.crop((0, top, w, top + new_h))
                
                # High-res thumbnail
                px_w, px_h = int(target_w * 2.5), int(target_h * 2.5)
                img = img.resize((px_w, px_h), PILImage.LANCZOS)

                # Rounded corners mask
                radius = 12
                mask = PILImage.new('L', (px_w, px_h), 0)
                draw = ImageDraw.Draw(mask)
                draw.rounded_rectangle((0, 0, px_w, px_h), radius=radius, fill=255)

                result = PILImage.new('RGBA', (px_w, px_h), (0, 0, 0, 0))
                result.paste(img, (0, 0), mask=mask)

                # Crisp subtle outline
                draw_b = ImageDraw.Draw(result)
                draw_b.rounded_rectangle((0, 0, px_w - 1, px_h - 1), radius=radius, outline=(203, 213, 225, 255), width=2)

                buf = io.BytesIO()
                result.save(buf, format='PNG')
                buf.seek(0)
                return Image(buf, width=target_w, height=target_h)
    except Exception:
        return None


# ── PDF Builder ───────────────────────────────────────────────────────────────

def generate_cv_pdf(worker_profile, profile_url: str = '') -> bytes:
    """
    Generate a polished, executive PDF resume for the given WorkerProfile.
    Returns raw PDF bytes.

    Args:
        worker_profile: The WorkerProfile instance.
        profile_url:    Absolute URL to the worker's public profile page.
                        Used to generate the footer QR code.
    """
    if not REPORTLAB_AVAILABLE:
        raise ImportError(
            'reportlab is required for CV generation. '
            'Install it with: pip install reportlab pillow qrcode[pil]'
        )

    PAGE_W, PAGE_H = A4
    MARGIN_LR = 36          # 0.5 inch / 1.27 cm
    MARGIN_TOP = 28
    MARGIN_BOT = 28
    BODY_W = PAGE_W - (2 * MARGIN_LR)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=MARGIN_LR,
        leftMargin=MARGIN_LR,
        topMargin=MARGIN_TOP,
        bottomMargin=MARGIN_BOT,
        title=f'{_clean(worker_profile.user.get_full_name() or worker_profile.user.username)} - TradeLink CV',
    )

    # ── Styles ────────────────────────────────────────────────────────────────
    style_h_name = ParagraphStyle(
        'HName', fontSize=20, fontName='Helvetica-Bold',
        textColor=_WHITE, leading=23, spaceAfter=2,
    )
    style_h_trade = ParagraphStyle(
        'HTrade', fontSize=10.5, fontName='Helvetica',
        textColor=colors.HexColor('#93c5fd'), leading=13, spaceAfter=0,
    )
    style_h_contact = ParagraphStyle(
        'HContact', fontSize=8, fontName='Helvetica',
        textColor=colors.HexColor('#cbd5e1'), leading=11, spaceAfter=0,
    )
    style_verified_pill = ParagraphStyle(
        'VerifiedPill', fontSize=7.5, fontName='Helvetica-Bold',
        textColor=_WHITE, alignment=TA_CENTER, leading=9,
    )
    style_section_title = ParagraphStyle(
        'SectionTitle', fontSize=9.5, fontName='Helvetica-Bold',
        textColor=_NAVY_DARK, leading=12, spaceAfter=0,
    )
    style_body = ParagraphStyle(
        'Body', fontSize=8.5, fontName='Helvetica',
        textColor=_TEXT_MAIN, leading=12.5, spaceAfter=3,
    )
    style_job_title = ParagraphStyle(
        'JobTitle', fontSize=9.5, fontName='Helvetica-Bold',
        textColor=_TEXT_MAIN, leading=12, spaceAfter=1,
    )
    style_job_meta = ParagraphStyle(
        'JobMeta', fontSize=8, fontName='Helvetica',
        textColor=_TEXT_MUTED, leading=11, spaceAfter=2,
    )
    style_meta_row = ParagraphStyle(
        'MetaRow', fontSize=8, fontName='Helvetica',
        textColor=_TEXT_MUTED, leading=11, spaceAfter=0,
    )
    style_badge_val = ParagraphStyle(
        'BadgeVal', fontSize=9.5, fontName='Helvetica-Bold',
        textColor=_NAVY_DARK, alignment=TA_CENTER, leading=12,
    )
    style_badge_lbl = ParagraphStyle(
        'BadgeLbl', fontSize=7, fontName='Helvetica',
        textColor=_TEXT_MUTED, alignment=TA_CENTER, leading=9,
    )
    style_chip = ParagraphStyle(
        'Chip', fontSize=7.5, fontName='Helvetica',
        textColor=_TEXT_MAIN, leading=10,
    )
    style_port_trade = ParagraphStyle(
        'PortTrade', fontSize=6.5, fontName='Helvetica-Bold',
        textColor=_BLUE_ACCENT, leading=8, spaceAfter=1,
    )
    style_port_cap = ParagraphStyle(
        'PortCap', fontSize=7.5, fontName='Helvetica',
        textColor=_TEXT_MAIN, leading=10, spaceAfter=1,
    )
    style_port_video = ParagraphStyle(
        'PortVideo', fontSize=7, fontName='Helvetica-Bold',
        textColor=colors.HexColor('#dc2626'), leading=9, spaceAfter=0,
    )
    style_footer_bold = ParagraphStyle(
        'FooterBold', fontSize=8, fontName='Helvetica-Bold',
        textColor=_NAVY_DARK, leading=11,
    )
    style_footer_sub = ParagraphStyle(
        'FooterSub', fontSize=7.5, fontName='Helvetica',
        textColor=_TEXT_MUTED, leading=10,
    )
    style_qr_sub = ParagraphStyle(
        'QRSub', fontSize=6.5, fontName='Helvetica-Bold',
        textColor=_NAVY_DARK, alignment=TA_CENTER, leading=8,
    )

    # ── Section Header Generator ──────────────────────────────────────────────
    def make_section_header(title: str, space_before: float = 8):
        elements = []
        if space_before > 0:
            elements.append(Spacer(1, space_before))
        accent = _ColorRect(3.5 * mm, 12, _BLUE_ACCENT)
        heading = Paragraph(_clean(title).upper(), style_section_title)
        tbl = Table([[accent, heading]], colWidths=[6 * mm, BODY_W - 6 * mm])
        tbl.setStyle(TableStyle([
            ('VALIGN',       (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING',  (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING',   (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING',(0, 0), (-1, -1), 0),
        ]))
        elements.append(tbl)
        elements.append(HRFlowable(
            width='100%', thickness=0.5,
            color=_BORDER_LINE, spaceAfter=5, spaceBefore=3,
        ))
        return elements

    # ── Collect Worker Data ───────────────────────────────────────────────────
    story = []
    user = worker_profile.user
    full_name = _clean(user.get_full_name() or user.username)
    trade_name = _clean(worker_profile.trade_category.name if worker_profile.trade_category else 'Skilled Trades')
    is_verified = worker_profile.is_verified

    # ── 1. HEADER CARD ────────────────────────────────────────────────────────
    avatar_flowable = _build_avatar_image(user, size_pt=52)

    # Title line with optional Verified badge
    title_cells = [Paragraph(f"<b>{trade_name.upper()}</b>", style_h_trade)]
    if is_verified:
        verified_tag = Table(
            [[Paragraph("VERIFIED", style_verified_pill)]],
            colWidths=[54],
        )
        verified_tag.setStyle(TableStyle([
            ('BACKGROUND',   (0, 0), (-1, -1), _GREEN_BG),
            ('TOPPADDING',   (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING',(0, 0), (-1, -1), 2),
            ('LEFTPADDING',  (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('ROUNDEDCORNERS',[3]),
        ]))
        title_row = Table([[title_cells[0], verified_tag]], colWidths=[None, 56])
        title_row.setStyle(TableStyle([
            ('VALIGN',       (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING',  (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING',   (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING',(0, 0), (-1, -1), 0),
        ]))
    else:
        title_row = title_cells[0]

    header_text_stack = [
        Paragraph(full_name, style_h_name),
        Spacer(1, 1),
        title_row,
    ]

    # Avatar + Name block
    AVATAR_COL_W = 62 if avatar_flowable else 0
    TEXT_COL_W = BODY_W - AVATAR_COL_W - 16

    if avatar_flowable:
        header_top_row = Table([[avatar_flowable, header_text_stack]], colWidths=[AVATAR_COL_W, TEXT_COL_W])
    else:
        header_top_row = Table([[header_text_stack]], colWidths=[BODY_W - 16])

    header_top_row.setStyle(TableStyle([
        ('VALIGN',       (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING',  (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING',   (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 0),
    ]))

    # Contact sub-strip
    contact_parts = []
    if user.email:
        contact_parts.append(f"Email: {_clean(user.email)}")
    if hasattr(user, 'phone_number') and user.phone_number:
        contact_parts.append(f"Tel: {_clean(str(user.phone_number))}")
    loc = ', '.join([p for p in [_clean(worker_profile.lga), _clean(worker_profile.state)] if p])
    if loc:
        contact_parts.append(f"Location: {loc}")
    if worker_profile.hourly_rate:
        contact_parts.append(f"Rate: NGN {worker_profile.hourly_rate:,.0f} / hr")

    contact_str = "    |    ".join(contact_parts) if contact_parts else "TradeLink NG Verified Professional"
    contact_para = Paragraph(contact_str, style_h_contact)

    header_box = Table(
        [
            [header_top_row],
            [contact_para],
        ],
        colWidths=[BODY_W],
    )
    header_box.setStyle(TableStyle([
        ('BACKGROUND',   (0, 0), (0, 0),   _NAVY_DARK),
        ('BACKGROUND',   (0, 1), (0, 1),   _NAVY_STRIP),
        ('TOPPADDING',   (0, 0), (0, 0),   10),
        ('BOTTOMPADDING',(0, 0), (0, 0),   10),
        ('LEFTPADDING',  (0, 0), (0, 0),   12),
        ('RIGHTPADDING', (0, 0), (0, 0),   12),
        ('TOPPADDING',   (0, 1), (0, 1),   5),
        ('BOTTOMPADDING',(0, 1), (0, 1),   5),
        ('LEFTPADDING',  (0, 1), (0, 1),   12),
        ('RIGHTPADDING', (0, 1), (0, 1),   12),
        ('ROUNDEDCORNERS',[5]),
    ]))
    story.append(header_box)
    story.append(Spacer(1, 6))

    # ── 2. METRIC STAT CARDS ──────────────────────────────────────────────────
    avg_rating = user.reviews_received.filter(is_visible=True).aggregate(avg=Avg('rating'))['avg']
    completed_jobs = user.reviews_received.filter(is_visible=True).count()

    stat_cards = []
    if avg_rating:
        stat_cards.append((f"{avg_rating:.1f} / 5.0", "Platform Rating"))
    if completed_jobs:
        stat_cards.append((f"{completed_jobs} Verified", "Jobs Completed"))
    if worker_profile.years_experience:
        stat_cards.append((f"{worker_profile.years_experience}+ Years", "Field Experience"))
    if worker_profile.open_to_employment:
        stat_cards.append(("Open to Work", "Availability Status"))
    elif worker_profile.availability:
        stat_cards.append((_clean(worker_profile.get_availability_display()), "Current Status"))
    if worker_profile.expected_monthly_salary:
        stat_cards.append((f"NGN {worker_profile.expected_monthly_salary:,.0f}", "Target Salary / Mo"))

    if stat_cards:
        card_count = len(stat_cards)
        card_w = (BODY_W - ((card_count - 1) * 6)) / card_count
        card_cells = []
        for val, lbl in stat_cards:
            c_tbl = Table(
                [
                    [Paragraph(val, style_badge_val)],
                    [Paragraph(lbl, style_badge_lbl)],
                ],
                colWidths=[card_w],
            )
            c_tbl.setStyle(TableStyle([
                ('BACKGROUND',   (0, 0), (-1, -1), _BLUE_LIGHT),
                ('TOPPADDING',   (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING',(0, 0), (-1, -1), 4),
                ('LEFTPADDING',  (0, 0), (-1, -1), 4),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                ('ALIGN',        (0, 0), (-1, -1), 'CENTER'),
                ('BOX',          (0, 0), (-1, -1), 0.5, _BLUE_BORDER),
                ('ROUNDEDCORNERS',[4]),
            ]))
            card_cells.append(c_tbl)

        stat_row = Table([card_cells], colWidths=[card_w + 6] * (card_count - 1) + [card_w])
        stat_row.setStyle(TableStyle([
            ('LEFTPADDING',  (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING',   (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING',(0, 0), (-1, -1), 0),
            ('VALIGN',       (0, 0), (-1, -1), 'TOP'),
        ]))
        story.append(stat_row)
        story.append(Spacer(1, 4))

    # ── 3. PROFESSIONAL SUMMARY ───────────────────────────────────────────────
    if worker_profile.bio:
        story += make_section_header('Professional Summary', space_before=4)
        story.append(Paragraph(_clean(worker_profile.bio), style_body))

    # Employment Preferences Strip
    pref_parts = []
    if worker_profile.notice_period:
        pref_parts.append(f"Notice Period: <b>{_clean(worker_profile.notice_period)}</b>")
    if worker_profile.employment_preference:
        pref_parts.append(f"Preference: <b>{_clean(worker_profile.get_employment_preference_display())}</b>")
    if worker_profile.is_willing_to_relocate:
        pref_parts.append("<b>Willing to Relocate</b>")
    if pref_parts:
        story.append(Paragraph("    |    ".join(pref_parts), style_meta_row))
        story.append(Spacer(1, 3))

    # ── 4. SKILLS & EXPERTISE (Pill Chips) ────────────────────────────────────
    skills = list(
        worker_profile.skills.filter(is_active=True)
        .annotate(endorsement_count=Count('endorsements'))
        .order_by('-endorsement_count')
    )
    if skills:
        story += make_section_header('Skills & Expertise', space_before=5)
        CHIP_COLS = 3
        gap = 4
        chip_w = (BODY_W - (CHIP_COLS - 1) * gap) / CHIP_COLS

        chip_rows = []
        current_row = []
        for s in skills:
            s_name = _clean(s.name)
            if s.endorsement_count:
                s_name += f"  ({s.endorsement_count})"
            c_box = Table(
                [[Paragraph(s_name, style_chip)]],
                colWidths=[chip_w],
            )
            c_box.setStyle(TableStyle([
                ('BACKGROUND',   (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
                ('TOPPADDING',   (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING',(0, 0), (-1, -1), 3),
                ('LEFTPADDING',  (0, 0), (-1, -1), 7),
                ('RIGHTPADDING', (0, 0), (-1, -1), 7),
                ('BOX',          (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
                ('ROUNDEDCORNERS',[3]),
            ]))
            current_row.append(c_box)
            if len(current_row) == CHIP_COLS:
                chip_rows.append(current_row)
                current_row = []

        if current_row:
            while len(current_row) < CHIP_COLS:
                current_row.append(Spacer(1, 1))
            chip_rows.append(current_row)

        chip_table = Table(chip_rows, colWidths=[chip_w + gap] * (CHIP_COLS - 1) + [chip_w])
        chip_table.setStyle(TableStyle([
            ('LEFTPADDING',  (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING',   (0, 0), (-1, -1), 1.5),
            ('BOTTOMPADDING',(0, 0), (-1, -1), 1.5),
            ('VALIGN',       (0, 0), (-1, -1), 'TOP'),
        ]))
        story.append(chip_table)

    # ── 5. WORK EXPERIENCE ────────────────────────────────────────────────────
    history = list(worker_profile.work_history.select_related('trade_category').all())
    if history:
        exp_elements = make_section_header('Work Experience', space_before=6)
        DATE_COL = 82
        CONTENT_COL = BODY_W - DATE_COL - 10

        for entry in history:
            dr_start = entry.start_date.strftime('%b %Y') if entry.start_date else ''
            if entry.is_current:
                dr_end = 'Present'
            elif entry.end_date:
                dr_end = entry.end_date.strftime('%b %Y')
            else:
                dr_end = ''
            dr_text = f"{dr_start} - {dr_end}" if (dr_start and dr_end) else (dr_start or dr_end)

            loc_text = f"  |  {_clean(entry.location_state)}" if entry.location_state else ''
            content_cells = [
                Paragraph(_clean(entry.role_title), style_job_title),
                Paragraph(f"{_clean(entry.employer_name)}{loc_text}", style_job_meta),
            ]
            if entry.description:
                content_cells.append(Paragraph(_clean(entry.description), style_body))

            row_tbl = Table(
                [[Paragraph(f"<b>{dr_text}</b>", style_job_meta), content_cells]],
                colWidths=[DATE_COL, CONTENT_COL],
            )
            row_tbl.setStyle(TableStyle([
                ('VALIGN',       (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING',  (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ('TOPPADDING',   (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING',(0, 0), (-1, -1), 4),
                ('LINEAFTER',    (0, 0), (0, -1), 1, _BLUE_BORDER),
            ]))
            exp_elements.append(row_tbl)
        
        story.append(KeepTogether(exp_elements))

    # ── 6. CERTIFICATIONS & QUALIFICATIONS ────────────────────────────────────
    certs = list(worker_profile.certifications.all())
    if certs:
        cert_elements = make_section_header('Certifications & Credentials', space_before=6)
        for cert in certs:
            v_tag = '  <font color="#16a34a"><b>[Verified Certificate]</b></font>' if cert.is_verified else ''
            meta_str = _clean(cert.issuing_body)
            if cert.year_obtained:
                meta_str += f"  |  Year: {cert.year_obtained}"
            
            c_block = [
                Paragraph(f"<b>{_clean(cert.name)}</b>{v_tag}", style_job_title),
                Paragraph(meta_str, style_job_meta),
            ]
            cert_elements.append(KeepTogether(c_block))
        
        story.append(KeepTogether(cert_elements))

    # ── 7. FEATURED PORTFOLIO (THE HERO SECTION) ──────────────────────────────
    portfolio_items = list(worker_profile.portfolio.order_by('display_order', '-created')[:6])
    if portfolio_items:
        story += make_section_header('Featured Work & Project Portfolio', space_before=7)

        PORT_COLS = 3
        port_gap = 6
        card_w = (BODY_W - (PORT_COLS - 1) * port_gap) / PORT_COLS
        img_h = card_w * 0.60  # clean 16:10 aspect ratio

        card_grid_rows = []
        current_card_row = []

        for item in portfolio_items:
            img_flowable = _build_portfolio_thumbnail(item, card_w, img_h)
            
            card_content = []
            if img_flowable:
                card_content.append(img_flowable)
                card_content.append(Spacer(1, 3))
            
            # Trade tag
            if item.trade_context:
                card_content.append(Paragraph(_clean(item.trade_context.name).upper(), style_port_trade))
            
            # Caption
            cap = _clean(item.caption or 'Completed Project')
            if len(cap) > 65:
                cap = cap[:62] + '...'
            card_content.append(Paragraph(cap, style_port_cap))

            # YouTube demo video link
            if item.youtube_url:
                v_link = f'<a href="{item.youtube_url}" color="#dc2626"><b>Watch Video Demo &gt;&gt;</b></a>'
                card_content.append(Paragraph(v_link, style_port_video))

            # Wrap in individual card table
            card_tbl = Table([[card_content]], colWidths=[card_w])
            card_tbl.setStyle(TableStyle([
                ('BACKGROUND',   (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
                ('TOPPADDING',   (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING',(0, 0), (-1, -1), 5),
                ('LEFTPADDING',  (0, 0), (-1, -1), 4),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                ('BOX',          (0, 0), (-1, -1), 0.5, _BORDER_LINE),
                ('ROUNDEDCORNERS',[4]),
                ('VALIGN',       (0, 0), (-1, -1), 'TOP'),
            ]))
            current_card_row.append(card_tbl)

            if len(current_card_row) == PORT_COLS:
                # Add each completed row directly to story or row list so it breaks cleanly across pages if needed!
                row_tbl = Table([current_card_row], colWidths=[card_w + port_gap] * (PORT_COLS - 1) + [card_w])
                row_tbl.setStyle(TableStyle([
                    ('LEFTPADDING',  (0, 0), (-1, -1), 0),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                    ('TOPPADDING',   (0, 0), (-1, -1), 2),
                    ('BOTTOMPADDING',(0, 0), (-1, -1), 2),
                    ('VALIGN',       (0, 0), (-1, -1), 'TOP'),
                ]))
                story.append(KeepTogether([row_tbl]))
                story.append(Spacer(1, 2))
                current_card_row = []

        if current_card_row:
            while len(current_card_row) < PORT_COLS:
                current_card_row.append(Spacer(1, 1))
            row_tbl = Table([current_card_row], colWidths=[card_w + port_gap] * (PORT_COLS - 1) + [card_w])
            row_tbl.setStyle(TableStyle([
                ('LEFTPADDING',  (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ('TOPPADDING',   (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING',(0, 0), (-1, -1), 2),
                ('VALIGN',       (0, 0), (-1, -1), 'TOP'),
            ]))
            story.append(KeepTogether([row_tbl]))

    # ── 8. FOOTER WITH QR CODE ────────────────────────────────────────────────
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width='100%', thickness=0.5, color=_BORDER_LINE, spaceAfter=6, spaceBefore=0))

    qr_image = _build_qr_image(profile_url, size_cm=2.3) if profile_url else None
    today_str = date.today().strftime('%d %B %Y')

    if qr_image:
        footer_left = [
            Paragraph("<b>TRADELINK NG  |  Official Verified Resume</b>", style_footer_bold),
            Spacer(1, 2),
            Paragraph(f"Platform: tradelinkng.com  |  Generated on {today_str}", style_footer_sub),
            Spacer(1, 2),
            Paragraph("Scan the QR code to verify credentials, view live reviews, and contact this professional on TradeLink NG.", style_footer_sub),
        ]
        footer_qr_col = [
            qr_image,
            Spacer(1, 2),
            Paragraph("Scan for Live Profile", style_qr_sub),
        ]
        footer_tbl = Table(
            [[footer_left, footer_qr_col]],
            colWidths=[BODY_W - 75, 75],
        )
        footer_tbl.setStyle(TableStyle([
            ('VALIGN',       (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN',        (1, 0), (1, 0),   'CENTER'),
            ('LEFTPADDING',  (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING',   (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING',(0, 0), (-1, -1), 0),
        ]))
        story.append(KeepTogether([footer_tbl]))
    else:
        story.append(Paragraph(
            f"<b>TradeLink NG</b>  -  tradelinkng.com  |  Official Resume  |  {today_str}",
            style_footer_sub,
        ))

    # Build PDF with NumberedCanvas
    doc.build(story, canvasmaker=NumberedCanvas)
    return buffer.getvalue()
