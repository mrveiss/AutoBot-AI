# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Company-scoped CRUD for :class:`LLCRole` (#14221 step 1).

Every query carries its own ``WHERE company_id`` predicate, independent of
whatever guard the route applies. That redundancy is deliberate: the row-level
filter has had to be pinned independently five times in this module now
(#13936, #13969, #13942, #14222, #14210), because a route guard and a row filter
fail in different ways and a test that only exercises one cannot see the other.

Emits ``role.created`` / ``role.updated`` / ``role.deleted`` through
``LLCServiceBase.activity_log``, matching ``ContactService`` and
``SecretService``. A role is the anchor that tools, credentials and workflows
hang off in later steps, so "who created this role and when" is precisely the
kind of question the activity log exists to answer — and a service that mutates
silently while its siblings audit is the drift that makes the log untrustworthy.

This step deliberately carries **no occupancy and no access semantics**. Who
holds a role is #14221 step 2 — modelling it as a column here would defeat the
point, since a role outliving its occupant is the whole reason the object
exists. Access grants are step 3, and whether they subsume ``MembershipRole`` is
an open owner decision.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.activity import ActorType
from ..models.role import LLCRole
from .base import LLCServiceBase


class RoleService(LLCServiceBase):
    """Reads and writes roles, always scoped to one company."""

    async def create(
        self,
        session: AsyncSession,
        *,
        company_id: uuid.UUID,
        name: str,
        description: Optional[str] = None,
        actor: Optional[str] = None,
    ) -> LLCRole:
        if company_id is None:
            raise ValueError("company_id is required to create a role")
        cleaned = (name or "").strip()
        if not cleaned:
            # A blank name would satisfy NOT NULL while naming nothing, and the
            # per-company unique constraint would then let exactly one such row
            # exist — a single anonymous role per company is worse than an error.
            raise ValueError("role name is required")

        role = LLCRole(company_id=company_id, name=cleaned, description=description)
        session.add(role)
        await session.flush()
        await self._record(session, role, "role.created", actor, {"id": str(role.id)})
        return role

    async def _record(
        self,
        session: AsyncSession,
        role: LLCRole,
        event_type: str,
        actor: Optional[str],
        after: Optional[Dict[str, Any]],
    ) -> None:
        """Emit one activity-log event, or nothing if the DI slot is unpopulated."""
        if not self.activity_log:
            return
        await self.activity_log.record(
            session=session,
            company_id=str(role.company_id),
            actor_type=ActorType.USER if actor else ActorType.SYSTEM,
            actor_id=actor,
            event_type=event_type,
            entity_type="llc_role",
            entity_id=str(role.id),
            after=after,
        )

    async def get(self, session: AsyncSession, company_id: uuid.UUID, role_id: uuid.UUID) -> Optional[LLCRole]:
        result = await session.execute(select(LLCRole).where(LLCRole.id == role_id, LLCRole.company_id == company_id))
        return result.scalar_one_or_none()

    async def list_by_company(self, session: AsyncSession, company_id: uuid.UUID) -> List[LLCRole]:
        result = await session.execute(select(LLCRole).where(LLCRole.company_id == company_id).order_by(LLCRole.name))
        return list(result.scalars().all())

    async def update(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        role_id: uuid.UUID,
        *,
        actor: Optional[str] = None,
        **fields: Any,
    ) -> Optional[LLCRole]:
        role = await self.get(session, company_id, role_id)
        if role is None:
            return None

        allowed: Dict[str, Any] = {k: v for k, v in fields.items() if k in {"name", "description"}}
        if "name" in allowed:
            cleaned = (allowed["name"] or "").strip()
            if not cleaned:
                raise ValueError("role name is required")
            allowed["name"] = cleaned

        for key, value in allowed.items():
            setattr(role, key, value)
        await session.flush()
        if allowed:
            await self._record(session, role, "role.updated", actor, allowed)
        return role

    async def delete(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        role_id: uuid.UUID,
        *,
        actor: Optional[str] = None,
    ) -> bool:
        """Delete a role. Returns True when a row was actually removed.

        The company predicate is on the DELETE itself rather than relying on a
        prior read — a read-then-delete would widen the window in which the
        scope could be lost. The activity-log read is separate and only runs
        when something is going to be deleted.
        """
        role = await self.get(session, company_id, role_id) if self.activity_log else None
        result = await session.execute(
            sa_delete(LLCRole).where(LLCRole.id == role_id, LLCRole.company_id == company_id)
        )
        deleted = bool(result.rowcount)
        if deleted and role is not None:
            await self._record(session, role, "role.deleted", actor, None)
        return deleted
