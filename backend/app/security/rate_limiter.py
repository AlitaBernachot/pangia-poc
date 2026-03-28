"""Rate limiting: fixed-window request counter backed by Redis.

Each request is counted against a key (typically the session ID) using a
fixed-window counter implemented with Redis INCR + EXPIRE.  The counter is
created with a TTL equal to the window duration so it resets automatically
once the window expires.

Configuration (via :class:`app.config.Settings`)::

    GUARDRAIL_RATE_LIMIT_ENABLED        = true
    GUARDRAIL_RATE_LIMIT_MAX_REQUESTS   = 60   # requests per window
    GUARDRAIL_RATE_LIMIT_WINDOW_SECONDS = 60   # window size in seconds
"""

from dataclasses import dataclass


@dataclass
class RateLimitResult:
    """Result returned by :func:`check_rate_limit`."""

    blocked: bool
    current_count: int = 0
    limit: int = 0
    reason: str | None = None


async def check_rate_limit(
    key: str,
    max_requests: int,
    window_seconds: int,
) -> RateLimitResult:
    """Increment and check the request counter for *key*.

    Uses a Redis fixed-window counter.  The counter key is namespaced as
    ``rate_limit:{key}`` and expires after *window_seconds*.

    Parameters
    ----------
    key:
        A unique identifier for the caller (e.g. session ID or IP address).
    max_requests:
        Maximum number of requests allowed within the window.
    window_seconds:
        Length of the rate-limit window in seconds.
    """
    from app.db.redis_client import get_redis

    redis = await get_redis()
    redis_key = f"rate_limit:{key}"

    # Atomic increment; set TTL only when the key is brand-new.
    count = await redis.incr(redis_key)
    if count == 1:
        await redis.expire(redis_key, window_seconds)

    if count > max_requests:
        return RateLimitResult(
            blocked=True,
            current_count=count,
            limit=max_requests,
            reason=(
                f"Rate limit exceeded: {count}/{max_requests} requests "
                f"in the last {window_seconds} seconds. Please wait before retrying."
            ),
        )

    return RateLimitResult(blocked=False, current_count=count, limit=max_requests)
