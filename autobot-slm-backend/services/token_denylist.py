# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
JWT jti-denylist backed by Redis.

Revocation is enforced on the async auth path (``decode_token_async``).
The sync ``decode_token`` path cannot check Redis and is documented
accordingly — it is used only in contexts where a short token TTL is the
primary guard.

Fail-open policy for ``is_jti_revoked``: if Redis is unavailable the
function returns ``False``.  This is acceptable because:
- SLM HS256 tokens have a short configured TTL (default 30 min).
- A revoked token will expire naturally before long.
- Denying all auth on Redis downtime would be worse than a brief window
  where a revoked token could be reused.

Bounded access (#11443): ``get_redis_client`` does NOT return ``None``
quickly when Redis is down or misconfigured — the shared connection
manager retries pool creation for ~60 s while holding a global lock, which
serialized every authenticated request behind a one-minute wait and made
the whole SLM GUI appear dead.  The documented fail-open therefore has to
be enforced HERE: every Redis interaction is wrapped in
``asyncio.wait_for`` with a short deadline, and failures arm a short
negative-cache so subsequent auths skip Redis entirely instead of paying
the timeout each time.
"""

import asyncio
import logging
import time

from autobot_shared.redis_client import get_async_redis_client

try:  # redis-py exceptions do NOT inherit builtin ConnectionError/OSError
    from redis.exceptions import RedisError as _RedisError
except ImportError:  # pragma: no cover - redis is a hard dep in deployments
    _RedisError = ConnectionError  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)

# Failures that arm the fail-open window. asyncio.TimeoutError is not OSError
# on py3.10, and redis.exceptions.ConnectionError is not builtin ConnectionError
# — both must be listed explicitly (#11445 review).
_REDIS_FAILURES = (asyncio.TimeoutError, ConnectionError, OSError, _RedisError)

_DENYLIST_PREFIX = "slm:jwt:denylist:"

# Hard deadline for any denylist Redis interaction (client acquisition +
# command). Auth latency must never be hostage to Redis (#11443).
_REDIS_DEADLINE_SECONDS = 1.5
# After a failure, skip Redis for this long (fail-open window) instead of
# re-paying the deadline on every authenticated request.
_UNAVAILABLE_RETRY_SECONDS = 30.0

# Monotonic timestamp until which Redis is considered unavailable (0 = OK).
_unavailable_until: float = 0.0


def _denylist_key(jti: str) -> str:
    """Return the Redis key for *jti*."""
    return f"{_DENYLIST_PREFIX}{jti}"


def _redis_marked_unavailable() -> bool:
    """True while the negative-cache window from a previous failure is active."""
    return time.monotonic() < _unavailable_until


def _mark_redis_unavailable(op: str, jti: str, exc: Exception | None) -> None:
    """Arm the negative-cache window and log the degradation once per trip."""
    global _unavailable_until
    was_armed = _redis_marked_unavailable()
    _unavailable_until = time.monotonic() + _UNAVAILABLE_RETRY_SECONDS
    if not was_armed:
        logger.warning(
            "%s: Redis unavailable (%s); denylist fail-open for %.0fs (jti=%r)",
            op,
            exc.__class__.__name__ if exc else "no client",
            _UNAVAILABLE_RETRY_SECONDS,
            jti,
        )


def _mark_redis_available() -> None:
    """Clear the negative-cache window after a successful interaction."""
    global _unavailable_until
    _unavailable_until = 0.0


async def revoke_jti(jti: str, ttl_seconds: int) -> None:
    """Add *jti* to the denylist with a Redis TTL of *ttl_seconds*.

    The key auto-expires when the original token would have expired anyway,
    so no background cleanup is needed.  Silently no-ops if Redis is
    unavailable (logs a warning) — bounded by the module deadline.
    """
    ttl = max(1, ttl_seconds)

    async def _do() -> bool:
        redis = await get_async_redis_client()
        if redis is None:
            return False
        await redis.set(_denylist_key(jti), "1", ex=ttl)
        return True

    try:
        ok = await asyncio.wait_for(_do(), timeout=_REDIS_DEADLINE_SECONDS)
    except _REDIS_FAILURES as exc:
        _mark_redis_unavailable("revoke_jti", jti, exc)
        logger.warning("revoke_jti: jti=%r NOT revoked (Redis unavailable)", jti)
        return
    if not ok:
        _mark_redis_unavailable("revoke_jti", jti, None)
        logger.warning("revoke_jti: jti=%r NOT revoked (Redis unavailable)", jti)
        return
    _mark_redis_available()
    logger.info("revoke_jti: jti=%r revoked with ttl=%d", jti, ttl)


async def is_jti_revoked(jti: str) -> bool:
    """Return ``True`` if *jti* is in the denylist.

    Fail-open: returns ``False`` when Redis is unavailable, misconfigured,
    or slower than the module deadline (#11443).  The token's own TTL still
    provides a time-bounded guard in that case.
    """
    if _redis_marked_unavailable():
        return False

    async def _do() -> bool | None:
        redis = await get_async_redis_client()
        if redis is None:
            return None
        return bool(await redis.exists(_denylist_key(jti)))

    try:
        result = await asyncio.wait_for(_do(), timeout=_REDIS_DEADLINE_SECONDS)
    except _REDIS_FAILURES as exc:
        _mark_redis_unavailable("is_jti_revoked", jti, exc)
        return False
    if result is None:
        _mark_redis_unavailable("is_jti_revoked", jti, None)
        return False
    _mark_redis_available()
    return result
