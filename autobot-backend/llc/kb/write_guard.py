# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""KB write guard — sub-company agents must not write to parent-company KB (GH#8598).

Prevents a sub-company agent from tagging KB facts with an ancestor org's
``organization_id``, which would silently inject content into the parent KB.
"""

import uuid
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger
from user_management.models.organization import Organization

logger = get_logger(__name__)

_SUPERADMIN_ROLES: frozenset[str] = frozenset({"platform_admin", "superadmin"})


async def assert_not_writing_to_ancestor_kb(
    requester_org_id: Optional[str],
    target_org_id: Optional[str],
    session: AsyncSession,
) -> None:
    """Raise HTTP 403 if *target_org_id* is an ancestor of *requester_org_id*.

    Sub-company agents may write to their own org's KB or to child orgs, but
    must not be able to write into a parent (ancestor) org's KB namespace.

    Skips the check when either ID is absent or they are the same org.
    """
    if not requester_org_id or not target_org_id:
        return
    if requester_org_id == target_org_id:
        return

    try:
        requester_uuid = uuid.UUID(requester_org_id)
        target_uuid = uuid.UUID(target_org_id)
    except (ValueError, AttributeError):
        # Malformed IDs — let downstream schema validation handle them.
        return

    visited: set[uuid.UUID] = {requester_uuid}
    current_id: uuid.UUID = requester_uuid

    while True:
        result = await session.execute(
            select(Organization.parent_org_id)
            .where(Organization.id == current_id)
            .where(Organization.deleted_at.is_(None))
        )
        parent_id: Optional[uuid.UUID] = result.scalar_one_or_none()
        if parent_id is None:
            break  # reached the root — target is not an ancestor
        if parent_id in visited:
            break  # cycle guard
        if parent_id == target_uuid:
            logger.warning(
                "KB write guard blocked: sub-company %s attempted write to ancestor KB %s",
                requester_org_id,
                target_org_id,
            )
            raise HTTPException(
                status_code=403,
                detail="Sub-company agents may not write to a parent company's knowledge base",
            )
        visited.add(parent_id)
        current_id = parent_id
