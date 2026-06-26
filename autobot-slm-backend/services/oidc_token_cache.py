# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
OIDC userinfo / authority-token claim cache — D1 (#10158).

Caches the normalized claims from a verified authority RS256 token so that
repeated requests from the same bearer token do NOT hit the JWKS verifier or
(by extension) the upstream IdP on every call.

Design
------
- Cache key  : ``slm:oidc:token_cache:{token_hash}`` — token hash (SHA-256
  hex, first 40 chars) so no secret material is stored as the key.
- Cache value : JSON-serialised normalized claims dict.
- TTL         : read once from ``SLM_OIDC_TOKEN_CACHE_TTL`` env var at module
  load (never hard-coded).  Default = 300 s (5 min) — balances freshness
  with IdP round-trip reduction.  Set to 0 to disable caching.
- Invalidation: ``invalidate_token_cache(token)`` writes an empty marker entry
  with TTL=1 that overwrites the cached claims, causing the next verify call
  to re-verify.  Called by the SLM logout path so a revoked SSO session is
  not served from the cache for up to TTL seconds.
- Fail-open   : if Redis is unavailable the cache is simply skipped; the
  token is re-verified from JWKS on every request (no crash, minor perf hit).
"""

import hashlib
import json
import logging
import os
from typing import Any, Dict, Optional

from autobot_shared.redis_client import get_async_redis_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level TTL constant — env var driven, never hard-coded
# ---------------------------------------------------------------------------

_CACHE_TTL_DEFAULT = 300  # 5 minutes

_ENV_CACHE_TTL = "SLM_OIDC_TOKEN_CACHE_TTL"


def _resolve_cache_ttl() -> int:
    """Return OIDC token cache TTL in seconds from env var or default."""
    raw = os.environ.get(_ENV_CACHE_TTL, "")
    if not raw:
        return _CACHE_TTL_DEFAULT
    try:
        val = int(raw)
    except ValueError:
        logger.warning(
            "%s=%r is not an integer; using default %d s", _ENV_CACHE_TTL, raw, _CACHE_TTL_DEFAULT
        )
        return _CACHE_TTL_DEFAULT
    if val < 0:
        logger.warning("%s=%d is negative; treating as 0 (cache disabled)", _ENV_CACHE_TTL, val)
        return 0
    return val


#: Module-level constant resolved at import time — avoids repeated env lookups.
OIDC_TOKEN_CACHE_TTL: int = _resolve_cache_ttl()

_CACHE_KEY_PREFIX = "slm:oidc:token_cache:"


def _cache_key(token: str) -> str:
    """Derive a Redis key from the first 40 hex chars of the token SHA-256 digest.

    Storing the raw token as a Redis key would leak secret material into Redis
    keyspace logs / MONITOR output.  The digest is collision-resistant for this
    bounded use-case.
    """
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return f"{_CACHE_KEY_PREFIX}{digest[:40]}"


async def get_cached_claims(token: str) -> Optional[Dict[str, Any]]:
    """Return cached normalized claims for *token*, or None on cache miss/error.

    Args:
        token: Raw bearer JWT string.

    Returns:
        Deserialized claims dict, or None when not cached or Redis is down.
    """
    if OIDC_TOKEN_CACHE_TTL == 0:
        return None
    redis = await get_async_redis_client()
    if redis is None:
        return None
    try:
        raw = await redis.get(_cache_key(token))
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as exc:
        logger.warning("oidc_token_cache: get failed: %s", exc)
        return None


async def cache_claims(token: str, claims: Dict[str, Any]) -> None:
    """Store *claims* for *token* in Redis with TTL = OIDC_TOKEN_CACHE_TTL.

    Silently no-ops when TTL is 0 (caching disabled) or Redis is unavailable.

    Args:
        token: Raw bearer JWT string.
        claims: Normalized claims dict returned by verify_authority_token.
    """
    if OIDC_TOKEN_CACHE_TTL == 0:
        return
    redis = await get_async_redis_client()
    if redis is None:
        return
    try:
        await redis.set(_cache_key(token), json.dumps(claims), ex=OIDC_TOKEN_CACHE_TTL)
        logger.debug("oidc_token_cache: cached claims for token (sub=%r)", claims.get("sub"))
    except Exception as exc:
        logger.warning("oidc_token_cache: set failed: %s", exc)


async def invalidate_token_cache(token: str) -> None:
    """Invalidate the cached claims for *token* (e.g. on logout).

    Overwrites the cache entry with a 1-second tombstone so the next request
    gets a cache miss and re-verifies from JWKS.

    Called by the A2 logout path (coordinate with jti-denylist).
    """
    redis = await get_async_redis_client()
    if redis is None:
        logger.warning("oidc_token_cache: invalidate skipped — Redis unavailable")
        return
    try:
        await redis.delete(_cache_key(token))
        logger.debug("oidc_token_cache: invalidated cache entry for token")
    except Exception as exc:
        logger.warning("oidc_token_cache: invalidate failed: %s", exc)
