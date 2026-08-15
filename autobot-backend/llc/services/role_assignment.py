# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Occupancy operations for :class:`LLCRoleAssignment` (#14221 step 2).

Ending a tenure is always an UPDATE of ``ended_at``, never a DELETE. The owner's
requirement is that work left behind still has a role to belong to, which only
holds if the history survives the departure.

Every query carries its own ``WHERE company_id``, independent of the route
guard and independent of the join to ``llc_roles`` — see the model docstring.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.enums import RoleHolderType
from ..models.role import LLCRole
from ..models.role_assignment import LLCRoleAssignment

_HOLDER_COLUMNS = {
    RoleHolderType.AGENT: "holder_agent_id",
    RoleHolderType.USER: "holder_user_id",
    RoleHolderType.CONTACT: "holder_contact_id",
}


def _coerce_holder_type(holder_type: object) -> RoleHolderType:
    """Accept an enum member or its string value; reject anything else.

    A bare string that is not a member must raise here rather than reach the
    ``String(16)`` column, which would happily store it.
    """
    try:
        return RoleHolderType(holder_type)
    except ValueError as exc:
        valid = ", ".join(sorted(m.value for m in RoleHolderType))
        raise ValueError(f"invalid holder_type {holder_type!r}; expected one of: {valid}") from exc


class RoleAssignmentService:
    """Assigns holders to roles and ends tenures without losing history."""

    async def assign(
        self,
        session: AsyncSession,
        *,
        company_id: uuid.UUID,
        role_id: uuid.UUID,
        holder_type: object,
        holder_id: uuid.UUID,
    ) -> LLCRoleAssignment:
        if company_id is None or role_id is None or holder_id is None:
            raise ValueError("company_id, role_id and holder_id are all required")
        resolved = _coerce_holder_type(holder_type)

        # The role must exist *in this company*. Without this an assignment
        # could name a role from another company, or one that never existed —
        # the orphan-reference shape fixed in #14222.
        role = await session.execute(
            select(LLCRole.id).where(LLCRole.id == role_id, LLCRole.company_id == company_id)
        )
        if role.scalar_one_or_none() is None:
            raise ValueError(f"role {role_id} does not exist in company {company_id}")

        if await self._current_tenure(session, company_id, role_id, resolved, holder_id):
            raise ValueError("holder already holds this role")

        assignment = LLCRoleAssignment(
            company_id=company_id,
            role_id=role_id,
            holder_type=resolved.value,
            **{_HOLDER_COLUMNS[resolved]: holder_id},
        )
        session.add(assignment)
        await session.flush()
        return assignment

    async def _current_tenure(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        role_id: uuid.UUID,
        holder_type: RoleHolderType,
        holder_id: uuid.UUID,
    ) -> Optional[LLCRoleAssignment]:
        column = getattr(LLCRoleAssignment, _HOLDER_COLUMNS[holder_type])
        result = await session.execute(
            select(LLCRoleAssignment).where(
                LLCRoleAssignment.company_id == company_id,
                LLCRoleAssignment.role_id == role_id,
                LLCRoleAssignment.holder_type == holder_type.value,
                column == holder_id,
                LLCRoleAssignment.ended_at.is_(None),
            )
        )
        return result.scalars().first()

    async def current_holders(
        self, session: AsyncSession, company_id: uuid.UUID, role_id: uuid.UUID
    ) -> List[LLCRoleAssignment]:
        """Holders with an open tenure. Several may hold one role at once."""
        result = await session.execute(
            select(LLCRoleAssignment)
            .where(
                LLCRoleAssignment.company_id == company_id,
                LLCRoleAssignment.role_id == role_id,
                LLCRoleAssignment.ended_at.is_(None),
            )
            .order_by(LLCRoleAssignment.started_at)
        )
        return list(result.scalars().all())

    async def history(
        self, session: AsyncSession, company_id: uuid.UUID, role_id: uuid.UUID
    ) -> List[LLCRoleAssignment]:
        """Every tenure ever, open or ended — who has held this role."""
        result = await session.execute(
            select(LLCRoleAssignment)
            .where(
                LLCRoleAssignment.company_id == company_id,
                LLCRoleAssignment.role_id == role_id,
            )
            .order_by(LLCRoleAssignment.started_at)
        )
        return list(result.scalars().all())

    async def roles_held_by(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        holder_type: object,
        holder_id: uuid.UUID,
    ) -> List[LLCRole]:
        """Roles this holder currently occupies — what offboarding must hand over."""
        resolved = _coerce_holder_type(holder_type)
        column = getattr(LLCRoleAssignment, _HOLDER_COLUMNS[resolved])
        result = await session.execute(
            select(LLCRole)
            .join(LLCRoleAssignment, LLCRoleAssignment.role_id == LLCRole.id)
            .where(
                LLCRole.company_id == company_id,
                LLCRoleAssignment.company_id == company_id,
                LLCRoleAssignment.holder_type == resolved.value,
                column == holder_id,
                LLCRoleAssignment.ended_at.is_(None),
            )
            .order_by(LLCRole.name)
        )
        return list(result.scalars().all())

    async def end_tenure(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        assignment_id: uuid.UUID,
        *,
        ended_at: Optional[datetime] = None,
    ) -> Optional[LLCRoleAssignment]:
        """Close an open tenure. The row survives — that is the whole point.

        Returns ``None`` when there is no open tenure with that id in this
        company. Re-ending an already-ended tenure is a no-op returning ``None``
        rather than silently rewriting the original end date.
        """
        result = await session.execute(
            select(LLCRoleAssignment).where(
                LLCRoleAssignment.id == assignment_id,
                LLCRoleAssignment.company_id == company_id,
                LLCRoleAssignment.ended_at.is_(None),
            )
        )
        assignment = result.scalar_one_or_none()
        if assignment is None:
            return None

        assignment.ended_at = ended_at or datetime.now(timezone.utc)
        await session.flush()
        return assignment

    async def vacate_holder(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        holder_type: object,
        holder_id: uuid.UUID,
        *,
        ended_at: Optional[datetime] = None,
    ) -> List[LLCRoleAssignment]:
        """End every open tenure for one holder — the offboarding entry point.

        Returns the tenures that were closed, so the caller knows which roles
        are now unoccupied and need a successor. Deliberately does not reassign:
        choosing the next holder is step 4, and inventing one here would hide
        that a role was left vacant.
        """
        resolved = _coerce_holder_type(holder_type)
        column = getattr(LLCRoleAssignment, _HOLDER_COLUMNS[resolved])
        result = await session.execute(
            select(LLCRoleAssignment).where(
                LLCRoleAssignment.company_id == company_id,
                LLCRoleAssignment.holder_type == resolved.value,
                column == holder_id,
                LLCRoleAssignment.ended_at.is_(None),
            )
        )
        closing = list(result.scalars().all())
        stamp = ended_at or datetime.now(timezone.utc)
        for assignment in closing:
            assignment.ended_at = stamp
        await session.flush()
        return closing
