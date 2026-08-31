# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Attach and detach tools on a role (#14221 step 4).

Tools have no database table — they register in-process by name via
``autobot_shared.tool_sdk.registry``. So the authority for "is this a real tool"
is the registry, not a foreign key, and validation lives here.

That raises a failure mode worth naming. If the registry has not been populated
(import ordering, a stripped-down process), every name looks unknown. Reporting
that as "unknown tool" would send someone hunting for a typo when the real cause
is that nothing has registered yet. So the two cases are separated: an empty
registry raises :class:`ToolRegistryUnavailable`, an absent name raises
``ValueError``. Same reasoning as the unattributed-workflow branch in step 5 —
"it isn't there" and "I can't tell" are different answers.
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


class ToolRegistryUnavailable(RuntimeError):
    """The tool registry holds no tools, so no name can be validated.

    Distinct from "unknown tool" on purpose: this is an environment problem,
    not a caller mistake, and conflating them turns a startup-ordering bug into
    a wild goose chase for a misspelling.
    """


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

    async def _require_role(self, session: AsyncSession, company_id: uuid.UUID, role_id: uuid.UUID) -> None:
        result = await session.execute(select(Role.id).where(Role.id == role_id, Role.org_id == company_id))
        if result.scalar_one_or_none() is None:
            raise ValueError(f"role {role_id} does not exist in company {company_id}")

    @staticmethod
    def _require_registered_tool(tool_name: str) -> str:
        """The tool must be registered. Returns the cleaned name."""
        cleaned = (tool_name or "").strip()
        if not cleaned:
            raise ValueError("a tool name is required")

        # Imported lazily, by the fully-qualified ``autobot_shared.tool_sdk``
        # path (#14373). Both matter:
        #
        # * Lazily, because a module-level import runs while the feature
        #   routers load, and an ImportError there takes the whole LLC router
        #   down, not just this service. Every other consumer imports it the
        #   same way (``tools/tool_registry.py``, ``api/image_generation.py``).
        # * Fully-qualified, not the bare top-level ``tool_sdk`` path, because
        #   ``get_tool_registry()`` returns a module-level singleton stored on
        #   ``autobot_shared/tool_sdk/registry.py``. Reaching that file under a
        #   second module identity (the bare name) would load a *second* copy
        #   of it with its own, independently empty, registry — every tool
        #   would look unregistered while the real registry was fine. The bare
        #   ``tool_sdk`` path is exactly what caused the original
        #   ``ModuleNotFoundError`` here (#14373) and is not a supported alias.
        from autobot_shared.tool_sdk.registry import get_tool_registry  # noqa: PLC0415

        known = {meta.name for meta in get_tool_registry().list_tools()}
        if not known:
            raise ToolRegistryUnavailable(
                "the tool registry is empty, so no tool name can be validated; "
                "this is an environment problem, not an unknown tool"
            )
        if cleaned not in known:
            raise ValueError(f"unknown tool {cleaned!r}")
        return cleaned

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

        attachment = LLCRoleTool(company_id=company_id, role_id=role_id, tool_name=cleaned)
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

    async def list_for_role(self, session: AsyncSession, company_id: uuid.UUID, role_id: uuid.UUID) -> List[str]:
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
