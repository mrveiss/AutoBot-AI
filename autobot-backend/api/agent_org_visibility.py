# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Which agents a caller may see and act on in the agent org router (#19246).

The router answered every signed-in user with every company's agents, and let anyone
delegate between them. The rule (owner decision on #19246, matching GET /companies, #12233):

- a platform admin sees and acts on every agent;
- anyone else sees the agents of the companies they are a member of, plus platform agents
  (no ``company_id``), which serve every user;
- acting on an agent (delegating, escalating, updating a delegation) needs its company's
  membership; platform agents are acted on by admins only.

An agent outside the caller's view answers 404, so its existence is not disclosed.
"""

import uuid
from dataclasses import dataclass, field
from typing import Dict, Iterable, Optional

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import (
    _SERVICE_PRINCIPAL_DENIED,
    _is_platform_admin_claim,
    _is_service_principal,
    _parse_uuid_safe,
    get_current_user,
    get_optional_db_session,
)
from llc.services.membership_service import MembershipService
from models.agent_org import AgentOrgNode

AGENT_NOT_FOUND = "Agent not found"


@dataclass(frozen=True)
class AgentVisibility:
    """The caller's view: admin, or the companies they belong to."""

    is_platform_admin: bool
    company_ids: frozenset = field(default_factory=frozenset)

    def can_see(self, company_id: Optional[uuid.UUID]) -> bool:
        return self.is_platform_admin or company_id is None or company_id in self.company_ids

    def can_act(self, company_id: Optional[uuid.UUID]) -> bool:
        return self.is_platform_admin or (company_id is not None and company_id in self.company_ids)


async def get_agent_visibility(
    current_user: dict = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_optional_db_session),
) -> AgentVisibility:
    """Resolve the caller's view once per request; service credentials are refused (#18688)."""
    if _is_service_principal(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_SERVICE_PRINCIPAL_DENIED)
    if _is_platform_admin_claim(current_user):
        return AgentVisibility(is_platform_admin=True)
    raw = current_user.get("user_id") or current_user.get("id") or current_user.get("sub")
    user_id = _parse_uuid_safe(str(raw)) if raw else None
    if user_id is None or session is None:
        return AgentVisibility(is_platform_admin=False)
    company_ids = await MembershipService().list_member_company_ids(session, str(user_id))
    # End the read transaction now: this dependency's session is a different one from the route's
    # (FastAPI caches per callable), and a held connection would starve a small pool until the
    # request ends. Same commit-on-success the session scope does at teardown (CodeRabbit on #19286).
    await session.commit()
    return AgentVisibility(is_platform_admin=False, company_ids=frozenset(company_ids))


async def agent_companies(session: AsyncSession) -> Dict[str, Optional[uuid.UUID]]:
    """agent_id -> company_id for every registered agent, in one query."""
    rows = await session.execute(select(AgentOrgNode.agent_id, AgentOrgNode.company_id))
    return {agent_id: company_id for agent_id, company_id in rows.all()}


def require_agents(
    visibility: AgentVisibility,
    companies: Dict[str, Optional[uuid.UUID]],
    agent_ids: Iterable[str],
    act: bool = False,
) -> None:
    """404 unless every agent is in the caller's view (``act``: may be acted on).

    A platform admin passes for any id, so an unknown agent keeps the endpoint's own answer.
    """
    if visibility.is_platform_admin:
        return
    allowed = visibility.can_act if act else visibility.can_see
    for agent_id in agent_ids:
        if agent_id not in companies or not allowed(companies[agent_id]):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=AGENT_NOT_FOUND)
