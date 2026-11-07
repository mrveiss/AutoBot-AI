# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The row locks a company move takes, and how a lost lock race is reported (#19593).

Split out of ``company.py``: :class:`CompanyMoveLockMixin` gives ``CompanyService``
its id-ordered chain lock, and :func:`deadlock_is_contention` is the ONE place a
Postgres ``deadlock_detected`` becomes the retryable :class:`CompanyMoveContendedError`,
for the org locks and the membership locks alike.
"""

import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator, List, Optional

from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from autobot_shared.db_errors import PG_DEADLOCK_DETECTED, sqlstate_of
from autobot_shared.logging_manager import get_logger
from user_management.models.organization import Organization

logger = get_logger(__name__)

#: Most chain-lock passes one move takes before giving up (#19593). A pass repeats
#: only when a concurrent move committed a change to the new parent's ancestor chain
#: between reading and locking it; needing more than this means the tree is being
#: churned under the move, and refusing it is safer than looping.
MOVE_LOCK_MAX_PASSES = 8


class CompanyCycleError(Exception):
    """Raised when a parent_org_id assignment would create a hierarchy cycle."""


class CompanyMoveContendedError(Exception):
    """A move lost a lock race; nothing was changed and the caller should retry (HTTP 409).

    Raised when the ancestor chain kept changing for MOVE_LOCK_MAX_PASSES passes, or
    when Postgres picked this move as a deadlock victim. Either way the transaction
    must be rolled back and the move retried from the start: only a fresh
    transaction gives up the rows this one already holds.
    """


@asynccontextmanager
async def deadlock_is_contention() -> AsyncIterator[None]:
    """Turn a Postgres ``deadlock_detected`` inside the block into :class:`CompanyMoveContendedError`.

    Every lock a move takes runs inside this, so a lost lock race is always a
    retryable 409 and never a 500. Any other database error propagates unchanged.
    """
    try:
        yield
    except DBAPIError as exc:
        if sqlstate_of(exc) != PG_DEADLOCK_DETECTED:
            raise
        logger.info("Company move deadlocked with a concurrent writer; refused as retryable")
        raise CompanyMoveContendedError("a concurrent change holds rows this move needs; retry the move") from exc


class CompanyMoveLockMixin:
    """The chain lock of ``CompanyService.move``; the host class provides ``self.session``."""

    async def _lock_move_rows(self, company_id: uuid.UUID, parent_org_id: Optional[uuid.UUID]) -> None:
        """Lock the moved org and the new parent's ancestor chain ``FOR UPDATE``, in id order (#19593).

        Overlapping movers each take their set in one id-ordered statement, so one
        waits for the other rather than both reading a tree about to change. The chain
        is re-read under the lock; if it grew (a concurrent move committed), the next
        pass re-locks the FULL set in id order, up to MOVE_LOCK_MAX_PASSES, then
        :class:`CompanyMoveContendedError`. A later pass still holds earlier rows while
        it waits, so a wait cycle is possible there; Postgres then aborts one mover with
        ``deadlock_detected``, which :func:`deadlock_is_contention` turns into the same
        retryable error. An in-transaction (savepoint) retry would rebuild the same cycle, so the
        retry is a fresh transaction by the caller. Fails closed: never a cycle.
        """
        wanted = {company_id, *await self._chain_ids(parent_org_id)}
        for _ in range(MOVE_LOCK_MAX_PASSES):
            await self._lock_ids(wanted)
            chain = {company_id, *await self._chain_ids(parent_org_id)}
            if chain <= wanted:
                return
            wanted |= chain
        raise CompanyMoveContendedError(
            f"Moving company {company_id}: the new parent's ancestor chain kept changing "
            f"across {MOVE_LOCK_MAX_PASSES} lock passes; retry the move"
        )

    async def _chain_ids(self, start_id: Optional[uuid.UUID]) -> List[uuid.UUID]:
        """*start_id* and its ancestors, nearest first; :class:`CompanyCycleError` on a loop."""
        chain: List[uuid.UUID] = []
        current_id = start_id
        while current_id is not None:
            if current_id in chain:
                raise CompanyCycleError(f"Company {start_id} has a hierarchy cycle above it")
            chain.append(current_id)
            result = await self.session.execute(select(Organization.parent_org_id).where(Organization.id == current_id))
            current_id = result.scalar_one_or_none()
        return chain

    async def _lock_ids(self, ids: set[uuid.UUID]) -> None:
        """Lock *ids* ``FOR UPDATE`` in one id-ordered statement; a deadlock is a retryable refusal."""
        stmt = select(Organization.id).where(Organization.id.in_(ids)).order_by(Organization.id).with_for_update()
        async with deadlock_is_contention():
            await self.session.execute(stmt)
