"""
bot/handlers.py
===============
Message routing and conversation-flow handlers for the TradeLink NG bot.

Architecture
────────────
MessageRouter.dispatch()
    Entry point called by the webhook view for every inbound message.
    Logs the message, checks for cancel keywords, then either:
      (a) routes to a command handler if the session is idle, or
      (b) continues the active multi-turn flow.

Flow handlers
    Each flow is a set of plain functions named
    ``start_<flow>(session, provider, to)`` and
    ``continue_<flow>(session, provider, to, text)``.
    They mutate ``session.flow``, ``session.step``, and ``session.data``
    to advance the conversation state machine.

    ``provider`` is a ``bot.providers.base.MessagingProvider`` instance
    (TwilioProvider or MetaProvider).  Handlers call ``provider.send_text()``
    and never import any channel-specific code directly.

Supported flows
    • Greeting / main menu      — single-step
    • Search jobs               — 2 steps: select category → view listings
    • Browse products           — single-step
    • My profile                — single-step (requires linked account)
    • My job matches            — single-step (requires linked worker account)
    • Link account              — 1 step: enter email
    • Post job request          — 5 steps: title → category → state →
                                           description → job type → confirm → create
"""

import logging

from bot.providers.base import MessagingProvider
from .models import WhatsAppMessage, WhatsAppSession

logger = logging.getLogger(__name__)


# ── Static content ────────────────────────────────────────────────────────────

MAIN_MENU_TEXT = (
    "👋 *Welcome to TradeLink NG!*\n\n"
    "Connect with skilled artisans or find quality tools — all via WhatsApp.\n\n"
    "What would you like to do?\n\n"
    "1️⃣  Find Jobs\n"
    "2️⃣  Browse Marketplace\n"
    "3️⃣  My Profile\n"
    "4️⃣  Post a Job Request\n"
    "5️⃣  My Job Matches\n"
    "6️⃣  Help\n\n"
    "_Type a number or keyword to continue._"
)

HELP_TEXT = (
    "📖 *TradeLink NG Bot — Commands*\n\n"
    "• *menu* or *0* — Main menu\n"
    "• *1* or *jobs* — Browse job listings\n"
    "• *2* or *products* — Browse marketplace\n"
    "• *3* or *profile* — View your profile\n"
    "• *4* or *post job* — Post a job request\n"
    "• *5* or *matches* — View your top job matches\n"
    "• *link* — Connect your WhatsApp to your account\n"
    "• *unlink* — Disconnect your WhatsApp account\n"
    "• *cancel* — Cancel current action & return to menu\n"
    "• *help* — Show this message\n\n"
    "🌐 Visit us: *tradelinkng.com*"
)

CANCEL_KEYWORDS = frozenset({'cancel', 'stop', 'quit', 'exit', 'back', '0', 'menu'})

# Nigerian states display → DB slug mapping
NIGERIAN_STATES_MAP = {
    'abia': 'abia',
    'adamawa': 'adamawa',
    'akwa ibom': 'akwa_ibom',
    'anambra': 'anambra',
    'bauchi': 'bauchi',
    'bayelsa': 'bayelsa',
    'benue': 'benue',
    'borno': 'borno',
    'cross river': 'cross_river',
    'delta': 'delta',
    'ebonyi': 'ebonyi',
    'edo': 'edo',
    'ekiti': 'ekiti',
    'enugu': 'enugu',
    'fct': 'fct',
    'abuja': 'fct',
    'fct abuja': 'fct',
    'fct — abuja': 'fct',
    'gombe': 'gombe',
    'imo': 'imo',
    'jigawa': 'jigawa',
    'kaduna': 'kaduna',
    'kano': 'kano',
    'katsina': 'katsina',
    'kebbi': 'kebbi',
    'kogi': 'kogi',
    'kwara': 'kwara',
    'lagos': 'lagos',
    'nasarawa': 'nasarawa',
    'niger': 'niger',
    'ogun': 'ogun',
    'ondo': 'ondo',
    'osun': 'osun',
    'oyo': 'oyo',
    'plateau': 'plateau',
    'rivers': 'rivers',
    'sokoto': 'sokoto',
    'taraba': 'taraba',
    'yobe': 'yobe',
    'zamfara': 'zamfara',
}

