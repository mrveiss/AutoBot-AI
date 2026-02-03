# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Roles API Routes (Issue #779).

CRUD endpoints for role definitions.
"""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

from models.database import Role, SyncType
from services.auth import get_current_user
from services.database import get_db
from services.role_registry import get_role_definitions, list_roles

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/roles", tags=["roles"])


class RoleResponse(BaseModel):
    """Role response schema."""

    name: str
    display_name: str | None
    sync_type: str | None
    source_paths: list
    target_path: str
    systemd_service: str | None
    auto_restart: bool
    health_check_port: int | None
    health_check_path: str | None
    pre_sync_cmd: str | None
    post_sync_cmd: str | None

    class Config:
        from_attributes = True


class RoleCreate(BaseModel):
    """Role creation schema."""

    name: str = Field(..., min_length=1, max_length=50)
    display_name: str | None = None
    sync_type: str = SyncType.COMPONENT.value
    source_paths: list = Field(default_factory=list)
    target_path: str = Field(..., min_length=1)
    systemd_service: str | None = None
    auto_restart: bool = False
    health_check_port: int | None = None
    health_check_path: str | None = None
    pre_sync_cmd: str | None = None
    post_sync_cmd: str | None = None


class RoleUpdate(BaseModel):
    """Role update schema."""

    display_name: str | None = None
    sync_type: str | None = None
    source_paths: list | None = None
    target_path: str | None = None
    systemd_service: str | None = None
    auto_restart: bool | None = None
    health_check_port: int | None = None
    health_check_path: str | None = None
    pre_sync_cmd: str | None = None
    post_sync_cmd: str | None = None


@router.get("", response_model=List[RoleResponse])
async def get_roles(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> List[RoleResponse]:
    """List all role definitions."""
    roles = await list_roles(db)
    return [RoleResponse.model_validate(r) for r in roles]


@router.get("/definitions")
async def get_definitions_for_agents() -> List[dict]:
    """
    Get lightweight role definitions for agents.

    No authentication required - agents use this to know what to detect.
    """
    return await get_role_definitions()


@router.get("/{role_name}", response_model=RoleResponse)
async def get_role_by_name(
    role_name: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> RoleResponse:
    """Get a specific role by name."""
    result = await db.execute(select(Role).where(Role.name == role_name))
    role = result.scalar_one_or_none()

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role not found: {role_name}",
        )

    return RoleResponse.model_validate(role)


@router.post("", response_model=RoleResponse)
async def create_role(
    role_data: RoleCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> RoleResponse:
    """Create a new role definition."""
    # Check if exists
    result = await db.execute(select(Role).where(Role.name == role_data.name))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Role already exists: {role_data.name}",
        )

    role = Role(**role_data.model_dump())
    db.add(role)
    await db.commit()
    await db.refresh(role)

    logger.info("Created role: %s", role.name)
    return RoleResponse.model_validate(role)


@router.put("/{role_name}", response_model=RoleResponse)
async def update_role(
    role_name: str,
    role_data: RoleUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> RoleResponse:
    """Update a role definition."""
    result = await db.execute(select(Role).where(Role.name == role_name))
    role = result.scalar_one_or_none()

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role not found: {role_name}",
        )

    for field, value in role_data.model_dump(exclude_unset=True).items():
        setattr(role, field, value)

    await db.commit()
    await db.refresh(role)

    logger.info("Updated role: %s", role.name)
    return RoleResponse.model_validate(role)


@router.delete("/{role_name}")
async def delete_role(
    role_name: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> dict:
    """Delete a role definition."""
    result = await db.execute(select(Role).where(Role.name == role_name))
    role = result.scalar_one_or_none()

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role not found: {role_name}",
        )

    await db.delete(role)
    await db.commit()

    logger.info("Deleted role: %s", role_name)
    return {"success": True, "message": f"Role '{role_name}' deleted"}
