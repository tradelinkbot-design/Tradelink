"""
verification/service/dojah_client.py
=====================================
Thin Python client for the Dojah KYC API.

Supported endpoints:
  • NIN Lookup   — /api/v1/kyc/nin
  • BVN Lookup   — /api/v1/kyc/bvn
  • CAC Lookup   — /api/v1/kyc/cac/company

All methods return a dict:
  {
    'success': bool,
    'ref':     str,          # Dojah transaction reference
    'data':    dict | None,  # raw entity data from Dojah on success
    'error':   str,          # human-readable error on failure
  }
"""

import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class DojahClient:
    """Wrapper around the Dojah REST API."""

    def __init__(self):
        self.app_id  = settings.DOJAH_APP_ID
        self.api_key = settings.DOJAH_API_KEY
        self.base_url = (settings.DOJAH_BASE_URL or 'https://api.dojah.io').rstrip('/')

    @property
    def _headers(self):
        return {
            'AppId':        self.app_id,
            'Authorization': self.api_key,
            'Accept':       'application/json',
            'Content-Type': 'application/json',
        }

    def _get(self, path: str, params: dict) -> dict:
        """Make a GET request to Dojah and normalise the response."""
        url = f'{self.base_url}{path}'
        try:
            resp = requests.get(url, headers=self._headers, params=params, timeout=15)
            payload = resp.json()
        except requests.Timeout:
            logger.error('Dojah timeout: %s', path)
            return {'success': False, 'ref': '', 'data': None,
                    'error': 'Dojah API timed out. Please try again.'}
        except Exception as exc:
            logger.exception('Dojah request error: %s', exc)
            return {'success': False, 'ref': '', 'data': None,
                    'error': f'Network error: {exc}'}

        ref = payload.get('reference', '') or payload.get('ref', '')

        # Dojah returns HTTP 200 even for logical failures; check entity field
        entity = payload.get('entity', payload.get('data', {})) or {}

        # Detect failure: empty entity or explicit error key
        if not entity or payload.get('error'):
            err = payload.get('error') or 'Verification failed — no matching record found.'
            logger.warning('Dojah verification failed (%s): %s', path, err)
            return {'success': False, 'ref': ref, 'data': None, 'error': err}

        if resp.status_code not in (200, 201):
            err = payload.get('error', f'Unexpected HTTP {resp.status_code}')
            return {'success': False, 'ref': ref, 'data': None, 'error': err}

        return {'success': True, 'ref': ref, 'data': entity, 'error': ''}

    # ── NIN ───────────────────────────────────────────────────────────────────

    def verify_nin(self, nin: str) -> dict:
        """
        Lookup a National Identification Number.
        Returns the holder's first/last name, DOB, gender, photo, etc.
        """
        return self._get('/api/v1/kyc/nin', {'nin': nin})

    # ── BVN ───────────────────────────────────────────────────────────────────

    def verify_bvn(self, bvn: str) -> dict:
        """
        Lookup a Bank Verification Number.
        Returns the holder's first/last name, phone, DOB, etc.
        """
        return self._get('/api/v1/kyc/bvn', {'bvn': bvn})

    # ── CAC ───────────────────────────────────────────────────────────────────

    def verify_cac(self, rc_number: str) -> dict:
        """
        Lookup a Corporate Affairs Commission registration number.
        Returns company name, status, date registered, directors, etc.
        """
        return self._get('/api/v1/kyc/cac/advance', {'rc_number': rc_number})


# Singleton — import this everywhere
dojah = DojahClient()
