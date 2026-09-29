"""
bot/providers/meta_provider.py
===============================
Messaging provider for the Meta WhatsApp Business Cloud API.

This is a refactored version of the original bot/client.py, now conforming
to the MessagingProvider interface.  All original functionality is preserved:
  • Plain-text messages
  • Interactive quick-reply buttons (up to 3)
  • Interactive list messages (up to 10 rows)
  • Template messages

Credentials read from Django settings:
    WHATSAPP_PHONE_NUMBER_ID  — phone number ID from Meta developer dashboard
    WHATSAPP_ACCESS_TOKEN     — permanent / temporary access token
    WHATSAPP_API_VERSION      — defaults to v19.0

Activate by setting  BOT_PROVIDER=meta  in your .env.
"""

import logging

import requests
from django.conf import settings

from .base import MessagingProvider

logger = logging.getLogger(__name__)

_GRAPH_BASE = 'https://graph.facebook.com'


class MetaProvider(MessagingProvider):
    """
    Provider for Meta WhatsApp Business Cloud API.

    Full interactive-message support (buttons, list pickers, templates).
    """

    def __init__(self):
        self.phone_number_id = getattr(settings, 'WHATSAPP_PHONE_NUMBER_ID', '')
        self.access_token    = getattr(settings, 'WHATSAPP_ACCESS_TOKEN', '')
        self.api_version     = getattr(settings, 'WHATSAPP_API_VERSION', 'v19.0')
        self.endpoint = (
            f'{_GRAPH_BASE}/{self.api_version}'
            f'/{self.phone_number_id}/messages'
        )

    # ── Private helpers ──────────────────────────────────────────────────────

    def _headers(self) -> dict:
        return {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type':  'application/json',
        }

    def _base_payload(self, to: str) -> dict:
        return {
            'messaging_product': 'whatsapp',
            'recipient_type':    'individual',
            'to':                to,
        }

    def _post(self, payload: dict) -> dict:
        """POST to the messages endpoint; log and re-raise on failure."""
        try:
            resp = requests.post(
                self.endpoint,
                json=payload,
                headers=self._headers(),
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.HTTPError as exc:
            logger.error(
                'Meta WhatsApp API HTTP error %s: %s',
                exc.response.status_code,
                exc.response.text[:500],
            )
            raise
        except requests.RequestException as exc:
            logger.error('Meta WhatsApp request failed: %s', exc)
            raise

    # ── MessagingProvider interface ──────────────────────────────────────────

    def send_text(self, to: str, body: str) -> dict:
        """Send a plain-text WhatsApp message."""
        payload = self._base_payload(to)
        payload.update({
            'type': 'text',
            'text': {'preview_url': False, 'body': body},
        })
        return self._post(payload)

    def send_buttons(
        self,
        to: str,
        body: str,
        buttons: list[dict],
        header: str = '',
        footer: str = '',
    ) -> dict:
        """
        Send an interactive message with up to 3 quick-reply buttons.

        ``buttons`` — list of ``{'id': str, 'title': str}`` (title max 20 chars).
        """
        btn_objs = [
            {'type': 'reply', 'reply': {'id': b['id'], 'title': b['title'][:20]}}
            for b in buttons[:3]
        ]
        interactive: dict = {
            'type':   'button',
            'body':   {'text': body},
            'action': {'buttons': btn_objs},
        }
        if header:
            interactive['header'] = {'type': 'text', 'text': header[:60]}
        if footer:
            interactive['footer'] = {'text': footer[:60]}

        payload = self._base_payload(to)
        payload.update({'type': 'interactive', 'interactive': interactive})
        return self._post(payload)

    def send_list(
        self,
        to: str,
        body: str,
        sections: list[dict],
        button_label: str = 'Select',
        header: str = '',
        footer: str = '',
    ) -> dict:
        """
        Send an interactive list message (max 10 rows total across all sections).

        ``sections`` — list of::

            {
                'title': str,
                'rows': [{'id': str, 'title': str, 'description': str}]
            }
        """
        interactive: dict = {
            'type': 'list',
            'body': {'text': body},
            'action': {
                'button':   button_label[:20],
                'sections': sections,
            },
        }
        if header:
            interactive['header'] = {'type': 'text', 'text': header[:60]}
        if footer:
            interactive['footer'] = {'text': footer[:60]}

        payload = self._base_payload(to)
        payload.update({'type': 'interactive', 'interactive': interactive})
        return self._post(payload)

    def send_template(
        self,
        to: str,
        template_name: str,
        language_code: str = 'en_US',
        components: list | None = None,
    ) -> dict:
        """Send a pre-approved WhatsApp template message."""
        template: dict = {
            'name':     template_name,
            'language': {'code': language_code},
        }
        if components:
            template['components'] = components

        payload = self._base_payload(to)
        payload.update({'type': 'template', 'template': template})
        return self._post(payload)
