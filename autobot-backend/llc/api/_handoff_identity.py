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

from ..models.work_item import LLCWorkItem
from ..services.authz import membership_role


def handing_off_agent(item: LLCWorkItem, current_user: Mapping[str, Any]) -> str:
    """The item's assigned agent, handed off by a person on its behalf; any other credential is refused.

    An agent reaches this through ``WorkItemService``, not this route.
    """
    if is_interactive_human(current_user):
        return str(item.assignee_agent_id)
    raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Only a person can hand this off here")


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
