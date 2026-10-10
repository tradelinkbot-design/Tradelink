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
    # Ensure dt is in local timezone
    local_dt = timezone.localtime(dt)
    local_now = timezone.localtime(now)

    diff = now - dt

    # Clock skew / just now
    if diff.total_seconds() < 120:
        return 'just now'

    # Minutes ago (< 1 hour)
    if diff.total_seconds() < 3600:
        mins = int(diff.total_seconds() // 60)
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

    try:
        status_obj = getattr(user, 'online_status', None)
        if status_obj is None:
            status_obj = UserOnlineStatus.objects.filter(user=user).first()
    except Exception:
        status_obj = None

    if status_obj:
        is_online = bool(status_obj.is_online)
        last_seen = status_obj.last_seen
    else:
        is_online = False
        last_seen = getattr(user, 'last_login', None)

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
    Throttled via cache to once every 2 minutes unless force=True.
    """
    if not user or not user.is_authenticated:
        return

    cache_key = f'user_presence_touch:{user.pk}'
    if not force and cache.get(cache_key):
        return

    cache.set(cache_key, 1, timeout=120)

    from chats.models import UserOnlineStatus
    try:
        UserOnlineStatus.objects.update_or_create(
            user=user,
            defaults={'is_online': is_online},
        )
    except Exception as exc:
        logger.warning('touch_user_presence failed for user %s: %s', user.pk, exc)
