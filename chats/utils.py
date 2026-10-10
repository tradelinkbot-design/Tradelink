"""
chats/utils.py
==============
Presence & last-seen formatting helpers for the TradeLink NG chat system.
"""

from datetime import timedelta
import logging
from typing import Optional, Tuple

from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)


def format_last_seen(dt, now=None) -> str:
    """
    Format a datetime into a friendly 'last seen' string.

    Examples:
      • < 2 minutes ago     → 'just now'
      • < 60 minutes ago    → '15m ago'
      • Earlier today       → 'today at 3:45 PM'
      • Yesterday           → 'yesterday at 10:15 AM'
      • Earlier this year   → '14 Oct at 2:30 PM'
      • Older               → '14 Oct 2024'
    """
    if not dt:
        return ''

    now = now or timezone.now()
    local_dt = timezone.localtime(dt)
    local_now = timezone.localtime(now)

    diff = now - dt

    # Clock skew / just now (< 2 mins)
    if diff.total_seconds() < 120:
        return 'just now'

    # Minutes ago (< 1 hour)
    if diff.total_seconds() < 3600:
        mins = max(1, int(diff.total_seconds() // 60))
        return f'{mins}m ago'

    # Same calendar day
    if local_dt.date() == local_now.date():
        time_str = local_dt.strftime('%I:%M %p').lstrip('0')
        return f'today at {time_str}'

    # Yesterday
    if local_dt.date() == (local_now.date() - timedelta(days=1)):
        time_str = local_dt.strftime('%I:%M %p').lstrip('0')
        return f'yesterday at {time_str}'

    # Same calendar year
    if local_dt.year == local_now.year:
        date_time_str = local_dt.strftime('%d %b at %I:%M %p').lstrip('0')
        return date_time_str

    # Different year
    return local_dt.strftime('%d %b %Y').lstrip('0')


def get_user_presence(user) -> Tuple[bool, Optional[object], str]:
    """
    Look up presence and last-seen information for a user.

    Returns:
        (is_online: bool, last_seen_dt: datetime|None, last_seen_display: str)
    """
    if not user:
        return False, None, 'Offline'

    from chats.models import UserOnlineStatus

    user_pk = getattr(user, 'pk', None) or getattr(user, 'id', None)
    if not user_pk:
        return False, None, 'Offline'

    # Query fresh record from database to avoid stale in-memory reverse cache
    try:
        status_obj = UserOnlineStatus.objects.filter(user_id=user_pk).first()
    except Exception:
        status_obj = None

    now = timezone.now()
    is_online = False
    last_seen = None

    if status_obj:
        last_seen = status_obj.last_seen
        diff_sec = (now - last_seen).total_seconds() if last_seen else 999999

        # A user is active/online if:
        # 1. Marked is_online=True AND seen within the last 5 minutes (avoids stale crashed sessions), OR
        # 2. Activity was recorded within the last 90 seconds (active web navigation or WebSocket ping)
        if (status_obj.is_online and diff_sec < 300) or (diff_sec < 90):
            is_online = True
        else:
            is_online = False
    else:
        last_seen = getattr(user, 'last_login', None)
        if last_seen:
            diff_sec = (now - last_seen).total_seconds()
            if diff_sec < 90:
                is_online = True

    if is_online:
        display = 'Online'
    elif last_seen:
        friendly = format_last_seen(last_seen)
        display = f'Last seen {friendly}' if friendly else 'Offline'
    else:
        display = 'Offline'

    return is_online, last_seen, display


def touch_user_presence(user, is_online: bool = True, force: bool = False) -> None:
    """
    Updates the user's presence and last_seen timestamp.
    Transitions to online immediately. Throttles subsequent heartbeats to every 45s.
    """
    if not user or not user.is_authenticated:
        return

    from chats.models import UserOnlineStatus
    user_pk = user.pk
    now = timezone.now()

    cache_key = f'user_presence_state:{user_pk}'
    cached_state = cache.get(cache_key)

    # If transitioning to online from offline, always write immediately
    if not force and is_online and cached_state == 'online':
        return

    cache.set(cache_key, 'online' if is_online else 'offline', timeout=45)

    try:
        UserOnlineStatus.objects.update_or_create(
            user_id=user_pk,
            defaults={'is_online': is_online, 'last_seen': now},
        )
    except Exception as exc:
        logger.warning('touch_user_presence failed for user %s: %s', user_pk, exc)
