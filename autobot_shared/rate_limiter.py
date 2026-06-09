# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Shared Rate Limiter (Issue #4460)

Single sliding-window rate limiter used across the entire AutoBot backend.
All per-area rate limiters (integrations, user middleware, LLM, gateway,
conversation) delegate to this class rather than maintaining separate
implementations.

Algorithm: dual sliding window (per-minute + per-hour) backed by Redis for
distributed correctness. Falls back gracefully to an allow-all policy when
Redis is unavailable so that a Redis outage never hard-blocks requests.

Tiered limits
-------------
Three named tiers map to default limits read from ``ssot_config``:

- ``anonymous``: unauthenticated callers (most restrictive)
- ``authenticated``: logged-in users
- ``privileged``: service accounts / admin users (least restrictive)

Scope key scheme
----------------
Keys follow the pattern ``autobot:rl:<prefix>:<identifier>`` so all rate
limit state lives under one predictable namespace prefix:

    user:{uuid}          → prefix "user"
    integration:{name}   → prefix "integration"
    llm:{provider}       → prefix "llm"
    conversation:{id}    → prefix "conversation"
    gateway:{platform}   → prefix "gateway"

Retry-After helper
------------------
``get_retry_after_seconds(key)`` returns the integer number of seconds the
caller should wait before the next request will be allowed.  Pass this value
directly in an HTTP ``Retry-After`` response header.
"""

from __future__ import annotations

import logging
import time

from autobot_shared.redis_client import get_async_redis_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default tiered limits
# These are read at class-instantiation time from ssot_config when present,
# falling back to the constants below when the config key is absent.
# ---------------------------------------------------------------------------

# (requests_per_minute, requests_per_hour)
_TIER_DEFAULTS: dict[str, tuple[int, int]] = {
    "anonymous": (20, 500),
    "authenticated": (60, 2000),
    "privileged": (300, 10000),
}

# Namespace prefix for all rate-limit keys in Redis
_KEY_PREFIX = "autobot:rl"


def _get_tier_defaults() -> dict[str, tuple[int, int]]:
    """Return tier limit defaults, preferring ssot_config when available."""
    try:
        from autobot_shared.ssot_config import config  # noqa: PLC0415

        return {
            "anonymous": (
                getattr(config, "rate_limit_anon_rpm", _TIER_DEFAULTS["anonymous"][0]),
                getattr(config, "rate_limit_anon_rph", _TIER_DEFAULTS["anonymous"][1]),
            ),
            "authenticated": (
                getattr(config, "rate_limit_auth_rpm", _TIER_DEFAULTS["authenticated"][0]),
                getattr(config, "rate_limit_auth_rph", _TIER_DEFAULTS["authenticated"][1]),
            ),
            "privileged": (
                getattr(config, "rate_limit_priv_rpm", _TIER_DEFAULTS["privileged"][0]),
                getattr(config, "rate_limit_priv_rph", _TIER_DEFAULTS["privileged"][1]),
            ),
        }
    except Exception:
        return dict(_TIER_DEFAULTS)


class RateLimiter:
    """Shared sliding-window rate limiter backed by Redis.

    Instantiate once per area with the appropriate scope prefix and default
    tier, then call ``is_allowed`` / ``record`` / ``get_retry_after_seconds``
    from async request handlers.

    Parameters
    ----------
    scope_prefix:
        Short label that distinguishes this rate-limiter instance, e.g.
        ``"user"``, ``"integration"``, ``"llm"``, ``"conversation"``,
        ``"gateway"``.  Combined with the caller-supplied *key* to form the
        Redis key ``autobot:rl:{scope_prefix}:{key}``.
    default_tier:
        One of ``"anonymous"``, ``"authenticated"``, ``"privileged"``.
        Determines the default (rpm, rph) limits when callers do not pass
        explicit limits.
    requests_per_minute:
        Override the per-minute window limit.  When *None*, the tier default
        is used.
    requests_per_hour:
        Override the per-hour window limit.  When *None*, the tier default is
        used.
    redis_database:
        Redis logical database name (default ``"main"``).
    """

    def __init__(
        self,
        scope_prefix: str,
        default_tier: str = "authenticated",
        requests_per_minute: int | None = None,
        requests_per_hour: int | None = None,
        redis_database: str = "main",
    ) -> None:
        self._prefix = scope_prefix
        self._db = redis_database
        tier_defaults = _get_tier_defaults()
        if default_tier not in tier_defaults:
            raise ValueError(f"Unknown tier '{default_tier}'. " f"Valid tiers: {list(tier_defaults)}")
        tier_rpm, tier_rph = tier_defaults[default_tier]
        self._rpm = requests_per_minute if requests_per_minute is not None else tier_rpm
        self._rph = requests_per_hour if requests_per_hour is not None else tier_rph

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _redis_key(self, key: str, window: str) -> str:
        """Return the Redis key for the given scope key and window name."""
        return f"{_KEY_PREFIX}:{self._prefix}:{key}:{window}"

    async def is_allowed(
        self,
        key: str,
        requests_per_minute: int | None = None,
        requests_per_hour: int | None = None,
    ) -> bool:
        """Return True when the request may proceed without exceeding limits.

        Does **not** record the request; call ``record`` after the request
        completes (or call ``acquire`` which combines both).

        Parameters
        ----------
        key:
            Scope identifier, e.g. ``"user:abc123"`` or ``"github"``.
        requests_per_minute:
            Per-call override for the minute-window limit.
        requests_per_hour:
            Per-call override for the hour-window limit.
        """
        rpm = requests_per_minute if requests_per_minute is not None else self._rpm
        rph = requests_per_hour if requests_per_hour is not None else self._rph
        now = time.time()

        try:
            redis = await get_async_redis_client(database=self._db)
            if redis is None:
                logger.warning(
                    "rate_limiter: Redis unavailable for key '%s:%s'; allowing request",
                    self._prefix,
                    key,
                )
                return True

            minute_count = await self._window_count(redis, key, "minute", now, 60)
            if minute_count >= rpm:
                logger.debug(
                    "rate_limiter: minute limit hit for %s:%s (%d/%d)",
                    self._prefix,
                    key,
                    minute_count,
                    rpm,
                )
                return False

            hour_count = await self._window_count(redis, key, "hour", now, 3600)
            if hour_count >= rph:
                logger.debug(
                    "rate_limiter: hour limit hit for %s:%s (%d/%d)",
                    self._prefix,
                    key,
                    hour_count,
                    rph,
                )
                return False

            return True
        except Exception as exc:
            logger.warning(
                "rate_limiter: Redis error for key '%s:%s': %s; allowing request",
                self._prefix,
                key,
                exc,
            )
            return True

    async def record(self, key: str) -> None:
        """Record that a request for *key* was dispatched.

        Uses a Redis sorted set where the score is the current epoch time.
        Old entries are pruned on each write to keep memory bounded.
        """
        now = time.time()
        try:
            redis = await get_async_redis_client(database=self._db)
            if redis is None:
                return

            hour_key = self._redis_key(key, "hour")
            pipe = redis.pipeline()
            # Add current timestamp as both score and member (unique via timestamp)
            pipe.zadd(hour_key, {str(now): now})
            # Remove entries older than one hour
            pipe.zremrangebyscore(hour_key, "-inf", now - 3600)
            # Expire the whole key after 2 hours so stale keys auto-clean
            pipe.expire(hour_key, 7200)
            await pipe.execute()
        except Exception as exc:
            logger.warning(
                "rate_limiter: failed to record request for '%s:%s': %s",
                self._prefix,
                key,  # codeql[py/clear-text-logging-sensitive-data]
                exc,
            )

    async def acquire(
        self,
        key: str,
        requests_per_minute: int | None = None,
        requests_per_hour: int | None = None,
    ) -> bool:
        """Check and record atomically using Redis Lua script.

        Returns True when the request is allowed. Uses a Lua script to ensure
        atomicity and prevent race conditions where concurrent requests could
        bypass rate limits (Issue #9610 review fix).
        """
        rpm = requests_per_minute if requests_per_minute is not None else self._rpm
        rph = requests_per_hour if requests_per_hour is not None else self._rph
        now = time.time()

        try:
            redis = await get_async_redis_client(database=self._db)
            if redis is None:
                logger.warning(
                    "rate_limiter: Redis unavailable for key '%s:%s'; allowing request",
                    self._prefix,
                    key,
                )
                return True

            # Lua script for atomic check+record
            # Returns 1 if allowed, 0 if rate limited
            lua_script = """
            local hour_key = KEYS[1]
            local now = tonumber(ARGV[1])
            local rpm = tonumber(ARGV[2])
            local rph = tonumber(ARGV[3])

            -- Count requests in minute and hour windows
            local minute_cutoff = now - 60
            local hour_cutoff = now - 3600
            local minute_count = redis.call('ZCOUNT', hour_key, minute_cutoff, '+inf')
            local hour_count = redis.call('ZCOUNT', hour_key, hour_cutoff, '+inf')

            -- Check limits
            if minute_count >= rpm or hour_count >= rph then
                return 0  -- Rate limited
            end

            -- Record request atomically
            redis.call('ZADD', hour_key, now, tostring(now))
            redis.call('ZREMRANGEBYSCORE', hour_key, '-inf', now - 3600)
            redis.call('EXPIRE', hour_key, 7200)

            return 1  -- Allowed
            """

            hour_key = self._redis_key(key, "hour")
            result = await redis.eval(lua_script, 1, hour_key, now, rpm, rph)
            allowed = bool(result)

            if not allowed:
                logger.debug(
                    "rate_limiter: limit hit for %s:%s (rpm=%d, rph=%d)",
                    self._prefix,
                    key,
                    rpm,
                    rph,
                )

            return allowed

        except Exception as exc:
            logger.warning(
                "rate_limiter: Redis error for key '%s:%s': %s; allowing request",
                self._prefix,
                key,
                exc,
            )
            return True

    async def get_retry_after_seconds(self, key: str) -> int:
        """Return integer seconds until the next request for *key* will be allowed.

        Inspects the oldest entry in the sliding window to compute the wait.
        Returns 0 when no limit is currently active.

        Suitable for use directly as the value of an HTTP ``Retry-After`` header.
        """
        now = time.time()
        try:
            redis = await get_async_redis_client(database=self._db)
            if redis is None:
                return 0

            hour_key = self._redis_key(key, "hour")
            minute_cutoff = now - 60
            hour_cutoff = now - 3600

            # Count entries in each window
            minute_count = await redis.zcount(hour_key, minute_cutoff, "+inf")
            hour_count = await redis.zcount(hour_key, hour_cutoff, "+inf")

            wait = 0.0

            if minute_count >= self._rpm:
                # Find the oldest entry in the minute window
                oldest_in_minute = await redis.zrangebyscore(
                    hour_key, minute_cutoff, "+inf", start=0, num=1, withscores=True
                )
                if oldest_in_minute:
                    oldest_ts = oldest_in_minute[0][1]
                    wait = max(wait, 60.0 - (now - oldest_ts))

            if hour_count >= self._rph:
                oldest_in_hour = await redis.zrangebyscore(
                    hour_key, hour_cutoff, "+inf", start=0, num=1, withscores=True
                )
                if oldest_in_hour:
                    oldest_ts = oldest_in_hour[0][1]
                    wait = max(wait, 3600.0 - (now - oldest_ts))

            return max(0, int(wait) + 1)  # +1 for safe rounding
        except Exception as exc:
            logger.warning(
                "rate_limiter: get_retry_after failed for '%s:%s': %s",
                self._prefix,
                key,
                exc,
            )
            return 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _window_count(
        self,
        redis,
        key: str,
        window: str,
        now: float,
        window_seconds: int,
    ) -> int:
        """Return the number of recorded requests in the last *window_seconds*."""
        hour_key = self._redis_key(key, "hour")
        cutoff = now - window_seconds
        count = await redis.zcount(hour_key, cutoff, "+inf")
        return int(count)


__all__ = ["RateLimiter"]