NIGERIAN_STATES_DISPLAY = (
    "Abia, Adamawa, Akwa Ibom, Anambra, Bauchi, Bayelsa, Benue, Borno, "
    "Cross River, Delta, Ebonyi, Edo, Ekiti, Enugu, FCT (Abuja), Gombe, "
    "Imo, Jigawa, Kaduna, Kano, Katsina, Kebbi, Kogi, Kwara, Lagos, "
    "Nasarawa, Niger, Ogun, Ondo, Osun, Oyo, Plateau, Rivers, Sokoto, "
    "Taraba, Yobe, Zamfara"
)

JOB_TYPE_MAP = {
    '1': ('once_off', 'One-Off / Gig'),
    '2': ('full_time', 'Full-Time'),
    '3': ('contract', 'Contract'),
    '4': ('part_time', 'Part-Time'),
    'one-off': ('once_off', 'One-Off / Gig'),
    'once off': ('once_off', 'One-Off / Gig'),
    'one off': ('once_off', 'One-Off / Gig'),
    'gig': ('once_off', 'One-Off / Gig'),
    'full time': ('full_time', 'Full-Time'),
    'full-time': ('full_time', 'Full-Time'),
    'fulltime': ('full_time', 'Full-Time'),
    'contract': ('contract', 'Contract'),
    'part time': ('part_time', 'Part-Time'),
    'part-time': ('part_time', 'Part-Time'),
    'parttime': ('part_time', 'Part-Time'),
}


# ── Internal helpers ──────────────────────────────────────────────────────────

def _log_msg(session: WhatsAppSession, direction: str, content: str, message_id: str = '') -> None:
    """Create a WhatsAppMessage audit log entry."""
    WhatsAppMessage.objects.create(
        session=session,
        direction=direction,
        message_id=message_id,
        content=content,
    )


def _send(provider: MessagingProvider, session: WhatsAppSession, to: str, text: str) -> None:
    """Send a plain-text message and log it as outbound."""
    try:
        provider.send_text(to, text)
        _log_msg(session, WhatsAppMessage.Direction.OUTBOUND, text)
    except Exception as exc:
        # Print to stderr so errors always appear in the dev-server terminal
        # even when Django's logging is set to WARNING or higher.
        import sys
        print(f'\n‼️  _send() FAILED for {to}: {exc!r}\n', file=sys.stderr)
        logger.exception('Failed to send message to %s', to)


def _resolve_state(raw: str):
    """
    Try to map raw user input to a (slug, display_label) pair.
    Returns None if no match found.
    """
    from jobs.models import NIGERIAN_STATES as STATES_CHOICES
    key = raw.strip().lower()
    slug = NIGERIAN_STATES_MAP.get(key)
    if not slug:
        # Fuzzy: accept substrings
        for map_key, map_slug in NIGERIAN_STATES_MAP.items():
            if key in map_key or map_key in key:
                slug = map_slug
                break
    if not slug:
        return None
    label = next((lbl for val, lbl in STATES_CHOICES if val == slug), raw.title())
    return slug, label


# ── Main Router ───────────────────────────────────────────────────────────────

