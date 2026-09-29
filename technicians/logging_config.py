"""
technicians/logging_config.py
=============================
Production-grade terminal and file logging configuration for Django, Daphne, Channels, and Celery.

Why this is needed:
By default in Django (when DEBUG=False), the 'django.request' logger routes 500 errors
ONLY to 'mail_admins' with 'propagate: False'. If ADMINS is not configured or email
fails, all unhandled 500 errors and tracebacks in production are completely SILENCED
from the terminal / stdout / stderr.

This module provides:
1. `ColoredTerminalFormatter`: Color-coded, high-visibility log formatter for terminal output.
2. `get_logging_config`: Generates the complete LOGGING dictionary for Django settings,
   ensuring django.request, application loggers, Daphne, Celery, and unhandled exceptions
   always print clearly to the terminal in production (and optionally rotate to logs/errors.log).
"""

import os
import sys
import logging
from pathlib import Path


class ColoredTerminalFormatter(logging.Formatter):
    """
    ANSI Color-coded log formatter for terminal output.
    Makes ERROR and CRITICAL logs immediately jump out in terminal output during production.
    Falls back gracefully to clean plain text if ANSI is disabled or unsupported.
    """

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # Foreground colors
    COLORS = {
        'DEBUG': "\033[36m",          # Cyan
        'INFO': "\033[32m",           # Green
        'WARNING': "\033[33m",        # Yellow
        'ERROR': "\033[1;31m",        # Bold Red
        'CRITICAL': "\033[1;37;41m",  # Bold White on Red Background
    }

    TB_HEADER = "\033[1;31m┌─── TRACEBACK (most recent call last) ──────────────────────────────────\033[0m"
    TB_FOOTER = "\033[1;31m└────────────────────────────────────────────────────────────────────────────\033[0m"

    def __init__(self, fmt=None, datefmt=None, style='%', validate=True, **kwargs):
        super().__init__(fmt=fmt, datefmt=datefmt, style=style, validate=validate)
        self.use_color = self._check_color_support()

    @staticmethod
    def _check_color_support() -> bool:
        """
        Check if terminal colors should be enabled.
        Honors NO_COLOR, FORCE_COLOR, and TERM environment variables.
        """
        if os.environ.get('NO_COLOR') or os.environ.get('TERM') == 'dumb':
            return False
        if os.environ.get('FORCE_COLOR'):
            return True
        # Modern terminal / Windows Terminal / Render / Heroku / Docker stdout supports ANSI
        if hasattr(sys.stderr, 'isatty') and sys.stderr.isatty():
            return True
        # Cloud container environments (Docker, Render, etc.) usually capture ANSI codes fine
        term = os.environ.get('TERM', '')
        return bool(term or os.environ.get('COLORTERM'))

    def format(self, record: logging.LogRecord) -> str:
        orig_levelname = record.levelname
        orig_msg = record.msg

        if self.use_color:
            color = self.COLORS.get(orig_levelname, '')
            # Pad level name to 8 characters for clean alignment
            record.levelname = f"{color}{orig_levelname:<8}{self.RESET}"

        formatted = super().format(record)

        # Restore original attributes so other handlers aren't mutated
        record.levelname = orig_levelname
        record.msg = orig_msg

        return formatted

    def formatException(self, ei) -> str:
        """Format traceback with distinct visual demarcation."""
        tb_text = super().formatException(ei)
        if self.use_color:
            # Highlight traceback in soft red
            colored_lines = []
            for line in tb_text.splitlines():
                colored_lines.append(f"\033[91m│ {line}\033[0m")
            tb_body = "\n".join(colored_lines)
            return f"\n{self.TB_HEADER}\n{tb_body}\n{self.TB_FOOTER}"
        else:
            return f"\n--- TRACEBACK ---\n{tb_text}\n-----------------"


