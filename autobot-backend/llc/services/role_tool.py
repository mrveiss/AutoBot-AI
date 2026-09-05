# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Attach and detach tools on a role (#14221 step 4).

Tools have no database table — they register in-process by name via
``autobot_shared.tool_sdk.registry``. So the authority for "is this a real tool"
is the registry, not a foreign key, and validation happens in code rather
than in the schema.

The check itself now lives in ``tool_registry_ref``, shared with
``CompanyToolService`` (#14852) so the two cannot disagree about what counts as
a real tool. It keeps the distinction that matters: an empty registry raises
:class:`ToolRegistryUnavailable`, an absent name raises ``ValueError``. Same
reasoning as the unattributed-workflow branch in step 5 — "it isn't there" and
"I can't tell" are different answers, and collapsing them turns a
startup-ordering bug into a hunt for a misspelling.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from user_management.models.role import Role

from ..models.activity import ActorType
from ..models.role_tool import LLCRoleTool
from .authz import require_company_admin
from .base import LLCServiceBase
from .tool_registry_ref import ToolRegistryUnavailable, require_registered_tool

#: Re-exported. ``llc/api/roles.py`` imports ``ToolRegistryUnavailable`` from
#: here; the definition moved to ``tool_registry_ref`` when a second caller
#: appeared (#14852), and this keeps every existing import site working.
__all__ = ["RoleToolService", "ToolRegistryUnavailable"]


class RoleToolService(LLCServiceBase):
    """Company-scoped attachment of tools to roles."""

    async def _record(
        self,
        session: AsyncSession,
        attachment: LLCRoleTool,
        event_type: str,
        actor: Optional[uuid.UUID],
        after: Optional[Dict[str, Any]],
    ) -> None:
        if not self.activity_log:
            return
        await self.activity_log.record(
            session=session,
            company_id=str(attachment.company_id),
            actor_type=ActorType.USER if actor else ActorType.SYSTEM,
            actor_id=str(actor) if actor else None,
            event_type=event_type,
            entity_type="llc_role_tool",
            entity_id=str(attachment.id),
            after=after,
        )

    async def _require_role(
        self, session: AsyncSession, company_id: uuid.UUID, role_id: uuid.UUID
    ) -> None:
        result = await session.execute(
            select(Role.id).where(Role.id == role_id, Role.org_id == company_id)
        )
        if result.scalar_one_or_none() is None:
            raise ValueError(f"role {role_id} does not exist in company {company_id}")

    @staticmethod
    def _require_registered_tool(tool_name: str) -> str:
        """The tool must be registered. Returns the cleaned name.

        Delegates to ``tool_registry_ref`` so this service and
        ``CompanyToolService`` (#14852) cannot drift on what counts as a
        real tool: an overlay written for a name that can never be attached
        would be a row nothing ever reads.
        """
        return require_registered_tool(tool_name)

    async def attach(
        self,
        session: AsyncSession,
        *,
        company_id: uuid.UUID,
        role_id: uuid.UUID,
        tool_name: str,
        actor_user_id: uuid.UUID,
    ) -> LLCRoleTool:
        if company_id is None or role_id is None:
            raise ValueError("company_id and role_id are both required")

        await require_company_admin(session, company_id, actor_user_id)
        await self._require_role(session, company_id, role_id)
        cleaned = self._require_registered_tool(tool_name)

        if await self.get(session, company_id, role_id, cleaned) is not None:
            raise ValueError(f"tool {cleaned!r} is already attached to role {role_id}")

        attachment = LLCRoleTool(
            company_id=company_id, role_id=role_id, tool_name=cleaned
        )
        session.add(attachment)
        await session.flush()
        await self._record(
            session,
            attachment,
            "role_tool.attached",
            actor_user_id,
            {"role_id": str(role_id), "tool_name": cleaned},
        )
        return attachment

    async def get(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        role_id: uuid.UUID,
        tool_name: str,
    ) -> Optional[LLCRoleTool]:
        result = await session.execute(
            select(LLCRoleTool).where(
                LLCRoleTool.company_id == company_id,
                LLCRoleTool.role_id == role_id,
                LLCRoleTool.tool_name == tool_name,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_role(
        self, session: AsyncSession, company_id: uuid.UUID, role_id: uuid.UUID
    ) -> List[str]:
        """Tool names this role carries — independent of who currently holds it."""
        result = await session.execute(
            select(LLCRoleTool.tool_name)
            .where(
                LLCRoleTool.company_id == company_id,
                LLCRoleTool.role_id == role_id,
            )
            .order_by(LLCRoleTool.tool_name)
        )
        return list(result.scalars().all())

    async def detach(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        role_id: uuid.UUID,
        tool_name: str,
        *,
        actor_user_id: uuid.UUID,
    ) -> bool:
        """Remove an attachment. Returns True when a row was actually removed.

        Does **not** re-validate the tool against the registry: a tool that has
        since been unregistered must still be detachable, or a removed tool
        would be permanently stuck on every role that carried it.
        """
        await require_company_admin(session, company_id, actor_user_id)
        attachment = await self.get(session, company_id, role_id, tool_name)
        result = await session.execute(
            sa_delete(LLCRoleTool).where(
                LLCRoleTool.company_id == company_id,
                LLCRoleTool.role_id == role_id,
                LLCRoleTool.tool_name == tool_name,
            )
        )
        detached = bool(result.rowcount)
        if detached and attachment is not None:
            await self._record(
                session,
                attachment,
                "role_tool.detached",
                actor_user_id,
                {"role_id": str(role_id), "tool_name": tool_name},
            )
        return detached
