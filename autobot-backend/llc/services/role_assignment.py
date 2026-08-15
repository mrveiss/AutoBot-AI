# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Occupancy operations for :class:`LLCRoleAssignment` (#14221 step 2).

Ending a tenure is always an UPDATE of ``ended_at``, never a DELETE. The owner's
requirement is that work left behind still has a role to belong to, which only
holds if the history survives the departure.

Every query carries its own ``WHERE company_id``, independent of the route
guard and independent of the join to ``roles`` — see the model docstring.

Emits ``role_assignment.created`` / ``role_assignment.ended`` through
``LLCServiceBase.activity_log``, matching ``RoleService`` and ``ContactService``.
Occupancy changes are exactly what an org chart needs an audit trail for: "who
held this role in March" is unanswerable from the current rows alone once
someone has been assigned and unassigned repeatedly.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from user_management.models.role import Role

from ..models.activity import ActorType
from ..models.enums import RoleHolderType
from ..models.role_assignment import LLCRoleAssignment
from .base import LLCServiceBase

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


class RoleAssignmentService(LLCServiceBase):
    """Assigns holders to roles and ends tenures without losing history."""

    async def _record(
        self,
        session: AsyncSession,
        assignment: LLCRoleAssignment,
        event_type: str,
        actor: Optional[str],
        after: Optional[Dict[str, Any]],
    ) -> None:
        """Emit one activity-log event, or nothing if the DI slot is unpopulated."""
        if not self.activity_log:
            return
        await self.activity_log.record(
            session=session,
            company_id=str(assignment.company_id),
            actor_type=ActorType.USER if actor else ActorType.SYSTEM,
            actor_id=actor,
            event_type=event_type,
            entity_type="llc_role_assignment",
            entity_id=str(assignment.id),
            after=after,
        )

    async def assign(
        self,
        session: AsyncSession,
        *,
        company_id: uuid.UUID,
        role_id: uuid.UUID,
        holder_type: object,
        holder_id: uuid.UUID,
        actor: Optional[str] = None,
    ) -> LLCRoleAssignment:
        if company_id is None or role_id is None or holder_id is None:
            raise ValueError("company_id, role_id and holder_id are all required")
        resolved = _coerce_holder_type(holder_type)
        await self._require_role(session, company_id, role_id)

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
        await self._record(
            session,
            assignment,
            "role_assignment.created",
            actor,
            {"role_id": str(role_id), "holder_type": resolved.value},
        )
        return assignment

    async def _require_role(self, session: AsyncSession, company_id: uuid.UUID, role_id: uuid.UUID) -> None:
        """The role must exist *in this company*.

        Without this an assignment could name a role from another company, or
        one that never existed — the orphan-reference shape fixed in #14222.
        """
        result = await session.execute(select(Role.id).where(Role.id == role_id, Role.org_id == company_id))
        if result.scalar_one_or_none() is None:
            raise ValueError(f"role {role_id} does not exist in company {company_id}")

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
    ) -> List[Role]:
        """Roles this holder currently occupies — what offboarding must hand over."""
        resolved = _coerce_holder_type(holder_type)
        column = getattr(LLCRoleAssignment, _HOLDER_COLUMNS[resolved])
        result = await session.execute(
            select(Role)
            .join(LLCRoleAssignment, LLCRoleAssignment.role_id == Role.id)
            .where(
                Role.org_id == company_id,
                LLCRoleAssignment.company_id == company_id,
                LLCRoleAssignment.holder_type == resolved.value,
                column == holder_id,
                LLCRoleAssignment.ended_at.is_(None),
            )
            .order_by(Role.name)
        )
        return list(result.scalars().all())

    async def end_tenure(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        assignment_id: uuid.UUID,
        *,
        ended_at: Optional[datetime] = None,
        actor: Optional[str] = None,
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

        await self._close(session, assignment, ended_at or datetime.now(timezone.utc), actor)
        return assignment

    async def _close(
        self,
        session: AsyncSession,
        assignment: LLCRoleAssignment,
        stamp: datetime,
        actor: Optional[str],
    ) -> None:
        assignment.ended_at = stamp
        await session.flush()
        await self._record(
            session,
            assignment,
            "role_assignment.ended",
            actor,
            {"role_id": str(assignment.role_id), "ended_at": stamp.isoformat()},
        )

    async def vacate_holder(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        holder_type: object,
        holder_id: uuid.UUID,
        *,
        ended_at: Optional[datetime] = None,
        actor: Optional[str] = None,
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
            # One event per tenure, not one per departure: each role losing its
            # holder is a separate thing the org chart has to answer for.
            await self._close(session, assignment, stamp, actor)
        return closing
