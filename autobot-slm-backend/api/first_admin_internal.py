# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The SLM's first admin, for the main app to link to at install (#10200, ADR-012).

The SLM is the record for people until the main app is installed, and its first admin must carry
over. The response includes the password hash so that person keeps their password, which is why
only a holder of the internal service key may read it: never a user token, whatever its role.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.auth.internal_api_key import verify_internal_api_key
from user_management.database import get_slm_session
from user_management.models.user import User

router = APIRouter(prefix="/internal", tags=["internal"])


class FirstAdminResponse(BaseModel):
    """What the main app needs to create and link this person."""

    id: uuid.UUID
    username: str
    email: str
    display_name: str | None
    password_hash: str | None


@router.get("/first-admin", response_model=FirstAdminResponse)
async def get_first_admin(
    session: Annotated[AsyncSession, Depends(get_slm_session)],
    x_internal_api_key: Annotated[str | None, Header()] = None,
) -> User:
    """The earliest active admin. 404 until the SLM has one."""
    if not verify_internal_api_key(x_internal_api_key):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "internal service key required")
    query = (
        select(User)
        .where(User.is_platform_admin.is_(True), User.is_active.is_(True), User.deleted_at.is_(None))
        .order_by(User.created_at)
        .limit(1)
    )
    admin = (await session.execute(query)).scalars().first()
    if admin is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "the SLM has no admin yet")
    return admin