class MessageRouter:
    """
    Routes each incoming message to the appropriate handler.

    Channel-agnostic: accepts any MessagingProvider so the same router
    works with Twilio, Meta, or any future provider.

    Usage (called from the webhook view)::

        from bot.providers import get_provider
        router = MessageRouter(session, from_number, text, message_id, get_provider())
        router.dispatch()
    """

    def __init__(
        self,
        session: WhatsAppSession,
        from_number: str,
        text: str,
        message_id: str,
        provider: MessagingProvider,
    ):
        self.session     = session
        self.from_number = from_number
        self.text        = text.strip()
        self.text_lower  = text.strip().lower()
        self.message_id  = message_id
        self.provider    = provider

    def dispatch(self) -> None:
        """Log the inbound message, route it, and catch any unhandled exceptions."""
        _log_msg(
            self.session,
            WhatsAppMessage.Direction.INBOUND,
            self.text,
            self.message_id,
        )

        try:
            # "cancel" / "menu" always resets flow regardless of current state
            if (
                self.text_lower in CANCEL_KEYWORDS
                and self.session.flow != WhatsAppSession.Flow.IDLE
            ):
                self.session.reset()
                _send(
                    self.provider, self.session, self.from_number,
                    "❌ Action cancelled.\n\n" + MAIN_MENU_TEXT,
                )
                return

            if self.session.flow == WhatsAppSession.Flow.IDLE:
                self._route_command()
            else:
                self._continue_flow()

        except Exception:
            logger.exception(
                'Unhandled error processing message from %s', self.from_number
            )
            _send(
                self.provider, self.session, self.from_number,
                "⚠️ Something went wrong on our end. Please try again or type *menu*.",
            )

    # ── Command routing ───────────────────────────────────────────────────────

    def _route_command(self) -> None:
        t = self.text_lower
        if t in ('hi', 'hello', 'hey', 'start', 'menu', '0'):
            handle_greeting(self.session, self.provider, self.from_number)
        elif t in ('1', 'jobs', 'find jobs', 'job', 'search jobs'):
            start_search_jobs(self.session, self.provider, self.from_number)
        elif t in ('2', 'products', 'shop', 'marketplace', 'browse', 'market'):
            handle_search_products(self.session, self.provider, self.from_number)
        elif t in ('3', 'profile', 'my profile', 'account', 'me'):
            handle_my_profile(self.session, self.provider, self.from_number)
        elif t in ('4', 'post job', 'post a job', 'hire', 'post', 'post request'):
            start_post_job(self.session, self.provider, self.from_number)
        elif t in ('5', 'matches', 'my matches', 'job matches', 'my job matches',
                   'recommendations', 'recommended', 'recs'):
            handle_my_job_matches(self.session, self.provider, self.from_number)
        elif t in ('6', 'help', '?'):
            handle_help(self.session, self.provider, self.from_number)
        elif t in ('link', 'connect', 'link account', 'connect account'):
            start_link_account(self.session, self.provider, self.from_number)
        elif t in ('unlink', 'disconnect', 'unlink account', 'disconnect account', 'logout'):
            handle_unlink(self.session, self.provider, self.from_number)
        else:
            handle_unknown(self.session, self.provider, self.from_number)

    # ── Flow continuation ─────────────────────────────────────────────────────

    def _continue_flow(self) -> None:
        flow = self.session.flow
        if flow == WhatsAppSession.Flow.POST_JOB:
            continue_post_job(self.session, self.provider, self.from_number, self.text)
        elif flow == WhatsAppSession.Flow.SEARCH_JOBS:
            continue_search_jobs(self.session, self.provider, self.from_number, self.text)
        elif flow == WhatsAppSession.Flow.LINK_ACCOUNT:
            continue_link_account(self.session, self.provider, self.from_number, self.text)
        else:
            # Unknown flow — reset and try as a new command
            self.session.reset()
            self._route_command()


# ── Simple / single-step handlers ────────────────────────────────────────────

def handle_greeting(session: WhatsAppSession, provider: MessagingProvider, to: str) -> None:
    _send(provider, session, to, MAIN_MENU_TEXT)


def handle_help(session: WhatsAppSession, provider: MessagingProvider, to: str) -> None:
    _send(provider, session, to, HELP_TEXT)


def handle_unknown(session: WhatsAppSession, provider: MessagingProvider, to: str) -> None:
    _send(
        provider, session, to,
        "🤔 I didn't understand that.\n\n"
        "Type *menu* to see options or *help* for a full command list.",
    )


