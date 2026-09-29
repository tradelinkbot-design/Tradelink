"""
core/ratelimit.py
==================
Redis-backed sliding-window rate limiter.
Works in both development (locmem cache) and production (Upstash Redis /
django-redis).  No extra packages needed — uses Django's CACHES backend.

Algorithm
---------
Production (django-redis):
    Uses a Redis sorted-set (ZSET) pipeline.  Each request is recorded as a
    member with its Unix timestamp as both the member name and score.  Entries
    older than ``window`` seconds are pruned atomically before counting, giving
    a true sliding window that prevents boundary bursts.

Development (locmem / any non-Redis backend):
    Falls back to the previous fixed-window add+incr counter.  Locmem does not
    support ZSET operations, but the difference is acceptable in local dev.

Response Headers
----------------
The ``@rate_limit`` decorator injects these headers on every response it
allows through:

    X-RateLimit-Limit     : configured limit
    X-RateLimit-Remaining : requests left in the current window
    X-RateLimit-Reset     : UTC Unix timestamp when the window resets

On 429 responses it also adds:

    Retry-After           : seconds until the window expires

Usage (CBV method decorator)
-----------------------------
    from core.ratelimit import rate_limit

    class SignInView(View):
        @rate_limit(key='signin:{ip}', limit=10, window=600)
        def post(self, request):
            ...

Usage (imperative check — sync)
--------------------------------
    from core.ratelimit import is_rate_limited

    if is_rate_limited(request, key='kyc:nin:{user}', limit=3, window=86400):
        return JsonResponse({'error': 'Daily limit reached.'}, status=429)

Usage (imperative check — async, WebSocket consumers)
-------------------------------------------------------
    from core.ratelimit import is_rate_limited_async

    if await is_rate_limited_async(
        user_pk=self.user.pk,
        key='chat_msg:{user}',
        limit=45,
        window=60,
    ):
        await self._send_error('Sending too fast.')
        return
"""

import functools
import hashlib
import logging
import time
import uuid

from django.core.cache import cache

logger = logging.getLogger(__name__)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _build_cache_key(key_template: str, request) -> str:
    """
    Resolve {ip} and {user} placeholders in the key template, then SHA-256
    hash the result so it is safe for all cache backends regardless of length.
    """
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    ip = x_forwarded.split(',')[0].strip() if x_forwarded else request.META.get('REMOTE_ADDR', 'unknown')
    user_id = str(request.user.pk) if request.user.is_authenticated else 'anon'

    resolved = key_template.format(ip=ip, user=user_id)
    hashed   = hashlib.sha256(resolved.encode()).hexdigest()[:32]
    return f'rl:{hashed}'


def _build_raw_cache_key(key_template: str, **kwargs) -> str:
    """
    Build a cache key from an arbitrary key template and keyword substitutions.
    Used by the async path where we only have user_pk, not a full request.
    """
    resolved = key_template.format(**kwargs)
    hashed   = hashlib.sha256(resolved.encode()).hexdigest()[:32]
    return f'rl:{hashed}'


def _sliding_count(cache_key: str, window: int) -> int:
    """
    Attempt a sliding-window count using a Redis ZSET pipeline (django-redis).

    Returns the number of requests recorded in the last ``window`` seconds
    *after* adding the current request.

    Falls back to -1 on any error so the caller can use the fixed-window path.
    """
    try:
        # Reach into django-redis to get the raw Redis client.
        client = cache.client.get_client()   # type: ignore[attr-defined]
    except AttributeError:
        # Not a django-redis backend (e.g. locmem in dev) — signal fallback.
        return -1

    now = time.time()
    member = f"{now}:{uuid.uuid4().hex[:8]}"  # unique per request to prevent collision in ZSET

    try:
        pipe = client.pipeline()
        pipe.zremrangebyscore(cache_key, 0, now - window)   # evict old entries
        pipe.zadd(cache_key, {member: now})                  # record this request
        pipe.zcard(cache_key)                                 # count in window
        pipe.expire(cache_key, window)                        # keep TTL fresh
        results = pipe.execute()
        return int(results[2])   # zcard result
    except Exception as exc:
        logger.warning('ratelimit: sliding ZSET error (will fallback): %s', exc)
        return -1


def _fixed_count(cache_key: str, window: int) -> int:
    """
    Fixed-window counter using Django cache add+incr.
    Used as a fallback when the Redis ZSET path is unavailable (dev / locmem).
    """
    cache.add(cache_key, 0, timeout=window)   # set only if absent (atomic in Redis)
    return cache.incr(cache_key)


def count_requests(cache_key: str, window: int) -> int:
    """
    Return the current request count (including this request) using the best
    available algorithm for the configured cache backend.
    """
    count = _sliding_count(cache_key, window)
    if count == -1:
        count = _fixed_count(cache_key, window)
    return count


def _window_reset_ts(window: int) -> int:
    """Unix timestamp (UTC) at which the current window expires."""
    return int(time.time()) + window


