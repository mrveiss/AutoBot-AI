# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Race-safe user insert (split out of ``user_service.py``, #15772).

``UserService.create_user`` reads (``_check_duplicate_user``) then inserts,
with nothing handling the collision: two concurrent requests for the same
email/username both pass the pre-check SELECT, both insert, and the loser's
unique-index violation surfaced as an uncaught ``IntegrityError`` -- a 500,
contradicting the 409 the sequential duplicate already returns (#15736,
#15752).

The insert here runs inside a SAVEPOINT (``session.begin_nested()``) rather
than a dialect-specific ``ON CONFLICT``: production is PostgreSQL and tests
run on SQLite, so a Postgres-only construct would make the conflict branch
unreachable in CI -- skipped exactly where it needs proving. A SAVEPOINT
reaches the identical code path on both dialects, and isolates the failed
INSERT so it rolls back only itself, leaving the caller's outer transaction
usable for whatever it does next.

Split into its own module because ``user_service.py`` is grandfathered at a
recorded line ceiling with zero headroom (#14236); the precedent for this
kind of split is ``user_service_errors.py`` (#15736).
"""

from __future__ import annotations

from typing import Awaitable, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger
from user_management.models import User
from user_management.services.user_service_errors import DuplicateUserError

logger = get_logger(__name__)

FindExisting = Callable[[str, str], Awaitable["User | None"]]


async def insert_user_or_raise_duplicate(
    session: AsyncSession,
    user: User,
    email: str,
    username: str,
    find_existing: FindExisting,
) -> None:
    """Insert *user*, translating a unique-index collision into ``DuplicateUserError``.

    Runs the INSERT inside a SAVEPOINT so a losing insert rolls back only
    itself rather than poisoning the caller's outer transaction (#15772).
    """
    session.add(user)
    try:
        async with session.begin_nested():
            await session.flush()
    except IntegrityError as exc:
        raise await _resolve_conflict(email, username, find_existing) from exc


async def _resolve_conflict(email: str, username: str, find_existing: FindExisting) -> DuplicateUserError:
    """Name the field the losing insert collided on, from the winning row.

    Deliberately independent of ``UserService._check_duplicate_user`` (the
    pre-insert check) -- it re-reads the table itself via *find_existing*, so
    a test that stubs out the pre-check to reach this branch cannot silently
    disable this lookup too.
    """
    existing = await find_existing(email, username)
    if existing is not None:
        if existing.email.lower() == email.lower():
            return DuplicateUserError(f"User with email '{email}' already exists", field="email")
        return DuplicateUserError(f"User with username '{username}' already exists", field="username")

    # Defensive: the unique index rejected the insert, so a colliding row
    # must exist. Don't fail open if the re-read somehow misses it.
    logger.error(
        "Unique-index conflict on user insert (email=%s, username=%s) but no colliding row found on re-read",
        email,
        username,
    )
    return DuplicateUserError(f"User with email '{email}' or username '{username}' already exists", field="email")
