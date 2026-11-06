# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Who is acting on a work item handoff, from the verified caller and never the body (#20476)."""

from __future__ import annotations

import uuid
from typing import Any, Mapping

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.auth.interactive_principal import is_interactive_human
from autobot_shared.auth.permissions import is_admin_role

from ..models.work_item import LLCWorkItem
from ..services.authz import membership_role
from ..services.work_item_actor_role import coworking_denial, resolve_actor_role


async def handing_off_agent(session: AsyncSession, item: LLCWorkItem, current_user: Mapping[str, Any]) -> str:
    """The item's assigned agent, handed off by a person who manages its agent work; any other caller is refused.

    Managing is the co-working rule (owner/lead or an admin role), so a plain member cannot hand an
    agent's item off or pick its reviewer. An agent reaches this through ``WorkItemService``, not this route.
    """
    if not is_interactive_human(current_user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Only a person can hand this off here")
    actor_id = current_user.get("user_id") or current_user.get("id")
    role = await resolve_actor_role(session, str(actor_id) if actor_id else None, str(item.company_id))
    if is_admin_role(current_user.get("role") or "member"):
        role = "admin"
    if coworking_denial(role) is not None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Only an owner, lead or admin can hand this off")
    if item.assignee_agent_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This work item has no assigned agent to hand off for")
    return str(item.assignee_agent_id)


async def member_reviewer(session: AsyncSession, company_id: Any, reviewer_user_id: str) -> str:
    """The named reviewer, who must belong to the company; an unknown or malformed id reads the same."""
    try:
        reviewer = uuid.UUID(reviewer_user_id)
    except ValueError:
        reviewer = None
    role = await membership_role(session, uuid.UUID(str(company_id)), reviewer, for_update=False) if reviewer else None
    if role is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="The reviewer is not a member of this company")
    return reviewer_user_id
