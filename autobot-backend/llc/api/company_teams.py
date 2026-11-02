# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Company OS team writes: create and delete a team, add and remove a member (#14106).

The write side of ``GET /companies/{company_id}/teams`` (``companies.py``). There is one
team implementation, :class:`~user_management.services.TeamService`, shared with
``/teams``; this module only supplies what that service cannot know:

* **Scope** is the path's company. ``TeamService`` reads its organisation from the
  context it is built with, so it is built here with ``org_id=company_id`` rather than
  the ambient tenant context. Every team lookup is then filtered by that company, so a
  team of another company is "not found" -- the same answer as one that does not exist.
* **Authority** is the rule neighbouring Company OS writes use
  (:func:`~llc.services.authz.require_company_admin_unless_platform`): owner or admin of
  *this* company. A plain member is refused.
* **Membership**: a user may only join a team of a company they belong to.

The audit trail is ``TeamService``'s own (``TEAM_CREATED`` / ``TEAM_DELETED`` /
``TEAM_MEMBER_ADDED`` / ``TEAM_MEMBER_REMOVED`` rows, stamped with the company and the
acting user), written in the same transaction as the change.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas_agent import (
    MemberAddedResponse,
    MemberRemovedResponse,
    TeamCreate,
    TeamCreatedResponse,
    TeamDeletedResponse,
)
from api.user_management.dependencies import get_current_user, require_org_context
from api.user_management.teams import _membership_to_response, _team_to_response
from llc.deps import assert_company_access
from llc.models.membership import LLCCompanyMembership
from llc.services.authz import NotAuthorisedError, require_company_admin_unless_platform
from user_management.database import get_async_session
from user_management.services import TeamService, TenantContext
from user_management.services.team_service import DuplicateTeamError, MembershipError, TeamNotFoundError

router = APIRouter(prefix="/companies", tags=["llc-companies"])

_TEAM_NOT_FOUND = "Team not found"
_USER_NOT_FOUND = "User not found in this company"


def _team_service(session: AsyncSession, company_id: uuid.UUID, ctx: TenantContext) -> TeamService:
    """The shared team logic, scoped to the path's company and acting as the caller."""
    return TeamService(
        session,
        TenantContext(org_id=company_id, user_id=ctx.user_id, is_platform_admin=ctx.is_platform_admin),
    )


async def _authorize(session: AsyncSession, company_id: uuid.UUID, ctx: TenantContext) -> None:
    """404 for another tenant's company, 403 unless owner/admin here (platform admins pass)."""
    assert_company_access(ctx, company_id)
    try:
        await require_company_admin_unless_platform(
            session, company_id, ctx.user_id, platform_admin=ctx.is_platform_admin
        )
    except NotAuthorisedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=exc.public_detail)


async def _require_company_user(session: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID) -> None:
    """404 unless *user_id* is a member of *company_id*; same answer as an unknown user."""
    found = await session.execute(
        select(LLCCompanyMembership.id).where(
            LLCCompanyMembership.company_id == company_id,
            LLCCompanyMembership.user_id == user_id,
        )
    )
    if found.first() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_USER_NOT_FOUND)


@router.post("/{company_id}/teams", response_model=TeamCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_company_team(
    company_id: uuid.UUID,
    body: TeamCreate,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> TeamCreatedResponse:
    """Create a team in the path's company; the caller becomes its team owner (``TeamService``)."""
    await _authorize(session, company_id, ctx)
    try:
        team = await _team_service(session, company_id, ctx).create_team(
            name=body.name, description=body.description, settings=body.settings, is_default=body.is_default
        )
        response = TeamCreatedResponse(message=f"Team '{team.name}' created successfully", team=_team_to_response(team))
        await session.commit()
    except DuplicateTeamError:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A team with that name already exists")
    return response


@router.delete("/{company_id}/teams/{team_id}", response_model=TeamDeletedResponse)
async def delete_company_team(
    company_id: uuid.UUID,
    team_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> TeamDeletedResponse:
    """Soft-delete a team of the path's company. A user action: nothing here deletes teams on its own."""
    await _authorize(session, company_id, ctx)
    try:
        await _team_service(session, company_id, ctx).delete_team(team_id, hard_delete=False)
        await session.commit()
    except TeamNotFoundError:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_TEAM_NOT_FOUND)
    return TeamDeletedResponse(message=f"Team {team_id} deleted successfully")


@router.post(
    "/{company_id}/teams/{team_id}/members/{user_id}",
    response_model=MemberAddedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_company_team_member(
    company_id: uuid.UUID,
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    role: str = Query("member", description="Member role (owner, admin, member)"),
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> MemberAddedResponse:
    """Add one of the company's own users to one of its teams."""
    await _authorize(session, company_id, ctx)
    await _require_company_user(session, company_id, user_id)
    try:
        membership = await _team_service(session, company_id, ctx).add_member(team_id, user_id, role=role)
        response = MemberAddedResponse(
            message=f"User added to team with role '{role}'", member=_membership_to_response(membership)
        )
        await session.commit()
    except TeamNotFoundError:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_TEAM_NOT_FOUND)
    except MembershipError:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already a member, or invalid role")
    return response


@router.delete("/{company_id}/teams/{team_id}/members/{user_id}", response_model=MemberRemovedResponse)
async def remove_company_team_member(
    company_id: uuid.UUID,
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> MemberRemovedResponse:
    """Remove a user from one of the company's teams."""
    await _authorize(session, company_id, ctx)
    try:
        await _team_service(session, company_id, ctx).remove_member(team_id, user_id)
        await session.commit()
    except TeamNotFoundError:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_TEAM_NOT_FOUND)
    except MembershipError:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Not a member, or last team owner")
    return MemberRemovedResponse(message="Member removed from team")