def handle_my_profile(session: WhatsAppSession, provider: MessagingProvider, to: str) -> None:
    if not session.user:
        _send(
            provider, session, to,
            "🔗 Your WhatsApp isn't linked to a TradeLink NG account yet.\n\n"
            "Type *link* to connect your account.",
        )
        return

    from jobs.models import NIGERIAN_STATES as _STATES
    _state_labels = dict(_STATES)

    user = session.user
    lines = [
        "👤 *Your TradeLink NG Profile*\n",
        f"• Name: {user.get_full_name() or user.username}",
        f"• Email: {user.email}",
        f"• Phone: {user.phone_number or 'Not set'}",
        f"• Member since: {user.created.strftime('%d %b %Y')}",
    ]

    try:
        wp = user.worker_profile
        trade         = wp.trade_category.name if wp.trade_category else 'Not set'
        state_display = _state_labels.get(wp.state, wp.state) if wp.state else 'Not set'
        lines += [
            "\n🔧 *Worker Profile*",
            f"• Trade: {trade}",
            f"• Experience: {wp.get_experience_level_display()}",
            f"• Location: {state_display}",
            f"• Availability: {wp.get_availability_display()}",
            f"• Profile: {wp.profile_completion}% complete",
            f"• Verified: {'✅ Yes' if wp.is_verified else '❌ No'}",
        ]
    except Exception:
        lines.append("\n🔧 *Worker Profile:* Not set up yet")

    try:
        ep = user.employer_profile
        lines += [
            "\n🏢 *Employer Profile*",
            f"• Company: {ep.company_name or user.username}",
            f"• Type: {ep.get_company_type_display()}",
            f"• Verified: {'✅ Yes' if ep.is_verified else '❌ No'}",
        ]
    except Exception:
        lines.append("\n🏢 *Employer Profile:* Not set up yet")

    lines.append("\n🌐 Manage your account at: *tradelinkng.com*")
    _send(provider, session, to, '\n'.join(lines))


# ── My Job Matches handler ────────────────────────────────────────────────────

def handle_my_job_matches(
    session: WhatsAppSession, provider: MessagingProvider, to: str
) -> None:
    """
    Show the top CLIP-scored job matches for the linked user's WorkerProfile.

    Requires:
    • A linked account  (session.user is not None)
    • The user must have a WorkerProfile

    Fetches up to 8 CLIPMatch rows ordered by descending score, filters to
    active jobs only, and formats each match with:
        – Match percentage  (score × 100, colour-coded tier emoji)
        – Job title
        – Location / job type / pay range
        – Direct link to apply
    """
    # Guard — account must be linked
    if not session.user:
        _send(
            provider, session, to,
            "🔗 You need to link your account to see your job matches.\n\n"
            "Type *link* to connect your TradeLink NG account.",
        )
        return

    user = session.user

    # Guard — user must have a WorkerProfile
    try:
        worker = user.worker_profile
    except Exception:
        _send(
            provider, session, to,
            "🔧 You don't have a *Worker Profile* set up yet.\n\n"
            "Visit *tradelinkng.com/profile* to create your worker profile and "
            "start receiving job matches.",
        )
        return

    # Fetch top matches
    try:
        from jobs.models import CLIPMatch, NIGERIAN_STATES as _STATES
        _state_labels = dict(_STATES)

        matches = (
            CLIPMatch.objects
            .filter(worker=worker, job__status='active', score__gte=0.60)
            .select_related(
                'job',
                'job__trade_category',
                'job__employer__user',
            )
            .order_by('-score')[:8]
        )

        if not matches:
            _send(
                provider, session, to,
                "📭 *No Job Matches Yet*\n\n"
                "We haven't computed your matches yet, or no active jobs match "
                "your trade with at least 60% similarity right now.\n\n"
                "💡 Make sure your worker profile is complete:\n"
                "*tradelinkng.com/profile*\n\n"
                "New matches are computed automatically when jobs are posted.",
            )
            return

        # Score → emoji tier
        def _tier(score: float) -> str:
            if score >= 0.80:
                return "🔥"   # Excellent
            if score >= 0.70:
                return "⭐"   # Strong
            return "👍"       # Good (60–69%)

        lines = [
            f"💼 *Your Top Job Matches*\n",
            f"Found {len(matches)} match{'es' if len(matches) != 1 else ''} "
            f"for your *{worker.trade_category.name if worker.trade_category else 'trade'}* profile.\n",
        ]

        for i, m in enumerate(matches, 1):
            job        = m.job
            pct        = round(m.score * 100)
            tier       = _tier(m.score)
            state_lbl  = _state_labels.get(job.state, job.state.title()) if job.state else "Remote / TBC"
            job_type   = job.get_job_type_display()

            # Pay range
            if job.pay_min and job.pay_max:
                pay = f"₦{job.pay_min:,.0f}–₦{job.pay_max:,.0f}"
            elif job.pay_min:
                pay = f"₦{job.pay_min:,.0f}+"
            elif job.pay_type == 'negotiable':
                pay = "Negotiable"
            else:
                pay = "Pay not specified"

            lines.append(
                f"{tier} *{i}. {job.title}*\n"
                f"   📊 Match: {pct}%  |  📍 {state_lbl}\n"
                f"   🕐 {job_type}  |  💰 {pay}\n"
                f"   🌐 tradelinkng.com/jobs/{str(job.id)[:8]}\n"
            )

        lines.append(
            "─────────────────\n"
            "🔥 Excellent (80%+)  ⭐ Strong (70–79%)  👍 Good (60–69%)\n\n"
            "Apply at: *tradelinkng.com/jobs*"
        )

        _send(provider, session, to, '\n'.join(lines))

    except Exception:
        logger.exception('Error fetching job matches for user %s', user.pk)
        _send(
            provider, session, to,
            "⚠️ Could not load your job matches right now. Please try again later.",
        )


