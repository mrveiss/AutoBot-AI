# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Admin API: linked people whose SLM copy could not be updated (#10200)."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas_person_links import PersonPushFailure, PersonPushFailuresResponse
from api.user_management.dependencies import get_db_session
from auth_rbac import require_role
from user_management.models import User
from user_management.models.person_link import PersonLink

router = APIRouter(prefix="/admin", dependencies=[Depends(require_role("admin", "superadmin"))])


@router.get("/person-links/push-failures", response_model=PersonPushFailuresResponse)
async def person_push_failures(session: AsyncSession = Depends(get_db_session)) -> PersonPushFailuresResponse:
    """Read only. A person here may still have SLM access after being deactivated."""
    query = (
        select(User.username, PersonLink.push_failed_at, PersonLink.push_error)
        .join(User, User.id == PersonLink.user_id)
        .where(PersonLink.push_failed_at.is_not(None))
        .order_by(PersonLink.push_failed_at)
    )
    rows = (await session.execute(query)).all()
    return PersonPushFailuresResponse(
        failures=[PersonPushFailure(username=row[0], failed_since=row[1], error=row[2]) for row in rows]
    )
