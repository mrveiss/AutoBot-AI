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

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger
from autobot_shared.security.redaction import safe_log_text
from models.agent_org import AgentOrgNode
from user_management.services import TenantContext

from ..models.work_item import LLCWorkItem
from ..services.authz import NotAuthorisedError, require_company_admin_unless_platform

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
    node_company = (
        await session.execute(select(AgentOrgNode.company_id).where(AgentOrgNode.id == uuid.UUID(agent_id)))
    ).scalar_one_or_none()
    if node_company is None or str(node_company) != str(item.company_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="That agent does not belong to this company")
