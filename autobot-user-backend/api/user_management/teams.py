# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Teams API Endpoints

REST API for team management operations.
"""

import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from backend.api.user_management.dependencies import (
    get_team_service,
    require_org_context,
    require_user_management_enabled,
)
from user_management.services import TeamService, TenantContext
from user_management.services.team_service import (
    DuplicateTeamError,
    MembershipError,
    TeamNotFoundError,
)

router = APIRouter(prefix="/teams", tags=["Teams"])
logger = logging.getLogger(__name__)


# -------------------------------------------------------------------------
# Request/Response Models
# -------------------------------------------------------------------------


class TeamCreate(BaseModel):
    """Request model for creating a team."""

    name: str = Field(..., min_length=1, max_length=255, description="Team name")
    description: Optional[str] = Field(
        None, max_length=500, description="Team description"
    )
    settings: Optional[dict] = Field(default_factory=dict, description="Team settings")
    is_default: bool = Field(False, description="Whether this is the default team")


class TeamUpdate(BaseModel):
    """Request model for updating a team."""

    name: Optional[str] = Field(
        None, min_length=1, max_length=255, description="Team name"
    )
    description: Optional[str] = Field(
        None, max_length=500, description="Team description"
    )
    settings: Optional[dict] = Field(None, description="Team settings")


class MembershipUpdate(BaseModel):
    """Request model for updating membership."""

    role: str = Field(..., description="New role (owner, admin, member)")


class MemberResponse(BaseModel):
    """Response model for team member."""

    user_id: uuid.UUID
    username: str
    email: str
    display_name: Optional[str]
    role: str
    joined_at: str

    class Config:
        from_attributes = True


class TeamResponse(BaseModel):
    """Response model for a team."""

    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    description: Optional[str]
    settings: dict
    is_default: bool
    member_count: int = 0
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class TeamListResponse(BaseModel):
    """Response model for paginated team list."""

    teams: List[TeamResponse]
    total: int
    limit: int
    offset: int


class TeamCreatedResponse(BaseModel):
    """Response for team creation."""

    success: bool = True
    message: str
    team: TeamResponse


class TeamDeletedResponse(BaseModel):
    """Response for team deletion."""

    success: bool = True
    message: str


class MemberAddedResponse(BaseModel):
    """Response for adding a member."""

    success: bool = True
    message: str
    member: MemberResponse


class MemberRemovedResponse(BaseModel):
    """Response for removing a member."""

    success: bool = True
    message: str


# -------------------------------------------------------------------------
# Team CRUD Endpoints
# -------------------------------------------------------------------------


@router.get(
    "",
    response_model=TeamListResponse,
    summary="List teams",
    description="List teams in the current organization.",
    dependencies=[
        Depends(require_user_management_enabled),
        Depends(require_org_context),
    ],
)
async def list_teams(
    limit: int = Query(50, ge=1, le=100, description="Maximum number of teams"),
    offset: int = Query(0, ge=0, description="Number of teams to skip"),
    search: Optional[str] = Query(None, description="Search by name or description"),
    team_service: TeamService = Depends(get_team_service),
):
    """List teams with pagination."""
    teams, total = await team_service.list_teams(
        limit=limit,
        offset=offset,
        search=search,
    )

    return TeamListResponse(
        teams=[_team_to_response(team) for team in teams],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "",
    response_model=TeamCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create team",
    description="Create a new team in the current organization.",
    dependencies=[
        Depends(require_user_management_enabled),
        Depends(require_org_context),
    ],
)
async def create_team(
    team_data: TeamCreate,
    team_service: TeamService = Depends(get_team_service),
):
    """Create a new team."""
    try:
        team = await team_service.create_team(
            name=team_data.name,
            description=team_data.description,
            settings=team_data.settings,
            is_default=team_data.is_default,
        )

        return TeamCreatedResponse(
            message=f"Team '{team.name}' created successfully",
            team=_team_to_response(team),
        )

    except DuplicateTeamError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )


@router.get(
    "/{team_id}",
    response_model=TeamResponse,
    summary="Get team",
    description="Get a specific team by ID.",
    dependencies=[Depends(require_user_management_enabled)],
)
async def get_team(
    team_id: uuid.UUID,
    team_service: TeamService = Depends(get_team_service),
):
    """Get team by ID."""
    team = await team_service.get_team(team_id)
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Team {team_id} not found",
        )

    return _team_to_response(team)


@router.patch(
    "/{team_id}",
    response_model=TeamResponse,
    summary="Update team",
    description="Update a team's details.",
    dependencies=[Depends(require_user_management_enabled)],
)
async def update_team(
    team_id: uuid.UUID,
    team_data: TeamUpdate,
    team_service: TeamService = Depends(get_team_service),
):
    """Update team details."""
    try:
        team = await team_service.update_team(
            team_id=team_id,
            name=team_data.name,
            description=team_data.description,
            settings=team_data.settings,
        )

        return _team_to_response(team)

    except TeamNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Team {team_id} not found",
        )
    except DuplicateTeamError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )


@router.delete(
    "/{team_id}",
    response_model=TeamDeletedResponse,
    summary="Delete team",
    description="Delete a team (soft delete by default).",
    dependencies=[Depends(require_user_management_enabled)],
)
async def delete_team(
    team_id: uuid.UUID,
    hard_delete: bool = Query(False, description="Permanently delete team"),
    team_service: TeamService = Depends(get_team_service),
):
    """Delete team."""
    try:
        await team_service.delete_team(team_id, hard_delete=hard_delete)
        return TeamDeletedResponse(
            message=f"Team {team_id} deleted successfully",
        )

    except TeamNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Team {team_id} not found",
        )


# -------------------------------------------------------------------------
# Membership Endpoints
# -------------------------------------------------------------------------


@router.get(
    "/{team_id}/members",
    response_model=List[MemberResponse],
    summary="List team members",
    description="List all members of a team.",
    dependencies=[Depends(require_user_management_enabled)],
)
async def list_team_members(
    team_id: uuid.UUID,
    role: Optional[str] = Query(None, description="Filter by role"),
    team_service: TeamService = Depends(get_team_service),
):
    """List team members."""
    memberships = await team_service.get_team_members(team_id, role=role)
    return [_membership_to_response(m) for m in memberships]


@router.post(
    "/{team_id}/members/{user_id}",
    response_model=MemberAddedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add team member",
    description="Add a user to a team.",
    dependencies=[Depends(require_user_management_enabled)],
)
async def add_team_member(
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    role: str = Query("member", description="Member role (owner, admin, member)"),
    team_service: TeamService = Depends(get_team_service),
):
    """Add user to team."""
    try:
        membership = await team_service.add_member(team_id, user_id, role=role)
        return MemberAddedResponse(
            message=f"User added to team with role '{role}'",
            member=_membership_to_response(membership),
        )

    except TeamNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Team {team_id} not found",
        )
    except MembershipError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )


@router.delete(
    "/{team_id}/members/{user_id}",
    response_model=MemberRemovedResponse,
    summary="Remove team member",
    description="Remove a user from a team.",
    dependencies=[Depends(require_user_management_enabled)],
)
async def remove_team_member(
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    team_service: TeamService = Depends(get_team_service),
):
    """Remove user from team."""
    try:
        await team_service.remove_member(team_id, user_id)
        return MemberRemovedResponse(
            message="Member removed from team",
        )

    except MembershipError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.patch(
    "/{team_id}/members/{user_id}",
    response_model=MemberResponse,
    summary="Update member role",
    description="Change a team member's role.",
    dependencies=[Depends(require_user_management_enabled)],
)
async def update_member_role(
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    update_data: MembershipUpdate,
    team_service: TeamService = Depends(get_team_service),
):
    """Update member role."""
    try:
        membership = await team_service.change_member_role(
            team_id, user_id, update_data.role
        )
        return _membership_to_response(membership)

    except MembershipError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# -------------------------------------------------------------------------
# User's Teams Endpoint
# -------------------------------------------------------------------------


@router.get(
    "/my-teams",
    response_model=List[TeamResponse],
    summary="Get my teams",
    description="Get all teams the current user is a member of.",
    dependencies=[Depends(require_user_management_enabled)],
)
async def get_my_teams(
    context: TenantContext = Depends(require_org_context),
    team_service: TeamService = Depends(get_team_service),
):
    """Get teams for current user."""
    if not context.user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User ID not found in context",
        )

    teams = await team_service.get_user_teams(context.user_id)
    return [_team_to_response(team) for team in teams]


# -------------------------------------------------------------------------
# Helper Functions
# -------------------------------------------------------------------------


def _team_to_response(team) -> TeamResponse:
    """Convert Team model to TeamResponse schema."""
    member_count = (
        len(team.memberships)
        if hasattr(team, "memberships") and team.memberships
        else 0
    )

    return TeamResponse(
        id=team.id,
        org_id=team.org_id,
        name=team.name,
        description=team.description,
        settings=team.settings or {},
        is_default=team.is_default,
        member_count=member_count,
        created_at=team.created_at.isoformat() if team.created_at else "",
        updated_at=team.updated_at.isoformat() if team.updated_at else "",
    )


def _membership_to_response(membership) -> MemberResponse:
    """Convert TeamMembership model to MemberResponse schema."""
    user = membership.user if hasattr(membership, "user") else None

    return MemberResponse(
        user_id=membership.user_id,
        username=user.username if user else "unknown",
        email=user.email if user else "unknown",
        display_name=user.display_name if user else None,
        role=membership.role,
        joined_at=membership.joined_at.isoformat() if membership.joined_at else "",
    )