def handle_search_products(
    session: WhatsAppSession, provider: MessagingProvider, to: str
) -> None:
    try:
        from marketplace.models import Product
        products = (
            Product.objects
            .filter(status='active')
            .select_related('category', 'seller__user')
            .order_by('-created')[:6]
        )
        if not products.exists():
            _send(
                provider, session, to,
                "🛒 No marketplace listings right now. Check back later!\n\n"
                "Type *menu* to go back.",
            )
            return

        lines = ["🛒 *Latest Marketplace Listings*\n"]
        for i, p in enumerate(products, 1):
            price = f"₦{p.price:,.0f}" if p.price else "Price on request"
            state_label = p.get_state_display() if hasattr(p, 'get_state_display') else (p.state or 'N/A')
            lines.append(
                f"*{i}. {p.title}*\n"
                f"   💰 {price}  📍 {state_label}\n"
                f"   {p.get_condition_display()}\n"
            )
        lines.append("🌐 See all listings at: *tradelinkng.com/marketplace*")
        _send(provider, session, to, '\n'.join(lines))
    except Exception:
        logger.exception('Error fetching products')
        _send(provider, session, to, "⚠️ Could not load products. Please try again later.")


# ── Search Jobs flow ──────────────────────────────────────────────────────────

def start_search_jobs(
    session: WhatsAppSession, provider: MessagingProvider, to: str
) -> None:
    from jobs.models import TradeCategory

    categories = list(
        TradeCategory.objects.filter(is_active=True).order_by('display_order', 'name')[:20]
    )
    if not categories:
        _send(
            provider, session, to,
            "⚠️ No trade categories found. Check back later!\n\nType *menu* to go back.",
        )
        return

    lines = ["🔍 *Search Jobs by Trade Category*\n"]
    for i, cat in enumerate(categories, 1):
        lines.append(f"{i}. {cat.name}")
    lines.append("\n_Reply with a number to see jobs in that category._\n_Type *cancel* to go back._")

    session.flow = WhatsAppSession.Flow.SEARCH_JOBS
    session.step = 'select_category'
    session.data = {
        'categories': [{'id': str(c.id), 'name': c.name} for c in categories]
    }
    session.save()

    _send(provider, session, to, '\n'.join(lines))


def continue_search_jobs(
    session: WhatsAppSession, provider: MessagingProvider, to: str, text: str
) -> None:
    if session.step != 'select_category':
        session.reset()
        handle_unknown(session, provider, to)
        return

    categories = session.data.get('categories', [])
    try:
        idx = int(text.strip()) - 1
        if not (0 <= idx < len(categories)):
            raise ValueError
    except ValueError:
        _send(provider, session, to,
              f"Please reply with a number between 1 and {len(categories)}.")
        return

    selected = categories[idx]
    session.reset()
    _show_jobs_for_category(session, provider, to, selected['id'], selected['name'])


