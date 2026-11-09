# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The SLM's side of the person link: its first admin, and the copy the main app keeps current (#10200, ADR-012).

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
from autobot_shared.security.constant_time import secure_compare
from autobot_shared.user_management.password_epoch import DEACTIVATION_EPOCH_LEAD_SECONDS, record_password_epoch
from user_management.database import get_slm_session
from user_management.models.user import User

router = APIRouter(prefix="/internal", tags=["internal"])


class PersonCopyRequest(BaseModel):
    """The main app's record of a linked person (#10200). It is the record after the link."""

    slm_user_id: uuid.UUID
    password_hash: str | None
    is_active: bool


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


@router.post("/person-copy", status_code=status.HTTP_204_NO_CONTENT)
async def update_person_copy(
    body: PersonCopyRequest,
    session: Annotated[AsyncSession, Depends(get_slm_session)],
    x_internal_api_key: Annotated[str | None, Header()] = None,
) -> None:
    """Write only what differs, so the periodic pass changes nothing when the two agree.

    The person's issued SLM sessions are revoked on a deactivation or a password change (#21154): the
    SLM's request gate reads the epoch store, never ``is_active`` or the hash. The deactivation epoch is
    recorded on every push of an inactive person, and both epochs are written before the change is committed.
    """
    if not verify_internal_api_key(x_internal_api_key):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "internal service key required")
    user = await session.get(User, body.slm_user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such SLM user")
    # No hash means the main app holds none. That must not wipe the password this person logs in with.
    password_changed = bool(body.password_hash) and not secure_compare(body.password_hash, user.password_hash)
    # The epoch goes FIRST, as scripts/autobot-admin.py does: if the epoch cannot be recorded nothing has
    # changed, the push fails and the retry still sees the difference; if the commit then fails the old
    # sessions are already revoked and the person only signs in again.
    if not body.is_active:
        await record_password_epoch(user.username, lead_seconds=DEACTIVATION_EPOCH_LEAD_SECONDS)
    elif password_changed:
        # No lead: the person signs straight back in and that new token must pass (as in the lifecycle).
        await record_password_epoch(user.username)
    if password_changed:
        user.password_hash = body.password_hash
    if user.is_active != body.is_active:
        user.is_active = body.is_active
    await session.commit()
