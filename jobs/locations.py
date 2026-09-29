"""
jobs/locations.py
=================
Provides helper functions for Nigerian States and Local Government Areas (LGAs)
sourced from open-source GitHub datasets (devhammed/nigeria-state-and-lgas).
"""

import json
from pathlib import Path

_DATA_FILE = Path(__file__).resolve().parent / 'data' / 'nigeria_states_lgas.json'
_CACHE = None


def get_nigerian_states_lgas():
    """
    Returns a dictionary mapping state codes (e.g. 'lagos', 'abuja', 'enugu')
    to sorted lists of their LGA names.
    """
    global _CACHE
    if _CACHE is None:
        try:
            with open(_DATA_FILE, 'r', encoding='utf-8') as f:
                _CACHE = json.load(f)
        except Exception:
            _CACHE = {}
    return _CACHE


def get_lgas_for_state(state_code):
    """
    Returns a list of LGA names for a given state code.
    e.g. get_lgas_for_state('lagos') -> ['Agege', 'Ajeromi-Ifelodun', ...]
    """
    if not state_code:
        return []
    data = get_nigerian_states_lgas()
    return data.get(state_code.strip().lower(), [])
