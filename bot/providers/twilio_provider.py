"""
bot/providers/twilio_provider.py
=================================
Messaging provider for the Twilio Messaging API (WhatsApp + SMS).

Uses the official ``twilio`` Python SDK.  Supports:
  • WhatsApp messages via Twilio WhatsApp Sandbox or an approved Sender
  • Plain-text messages (send_text)
  • Interactive messages fall back to numbered plain-text (Twilio does not
    support Meta-style interactive buttons/lists)
  • Webhook signature validation via twilio.request_validator

Credentials read from Django settings:
    TWILIO_ACCOUNT_SID  — your Twilio Account SID (AC…)
    TWILIO_AUTH_TOKEN   — your Twilio Auth Token
    TWILIO_FROM_NUMBER  — the WhatsApp-enabled Twilio number in E.164 format
                          e.g. '+14155238886' (sandbox) or your approved number

Phone-number convention
-----------------------
Inbound ``From`` values arrive from Twilio as 'whatsapp:+2348012345678'.
The view strips the 'whatsapp:+' prefix before passing to MessageRouter
so the stored phone_number is always bare E.164 (2348012345678).

Activate by setting  BOT_PROVIDER=twilio  in your .env.
"""

import logging

from django.conf import settings

from .base import MessagingProvider

logger = logging.getLogger(__name__)


class TwilioProvider(MessagingProvider):
    """
    Provider for the Twilio WhatsApp Messaging API.

    send_buttons() and send_list() fall back to numbered plain-text because
    Twilio WhatsApp does not support Meta-style interactive widgets.
    Full rich messages return automatically when you switch BOT_PROVIDER=meta.
    """

    def __init__(self):
        self.account_sid = getattr(settings, 'TWILIO_ACCOUNT_SID', '')
        self.auth_token  = getattr(settings, 'TWILIO_AUTH_TOKEN', '')
        self.from_number = getattr(settings, 'TWILIO_FROM_NUMBER', '')

        # Lazily import so the app doesn't crash if twilio isn't installed
        # and BOT_PROVIDER is set to 'meta'.
        try:
            from twilio.rest import Client
            self._client = Client(self.account_sid, self.auth_token)
        except ImportError:
            logger.error(
                'twilio package is not installed. '
                'Run: pip install "twilio>=9.0.0"'
            )
            self._client = None

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _whatsapp_address(self, number: str) -> str:
        """
        Convert a bare E.164 phone number to a Twilio WhatsApp address.
        e.g. '2348012345678' → 'whatsapp:+2348012345678'
        """
        clean = number.lstrip('+')
        return f'whatsapp:+{clean}'

    def _from_address(self) -> str:
        """
        Return the configured Twilio WhatsApp sender address.
        Handles both '+14155238886' and 'whatsapp:+14155238886' input formats.
        """
        number = self.from_number
        # Strip any existing whatsapp: prefix before re-adding
        if number.startswith('whatsapp:'):
            number = number[len('whatsapp:'):]
        number = number.lstrip('+')
        return f'whatsapp:+{number}'

    # ── MessagingProvider interface ──────────────────────────────────────────

    def send_text(self, to: str, body: str) -> dict:
        """
        Send a plain-text WhatsApp message via Twilio.

        :param to:   Destination phone number (E.164 without leading +).
        :param body: Message body text.
        :returns:    dict with ``sid`` and ``status`` from Twilio.
        :raises:     twilio.base.exceptions.TwilioRestException on API error.
        """
        if self._client is None:
            raise RuntimeError('Twilio client not initialised — check TWILIO_ACCOUNT_SID/AUTH_TOKEN.')

        try:
            message = self._client.messages.create(
                from_=self._from_address(),
                to=self._whatsapp_address(to),
                body=body,
            )
            logger.info(
                'Twilio message sent to +%s | SID=%s status=%s',
                to, message.sid, message.status,
            )
            return {'sid': message.sid, 'status': message.status}

        except Exception as exc:
            logger.error('Twilio send_text failed for +%s: %s', to, exc)
            raise

    # send_buttons() and send_list() intentionally inherit the plain-text
    # fallback from MessagingProvider.base — no override needed.

    # ── Webhook signature validation ─────────────────────────────────────────

    @staticmethod
    def validate_signature(request) -> bool:
        """
        Validate that an incoming webhook POST was signed by Twilio.

        Skipped automatically in two safe cases:
          1. DEBUG=True  — local development (ngrok URL reconstruction is
                           unreliable so signature checking always fails in dev)
          2. TWILIO_AUTH_TOKEN not set — unconfigured / test environment

        In production (DEBUG=False) full HMAC validation is enforced.

        Returns True  → request is valid / dev mode active
        Returns False → invalid signature (production only)
        """
        # ── Dev bypass (ngrok URL reconstruction is unreliable) ───────────────
        if getattr(settings, 'DEBUG', False):
            logger.debug('TwilioProvider: DEBUG=True, skipping signature check.')
            return True

        auth_token = getattr(settings, 'TWILIO_AUTH_TOKEN', '')
        if not auth_token:
            logger.debug('TwilioProvider: auth token not set, skipping signature check.')
            return True

        try:
            from twilio.request_validator import RequestValidator
        except ImportError:
            logger.error('twilio package not installed — cannot validate signature.')
            return False

        validator = RequestValidator(auth_token)

        # Build the full URL Twilio signed (must match what Twilio sent to).
        # Works behind reverse proxies / load balancers that set X-Forwarded-Proto.
        scheme = request.META.get('HTTP_X_FORWARDED_PROTO', request.scheme)
        host   = request.get_host()
        url    = f'{scheme}://{host}{request.path}'

        # Twilio POST params (form-encoded body)
        post_params = {k: v for k, v in request.POST.items()}

        signature = request.META.get('HTTP_X_TWILIO_SIGNATURE', '')

        valid = validator.validate(url, post_params, signature)
        if not valid:
            logger.warning(
                'Twilio signature validation FAILED for %s (signature=%s...)',
                url, signature[:20],
            )
        return valid