"""
bot/views.py
============
Webhook endpoints for both Meta WhatsApp Business Cloud API and Twilio.

Endpoints
─────────
GET  /bot/webhook/         — Meta verification challenge (one-time setup)
POST /bot/webhook/         — Incoming messages from Meta WhatsApp
POST /bot/twilio/webhook/  — Incoming messages from Twilio (WhatsApp or SMS)

Active provider is controlled by BOT_PROVIDER in settings:
    'twilio' (default) — route to TwilioWebhookView
    'meta'             — route to BotWebhookView

Both endpoints remain active simultaneously so you can switch providers
with a single env-var change and a redeploy, without touching URL configs.

Security
────────
• Meta GET  requests are verified against WHATSAPP_VERIFY_TOKEN in settings.
• Meta POST requests are verified via X-Hub-Signature-256 HMAC.
• Twilio POST requests are verified via X-Twilio-Signature (TwilioProvider.validate_signature).
• If credentials are blank (dev mode), signature checks are skipped.
"""

import hashlib
import hmac
import json
import logging

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from .handlers import MessageRouter
from .models import WhatsAppSession
from .providers import get_provider
from core.ratelimit import rate_limit

logger = logging.getLogger(__name__)


# ── Shared session-dispatch helper ────────────────────────────────────────────

def _dispatch_message(from_number: str, text: str, message_id: str) -> None:
    """
    Look up (or create) the WhatsAppSession for ``from_number``, then
    run the MessageRouter with the currently configured provider.

    Called by both BotWebhookView and TwilioWebhookView after each has
    normalised its payload to (from_number, text, message_id).
    """
    # Use select_related so session.user never triggers a second DB query
    try:
        session = WhatsAppSession.objects.select_related('user').get(
            phone_number=from_number
        )
    except WhatsAppSession.DoesNotExist:
        session = WhatsAppSession.objects.create(
            phone_number=from_number,
            flow=WhatsAppSession.Flow.IDLE,
        )

    provider = get_provider()
    router = MessageRouter(session, from_number, text, message_id, provider)
    router.dispatch()


# ── Meta WhatsApp webhook ─────────────────────────────────────────────────────

def _verify_meta_signature(request) -> bool:
    """
    Verify the X-Hub-Signature-256 header sent by Meta.
    Returns True if valid or if access token is not configured (dev mode).
    """
    token = getattr(settings, 'WHATSAPP_ACCESS_TOKEN', '')
    if not token:
        return True  # Dev / test mode — skip verification

    signature_header = request.headers.get('X-Hub-Signature-256', '')
    if not signature_header.startswith('sha256='):
        return False

    expected = hmac.new(
        token.encode('utf-8'),
        msg=request.body,
        digestmod=hashlib.sha256,
    ).hexdigest()

    received = signature_header[len('sha256='):]
    return hmac.compare_digest(expected, received)


def _extract_meta_message(payload: dict):
    """
    Extract (from_number, text, message_id) from a WhatsApp Cloud API payload.
    Returns None if the payload does not contain a text message.
    """
    try:
        entry   = payload['entry'][0]
        changes = entry['changes'][0]
        value   = changes['value']
        message = value['messages'][0]

        # Only handle text messages for now (ignore image, audio, reaction, etc.)
        if message.get('type') != 'text':
            return None

        from_number = message['from']              # E.164 without +
        text        = message['text']['body']
        message_id  = message.get('id', '')
        return from_number, text, message_id
    except (KeyError, IndexError, TypeError):
        return None