def _show_jobs_for_category(
    session: WhatsAppSession,
    provider: MessagingProvider,
    to: str,
    category_id: str,
    category_name: str,
) -> None:
    from jobs.models import Job

    jobs = (
        Job.objects
        .filter(trade_category_id=category_id, status=Job.Status.ACTIVE)
        .select_related('employer__user')
        .order_by('-created')[:8]
    )

    if not jobs.exists():
        _send(
            provider, session, to,
            f"😔 No active *{category_name}* jobs right now.\n\n"
            f"Type *1* to search another category or *menu* for the main menu.",
        )
        return

    lines = [f"💼 *{category_name} Jobs*\n"]
    for job in jobs:
        state_label = ''
        if job.state:
            try:
                state_label = f"📍 {dict(job._meta.get_field('state').choices).get(job.state, job.state)}  "
            except Exception:
                state_label = f"📍 {job.state}  "
        pay = ''
        if job.pay_min:
            pay_max_str = f'–₦{job.pay_max:,.0f}' if job.pay_max else '+'
            pay = f"₦{job.pay_min:,.0f}{pay_max_str}  "
        lines.append(
            f"• *{job.title}*\n"
            f"  {state_label}{pay}{job.get_job_type_display()}\n"
        )
    lines.append("🌐 Apply at: *tradelinkng.com/jobs*")
    _send(provider, session, to, '\n'.join(lines))


# ── Link Account flow ─────────────────────────────────────────────────────────

def start_link_account(
    session: WhatsAppSession, provider: MessagingProvider, to: str
) -> None:
    if session.user:
        user = session.user
        _send(
            provider, session, to,
            f"✅ Already linked to *{user.username}* ({user.email}).\n\n"
            "Type *menu* to see what you can do.",
        )
        return

    session.flow = WhatsAppSession.Flow.LINK_ACCOUNT
    session.step = 'ask_email'
    session.data = {}
    session.save()

    _send(
        provider, session, to,
        "🔗 *Link Your TradeLink NG Account*\n\n"
        "Please reply with the *email address* you used to register on TradeLink NG.\n\n"
        "_Type *cancel* to go back._",
    )


def continue_link_account(
    session: WhatsAppSession, provider: MessagingProvider, to: str, text: str
) -> None:
    from users.models import User

    if session.step != 'ask_email':
        session.reset()
        handle_unknown(session, provider, to)
        return

    email = text.strip().lower()
    if '@' not in email or '.' not in email:
        _send(
            provider, session, to,
            "⚠️ That doesn't look like a valid email. Please try again or type *cancel*.",
        )
        return

    try:
        user = User.objects.get(email__iexact=email)
    except User.DoesNotExist:
        _send(
            provider, session, to,
            f"❌ No account found with email *{email}*.\n\n"
            "Please check the email and try again, or type *cancel* to go back.",
        )
        return

    session.user = user
    # NOTE: reset() must include 'user' in update_fields — without it the FK
    # assignment above is never written to the DB and every subsequent request
    # sees session.user as None.
    session.reset(extra_fields=['user'])
    _send(
        provider, session, to,
        f"🎉 *Account linked successfully!*\n\n"
        f"Welcome, *{user.get_full_name() or user.username}*!\n\n"
        "You can now post jobs, view your profile, and receive notifications.\n\n"
        "Type *menu* to get started.",
    )


def handle_unlink(
    session: WhatsAppSession, provider: MessagingProvider, to: str
) -> None:
    if not session.user:
        _send(
            provider, session, to,
            "ℹ️ Your WhatsApp is not linked to any account right now.\n\n"
            "Type *link* to connect an account.",
        )
        return

    session.user = None
    session.reset(extra_fields=['user'])
    _send(
        provider, session, to,
        "🔌 *Account unlinked successfully.*\n\n"
        "Your WhatsApp is no longer connected to TradeLink NG.\n"
        "Type *link* if you want to connect a different account.",
    )


# ── Post Job Request flow (5 steps) ──────────────────────────────────────────

def start_post_job(
    session: WhatsAppSession, provider: MessagingProvider, to: str
) -> None:
    if not session.user:
        _send(
            provider, session, to,
            "🔗 You need to link your account before posting a job.\n\n"
            "Type *link* to connect your TradeLink NG account.",
        )
        return

    session.flow = WhatsAppSession.Flow.POST_JOB
    session.step = 'ask_title'
    session.data = {}
    session.save()

    _send(
        provider, session, to,
        "📋 *Post a Job Request — Step 1 of 5*\n\n"
        "You can type *cancel* at any time to stop.\n\n"
        "What is the *job title*?\n\n"
        "_Examples:_\n"
        "• Fix leaking roof\n"
        "• Install CCTV cameras\n"
        "• Repair generator\n"
        "• Tile bathroom floor",
    )


