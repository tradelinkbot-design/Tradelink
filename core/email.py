"""
core/email.py
=============
Centralised email dispatch layer for TradeLink NG.

Routing logic:
    DEBUG=True  → Gmail SMTP via Django's built-in EmailMultiAlternatives
                  (uses EMAIL_HOST / EMAIL_HOST_USER / EMAIL_HOST_PASSWORD)
    DEBUG=False → Resend HTTP API via the official `resend` SDK
                  (uses RESEND_API_KEY; never touches SMTP ports)

Usage
-----
    from core.email import send_email

    send_email(
        subject="Your subject",
        to="user@example.com",          # str or list[str]
        html_content="<p>Hello</p>",
        text_content="Hello",           # optional plain-text fallback
    )

Returns True on success, False on failure (errors are always logged).
"""

from __future__ import annotations

import logging
from typing import Union

from django.conf import settings
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


def send_email(
    *,
    subject: str,
    to: Union[str, list[str]],
    html_content: str,
    text_content: str | None = None,
    from_email: str | None = None,
) -> bool:
    """
    Send a transactional email.

    Parameters
    ----------
    subject      : Email subject line.
    to           : Recipient address(es) — a single string or a list.
    html_content : HTML body of the email.
    text_content : Plain-text fallback. Auto-stripped from HTML when omitted.
    from_email   : Sender address. Defaults to settings.DEFAULT_FROM_EMAIL.

    Returns
    -------
    True if the email was accepted by the provider, False otherwise.
    """
    if isinstance(to, str):
        to = [to]

    sender = from_email or settings.DEFAULT_FROM_EMAIL
    plain  = text_content or strip_tags(html_content)

    if settings.DEBUG:
        return _send_via_gmail(subject=subject, to=to, sender=sender,
                               html_content=html_content, text_content=plain)
    else:
        return _send_via_resend(subject=subject, to=to, sender=sender,
                                html_content=html_content, text_content=plain)


# ── Private helpers ────────────────────────────────────────────────────────────

def _send_via_gmail(
    *,
    subject: str,
    to: list[str],
    sender: str,
    html_content: str,
    text_content: str,
) -> bool:
    """Development path: Django SMTP backend → Gmail."""
    from django.core.mail import EmailMultiAlternatives

    try:
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=sender,
            to=to,
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)

        logger.info("Email sent via Gmail SMTP to %s | subject: %r", to, subject)
        return True

    except Exception as exc:
        logger.exception("Gmail SMTP send failed to %s: %s", to, exc)
        return False


def _send_via_resend(
    *,
    subject: str,
    to: list[str],
    sender: str,
    html_content: str,
    text_content: str,
) -> bool:
    """Production path: Resend HTTP API (port 443 — bypasses all SMTP blocks)."""
    import resend

    api_key = getattr(settings, 'RESEND_API_KEY', '')
    if not api_key:
        logger.error(
            "RESEND_API_KEY is not set — cannot send email to %s. "
            "Add it to your production environment variables.",
            to,
        )
        return False

    resend.api_key = api_key

    try:
        params: resend.Emails.SendParams = {
            "from":    sender,
            "to":      to,
            "subject": subject,
            "html":    html_content,
            "text":    text_content,
        }
        response = resend.Emails.send(params)
        email_id = response.get("id") if isinstance(response, dict) else getattr(response, "id", None)
        logger.info(
            "Email sent via Resend to %s | subject: %r | id: %s",
            to, subject, email_id,
        )
        return True

    except Exception as exc:
        logger.exception("Resend API send failed to %s: %s", to, exc)
        return False