@method_decorator(csrf_exempt, name='dispatch')
class BotWebhookView(View):
    """Handles Meta webhook verification (GET) and incoming messages (POST)."""

    # ── GET — webhook verification ────────────────────────────────────────────

    def get(self, request, *args, **kwargs):
        """
        Meta calls this endpoint once when you register the webhook in the
        Meta developer dashboard.  It sends three query params and expects
        the hub.challenge value back as a plain-text 200 response.
        """
        mode      = request.GET.get('hub.mode')
        token     = request.GET.get('hub.verify_token')
        challenge = request.GET.get('hub.challenge')

        verify_token = getattr(settings, 'WHATSAPP_VERIFY_TOKEN', '')

        if mode == 'subscribe' and token == verify_token:
            logger.info('Meta WhatsApp webhook verified successfully.')
            return HttpResponse(challenge, content_type='text/plain')

        logger.warning(
            'Meta WhatsApp webhook verification failed. mode=%s token=%s', mode, token
        )
        return HttpResponse('Forbidden', status=403)

    # ── POST — incoming messages ──────────────────────────────────────────────

    @rate_limit(key='meta_webhook:{ip}', limit=60, window=60, message='Too many webhook requests.', json=True)
    def post(self, request, *args, **kwargs):
        """
        Receives incoming WhatsApp messages from Meta.  Always returns 200
        immediately so Meta does not retry; actual processing is synchronous.
        """
        if not _verify_meta_signature(request):
            logger.warning(
                'Meta webhook: invalid signature from %s',
                request.META.get('REMOTE_ADDR'),
            )
            return HttpResponse('Unauthorized', status=401)

        try:
            payload = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return HttpResponse('Bad Request', status=400)

        # Confirm it is a whatsapp_business_account event
        if payload.get('object') != 'whatsapp_business_account':
            return JsonResponse({'status': 'ignored'})

        extracted = _extract_meta_message(payload)
        if not extracted:
            # Status updates, read receipts, non-text messages — acknowledge & ignore
            return JsonResponse({'status': 'ok'})

        from_number, text, message_id = extracted
        _dispatch_message(from_number, text, message_id)
        return JsonResponse({'status': 'ok'})


# ── Twilio webhook ────────────────────────────────────────────────────────────

@method_decorator(csrf_exempt, name='dispatch')
class TwilioWebhookView(View):
    """
    Handles incoming WhatsApp (or SMS) messages from Twilio.

    Twilio posts form-encoded data with fields:
        From        — 'whatsapp:+2348012345678'  (or 'sms:+...' for SMS)
        Body        — message text
        MessageSid  — unique message identifier (Twilio equivalent of wamid)

    The 'whatsapp:+' prefix is stripped before storing in WhatsAppSession
    so the phone_number column format is consistent regardless of provider.

    Webhook URL to configure in Twilio Console:
        POST https://yourdomain.com/bot/twilio/webhook/
    """

    @rate_limit(key='twilio_webhook:{ip}', limit=60, window=60, message='Too many webhook requests.', json=True)
    def post(self, request, *args, **kwargs):
        """
        Validate Twilio signature, extract message, dispatch to MessageRouter.
        Always returns a 200 TwiML response (empty <Response/>) so Twilio
        does not retry.  Actual replies are sent via the REST API in handlers.
        """
        from .providers.twilio_provider import TwilioProvider

        if not TwilioProvider.validate_signature(request):
            logger.warning(
                'Twilio webhook: invalid signature from %s',
                request.META.get('REMOTE_ADDR'),
            )
            return HttpResponse('Forbidden', status=403)

        from_raw   = request.POST.get('From', '')
        body       = request.POST.get('Body', '').strip()
        message_id = request.POST.get('MessageSid', '')

        if not from_raw or not body:
            # Delivery status callbacks have no Body — acknowledge & ignore
            return HttpResponse(
                '<?xml version="1.0" encoding="UTF-8"?><Response/>',
                content_type='text/xml',
            )

        # Normalise Twilio From to bare E.164: 'whatsapp:+2348012345678' → '2348012345678'
        from_number = from_raw
        for prefix in ('whatsapp:', 'sms:', 'messenger:'):
            from_number = from_number.replace(prefix, '')
        from_number = from_number.lstrip('+').strip()

        logger.info(
            'Twilio inbound | from=%s | sid=%s | body_len=%d',
            from_number, message_id, len(body),
        )

        try:
            _dispatch_message(from_number, body, message_id)
        except Exception:
            logger.exception(
                'Unhandled error in Twilio webhook for %s', from_number
            )

        # Always return empty TwiML — replies are sent via REST API
        return HttpResponse(
            '<?xml version="1.0" encoding="UTF-8"?><Response/>',
            content_type='text/xml',
        )
