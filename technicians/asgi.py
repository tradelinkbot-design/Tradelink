
import os
import sys
import asyncio
import logging

# ── pgvector Python package path ──────────────────────────────────────────────
_EXTRA_PKGS = r'C:\Users\hp\py_extra_pkgs'
if _EXTRA_PKGS not in sys.path:
    sys.path.insert(0, _EXTRA_PKGS)
# ─────────────────────────────────────────────────────────────────────────────

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'technicians.settings')

# Import Django ASGI app first so models are loaded before routing
django_asgi_app = get_asgi_application()

# Import WebSocket patterns AFTER Django is set up
from chats.routing import websocket_urlpatterns  # noqa: E402


def _silence_shielded_cancelled_error(loop, context):
    """
    Suppresses noisy 'CancelledError exception in shielded future' messages logged
    by Python's asyncio when clients (or Render health-checks) disconnect early.
    """
    exc = context.get('exception')
    msg = context.get('message', '')
    if isinstance(exc, asyncio.CancelledError) or 'CancelledError' in msg or 'shielded future' in msg:
        return
    loop.default_exception_handler(context)


class CancelledErrorFilterMiddleware:
    """
    ASGI middleware ensuring the running event loop silences unhandled
    CancelledError logs on shielded futures caused by client disconnections.
    """
    def __init__(self, inner_app):
        self.inner_app = inner_app
        self._installed = False

    async def __call__(self, scope, receive, send):
        if not self._installed:
            try:
                loop = asyncio.get_running_loop()
                loop.set_exception_handler(_silence_shielded_cancelled_error)
                self._installed = True
            except Exception:
                pass
        try:
            await self.inner_app(scope, receive, send)
        except asyncio.CancelledError:
            raise


raw_application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter(websocket_urlpatterns)
        )
    ),
})

application = CancelledErrorFilterMiddleware(raw_application)