def continue_post_job(
    session: WhatsAppSession, provider: MessagingProvider, to: str, text: str
) -> None:
    step = session.step
    dispatch = {
        'ask_title':       _pj_got_title,
        'ask_category':    _pj_got_category,
        'ask_state':       _pj_got_state,
        'ask_description': _pj_got_description,
        'ask_job_type':    _pj_got_type,
        'confirm':         _pj_confirm,
    }
    handler = dispatch.get(step)
    if handler:
        handler(session, provider, to, text)
    else:
        session.reset()
        handle_unknown(session, provider, to)


# Step 1 — title
def _pj_got_title(
    session: WhatsAppSession, provider: MessagingProvider, to: str, text: str
) -> None:
    title = text.strip()
    if len(title) < 5:
        _send(provider, session, to,
              "⚠️ Title too short — please give a descriptive title (at least 5 characters).")
        return
    if len(title) > 200:
        _send(provider, session, to, "⚠️ Title is too long. Please keep it under 200 characters.")
        return

    from jobs.models import TradeCategory
    categories = list(
        TradeCategory.objects.filter(is_active=True).order_by('display_order', 'name')
    )

    session.data['title'] = title
    session.data['categories'] = [
        {'id': str(c.id), 'name': c.name} for c in categories
    ]
    session.step = 'ask_category'
    session.save()

    lines = [
        f"✅ *Title:* {title}\n",
        "*Step 2 of 5* — Which *trade category* best fits this job?\n",
    ]
    for i, cat in enumerate(categories, 1):
        lines.append(f"{i}. {cat.name}")
    lines.append("\n_Reply with the number._")
    _send(provider, session, to, '\n'.join(lines))


# Step 2 — category
def _pj_got_category(
    session: WhatsAppSession, provider: MessagingProvider, to: str, text: str
) -> None:
    categories = session.data.get('categories', [])

    selected = None
    # Numeric selection
    try:
        idx = int(text.strip()) - 1
        if 0 <= idx < len(categories):
            selected = categories[idx]
    except ValueError:
        pass

    # Text match fallback
    if not selected:
        name_lower = text.strip().lower()
        selected = next(
            (c for c in categories if c['name'].lower() == name_lower), None
        )

    if not selected:
        _send(provider, session, to,
              f"Please reply with a number between 1 and {len(categories)}.")
        return

    session.data['category_id']   = selected['id']
    session.data['category_name'] = selected['name']
    # Categories no longer needed — trim session data
    del session.data['categories']
    session.step = 'ask_state'
    session.save()

    _send(
        provider, session, to,
        f"✅ *Category:* {selected['name']}\n\n"
        "*Step 3 of 5* — Which *state* is the job located in?\n\n"
        f"Available states:\n{NIGERIAN_STATES_DISPLAY}\n\n"
        "_Type the state name e.g. Lagos, Abuja, Rivers_",
    )


# Step 3 — state
def _pj_got_state(
    session: WhatsAppSession, provider: MessagingProvider, to: str, text: str
) -> None:
    result = _resolve_state(text)
    if not result:
        _send(
            provider, session, to,
            "⚠️ State not recognised. Please type a valid Nigerian state.\n"
            "_e.g. Lagos, Abuja, Rivers, Kano, Oyo_",
        )
        return

    state_slug, state_label = result
    session.data['state']         = state_slug
    session.data['state_display'] = state_label
    session.step = 'ask_description'
    session.save()

    _send(
        provider, session, to,
        f"✅ *Location:* {state_label}\n\n"
        "*Step 4 of 5* — Please *describe the job* in detail.\n\n"
        "_Include specifics like: what needs to be done, available materials, "
        "timeline, access conditions, etc._\n\n"
        "_Minimum 20 characters._",
    )


