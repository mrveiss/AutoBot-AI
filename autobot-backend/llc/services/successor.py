# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Who takes over a person's things when they are removed (#20029, shared with #20446).

``resolve_successor`` only reads. It answers one question for one company, because a person can belong to
several: which active human inherits from ``user_id``. The order, first hit wins:

1. the explicit human manager (``ReportingLineService.explicit_manager``);
2. the designated human CEO (``_resolve_ceo``), skipping the Dispatcher or any agent CEO;
3. a company owner: longest tenure, then lowest id;
4. a user holding the same role (``llc_role_assignments``): longest tenure, then lowest id;
5. nobody: the caller decides what that means.

Rules that hold at every step:

* The recipient is an active human: a user row that exists, is ``is_active`` and not soft-deleted. A hard
  delete leaves memberships behind, so a membership alone proves nothing and the join to ``users`` is the check.
* The removed user is never their own successor.
* ``direct_reports`` is never read: a manager's reports are not who inherits.
* An agent (or inactive) manager at step 1 falls through to step 2, not further up that agent's chain. This is a
  reading: the maintainer decision names only an explicit *human* manager, and walking an agent's own line would
  put a person on the receiving end that nobody chose.

Each step is a small helper so #20446 can reuse them.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from user_management.models.user import User

from ..models.enums import MembershipRole, RoleHolderType
from ..models.membership import LLCCompanyMembership
from ..models.role_assignment import LLCRoleAssignment
from .reporting_line import Holder, ReportingLineService

_USER = RoleHolderType.USER.value
_LATEST = datetime.max


def pick_longest_tenure(rows: Iterable[tuple[uuid.UUID, Optional[datetime]]]) -> Optional[uuid.UUID]:
    """The id with the earliest start, the lowest id on a tie; None for no rows.

    A missing start sorts last, so a row that records nothing never beats one that does. Naive and aware
    datetimes are compared by their wall-clock fields, as both come from one column.
    """
    ranked = [(since.replace(tzinfo=None) if since else _LATEST, uid) for uid, since in rows]
    return min(ranked)[1] if ranked else None


async def active_human_ids(session: AsyncSession, candidates: Iterable[uuid.UUID]) -> set[uuid.UUID]:
    """Those of *candidates* that are an active, non-deleted user row. Hard-deleted users are absent."""
    ids = set(candidates)
    if not ids:
        return set()
    stmt = select(User.id).where(User.id.in_(ids), User.deleted_at.is_(None)).filter_by(is_active=True)
    return set((await session.execute(stmt)).scalars().all())


async def _active_or_none(session: AsyncSession, holder: Optional[Holder], removed: uuid.UUID) -> Optional[uuid.UUID]:
    """The holder's id when it is an active human other than *removed*; an agent or anyone else is None."""
    if holder is None or holder.type != _USER or holder.id == removed:
        return None
    return holder.id if holder.id in await active_human_ids(session, [holder.id]) else None


async def manager_successor(session: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID) -> Optional[uuid.UUID]:
    """Step 1: the explicit human manager. An agent manager yields None and the caller moves to step 2."""
    manager = await ReportingLineService().explicit_manager(session, company_id, Holder(_USER, user_id))
    return await _active_or_none(session, manager, user_id)


async def ceo_successor(session: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID) -> Optional[uuid.UUID]:
    """Step 2: the designated CEO, only when that holder is an active human."""
    ceo = await ReportingLineService()._resolve_ceo(session, company_id)
    return await _active_or_none(session, ceo, user_id)


async def owner_successor(session: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID) -> Optional[uuid.UUID]:
    """Step 3: the company owner who has been a member longest, the lowest id on a tie."""
    rows = (
        await session.execute(
            select(LLCCompanyMembership.user_id, LLCCompanyMembership.created_at).where(
                LLCCompanyMembership.company_id == company_id,
                LLCCompanyMembership.role == MembershipRole.OWNER.value,
                LLCCompanyMembership.user_id != user_id,
            )
        )
    ).all()
    alive = await active_human_ids(session, [uid for uid, _ in rows])
    return pick_longest_tenure((uid, since) for uid, since in rows if uid in alive)


async def _held_role_ids(session: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID) -> list[uuid.UUID]:
    """The roles *user_id* holds now in this company."""
    rows = await session.execute(
        select(LLCRoleAssignment.role_id).where(
            LLCRoleAssignment.company_id == company_id,
            LLCRoleAssignment.holder_type == _USER,
            LLCRoleAssignment.holder_user_id == user_id,
            LLCRoleAssignment.ended_at.is_(None),
        )
    )
    return list(rows.scalars().all())


async def role_successor(session: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID) -> Optional[uuid.UUID]:
    """Step 4: another current holder of a role the user holds, longest in the role, the lowest id on a tie."""
    role_ids = await _held_role_ids(session, company_id, user_id)
    if not role_ids:
        return None
    rows = (
        await session.execute(
            select(LLCRoleAssignment.holder_user_id, LLCRoleAssignment.started_at).where(
                LLCRoleAssignment.company_id == company_id,
                LLCRoleAssignment.role_id.in_(role_ids),
                LLCRoleAssignment.holder_type == _USER,
                LLCRoleAssignment.holder_user_id != user_id,
                LLCRoleAssignment.ended_at.is_(None),
            )
        )
    ).all()
    alive = await active_human_ids(session, [uid for uid, _ in rows])
    return pick_longest_tenure((uid, since) for uid, since in rows if uid in alive)


async def resolve_successor(session: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID) -> Optional[uuid.UUID]:
    """The active human who inherits from *user_id* in *company_id*, or None. Reads only."""
    for step in (manager_successor, ceo_successor, owner_successor, role_successor):
        found = await step(session, company_id, user_id)
        if found is not None:
            return found
    return None