# ── Public sync API ───────────────────────────────────────────────────────────

def is_rate_limited(request, *, key: str, limit: int, window: int) -> bool:
    """
    Return True if this request exceeds the rate limit.

    Fails open on cache errors — users are never blocked due to Redis downtime.

    Args:
        request: Django HttpRequest.
        key:     Template string.  Supports {ip} and {user} placeholders.
        limit:   Max requests allowed within the window.
        window:  Window duration in seconds.
    """
    cache_key = _build_cache_key(key, request)
    try:
        count = count_requests(cache_key, window)
        return count > limit
    except Exception as exc:
        logger.warning('ratelimit: cache error (failing open): %s', exc)
        return False


# ── Public async API (for Django Channels consumers) ─────────────────────────

async def is_rate_limited_async(
    user_pk,
    *,
    key: str,
    limit: int,
    window: int,
) -> bool:
    """
    Async-native rate limit check for use inside Django Channels consumers.

    Unlike ``is_rate_limited`` this does not take a full HttpRequest — pass the
    user PK (or any string) and use {user} in the key template.

    Example::

        if await is_rate_limited_async(self.user.pk, key='chat_msg:{user}', limit=45, window=60):
            await self._send_error('Too fast.')
            return

    Fails open on errors.
    """
    from channels.db import database_sync_to_async

    cache_key = _build_raw_cache_key(key, user=str(user_pk))

    @database_sync_to_async
    def _check():
        try:
            count = count_requests(cache_key, window)
            return count > limit
        except Exception as exc:
            logger.warning('ratelimit[async]: cache error (failing open): %s', exc)
            return False

    return await _check()


# ── Decorator ─────────────────────────────────────────────────────────────────

def rate_limit(
    key: str,
    limit: int,
    window: int,
    message: str = 'Too many requests. Please slow down and try again.',
    json: bool = False,
):
    """
    Decorator for Django class-based view methods (get, post, etc.).

    Injects ``X-RateLimit-*`` headers on every allowed response and returns
    a 429 with ``Retry-After`` when the limit is exceeded.

    Args:
        key:     Cache key template.  Supports {ip} and {user} placeholders.
        limit:   Max requests allowed within the window.
        window:  Window duration in seconds.
        message: User-facing error message on rate limit.
        json:    If True  → return a JSON 429 response.
                 If False → flash a message and redirect back to the same path.

    Example::

        class NINVerifyView(LoginRequiredMixin, FormView):
            @rate_limit(key='nin:{user}', limit=3, window=86400, json=False)
            def form_valid(self, form):
                ...
    """
    def decorator(method):
        @functools.wraps(method)
        def wrapper(*args, **kwargs):
            # ── Extract the HttpRequest from CBV / FBV args ──────────────────
            request = None
            if args:
                if hasattr(args[0], 'META'):
                    request = args[0]
                elif len(args) > 1 and hasattr(args[1], 'META'):
                    request = args[1]
                elif hasattr(args[0], 'request') and hasattr(args[0].request, 'META'):
                    request = args[0].request

            if request is None:
                # Cannot determine request — pass through without limiting.
                return method(*args, **kwargs)

            # ── Build cache key and count ────────────────────────────────────
            cache_key = _build_cache_key(key, request)
            try:
                count = count_requests(cache_key, window)
            except Exception as exc:
                logger.warning('ratelimit: cache error (failing open): %s', exc)
                return method(*args, **kwargs)

            remaining = max(0, limit - count)
            reset_ts  = _window_reset_ts(window)

            # ── Limit exceeded → 429 ────────────────────────────────────────
            if count > limit:
                ip = (
                    request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
                    or request.META.get('REMOTE_ADDR', '?')
                )
                logger.warning(
                    'ratelimit: BLOCKED limit=%d window=%ds key=%s ip=%s user=%s',
                    limit, window, key, ip,
                    getattr(request.user, 'pk', 'anon'),
                )
                retry_after = window  # conservative: wait a full window

                if json:
                    from django.http import JsonResponse
                    resp = JsonResponse({'error': message}, status=429)
                else:
                    from django.contrib import messages as flash
                    from django.shortcuts import redirect
                    flash.error(request, message)
                    resp = redirect(getattr(request, 'path', '/'))

                resp['X-RateLimit-Limit']     = str(limit)
                resp['X-RateLimit-Remaining'] = '0'
                resp['X-RateLimit-Reset']     = str(reset_ts)
                resp['Retry-After']           = str(retry_after)
                return resp

            # ── Allowed → call the view and inject informational headers ─────
            response = method(*args, **kwargs)

            # Only inject headers on proper HttpResponse objects.
            if hasattr(response, '__setitem__'):
                response['X-RateLimit-Limit']     = str(limit)
                response['X-RateLimit-Remaining'] = str(remaining)
                response['X-RateLimit-Reset']     = str(reset_ts)

            return response

        return wrapper
    return decorator
