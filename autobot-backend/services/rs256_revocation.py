# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Cross-service RS256 authority token revocation — write side (#10278).

autobot-backend is the authority that mints RS256 tokens.  When a token is
revoked (logout or explicit revocation) this module writes to the shared
Redis denylist so that all consumers (SLM and future services) reject the
token before its natural expiry.

The shared key namespace ``auth:rs256:jti:denylist:`` is defined here and
mirrored in ``autobot-slm-backend/services/rs256_denylist.py`` — both read
from and write to the same Redis keys.

Design
------
- Decodes the token WITHOUT verifying expiry so that a token that just crossed
  its exp boundary can still be revoked (prevents a thin race).
- Returns False when the token is already fully expired and the jti would have
  self-expired from Redis anyway (caller can treat as no-op).
- Writes the denylist entry with TTL = max(1, remaining_lifetime) so the key
  auto-expires once the token can no longer be presented.
- Never logs the token value; only the jti (opaque random UUID) is logged.
"""

import time

from auth_middleware import get_auth_middleware
from autobot_shared.auth.jwt_core import JWTDecodeError, _peek_alg, decode_jwt_no_verify_exp
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client

logger = get_logger(__name__)

#: Shared Redis key prefix — MUST match ``RS256_DENYLIST_PREFIX`` in
#: ``autobot-slm-backend/services/rs256_denylist.py``.
RS256_DENYLIST_PREFIX = "auth:rs256:jti:denylist:"


async def revoke_authority_token_jti(token: str) -> bool:
    """Add the jti of an RS256 authority token to the cross-service denylist.

    Args:
        token: The RS256 JWT string to revoke.

    Returns:
        True if the jti was written to the denylist, False if the token was
        already expired (nothing useful to revoke).

    Raises:
        JWTDecodeError: Token is malformed and the jti cannot be extracted.
    """
    alg = _peek_alg(token)
    if alg != "RS256":  # nosec B105 - JWT algorithm identifier string, not a credential
        raise JWTDecodeError(f"revoke_authority_token_jti: expected RS256 token, got alg={alg!r}")

    mw = get_auth_middleware()
    try:
        payload = decode_jwt_no_verify_exp(token, public_key=mw.jwt_public_key, algorithms=["RS256"])
    except JWTDecodeError:
        raise

    jti = payload.get("jti")
    if not jti:
        raise JWTDecodeError("revoke_authority_token_jti: token has no jti claim")

    exp = payload.get("exp")
    now = int(time.time())
    remaining = max(0, int(exp) - now) if exp else 3600

    if remaining == 0:
        logger.debug("rs256_revocation: token already expired (jti=%r); no denylist write needed", jti)
        return False

    redis = await get_async_redis_client()
    if redis is None:
        logger.warning("rs256_revocation: Redis unavailable; jti=%r NOT added to denylist", jti)
        return False

    key = f"{RS256_DENYLIST_PREFIX}{jti}"
    await redis.set(key, "1", ex=max(1, remaining))
    logger.info("rs256_revocation: jti=%r revoked (ttl=%ds)", jti, remaining)
    return True
