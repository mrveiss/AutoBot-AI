# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""App-side triggers for the secrets uniqueness constraint (#17850).

Migration ``20261120_117`` skips the constraint while duplicate secrets exist. The app applies it itself, through the
one function that holds the DDL (``migrations.secret_unique``): after the approved duplicate removal empties the last
group, and at startup. Failure is logged by exception type only and never raised, so it cannot crash startup or fail
an approval.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from autobot_shared.logging_manager import get_logger
from migrations.secret_unique import CREATED, ensure_secret_unique_constraint

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)


async def ensure_constraint_in(session: "AsyncSession") -> str | None:
    """Run the ensure on ``session``'s own transaction and commit. None (logged by type) on any failure."""
    try:
        outcome = await (await session.connection()).run_sync(ensure_secret_unique_constraint)
        await session.commit()
        return outcome
    except Exception as exc:
        logger.warning("secrets uniqueness constraint not ensured: %s", type(exc).__name__)
        try:
            await session.rollback()
        except Exception as rollback_exc:
            logger.warning("rollback after a failed constraint ensure failed: %s", type(rollback_exc).__name__)
        return None


async def ensure_secret_unique_at_startup() -> None:
    """Cheap startup check: create the constraint when missing and no duplicates remain. Never raises."""
    try:
        from user_management.database import get_async_session_factory

        async with get_async_session_factory()() as session:
            outcome = await ensure_constraint_in(session)
        if outcome == CREATED:
            logger.info("secrets uniqueness constraint applied at startup")
    except Exception as exc:
        logger.warning("secrets uniqueness constraint startup check failed: %s", type(exc).__name__)


async def ensure_after_duplicate_removal(session: "AsyncSession") -> None:
    """Called after a removal: once no duplicate group is left, the constraint is created."""
    from services.secret_duplicates import find_duplicate_groups

    try:
        if await find_duplicate_groups(session):
            return
    except Exception as exc:
        logger.warning("duplicate recount after a removal failed: %s", type(exc).__name__)
        return
    await ensure_constraint_in(session)
