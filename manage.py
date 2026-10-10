#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys

# ── pgvector Python package path ─────────────────────────────────────────────
# The pgvector package was installed to a user-writable directory because the
# shared venv's site-packages is owned by BUILTIN\Administrators.
# This path is added early so all management commands, migrations and Celery
# tasks can `import pgvector` without any extra setup.
_EXTRA_PKGS = r'C:\Users\hp\py_extra_pkgs'
if _EXTRA_PKGS not in sys.path:
    sys.path.insert(0, _EXTRA_PKGS)
# ─────────────────────────────────────────────────────────────────────────────


def main():
    """Run administrative tasks."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "technicians.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
