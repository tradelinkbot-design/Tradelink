"""
WSGI config for technicians project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.0/howto/deployment/wsgi/
"""

import os
import sys

# ── pgvector Python package path ──────────────────────────────────────────────
_EXTRA_PKGS = r'C:\Users\hp\py_extra_pkgs'
if _EXTRA_PKGS not in sys.path:
    sys.path.insert(0, _EXTRA_PKGS)
# ─────────────────────────────────────────────────────────────────────────────

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "technicians.settings")

application = get_wsgi_application()
