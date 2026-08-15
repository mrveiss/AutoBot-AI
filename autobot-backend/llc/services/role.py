# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Company-scoped role operations over the canonical ``roles`` table (#14221 step 1).

**No new role table.** An earlier draft of this step added ``llc_roles``, which
was a fork: ``autobot_shared.user_management.models.role.Role`` already carries
``org_id``, ``name``, ``description``, and already has ``role_permissions`` and
``user_roles`` hanging off it.

The fork was not obvious because "company" and "organization" read as different
things. They are not — a Company OS company **is** a row in ``organizations``:

* ``llc/models/company.py``: "storage is the ``organizations`` table; the LLC
  layer adds company-lifecycle …"
* ``llc/models/heartbeat_run.py``: "company_id matches the UUID PK of the
  organizations table"

So ``Role.org_id`` and every LLC ``company_id`` are the same column, and a role
scoped to a Company OS company is a ``Role`` row with ``org_id`` set. Owner
framing this satisfies directly:

    one user can have different roles in different companies … companies are
    not business entities, they are virtual company objects, more like
    departments inside one business entity

That is a user holding several ``Role`` rows whose ``org_id`` differ — already
expressible, with no new table. Who may *reach* a company at all stays
``LLCCompanyMembership``'s job.

Two safety properties this service must hold, because it operates on a shared
table rather than one it owns:

1. Every query filters ``org_id == company_id``. System roles have
   ``org_id IS NULL``, so they are invisible here — a company-scoped caller can
   neither read nor modify them.
2. ``is_system`` roles are refused explicitly on write, so a system role that
   somehow carried an ``org_id`` still could not be edited or deleted through a
   company-scoped path.

``name`` uniqueness per company is enforced here in the application, because the
shared ``roles`` table has **no** unique constraint on ``(org_id, name)``. That
gap is real and is tracked separately — adding a constraint to a live shared
table with existing rows is its own migration with its own risk, and does not
belong bundled into this step.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from user_management.models.role import Role

from ..models.activity import ActorType
from .base import LLCServiceBase


class RoleService(LLCServiceBase):
    """Reads and writes company-scoped roles on the canonical ``roles`` table."""

    async def create(
        self,
        session: AsyncSession,
        *,
        company_id: uuid.UUID,
        name: str,
        description: Optional[str] = None,
        actor: Optional[str] = None,
    ) -> Role:
        if company_id is None:
            raise ValueError("company_id is required to create a role")
        cleaned = (name or "").strip()
        if not cleaned:
            # A blank name would satisfy NOT NULL while naming nothing.
            raise ValueError("role name is required")

        if await self._find_by_name(session, company_id, cleaned) is not None:
            raise ValueError(f"a role named {cleaned!r} already exists in this company")

        role = Role(org_id=company_id, name=cleaned, description=description, is_system=False)
        session.add(role)
        await session.flush()
        await self._record(session, role, "role.created", actor, {"id": str(role.id)})
        return role

    async def _find_by_name(self, session: AsyncSession, company_id: uuid.UUID, name: str) -> Optional[Role]:
        result = await session.execute(select(Role).where(Role.org_id == company_id, Role.name == name))
        return result.scalars().first()

    async def _record(
        self,
        session: AsyncSession,
        role: Role,
        event_type: str,
        actor: Optional[str],
        after: Optional[Dict[str, Any]],
    ) -> None:
        """Emit one activity-log event, or nothing if the DI slot is unpopulated."""
        if not self.activity_log:
            return
        await self.activity_log.record(
            session=session,
            company_id=str(role.org_id),
            actor_type=ActorType.USER if actor else ActorType.SYSTEM,
            actor_id=actor,
            event_type=event_type,
            entity_type="role",
            entity_id=str(role.id),
            after=after,
        )

    async def get(self, session: AsyncSession, company_id: uuid.UUID, role_id: uuid.UUID) -> Optional[Role]:
        """A role in this company. System roles (``org_id IS NULL``) never match."""
        result = await session.execute(select(Role).where(Role.id == role_id, Role.org_id == company_id))
        return result.scalar_one_or_none()

    async def list_by_company(self, session: AsyncSession, company_id: uuid.UUID) -> List[Role]:
        result = await session.execute(select(Role).where(Role.org_id == company_id).order_by(Role.name))
        return list(result.scalars().all())

    async def update(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        role_id: uuid.UUID,
        *,
        actor: Optional[str] = None,
        **fields: Any,
    ) -> Optional[Role]:
        role = await self.get(session, company_id, role_id)
        if role is None:
            return None
        if role.is_system:
            raise ValueError("a system role cannot be modified through a company-scoped path")

        allowed: Dict[str, Any] = {k: v for k, v in fields.items() if k in {"name", "description"}}
        if "name" in allowed:
            cleaned = (allowed["name"] or "").strip()
            if not cleaned:
                raise ValueError("role name is required")
            clash = await self._find_by_name(session, company_id, cleaned)
            if clash is not None and clash.id != role.id:
                raise ValueError(f"a role named {cleaned!r} already exists in this company")
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
        """Delete a company role. Returns True when a row was actually removed.

        Refuses system roles. The DELETE carries the ``org_id`` predicate itself
        rather than trusting the prior read, so losing the read cannot widen it.
        """
        role = await self.get(session, company_id, role_id)
        if role is None:
            return False
        if role.is_system:
            raise ValueError("a system role cannot be deleted through a company-scoped path")

        result = await session.execute(
            sa_delete(Role).where(
                Role.id == role_id,
                Role.org_id == company_id,
                Role.is_system.is_(False),
            )
        )
        deleted = bool(result.rowcount)
        if deleted:
            await self._record(session, role, "role.deleted", actor, None)
        return deleted
