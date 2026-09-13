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

Fail-CLOSED policy (#16412)
----------------------------
If Redis is unavailable or errors, ``is_rs256_jti_revoked`` raises instead of
returning ``False``.  A denylist check exists to catch an authority token that
was logged out or explicitly revoked; if Redis cannot answer, "not revoked"
and "unknown" are indistinguishable, and treating them the same would let
such a token through for as long as the outage lasts.  This mirrors the
owner's #16387 decision for the HS256 denylist (``token_denylist.py``):
a Redis outage denies the RS256 authority-token path rather than honouring a
possibly-revoked token.  ``verify_authority_token`` (``jwks_verifier.py``)
catches the raise, at both the cache-hit and full-verify call sites, and
denies the token (401).

The write side, ``revoke_rs256_jti``, stays fail-open (best-effort, as in
#16387): a revoke that cannot reach Redis has nothing else to deny closed
against, and the read-side check above is what carries the fail-closed
guarantee.

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

    Unlike ``is_rs256_jti_revoked``'s fail-CLOSED revocation *check* (#16412),
    this write path stays fail-open: a revoke that cannot reach Redis has
    nothing else to deny closed against, and the read-side check is what
    carries the fail-closed guarantee.

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

    Fail-CLOSED (#16412): raises when Redis is unavailable or the check
    itself errors, rather than returning ``False``.  The caller
    (``verify_authority_token`` in ``jwks_verifier.py``) must deny the token
    on this raise -- "could not check" is not the same answer as "not
    revoked".

    Args:
        jti: The JWT ID claim to check.

    Returns:
        True if the jti has been explicitly revoked, False otherwise.

    Raises:
        ConnectionError | OSError | asyncio.TimeoutError | redis.exceptions.RedisError:
            the denylist could not be checked.
    """
    redis = await get_async_redis_client()
    if redis is None:
        raise ConnectionError("rs256 denylist check failed: no Redis client available")
    exists = await redis.exists(_rs256_denylist_key(jti))
    return bool(exists)
