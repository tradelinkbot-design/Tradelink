"""
chats/middleware.py
===================
Middleware that tracks user online activity and last-seen timestamps across TradeLink.
"""

from chats.utils import touch_user_presence


class UserPresenceMiddleware:
    """
    Middleware that updates UserOnlineStatus.last_seen for logged-in users.
    Throttled to run at most once every 2 minutes per user.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if getattr(request, 'user', None) and request.user.is_authenticated:
            touch_user_presence(request.user, is_online=True, force=False)

        response = self.get_response(request)
        return response
