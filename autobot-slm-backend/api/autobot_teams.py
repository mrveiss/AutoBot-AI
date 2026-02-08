# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Team Management API

Manages teams in the remote AutoBot database (172.16.168.23:5432/autobot_users).
Teams group application users for collaboration and shared resources.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from services.auth import require_admin
from sqlalchemy.ext.asyncio import AsyncSession
from user_management.database import get_autobot_session
from user_management.services import TeamService, TenantContext

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/autobot-teams", tags=["autobot-teams"])


# Pydantic schemas for teams
class TeamCreate(BaseModel):
    """Schema for creating a team."""

    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    organization_id: uuid.UUID | None = None


class TeamUpdate(BaseModel):
    """Schema for updating a team."""

    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None


class TeamResponse(BaseModel):
    """Schema for team response."""

    id: uuid.UUID
    name: str
    description: str | None
    organization_id: uuid.UUID | None
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class TeamListResponse(BaseModel):
    """Schema for paginated team list response."""

    teams: list[TeamResponse]
    total: int
    limit: int
    offset: int


class TeamMemberAdd(BaseModel):
    """Schema for adding a member to a team."""

    user_id: uuid.UUID
    role: str = "member"


async def get_autobot_db():
    """Dependency for AutoBot database session."""
    async with get_autobot_session() as session:
        yield session


@router.post("", response_model=TeamResponse, status_code=status.HTTP_201_CREATED)
async def create_team(
    team_data: TeamCreate,
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_autobot_db),
) -> TeamResponse:
    """Create a new AutoBot team."""
    logger.info("Creating AutoBot team: %s", team_data.name)
    context = TenantContext(is_platform_admin=True)
    team_service = TeamService(db, context)

    try:
        team = await team_service.create_team(
            name=team_data.name,
            description=team_data.description,
            organization_id=team_data.organization_id,
        )
        return TeamResponse.model_validate(team)
    except Exception as e:
        logger.error("Failed to create AutoBot team: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from e


@router.get("", response_model=TeamListResponse)
async def list_teams(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: str = Query(None),
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_autobot_db),
) -> TeamListResponse:
    """List AutoBot teams with pagination and search."""
    logger.info(
        "Listing AutoBot teams (skip=%d, limit=%d, search=%s)", skip, limit, search
    )
    context = TenantContext(is_platform_admin=True)
    team_service = TeamService(db, context)

    teams, total = await team_service.list_teams(
        limit=limit, offset=skip, search=search
    )
    return TeamListResponse(
        teams=[TeamResponse.model_validate(team) for team in teams],
        total=total,
        limit=limit,
        offset=skip,
    )


@router.get("/{team_id}", response_model=TeamResponse)
async def get_team(
    team_id: uuid.UUID,
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_autobot_db),
) -> TeamResponse:
    """Get AutoBot team by ID."""
    context = TenantContext(is_platform_admin=True)
    team_service = TeamService(db, context)

    team = await team_service.get_team(team_id)
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Team not found"
        )
    return TeamResponse.model_validate(team)


@router.patch("/{team_id}", response_model=TeamResponse)
async def update_team(
    team_id: uuid.UUID,
    updates: TeamUpdate,
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_autobot_db),
) -> TeamResponse:
    """Update AutoBot team."""
    logger.info("Updating AutoBot team: %s", team_id)
    context = TenantContext(is_platform_admin=True)
    team_service = TeamService(db, context)

    try:
        team = await team_service.update_team(
            team_id=team_id,
            name=updates.name,
            description=updates.description,
        )
        return TeamResponse.model_validate(team)
    except Exception as e:
        logger.error("Failed to update AutoBot team: %s", e)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team(
    team_id: uuid.UUID,
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_autobot_db),
) -> None:
    """Delete AutoBot team."""
    logger.info("Deleting AutoBot team: %s", team_id)
    context = TenantContext(is_platform_admin=True)
    team_service = TeamService(db, context)

    try:
        await team_service.delete_team(team_id)
    except Exception as e:
        logger.error("Failed to delete AutoBot team: %s", e)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.post("/{team_id}/members", status_code=status.HTTP_201_CREATED)
async def add_team_member(
    team_id: uuid.UUID,
    member: TeamMemberAdd,
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_autobot_db),
) -> dict:
    """Add a member to an AutoBot team."""
    logger.info("Adding member %s to team %s", member.user_id, team_id)
    context = TenantContext(is_platform_admin=True)
    team_service = TeamService(db, context)

    try:
        await team_service.add_member(
            team_id=team_id,
            user_id=member.user_id,
            role=member.role,
        )
        return {"message": "Member added successfully"}
    except Exception as e:
        logger.error("Failed to add team member: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from e


@router.delete("/{team_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_team_member(
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_autobot_db),
) -> None:
    """Remove a member from an AutoBot team."""
    logger.info("Removing member %s from team %s", user_id, team_id)
    context = TenantContext(is_platform_admin=True)
    team_service = TeamService(db, context)

    try:
        await team_service.remove_member(team_id=team_id, user_id=user_id)
    except Exception as e:
        logger.error("Failed to remove team member: %s", e)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
