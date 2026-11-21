# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Company scoping for the heartbeat routes (#21376).

The owning company of ``agent_id`` is resolved through the agent record: ``AgentOrgNode.agent_id`` is the
logical slug the heartbeat keyspace uses (``models/agent_org.py``, dual-keyspace note), and
``AgentOrgNode.company_id`` names the company.

* Reads need membership of that company; writes need owner/admin of it (``require_company_admin_unless_platform``).
* A platform admin passes everywhere, as on the company routes.
* A platform agent (no node, or a node with no company) is platform-admin-only: nobody else owns it.
* An agent the caller may not see answers 404, like ``assert_company_access``, so existence is not disclosed.
  A member without the admin role answers 403: they can already see the agent.
"""

import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import _is_platform_admin_claim, get_db_session
from auth_middleware import get_current_user
from autobot_shared.principal import resolve_principal_id
from llc.services.authz import NotAuthorisedError, is_company_member, require_company_admin_unless_platform
from models.agent_org import AgentOrgNode

AGENT_NOT_FOUND = "Agent not found"


@dataclass(frozen=True)
class AgentScope:
    """Who is asking, and which company owns the agent (``None`` for a platform agent)."""

    company_id: uuid.UUID | None
    platform_admin: bool


async def _owning_company(session: AsyncSession, agent_id: str) -> uuid.UUID | None:
    row = (await session.execute(select(AgentOrgNode.company_id).where(AgentOrgNode.agent_id == agent_id))).first()
    return None if row is None else row[0]


async def authorise_agent(session: AsyncSession, agent_id: str, user: dict, *, manage: bool) -> AgentScope:
    """The caller's scope for ``agent_id``; 404 when it is not theirs to see, 403 when a member may not manage it."""
    admin = _is_platform_admin_claim(user)
    company_id = await _owning_company(session, agent_id)
    user_id = resolve_principal_id(user) or ""
    if not admin and (company_id is None or not await is_company_member(session, company_id, user_id)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=AGENT_NOT_FOUND)
    if manage and company_id is not None:
        await _require_manager(session, company_id, user_id, admin)
    return AgentScope(company_id=company_id, platform_admin=admin)


async def _require_manager(session: AsyncSession, company_id: uuid.UUID, user_id: str, admin: bool) -> None:
    try:
        await require_company_admin_unless_platform(session, company_id, _uuid_or_none(user_id), platform_admin=admin)
    except NotAuthorisedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=exc.public_detail) from exc


def _uuid_or_none(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


async def read_scope(
    agent_id: str, session: AsyncSession = Depends(get_db_session), user: dict = Depends(get_current_user)
) -> AgentScope:
    """Dependency: the caller may read this agent (company member, or platform admin)."""
    return await authorise_agent(session, agent_id, user, manage=False)


async def manage_scope(
    agent_id: str, session: AsyncSession = Depends(get_db_session), user: dict = Depends(get_current_user)
) -> AgentScope:
    """Dependency: the caller may change this agent (company owner/admin, or platform admin)."""
    return await authorise_agent(session, agent_id, user, manage=True)


async def may_see_user(session: AsyncSession, scope: AgentScope, user_id: str | None) -> bool:
    """Whether the caller may be shown the display name of ``user_id``.

    The company rule: a name is shown to a platform admin, or to a caller of the same company when that user
    is also a member of it (the members list and org chart show exactly those names). Anyone else sees none.
    """
    if scope.platform_admin:
        return True
    return (
        bool(user_id) and scope.company_id is not None and await is_company_member(session, scope.company_id, user_id)
    )
