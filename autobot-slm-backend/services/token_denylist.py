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
"""

import logging

from autobot_shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)

_DENYLIST_PREFIX = "slm:jwt:denylist:"


def _denylist_key(jti: str) -> str:
    """Return the Redis key for *jti*."""
    return f"{_DENYLIST_PREFIX}{jti}"


async def revoke_jti(jti: str, ttl_seconds: int) -> None:
    """Add *jti* to the denylist with a Redis TTL of *ttl_seconds*.

    The key auto-expires when the original token would have expired anyway,
    so no background cleanup is needed.  Silently no-ops if Redis is
    unavailable (logs a warning).
    """
    redis = await get_redis_client(async_client=True)
    if redis is None:
        logger.warning("revoke_jti: Redis unavailable; jti=%r NOT revoked", jti)
        return
    ttl = max(1, ttl_seconds)
    await redis.set(_denylist_key(jti), "1", ex=ttl)
    logger.info("revoke_jti: jti=%r revoked with ttl=%d", jti, ttl)


async def is_jti_revoked(jti: str) -> bool:
    """Return ``True`` if *jti* is in the denylist.

    Fail-open: returns ``False`` when Redis is unavailable.  The token's own
    TTL still provides a time-bounded guard in that case.
    """
    redis = await get_redis_client(async_client=True)
    if redis is None:
        logger.warning("is_jti_revoked: Redis unavailable; treating jti=%r as NOT revoked (fail-open)", jti)
        return False
    exists = await redis.exists(_denylist_key(jti))
    return bool(exists)
