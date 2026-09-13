# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Password-change token revocation, shared by both backends (#12924).

Changing a password must stop the sessions that were opened with the old one.
Neither backend actually did that:

- **autobot-backend** called ``SessionService.invalidate_user_sessions`` on
  password change, which writes blacklist entries to Redis — but
  ``is_token_blacklisted`` has **zero production callers**, and the backend's
  token extraction (``auth_middleware._extract_user_from_jwt``) is synchronous
  so it cannot await a Redis lookup at all. The control was inert.
- **autobot-slm-backend** has a working per-token JTI denylist that *is*
  checked on the async decode path, but nothing triggered it on password
  change, and there is no user→JTI index to revoke a user's other sessions
  with.

Per the owner's 2026-08-01 decision this uses an **epoch check** rather than
per-token bookkeeping: record when a subject's password last changed, and
reject any token issued before that moment. One write invalidates every
outstanding token for that subject at once — no index to maintain, no TTL
bookkeeping per token, and it behaves identically on both backends.

**Keyed by token subject, not user id.** Both backends put the username in
``sub``, and the backend has *two* password-change paths — the config-based
self-service endpoint in ``api/auth.py`` (which only knows a username) and the
database-backed ``UserService.change_password`` (which knows a UUID). Keying on
the subject is the one identifier both paths and both backends share.

**Failure policy: fail closed** (#16411, owner decision 2026-09-12; the SLM's
rule since #16387). If Redis cannot answer, ``get_password_epoch`` raises
:class:`RevocationCheckUnavailable` rather than reporting "not revoked", and
both callers deny the token with a 401. A token that may be revoked is never
honoured; the accepted cost is that a Redis outage takes login down with it.
A marker or a token ``iat`` that is not an integer is treated the same way
(#16422): the check cannot place the token against the epoch, so it denies.

**Tokens minted before this shipped have no ``iat``** and are treated as not
revoked, so deploying this does not sign everyone out. They age out naturally
at their own ``exp``; #12924's window closes as soon as they do.
"""

import asyncio
import logging
import time

from redis.exceptions import RedisError

from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.ssot_constants import TTL_24_HOURS

# Plain stdlib logging, deliberately. This module is imported at module scope by
# `autobot-slm-backend/services/auth.py`, whose test harness
# (`tests/api/test_auth_logout.py`) loads that file with most of the config
# stack replaced by MagicMock. `autobot_shared.logging_manager.get_logger`
# builds a RotatingFileHandler from config at call time and raises under that
# harness. Its sibling in the same import chain,
# `autobot-slm-backend/services/token_denylist.py`, uses stdlib logging for the
# same reason, and it is what CLAUDE.md's pattern table prescribes.
logger = logging.getLogger(__name__)

#: Redis key prefix for the per-subject password-change epoch.
#: nosec B105 — this is a Redis key namespace, not a credential. bandit flags
#: it only because the constant name contains "PASSWORD".
PASSWORD_EPOCH_PREFIX = "auth:pwd_epoch:"  # nosec B105

#: How long an epoch marker is kept. It only has to outlive the longest-lived
#: token that could predate it; after that every such token has expired on its
#: own and the marker cannot change any decision.
PASSWORD_EPOCH_TTL_SECONDS = TTL_24_HOURS


#: What a store that cannot answer raises: the client's own errors plus the
#: connection and timeout errors it can surface. Deliberately not ``Exception``
#: -- a bug in this module must surface as itself, not pass for an outage.
_STORE_FAILURES = (asyncio.TimeoutError, OSError, RedisError)


class RevocationCheckUnavailable(ConnectionError):
    """The check reached no verdict, so revocation cannot be ruled out (#16411, #16422).

    A ``ConnectionError`` so the SLM, which catches the store failures around
    this check and denies with a 401 (#16387), treats it exactly as it treats
    the client's own errors -- never as a 500.
    """


def _epoch_key(subject: str) -> str:
    """Redis key holding the password-change epoch for *subject*."""
    return f"{PASSWORD_EPOCH_PREFIX}{subject}"


async def _epoch_store():
    """The Redis client the check reads, or :class:`RevocationCheckUnavailable`."""
    try:
        redis = await get_async_redis_client()
    except _STORE_FAILURES as exc:
        raise RevocationCheckUnavailable(f"no Redis client ({type(exc).__name__})") from exc
    if redis is None:
        raise RevocationCheckUnavailable("no Redis client")
    return redis


async def set_password_epoch(subject: str, *, now: int | None = None) -> int | None:
    """Mark *subject*'s password as changed now, revoking older tokens.

    Returns the epoch written, or ``None`` if Redis was unavailable — in which
    case **no revocation happened** and the caller should treat the password
    change as not having invalidated other sessions.

    Args:
        subject: The token subject (``sub`` claim) whose sessions to revoke.
        now: Override for the epoch timestamp, for tests.
    """
    epoch = int(time.time()) if now is None else now

    redis = await get_async_redis_client()
    if redis is None:
        logger.error(
            "password epoch NOT recorded for subject=%s — Redis unavailable; "
            "tokens issued before this password change remain valid",
            subject,
        )
        return None

    try:
        await redis.setex(_epoch_key(subject), PASSWORD_EPOCH_TTL_SECONDS, str(epoch))
    except Exception as exc:
        logger.error(
            "password epoch NOT recorded for subject=%s: %s — tokens issued "
            "before this password change remain valid",
            subject,
            exc,
        )
        return None

    logger.info("Password epoch recorded for subject=%s: tokens issued before %s are revoked", subject, epoch)
    return epoch


async def get_password_epoch(subject: str) -> int | None:
    """Return *subject*'s password-change epoch, or None if none is recorded.

    Raises:
        RevocationCheckUnavailable: Redis could not answer (#16411), or the
            stored marker is not an integer (#16422).
    """
    redis = await _epoch_store()
    try:
        raw = await redis.get(_epoch_key(subject))
    except _STORE_FAILURES as exc:
        raise RevocationCheckUnavailable(f"epoch lookup failed ({type(exc).__name__})") from exc

    if raw is None:
        return None

    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise RevocationCheckUnavailable("epoch marker is not an integer") from exc


async def is_token_revoked_by_password_change(claims: dict) -> bool:
    """True if *claims* describe a token issued before its subject's password change.

    Returns ``False`` when the subject is unknown or the token carries no
    ``iat`` -- see the module docstring for why.

    Raises:
        RevocationCheckUnavailable: Redis could not answer (#16411), or the
            marker or the token's ``iat`` is not an integer (#16422). The token
            may be revoked, so every caller must deny it.
    """
    subject = claims.get("sub")
    if not subject:
        return False

    issued_at = claims.get("iat")
    if issued_at is None:
        # Pre-#12924 token: no way to place it relative to the epoch.
        return False

    try:
        issued_at = int(issued_at)
    except (TypeError, ValueError) as exc:
        # An unreadable iat cannot be placed against any epoch, so the token is
        # denied whether or not its subject has a marker (#16422).
        raise RevocationCheckUnavailable("token iat is not an integer") from exc

    epoch = await get_password_epoch(str(subject))
    if epoch is None:
        return False

    if issued_at < epoch:
        logger.warning(
            "Token for subject=%s rejected: issued at %s, before password change at %s",
            subject,
            issued_at,
            epoch,
        )
        return True

    return False
