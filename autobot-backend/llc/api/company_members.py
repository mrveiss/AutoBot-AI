# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Company OS membership writes: add, change a role, remove (#19654, GH#8223).

The rules for who may do each are in :mod:`llc.services.membership_policy`.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, NoReturn

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_current_user, require_org_context
from llc.deps import assert_company_access
from llc.models.enums import MembershipRole
from llc.services.activity_log import LLCActivityLogService
from llc.services.authz import NotAuthorisedError
from llc.services.membership_policy import LastOwnerError, authorize_member_change, lock_company_members
from llc.services.membership_service import MemberAlreadyExistsError, MemberNotFoundError, MembershipService
from user_management.database import get_async_session
from user_management.services import TenantContext

from .companies import _to_member_read

router = APIRouter(prefix="/companies", tags=["llc-companies"])


class MemberAddRequest(BaseModel):
    user_id: uuid.UUID
    role: MembershipRole = MembershipRole.MEMBER


class MemberRoleRequest(BaseModel):
    role: MembershipRole


def _get_membership_service() -> MembershipService:
    return MembershipService(activity_log=LLCActivityLogService())


async def _refuse(session: AsyncSession, exc: Exception) -> NoReturn:
    """Roll back, then the fixed public text for *exc*; its message carries ids and is for logs."""
    await session.rollback()
    if isinstance(exc, NotAuthorisedError):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=exc.public_detail)
    if isinstance(exc, LastOwnerError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A company must keep an owner")
    if isinstance(exc, MemberAlreadyExistsError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already a member")
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")


async def _current_role(session: AsyncSession, svc: MembershipService, company_id: uuid.UUID, user_id: uuid.UUID):
    """The member's role, for a change that needs one to exist."""
    existing = await svc.get_member(session, str(company_id), str(user_id))
    if existing is None:
        raise MemberNotFoundError(f"User {user_id} is not a member of company {company_id}")
    return existing.role


@router.post("/{company_id}/members", status_code=status.HTTP_201_CREATED)
async def add_member(
    company_id: uuid.UUID,
    body: MemberAddRequest,
    session: AsyncSession = Depends(get_async_session),
    svc: MembershipService = Depends(_get_membership_service),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> Dict[str, Any]:
    assert_company_access(ctx, company_id)
    try:
        await lock_company_members(session, company_id)
        await authorize_member_change(
            session,
            company_id,
            ctx.user_id,
            platform_admin=ctx.is_platform_admin,
            current_role=None,
            new_role=body.role,
        )
        membership = await svc.add_member(
            session, str(company_id), str(body.user_id), body.role, actor_id=str(ctx.user_id)
        )
        await session.commit()
        return _to_member_read(membership)
    except (NotAuthorisedError, MemberAlreadyExistsError) as exc:
        await _refuse(session, exc)


@router.patch("/{company_id}/members/{user_id}")
async def change_member_role(
    company_id: uuid.UUID,
    user_id: uuid.UUID,
    body: MemberRoleRequest,
    session: AsyncSession = Depends(get_async_session),
    svc: MembershipService = Depends(_get_membership_service),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> Dict[str, Any]:
    assert_company_access(ctx, company_id)
    try:
        await lock_company_members(session, company_id)
        current = await _current_role(session, svc, company_id, user_id)
        await authorize_member_change(
            session,
            company_id,
            ctx.user_id,
            platform_admin=ctx.is_platform_admin,
            current_role=current,
            new_role=body.role,
        )
        membership = await svc.change_role(session, str(company_id), str(user_id), body.role, actor_id=str(ctx.user_id))
        await session.commit()
        return _to_member_read(membership)
    except (NotAuthorisedError, LastOwnerError, MemberNotFoundError) as exc:
        await _refuse(session, exc)


@router.delete("/{company_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    company_id: uuid.UUID,
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    svc: MembershipService = Depends(_get_membership_service),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> None:
    assert_company_access(ctx, company_id)
    try:
        await lock_company_members(session, company_id)
        current = await _current_role(session, svc, company_id, user_id)
        await authorize_member_change(
            session,
            company_id,
            ctx.user_id,
            platform_admin=ctx.is_platform_admin,
            current_role=current,
            new_role=None,
        )
        await svc.remove_member(session, str(company_id), str(user_id), actor_id=str(ctx.user_id))
        await session.commit()
    except (NotAuthorisedError, LastOwnerError, MemberNotFoundError) as exc:
        await _refuse(session, exc)