# Step 4 — description
def _pj_got_description(
    session: WhatsAppSession, provider: MessagingProvider, to: str, text: str
) -> None:
    desc = text.strip()
    if len(desc) < 20:
        _send(
            provider, session, to,
            "⚠️ Description too short. Please provide more detail (at least 20 characters).",
        )
        return
    if len(desc) > 3000:
        _send(
            provider, session, to,
            "⚠️ Description too long. Please shorten it to under 3000 characters.",
        )
        return

    session.data['description'] = desc
    session.step = 'ask_job_type'
    session.save()

    _send(
        provider, session, to,
        "✅ *Description recorded.*\n\n"
        "*Step 5 of 5* — What *type of job* is this?\n\n"
        "1️⃣  One-Off / Gig\n"
        "2️⃣  Full-Time\n"
        "3️⃣  Contract\n"
        "4️⃣  Part-Time\n\n"
        "_Reply with a number._",
    )


# Step 5 — job type
def _pj_got_type(
    session: WhatsAppSession, provider: MessagingProvider, to: str, text: str
) -> None:
    result = JOB_TYPE_MAP.get(text.strip().lower())
    if not result:
        _send(
            provider, session, to,
            "Please reply with 1, 2, 3, or 4 to select the job type.\n\n"
            "1️⃣ One-Off / Gig  2️⃣ Full-Time  3️⃣ Contract  4️⃣ Part-Time",
        )
        return

    job_type_value, job_type_label = result
    session.data['job_type']       = job_type_value
    session.data['job_type_label'] = job_type_label
    session.step = 'confirm'
    session.save()

    d = session.data
    desc_preview = d['description'][:250] + ('…' if len(d['description']) > 250 else '')
    _send(
        provider, session, to,
        "📋 *Job Summary — Please Confirm*\n\n"
        f"• *Title:* {d['title']}\n"
        f"• *Category:* {d['category_name']}\n"
        f"• *Location:* {d['state_display']}\n"
        f"• *Type:* {job_type_label}\n"
        f"• *Description:* {desc_preview}\n\n"
        "Reply *YES* to post this job or *NO* to cancel.",
    )


# Confirm step
def _pj_confirm(
    session: WhatsAppSession, provider: MessagingProvider, to: str, text: str
) -> None:
    answer = text.strip().lower()
    if answer in ('yes', 'y', 'confirm', 'ok', 'okay', 'post', 'submit', 'proceed'):
        _pj_create(session, provider, to)
    elif answer in ('no', 'n'):
        session.reset()
        _send(
            provider, session, to,
            "❌ Job post cancelled.\n\nType *menu* to go back to the main menu.",
        )
    else:
        _send(provider, session, to,
              "Please reply *YES* to post this job or *NO* to cancel.")


def _pj_create(
    session: WhatsAppSession, provider: MessagingProvider, to: str
) -> None:
    """Create the Job object in the database and notify the user."""
    from jobs.models import EmployerProfile, Job

    user = session.user
    d    = session.data

    try:
        # Ensure the user has an EmployerProfile (create one if not)
        try:
            employer = user.employer_profile
        except EmployerProfile.DoesNotExist:
            employer = EmployerProfile.objects.create(
                user=user,
                company_name=user.get_full_name() or user.username,
            )

        job = Job.objects.create(
            employer=employer,
            trade_category_id=d['category_id'],
            title=d['title'],
            description=d['description'],
            state=d['state'],
            job_type=d['job_type'],
            pay_type=Job.PayType.NEGOTIABLE,
            status=Job.Status.ACTIVE,
        )

        session.reset()
        short_id = str(job.id)[:8].upper()
        _send(
            provider, session, to,
            f"🎉 *Job Posted Successfully!*\n\n"
            f"*{job.title}* is now live and workers will start applying soon.\n\n"
            f"📌 Job ID: #{short_id}\n\n"
            f"🌐 Manage your jobs at:\n"
            f"*tradelinkng.com/jobs/my-jobs*\n\n"
            f"Type *menu* to return to the main menu.",
        )

    except Exception:
        logger.exception('Failed to create job for session %s', session.id)
        session.reset()
        _send(
            provider, session, to,
            "⚠️ Something went wrong while posting the job.\n\n"
            "Please try again or visit *tradelinkng.com* to post directly.",
        )
