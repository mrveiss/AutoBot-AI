# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Who may act as a named agent on the member checkout and release routes (#20521, owner decision 2026-11-21).

A body ``agent_id`` is accepted only when the agent belongs to the item's company and the caller is an owner or
admin of that company. Any other member naming an agent is refused with 403. An agent acting for itself does so
through its own credential (the ``/agent`` routes), never through this body field.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional, Union

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger
from autobot_shared.security.redaction import safe_log_text
from models.agent_org import AgentOrgNode
from user_management.services import TenantContext

from ..models.work_item import LLCWorkItem
from ..services.authz import NotAuthorisedError, is_company_member, require_company_admin_unless_platform

logger = get_logger(__name__)

_NOT_ALLOWED = "Only a company owner or admin may act as a named agent"


async def require_may_act_as(session: AsyncSession, ctx: TenantContext, item: LLCWorkItem, agent_id: str) -> None:
    """Refuse (403) unless the caller is an owner/admin of the item's company and *agent_id* is one of its agents."""
    try:
        await require_company_admin_unless_platform(
            session, item.company_id, ctx.user_id, platform_admin=ctx.is_platform_admin
        )
    except NotAuthorisedError as exc:
        logger.warning("Refused acting as a named agent on item %s: %s", item.id, safe_log_text(repr(exc)))
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=_NOT_ALLOWED) from exc
    if not await agent_in_company(session, item.company_id, agent_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="That agent does not belong to this company")


async def agent_in_company(
    session: AsyncSession, company_id: Any, agent_id: Union[str, uuid.UUID], *, slug_ok: bool = False
) -> bool:
    """Whether *agent_id* is an agent node of the company; a malformed or unknown id reads as not.

    *slug_ok* also accepts the node's company-scoped slug, for a free-text column that may hold either keyspace.
    """
    try:
        match = AgentOrgNode.id == uuid.UUID(str(agent_id))
    except ValueError:
        if not slug_ok:
            return False
        match = AgentOrgNode.agent_id == str(agent_id)
    in_company = AgentOrgNode.company_id == uuid.UUID(str(company_id))
    return (await session.execute(select(AgentOrgNode.id).where(match, in_company))).scalars().first() is not None


async def require_member_targets(
    session: AsyncSession,
    company_id: Any,
    user_id: Optional[Union[str, uuid.UUID]] = None,
    agent_id: Optional[Union[str, uuid.UUID]] = None,
    *,
    slug_ok: bool = False,
) -> None:
    """A named assignee or handoff target stays allowed in the body but must belong to the company (#20521, 422)."""
    if user_id and not await is_company_member(session, company_id, user_id):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail="The named user is not a member of this company"
        )
    if agent_id and not await agent_in_company(session, company_id, agent_id, slug_ok=slug_ok):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail="The named agent does not belong to this company"
        )
