"""
test_logging_terminal.py
========================
Test and demonstrate terminal error logging in production mode (DEBUG=False).
"""

import os
import sys

# Force DEBUG=False to simulate production environment
os.environ['DEBUG'] = 'False'
os.environ['FORCE_COLOR'] = '1'
os.environ.setdefault('DATABASE_URL', 'sqlite:///db.sqlite3')
os.environ.setdefault('REDIS_URL', 'redis://localhost:6379/0')
os.environ.setdefault('CLOUDINARY_CLOUD_NAME', 'mock_cloud')
os.environ.setdefault('CLOUDINARY_API_KEY', '1234567890')
os.environ.setdefault('CLOUDINARY_API_SECRET', 'mock_secret')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'technicians.settings')

import django
django.setup()

import logging
from django.test import RequestFactory
from core.middleware import TerminalErrorLoggingMiddleware

print("\n" + "="*80)
print("TESTING PRODUCTION TERMINAL LOGGING")
print("="*80 + "\n")

# 1. Test standard logger levels
logger = logging.getLogger('marketplace')
print(">> Emitting standard logs across levels:")
logger.info("This is a standard INFO log message.")
logger.warning("This is a WARNING log message.")
logger.error("This is an ERROR log message.")

# 2. Test logger with exception traceback
print("\n>> Emitting an exception traceback via logger.exception:")
try:
    1 / 0
except ZeroDivisionError:
    logger.exception("ZeroDivisionError caught in marketplace task!")

# 3. Test TerminalErrorLoggingMiddleware with simulated unhandled 500 request
print("\n>> Testing TerminalErrorLoggingMiddleware with simulated view exception:")
factory = RequestFactory()
request = factory.post(
    '/jobs/create/?category=electrical',
    data={
        'title': 'Fix generator',
        'password': 'super-secret-password-123',
        'budget': 50000,
    }
)

def failing_view(req):
    raise ValueError("Simulated production database timeout or syntax error!")

middleware = TerminalErrorLoggingMiddleware(failing_view)

try:
    response = middleware(request)
except Exception as e:
    # Process exception like Django's BaseHandler does
    middleware.process_exception(request, e)

print("\n" + "="*80)
print("TEST COMPLETED SUCCESSFULLY")
print("="*80 + "\n")
