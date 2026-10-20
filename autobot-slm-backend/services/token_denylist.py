# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
JWT jti-denylist, kept in the SLM's own PostgreSQL (#18663).

Revocation is enforced on the async auth path (``decode_token_async``). The sync
``decode_token`` path cannot check the store and is documented accordingly -- it
is used only where a short token TTL is the primary guard.

**Why PostgreSQL, not Redis (#18663).** The SLM is the configuration and
monitoring layer: it is what deploys the fleet, Redis included, so it must work
with nothing but its own database. With the denylist in a Redis the SLM host
never has, the fail-closed check below refused every authenticated request and
nobody could log in to a freshly installed SLM.

Fail-CLOSED policy for ``is_jti_revoked`` (#16387, unchanged): if the store
cannot answer, the function raises instead of returning ``False`` -- "not
revoked" and "unknown" are different answers. ``decode_token_async``
(``services/auth.py``) catches the raise and answers 503 (#18892). The store is now the
database the SLM cannot run without, so this no longer denies a healthy SLM.

Upgrade note: revocations recorded in Redis before #18663 are not carried over --
tokens logged out before the upgrade stay valid until they expire (at most the
token lifetime).

``revoke_jti`` stays fail-open (#16387): a logout that cannot reach the store has
nothing else to deny against; decode-time verification carries the guarantee.

Bounded access (#11443): every store interaction runs under a short deadline, so
auth latency is never hostage to a stuck connection.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError

try:  # asyncpg can raise its own errors at connect time, before SQLAlchemy wraps them
    import asyncpg

    _DRIVER_FAILURES: tuple = (asyncpg.PostgresError, asyncpg.InterfaceError)
except ImportError:  # pragma: no cover - asyncpg is the SLM's driver in deployments
    _DRIVER_FAILURES = ()

logger = logging.getLogger(__name__)

# Failures that mean "the store could not answer".
_STORE_FAILURES = (asyncio.TimeoutError, ConnectionError, OSError, SQLAlchemyError, *_DRIVER_FAILURES)

# Hard deadline for any denylist store interaction (#11443).
_STORE_DEADLINE_SECONDS = 2.0


def _session():
    """A session on the SLM database; ConnectionError if it is not initialized yet."""
    from services.database import db_service  # lazy: importable without the DB stack (config-mocking test harnesses)

    if db_service.session_factory is None:
        raise ConnectionError("jti denylist store unavailable: SLM database not initialized")
    return db_service.session_factory()


async def _revoke(jti: str, ttl_seconds: int) -> None:
    from sqlalchemy.dialects.postgresql import insert  # lazy: test suites stub sqlalchemy without dialects

    from models.auth_revocation import RevokedToken  # lazy, as in _session

    now = datetime.now(timezone.utc)
    async with _session() as session:
        stmt = insert(RevokedToken).values(jti=jti, expires_at=now + timedelta(seconds=ttl_seconds))
        # A repeat revocation keeps the later expiry, never shortens it.
        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=["jti"],
                set_={"expires_at": func.greatest(RevokedToken.expires_at, stmt.excluded.expires_at)},
            )
        )
        # Rows of tokens that have expired anyway carry no information; prune on write.
        await session.execute(delete(RevokedToken).where(RevokedToken.expires_at <= now))
        await session.commit()


async def revoke_jti(jti: str, ttl_seconds: int) -> None:
    """Deny *jti* until it would have expired anyway (*ttl_seconds*, clamped to >= 1).

    Fail-open (#16387): logs a warning and returns if the store is unavailable.
    """
    ttl = max(1, ttl_seconds)
    try:
        await asyncio.wait_for(_revoke(jti, ttl), timeout=_STORE_DEADLINE_SECONDS)
    except _STORE_FAILURES as exc:
        logger.warning("revoke_jti: jti=%r NOT revoked (store unavailable: %s)", jti, exc.__class__.__name__)
        return
    logger.info("revoke_jti: jti=%r revoked with ttl=%d", jti, ttl)


async def _lookup(jti: str) -> bool:
    from models.auth_revocation import RevokedToken  # lazy, as in _session

    async with _session() as session:
        row = await session.execute(
            select(RevokedToken.jti).where(
                RevokedToken.jti == jti, RevokedToken.expires_at > datetime.now(timezone.utc)
            )
        )
        return row.first() is not None


async def is_jti_revoked(jti: str) -> bool:
    """Return ``True`` if *jti* is on the denylist.

    Fail-CLOSED (#16387): raises when the store cannot answer within the deadline
    (#11443) rather than returning ``False``; the caller must deny the token.

    Raises:
        ConnectionError | asyncio.TimeoutError: the denylist could not be checked. A
            database error is raised as ConnectionError, the store-unavailable type
            ``decode_token_async`` turns into a 503 + Retry-After (#18892): the token is
            refused, but as "could not decide", not as a dead credential (401) or a 500.
    """
    try:
        return await asyncio.wait_for(_lookup(jti), timeout=_STORE_DEADLINE_SECONDS)
    except (SQLAlchemyError, *_DRIVER_FAILURES) as exc:
        raise ConnectionError(f"jti denylist store unavailable: {exc.__class__.__name__}") from exc
