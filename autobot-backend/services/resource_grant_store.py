# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""DB-backed CRUD + lookup for resource_grants (#11277)."""

import uuid

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.scoping.visibility import Principal
from models.resource_grant import ResourceGrant


async def grant(
    session: AsyncSession,
    resource_type: str,
    resource_id: str,
    grantee_type: str,
    grantee_id: str,
    permission: str = "use",
    created_by: uuid.UUID | None = None,
) -> ResourceGrant:
    """Add or update a grant (idempotent on the unique target key)."""
    existing = (
        await session.execute(
            select(ResourceGrant).where(
                ResourceGrant.resource_type == resource_type,
                ResourceGrant.resource_id == resource_id,
                ResourceGrant.grantee_type == grantee_type,
                ResourceGrant.grantee_id == grantee_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.permission = permission
        await session.flush()
        return existing
    row = ResourceGrant(
        resource_type=resource_type,
        resource_id=resource_id,
        grantee_type=grantee_type,
        grantee_id=grantee_id,
        permission=permission,
        created_by=created_by,
    )
    session.add(row)
    await session.flush()
    return row


async def revoke(
    session: AsyncSession,
    resource_type: str,
    resource_id: str,
    grantee_type: str,
    grantee_id: str,
) -> bool:
    """Delete a grant. Returns True if a row was removed."""
    result = await session.execute(
        delete(ResourceGrant).where(
            ResourceGrant.resource_type == resource_type,
            ResourceGrant.resource_id == resource_id,
            ResourceGrant.grantee_type == grantee_type,
            ResourceGrant.grantee_id == grantee_id,
        )
    )
    await session.flush()
    return (result.rowcount or 0) > 0


async def has_grant(
    session: AsyncSession,
    resource_type: str,
    resource_id: str,
    principal: Principal,
) -> bool:
    """True if any grant row matches the principal's user or a group they're in."""
    grantee_clauses = [and_(ResourceGrant.grantee_type == "user", ResourceGrant.grantee_id == principal.user_id)]
    if principal.group_ids:
        grantee_clauses.append(
            and_(
                ResourceGrant.grantee_type == "group",
                ResourceGrant.grantee_id.in_(list(principal.group_ids)),
            )
        )
    row = (
        await session.execute(
            select(ResourceGrant.id)
            .where(
                ResourceGrant.resource_type == resource_type,
                ResourceGrant.resource_id == resource_id,
                or_(*grantee_clauses),
            )
            .limit(1)
        )
    ).first()
    return row is not None