def get_logging_config(base_dir: Path, debug: bool = False) -> dict:
    """
    Build the Django LOGGING configuration dictionary.

    Parameters:
    - base_dir: Path to the Django project root directory.
    - debug: Boolean indicating whether DEBUG mode is active.

    Returns:
    - dict: Configuration dictionary ready to assign to `LOGGING` in settings.py.
    """
    # Ensure logs directory exists
    logs_dir = Path(base_dir) / 'logs'
    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
        has_file_logging = True
    except Exception:
        has_file_logging = False

    # Default log levels (can be overridden via environment variable DJANGO_LOG_LEVEL)
    default_log_level = 'DEBUG' if debug else os.environ.get('DJANGO_LOG_LEVEL', 'INFO')
    error_log_level = 'ERROR'

    date_format = '%Y-%m-%d %H:%M:%S'
    terminal_format = '%(asctime)s [%(levelname)s] [%(name)s:%(lineno)d] %(message)s'
    file_format = '%(asctime)s [%(levelname)s] [%(name)s:%(lineno)d] [pid:%(process)d] %(message)s'

    handlers = {
        'console': {
            'level': default_log_level,
            'class': 'logging.StreamHandler',
            'stream': 'ext://sys.stderr',
            'formatter': 'colored_terminal',
        },
        'console_errors': {
            'level': 'ERROR',
            'class': 'logging.StreamHandler',
            'stream': 'ext://sys.stderr',
            'formatter': 'colored_terminal',
        },
    }

    # Add rotating file handlers if directory is writable
    if has_file_logging:
        handlers['file_errors'] = {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(logs_dir / 'errors.log'),
            'maxBytes': 10 * 1024 * 1024,  # 10 MB per file
            'backupCount': 5,
            'formatter': 'verbose',
            'encoding': 'utf-8',
        }
        handlers['file_all'] = {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(logs_dir / 'technicians.log'),
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'backupCount': 3,
            'formatter': 'verbose',
            'encoding': 'utf-8',
        }

    # Handlers attached to error loggers
    error_handlers = ['console_errors']
    if has_file_logging:
        error_handlers.append('file_errors')

    general_handlers = ['console']
    if has_file_logging:
        general_handlers.append('file_all')

    config = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'colored_terminal': {
                '()': 'technicians.logging_config.ColoredTerminalFormatter',
                'fmt': terminal_format,
                'datefmt': date_format,
            },
            'verbose': {
                'format': file_format,
                'datefmt': date_format,
            },
            'simple': {
                'format': '[%(levelname)s] %(message)s',
            },
        },
        'handlers': handlers,
        'loggers': {
            # CRITICAL: Overrides Django's silent production default for 500 errors!
            'django.request': {
                'handlers': error_handlers,
                'level': 'ERROR',
                'propagate': False,
            },
            'django.server': {
                'handlers': ['console'],
                'level': 'INFO',
                'propagate': False,
            },
            'django': {
                'handlers': ['console'],
                'level': 'WARNING',
                'propagate': False,
            },
            'django.db.backends': {
                'handlers': error_handlers,
                'level': 'ERROR',
                'propagate': False,
            },
            'daphne': {
                'handlers': ['console'],
                'level': 'INFO',
                'propagate': False,
            },
            'channels': {
                'handlers': ['console'],
                'level': 'INFO',
                'propagate': False,
            },
            'celery': {
                'handlers': ['console'],
                'level': 'INFO',
                'propagate': False,
            },
            # Dedicated production error logger for middleware banners
            'production.errors': {
                'handlers': error_handlers,
                'level': 'ERROR',
                'propagate': False,
            },
            # Application-level modules
            'users': {
                'handlers': general_handlers,
                'level': default_log_level,
                'propagate': False,
            },
            'marketplace': {
                'handlers': general_handlers,
                'level': default_log_level,
                'propagate': False,
            },
            'jobs': {
                'handlers': general_handlers,
                'level': default_log_level,
                'propagate': False,
            },
            'chats': {
                'handlers': general_handlers,
                'level': default_log_level,
                'propagate': False,
            },
            'bot': {
                'handlers': general_handlers,
                'level': default_log_level,
                'propagate': False,
            },
            'core': {
                'handlers': general_handlers,
                'level': default_log_level,
                'propagate': False,
            },
            'hiring': {
                'handlers': general_handlers,
                'level': default_log_level,
                'propagate': False,
            },
            'verification': {
                'handlers': general_handlers,
                'level': default_log_level,
                'propagate': False,
            },
        },
        'root': {
            'handlers': general_handlers,
            'level': default_log_level,
        },
    }

    return config
