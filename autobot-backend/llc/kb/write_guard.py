# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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

# "May write KB content across an organisation boundary" (#12786).
#
# This is a DIFFERENT question from ``is_admin_role`` and the member sets differ
# on purpose — compare them rather than the names:
#
#     ADMIN_ROLES         : admin, superadmin
#     CROSS_ORG_KB_ROLES  : platform_admin, superadmin
#
# ``admin`` is administrative *within its own organisation* and is deliberately
# absent here: the whole point of the guard below is that an org admin must not
# reach a parent org's KB namespace. Folding this into ``ADMIN_ROLES`` would add
# ``admin`` and delete the property the guard exists to enforce, so it stays a
# separate, named set.
#
# ``platform_admin``: no code path anywhere mints this role string — the
# platform-level flag the rest of the codebase uses is the boolean
# ``users.is_platform_admin`` / ``TenantContext.is_platform_admin``, not a role
# named ``platform_admin``. It is preserved rather than dropped (removing it
# would silently change this guard's behaviour if any deployment does set it),
# and reconciling the two spellings is tracked separately — see the PR for
# #12786.
CROSS_ORG_KB_ROLES: frozenset[str] = frozenset({"platform_admin", "superadmin"})


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
