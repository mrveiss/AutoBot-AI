# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The SLM's password-epoch store, in its own PostgreSQL (#18663).

``autobot_shared.user_management.password_epoch`` decides whether a token was
issued before its subject's last password change (#12924) and keeps the epoch
in Redis by default -- right for the backend, which runs where Redis is. The SLM
deploys Redis, so it must not need it: ``install()`` routes the shared module's
epoch reads and writes to the ``slm_password_epochs`` table instead. The rule
itself, and its fail-closed handling (#16411, #16422), stay in the shared module.

- ``get``: raises ``RevocationCheckUnavailable`` when the store cannot answer,
  so the caller denies the token (fail-closed, like the Redis store).
- ``set``: returns the epoch, or ``None`` after logging when the write fails
  (fail-open, like the Redis store: the password change itself has happened).
"""

from __future__ import annotations

import asyncio
import logging
import time

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from autobot_shared.user_management import password_epoch
from autobot_shared.user_management.password_epoch import RevocationCheckUnavailable

try:  # asyncpg can raise its own errors at connect time, before SQLAlchemy wraps them
    import asyncpg

    _DRIVER_FAILURES: tuple = (asyncpg.PostgresError, asyncpg.InterfaceError)
except ImportError:  # pragma: no cover - asyncpg is the SLM's driver in deployments
    _DRIVER_FAILURES = ()

logger = logging.getLogger(__name__)

_STORE_FAILURES = (asyncio.TimeoutError, ConnectionError, OSError, SQLAlchemyError, *_DRIVER_FAILURES)
_STORE_DEADLINE_SECONDS = 2.0  # same bound as the jti denylist (#11443)


def _session():
    from services.database import db_service  # lazy: importable without the DB stack (config-mocking test harnesses)

    if db_service.session_factory is None:
        raise ConnectionError("password-epoch store unavailable: SLM database not initialized")
    return db_service.session_factory()


async def _read(subject: str) -> int | None:
    from models.auth_revocation import PasswordEpoch  # lazy, as in _session

    async with _session() as session:
        row = await session.execute(select(PasswordEpoch.epoch).where(PasswordEpoch.subject == subject))
        value = row.scalar_one_or_none()
        return None if value is None else int(value)


async def get_epoch(subject: str) -> int | None:
    """The last password change of *subject*, or None if it never changed."""
    try:
        return await asyncio.wait_for(_read(subject), timeout=_STORE_DEADLINE_SECONDS)
    except _STORE_FAILURES as exc:
        raise RevocationCheckUnavailable(f"password-epoch store unavailable: {exc.__class__.__name__}") from exc


async def _write(subject: str, epoch: int) -> None:
    from sqlalchemy.dialects.postgresql import insert  # lazy: test suites stub sqlalchemy without dialects

    from models.auth_revocation import PasswordEpoch  # lazy, as in _session

    async with _session() as session:
        stmt = insert(PasswordEpoch).values(subject=subject, epoch=epoch)
        # Never move an epoch backwards: that would re-validate tokens it revoked.
        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=["subject"], set_={"epoch": func.greatest(PasswordEpoch.epoch, stmt.excluded.epoch)}
            )
        )
        await session.commit()


async def set_epoch(subject: str, *, now: int | None = None) -> int | None:
    """Record a password change of *subject* now; None (logged) if the store failed."""
    epoch = int(now if now is not None else time.time())
    try:
        await asyncio.wait_for(_write(subject, epoch), timeout=_STORE_DEADLINE_SECONDS)
    except _STORE_FAILURES as exc:
        logger.error("password epoch NOT recorded for subject=%s: %s", subject, exc.__class__.__name__)
        return None
    return epoch


def install() -> None:
    """Route the shared password-epoch rule to the SLM's own database (#18663)."""
    password_epoch.use_epoch_store(get_epoch=get_epoch, set_epoch=set_epoch)
