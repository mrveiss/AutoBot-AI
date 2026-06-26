# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Cross-service RS256 jti denylist (#10278).

Both autobot-backend (the authority that mints RS256 tokens) and
autobot-slm-backend (a consumer that verifies them) share this Redis keyspace.
When autobot-backend revokes an RS256 authority token on logout or explicit
revocation it writes to ``auth:rs256:jti:denylist:<jti>`` with TTL = remaining
token lifetime.  SLM's ``verify_authority_token`` checks the same key before
accepting the token.

Key namespace
-------------
``auth:rs256:jti:denylist:{jti}``

Both services use the same Redis instance (shared ``autobot_shared`` Redis
client).  The namespace prefix ``auth:rs256:jti:denylist:`` is intentionally
distinct from the SLM-only HS256 denylist (``slm:jwt:denylist:``) so both
can coexist without collision.

Fail-open policy
----------------
If Redis is unavailable ``is_rs256_jti_revoked`` returns ``False`` — the same
fail-open contract used by the HS256 denylist in ``token_denylist.py``.  RS256
authority tokens already have a bounded lifetime so a brief window during Redis
downtime is acceptable.

TTL
---
Entry TTL must be >= the remaining lifetime of the revoked token so the
denylist never clears before the token would have expired anyway.  Callers
should pass the remaining seconds derived from the token's ``exp`` claim.
"""

import logging

from autobot_shared.redis_client import get_async_redis_client

logger = logging.getLogger(__name__)

#: Shared Redis key prefix used by BOTH autobot-backend (write) and SLM (read).
RS256_DENYLIST_PREFIX = "auth:rs256:jti:denylist:"


def _rs256_denylist_key(jti: str) -> str:
    """Return the cross-service Redis key for a RS256 *jti*."""
    return f"{RS256_DENYLIST_PREFIX}{jti}"


async def revoke_rs256_jti(jti: str, ttl_seconds: int) -> None:
    """Add *jti* to the cross-service RS256 denylist with TTL *ttl_seconds*.

    Called by autobot-backend on logout/explicit revocation.  The entry
    auto-expires when the original token would have expired so no background
    cleanup is needed.

    Silently no-ops if Redis is unavailable (logs a warning).

    Args:
        jti: The JWT ID claim from the RS256 authority token.
        ttl_seconds: Remaining lifetime of the token in seconds (>= 1).
    """
    redis = await get_async_redis_client()
    if redis is None:
        logger.warning("rs256_denylist: Redis unavailable; jti=%r NOT revoked", jti)
        return
    ttl = max(1, ttl_seconds)
    await redis.set(_rs256_denylist_key(jti), "1", ex=ttl)
    logger.info("rs256_denylist: jti=%r revoked (ttl=%ds)", jti, ttl)


async def is_rs256_jti_revoked(jti: str) -> bool:
    """Return True if *jti* is in the cross-service RS256 denylist.

    Fail-open: returns False when Redis is unavailable.

    Args:
        jti: The JWT ID claim to check.

    Returns:
        True if the jti has been explicitly revoked, False otherwise.
    """
    redis = await get_async_redis_client()
    if redis is None:
        logger.warning("rs256_denylist: Redis unavailable; treating jti=%r as NOT revoked (fail-open)", jti)
        return False
    exists = await redis.exists(_rs256_denylist_key(jti))
    return bool(exists)
