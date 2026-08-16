# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Access settings on a company role, and what a holder may actually do (#14221 step 3).

Owner decision this implements:

    role based access is above all, as admin creates the role permissions

Two halves, and the second is the one that makes the first mean anything:

* **Granting** — an *admin* attaches permissions to a role. Enforced here, not
  deferred to a route, because "admin creates the role permissions" is an
  authorisation rule and a rule that lives only in a route is one guard away
  from not existing.
* **Resolving** — :meth:`effective_permissions` answers *what may this holder
  do*, as the union over the roles they hold **right now**. Ending a tenure
  therefore withdraws access with no separate revocation step, which is the
  property that makes offboarding safe by construction rather than by
  remembering.

**No new tables.** ``role_permissions`` and ``permissions`` already exist and
already carry this shape; step 1's note about not forking ``roles`` applies
identically here. Permission names are the canonical dot-style values of
``autobot_shared.auth.permissions.Permission``. Legacy colon-style ``secrets:*``
rows also exist in the ``permissions`` table on purpose — migration
``20260623_062_rbac_colon_to_dot_reconcile`` reconciled the two and deliberately
kept them for the secrets_authz policy — so this service resolves names against
the table rather than against the enum, and neither invents nor rejects a
vocabulary it does not own.

``MembershipRole`` keeps its job: it decides who may *administer* a company.
Role permissions decide what a holder may *do*. The owner's ordering — role
access "above all" — is about operational authority, not about replacing the
gate on who may grant.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from user_management.models.role import Permission, Role, RolePermission

from ..models.activity import ActorType
from ..models.enums import RoleHolderType
from ..models.role_assignment import LLCRoleAssignment
from .authz import NotAuthorisedError, require_company_admin
from .base import LLCServiceBase

_HOLDER_COLUMNS = {
    RoleHolderType.AGENT: "holder_agent_id",
    RoleHolderType.USER: "holder_user_id",
    RoleHolderType.CONTACT: "holder_contact_id",
}


class RolePermissionService(LLCServiceBase):
    """Grants, revokes and resolves permissions attached to company roles."""

    async def _require_company_role(self, session: AsyncSession, company_id: uuid.UUID, role_id: uuid.UUID) -> Role:
        result = await session.execute(select(Role).where(Role.id == role_id, Role.org_id == company_id))
        role = result.scalar_one_or_none()
        if role is None:
            raise ValueError(f"role {role_id} does not exist in company {company_id}")
        if role.is_system:
            raise ValueError("a system role's permissions cannot be changed through a company path")
        return role

    async def _resolve_permission(self, session: AsyncSession, name: str) -> Permission:
        cleaned = (name or "").strip()
        if not cleaned:
            raise ValueError("a permission name is required")
        result = await session.execute(select(Permission).where(Permission.name == cleaned))
        permission = result.scalar_one_or_none()
        if permission is None:
            # Deliberately not auto-created: an unknown name is far more likely
            # a typo than a new permission, and silently seeding it would make
            # a misspelt grant look successful while granting nothing.
            raise ValueError(f"unknown permission {cleaned!r}")
        return permission

    async def grant(
        self,
        session: AsyncSession,
        *,
        company_id: uuid.UUID,
        role_id: uuid.UUID,
        permission: str,
        actor_user_id: uuid.UUID,
    ) -> bool:
        """Attach a permission to a role. True if newly granted, False if already held."""
        await require_company_admin(session, company_id, actor_user_id)
        role = await self._require_company_role(session, company_id, role_id)
        resolved = await self._resolve_permission(session, permission)

        existing = await session.execute(
            select(RolePermission).where(
                RolePermission.role_id == role.id,
                RolePermission.permission_id == resolved.id,
            )
        )
        if existing.scalar_one_or_none() is not None:
            return False

        session.add(RolePermission(role_id=role.id, permission_id=resolved.id))
        await session.flush()
        await self._record(
            session, company_id, role, "role.permission_granted", actor_user_id, {"permission": resolved.name}
        )
        return True

    async def revoke(
        self,
        session: AsyncSession,
        *,
        company_id: uuid.UUID,
        role_id: uuid.UUID,
        permission: str,
        actor_user_id: uuid.UUID,
    ) -> bool:
        """Detach a permission from a role. True if a grant was actually removed."""
        await require_company_admin(session, company_id, actor_user_id)
        role = await self._require_company_role(session, company_id, role_id)
        resolved = await self._resolve_permission(session, permission)

        result = await session.execute(
            sa_delete(RolePermission).where(
                RolePermission.role_id == role.id,
                RolePermission.permission_id == resolved.id,
            )
        )
        revoked = bool(result.rowcount)
        if revoked:
            await self._record(
                session, company_id, role, "role.permission_revoked", actor_user_id, {"permission": resolved.name}
            )
        return revoked

    async def _record(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        role: Role,
        event_type: str,
        actor: Optional[uuid.UUID],
        after: Optional[Dict[str, Any]],
    ) -> None:
        if not self.activity_log:
            return
        await self.activity_log.record(
            session=session,
            company_id=str(company_id),
            actor_type=ActorType.USER if actor else ActorType.SYSTEM,
            actor_id=str(actor) if actor else None,
            event_type=event_type,
            entity_type="role",
            entity_id=str(role.id),
            after=after,
        )

    async def list_for_role(self, session: AsyncSession, company_id: uuid.UUID, role_id: uuid.UUID) -> List[str]:
        """Permission names on this role, sorted. Empty for a role in another company."""
        result = await session.execute(
            select(Permission.name)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(Role, Role.id == RolePermission.role_id)
            .where(Role.id == role_id, Role.org_id == company_id)
            .order_by(Permission.name)
        )
        return list(result.scalars().all())

    async def effective_permissions(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        holder_type: object,
        holder_id: uuid.UUID,
    ) -> Set[str]:
        """What this holder may do in this company, right now.

        The union over **open** tenures only. Ending a tenure withdraws the
        access it carried, with no separate revocation — an ended tenure that
        still granted permissions would be the exact hole offboarding exists to
        close.
        """
        resolved = RoleHolderType(holder_type)
        column = getattr(LLCRoleAssignment, _HOLDER_COLUMNS[resolved])
        result = await session.execute(
            select(Permission.name)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(Role, Role.id == RolePermission.role_id)
            .join(LLCRoleAssignment, LLCRoleAssignment.role_id == Role.id)
            .where(
                Role.org_id == company_id,
                LLCRoleAssignment.company_id == company_id,
                LLCRoleAssignment.holder_type == resolved.value,
                column == holder_id,
                LLCRoleAssignment.ended_at.is_(None),
            )
        )
        return set(result.scalars().all())

    async def holder_may(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        holder_type: object,
        holder_id: uuid.UUID,
        permission: str,
    ) -> bool:
        """Single-permission check, expressed through :meth:`effective_permissions`.

        Sharing the resolver rather than writing a second query keeps the two
        from drifting apart — a narrower fast path is how "may" and "may not"
        start disagreeing.
        """
        return (permission or "").strip() in await self.effective_permissions(
            session, company_id, holder_type, holder_id
        )

    async def roles_granting(self, session: AsyncSession, company_id: uuid.UUID, permission: str) -> List[Role]:
        """Which roles in this company carry a permission — the audit direction."""
        result = await session.execute(
            select(Role)
            .join(RolePermission, RolePermission.role_id == Role.id)
            .join(Permission, Permission.id == RolePermission.permission_id)
            .where(Role.org_id == company_id, Permission.name == (permission or "").strip())
            .order_by(Role.name)
        )
        return list(result.scalars().all())
