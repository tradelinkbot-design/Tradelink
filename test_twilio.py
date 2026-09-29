"""
test_twilio.py
==============
Quick sanity-check for the Twilio messaging provider.

Run from the project root with Django configured:

    python test_twilio.py <phone_number>

Where <phone_number> is the destination in E.164 format WITHOUT the leading +
e.g.:  python test_twilio.py 2348012345678

The script will:
1. Print the active BOT_PROVIDER
2. Initialise the provider via get_provider()
3. Send a test message to the given number
4. Print the provider response (Twilio SID / status)

Prerequisites
─────────────
• TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER set in .env
• The destination number has sent "join <keyword>" to the Twilio sandbox
  (for sandbox testing) OR is a verified Twilio number (for production)
• BOT_PROVIDER=twilio in .env
"""

import os
import sys

# ── Load .env FIRST before anything Django-related ───────────────────────────
from dotenv import load_dotenv
load_dotenv()

import django

# Bootstrap Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'technicians.settings')
django.setup()

from django.conf import settings  # noqa: E402 — must be after django.setup()


def _check_credentials():
    """Fail fast with a clear message if any required credential is missing."""
    required = {
        'TWILIO_ACCOUNT_SID': getattr(settings, 'TWILIO_ACCOUNT_SID', ''),
        'TWILIO_AUTH_TOKEN':  getattr(settings, 'TWILIO_AUTH_TOKEN', ''),
        'TWILIO_FROM_NUMBER': getattr(settings, 'TWILIO_FROM_NUMBER', ''),
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        print('\n❌ Missing credentials — not loaded from .env:')
        for key in missing:
            print(f'   • {key}')
        print('\nMake sure your .env file exists in the project root and contains these keys.')
        print('Also confirm your settings.py calls load_dotenv() near the top.\n')
        sys.exit(1)


def main():
    if len(sys.argv) < 2:
        print('Usage: python test_twilio.py <phone_number>')
        print('Example: python test_twilio.py 2348012345678')
        sys.exit(1)

    # Check credentials before doing anything else
    _check_credentials()

    phone = sys.argv[1].lstrip('+')
    provider_name = getattr(settings, 'BOT_PROVIDER', 'twilio')

    print(f'\n{"="*60}')
    print(f'  BOT_PROVIDER : {provider_name}')
    print(f'  Sending to   : +{phone}')
    print(f'{"="*60}\n')

    from bot.providers import get_provider
    provider = get_provider()
    print(f'Provider class : {provider.__class__.__name__}')

    if provider_name == 'twilio':
        sid = settings.TWILIO_ACCOUNT_SID
        print(f'Twilio SID     : {sid[:10]}...')
        print(f'From number    : {settings.TWILIO_FROM_NUMBER}')

    print('\nSending test message...')
    try:
        result = provider.send_text(
            phone,
            '✅ *TradeLink NG Bot* — Test message sent successfully!\n\n'
            'If you received this, your bot is working. 🚀\n\n'
            'Reply *menu* to see what the bot can do.',
        )
        print(f'\n✅ Message sent! Provider response:')
        print(f'   {result}')
    except Exception as exc:
        print(f'\n❌ Failed to send message: {exc}')
        sys.exit(1)

    print('\nDone.')


if __name__ == '__main__':
    main()