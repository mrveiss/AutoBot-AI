# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Effective co-working permission role of an actor (GH#8583); split from work_item_service (#13999)."""

import logging
import uuid
from typing import Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.membership import LLCCompanyMembership
from ..models.work_item import LLCWorkItem

logger = logging.getLogger(__name__)

_AGENT_ORG_ROLE_TO_COWORKER_ROLE: Dict[str, str] = {
    "manager": "admin",
    "coordinator": "lead",
    "specialist": "member",
    "worker": "member",
}


async def resolve_actor_role(session: AsyncSession, actor_id: Optional[str], company_id: str) -> str:
    """Resolve the effective coworker-permission role for actor_id (GH#8583).

    Tries LLCCompanyMembership first (human user identified by UUID), then
    AgentOrgNode (agent identified by string key).  Returns "member" when the
    actor is unknown — this is the safest default and will be rejected by
    enable_coworking / disable_coworking permission checks.
    """
    if not actor_id:
        return "member"

    # Human user path: actor_id must be a valid UUID.
    try:
        actor_uuid = uuid.UUID(actor_id)
        company_uuid = uuid.UUID(company_id)
        result = await session.execute(
            select(LLCCompanyMembership).where(
                LLCCompanyMembership.user_id == actor_uuid,
                LLCCompanyMembership.company_id == company_uuid,
            )
        )
        membership = result.scalar_one_or_none()
        if membership is not None:
            return membership.role.value if hasattr(membership.role, "value") else str(membership.role)
    except (ValueError, AttributeError):
        pass

    # Agent path: look up AgentOrgNode by string agent_id.
    try:
        from models.agent_org import AgentOrgNode

        company_uuid = uuid.UUID(company_id)
        result = await session.execute(
            select(AgentOrgNode).where(
                AgentOrgNode.agent_id == actor_id,
                AgentOrgNode.company_id == company_uuid,
            )
        )
        node = result.scalar_one_or_none()
        if node is not None:
            org_role = node.org_role.value if hasattr(node.org_role, "value") else str(node.org_role)
            return _AGENT_ORG_ROLE_TO_COWORKER_ROLE.get(org_role, "member")
    except ImportError as exc:
        logger.warning("AgentOrgNode model unavailable; defaulting actor_role to member: %s", exc)
    except (ValueError, AttributeError):
        pass

    return "member"


_COWORKING_ALLOWED_ROLES: frozenset = frozenset({"owner", "admin", "lead"})


def _coworking_state(item: LLCWorkItem) -> dict:
    """The co-worker fields of *item*, as the activity log's before/after snapshot."""
    return {
        "co_worker_type": item.co_worker_type,
        "co_worker_agent_id": str(item.co_worker_agent_id) if item.co_worker_agent_id else None,
        "co_worker_user_id": str(item.co_worker_user_id) if item.co_worker_user_id else None,
        "co_working_enabled": item.co_working_enabled,
    }
