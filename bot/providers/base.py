"""
bot/providers/base.py
=====================
Abstract base class that every messaging provider must implement.

A "provider" is responsible for:
  1. Sending messages (text, buttons, lists, templates) to a phone number.
  2. Nothing else — all conversation logic lives in handlers.py.

Default implementations of send_buttons / send_list fall back to
numbered plain-text so that Twilio (which lacks Meta's interactive widgets)
works out of the box.  When running under Meta, the concrete MetaProvider
overrides those methods to use rich interactive payloads.

Phone-number convention
-----------------------
All ``to`` arguments are E.164 strings **without** a leading ``+``,
matching what the WhatsAppSession.phone_number column stores
(e.g. ``'2348012345678'``).  Each provider prepends / formats as needed
internally.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class MessagingProvider(ABC):
    """
    Contract every channel adapter must fulfil.

    Concrete providers: TwilioProvider, MetaProvider.
    """

    # ── Required ─────────────────────────────────────────────────────────────

    @abstractmethod
    def send_text(self, to: str, body: str) -> dict:
        """
        Send a plain-text message.

        :param to:   Destination phone number (E.164 without leading +).
        :param body: Message text (may include WhatsApp markdown: *bold*, _italic_).
        :returns:    Provider-specific response dict (used for logging/debugging).
        :raises:     Any exception on API failure — callers should handle.
        """

    # ── Optional (default: plain-text fallback) ───────────────────────────────

    def send_buttons(
        self,
        to: str,
        body: str,
        buttons: list[dict],
        header: str = '',
        footer: str = '',
    ) -> dict:
        """
        Send a message with quick-reply buttons.

        ``buttons`` — list of ``{'id': str, 'title': str}``.

        Default: renders as a numbered plain-text list so providers that
        don't support interactive messages still work.
        """
        lines = []
        if header:
            lines.append(f'*{header}*\n')
        lines.append(body)
        lines.append('')
        for i, btn in enumerate(buttons, 1):
            lines.append(f'{i}. {btn["title"]}')
        if footer:
            lines.append(f'\n_{footer}_')
        return self.send_text(to, '\n'.join(lines))

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
        Send a list-picker message.

        ``sections`` — list of ``{'title': str, 'rows': [{'id', 'title', 'description'}]}``.

        Default: renders as numbered plain-text grouped by section.
        """
        lines = []
        if header:
            lines.append(f'*{header}*\n')
        lines.append(body)
        lines.append('')
        counter = 1
        for section in sections:
            if section.get('title'):
                lines.append(f"*{section['title']}*")
            for row in section.get('rows', []):
                desc = f" — {row['description']}" if row.get('description') else ''
                lines.append(f'{counter}. {row["title"]}{desc}')
                counter += 1
        if footer:
            lines.append(f'\n_{footer}_')
        return self.send_text(to, '\n'.join(lines))

    def send_template(
        self,
        to: str,
        template_name: str,
        language_code: str = 'en_US',
        components: list | None = None,
    ) -> dict:
        """
        Send a pre-approved template message.

        Default: logs a warning and no-ops (Twilio uses a different
        content-template mechanism).
        """
        logger.warning(
            '%s.send_template() not implemented — skipping template "%s" to +%s',
            self.__class__.__name__, template_name, to,
        )
        return {}
