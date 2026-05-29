# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Slash Command Presets API (GH#8595)

GET    /api/presets         -> SlashCommandPreset[]
POST   /api/presets         -> SlashCommandPreset
PUT    /api/presets/{id}    -> SlashCommandPreset
DELETE /api/presets/{id}    -> 204

Personal presets scoped to owner; org presets visible to all org members.
Command slug validation: lowercase, no spaces, alphanumeric + underscores.
"""

import re
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_middleware import get_current_user
from autobot_shared.logging_manager import get_logger
from models.slash_command_preset import SlashCommandPreset
from user_management.database import get_async_session

logger = get_logger(__name__)

router = APIRouter(tags=["chat"])


class SlashCommandPresetCreate(BaseModel):
    """Request body for creating a slash command preset."""

    command: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1, max_length=1000)
    prompt_template: str = Field(..., min_length=1)
    org_id: Optional[UUID] = None

    @field_validator("command")
    @classmethod
    def validate_command(cls, v: str) -> str:
        if not re.match(r"^[a-z0-9_]+$", v):
            raise ValueError("Command must be lowercase alphanumeric with underscores only")
        return v


class SlashCommandPresetUpdate(BaseModel):
    """Request body for updating a slash command preset."""

    description: Optional[str] = None
    prompt_template: Optional[str] = None

    @field_validator("description", "prompt_template")
    @classmethod
    def validate_not_empty(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.strip():
            raise ValueError("Field cannot be empty")
        return v


class SlashCommandPresetResponse(BaseModel):
    """Response model for slash command presets."""

    id: UUID
    org_id: Optional[UUID]
    user_id: Optional[str]
    command: str
    description: str
    prompt_template: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


@router.get("/api/presets", response_model=list[SlashCommandPresetResponse])
async def list_presets(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> list[SlashCommandPresetResponse]:
    """List all presets accessible to the current user (personal + org)."""
    user_id = current_user.get("username", "")
    org_id = current_user.get("org_id")

    query = select(SlashCommandPreset).where(
        or_(
            SlashCommandPreset.user_id == user_id,
            and_(
                SlashCommandPreset.org_id == org_id,
                SlashCommandPreset.user_id.is_(None),
            ),
        )
    )
    result = await session.execute(query)
    presets = result.scalars().all()
    return [SlashCommandPresetResponse.model_validate(p) for p in presets]


@router.post("/api/presets", response_model=SlashCommandPresetResponse, status_code=201)
async def create_preset(
    payload: SlashCommandPresetCreate,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> SlashCommandPresetResponse:
    """Create a new slash command preset (personal or org-scoped)."""
    user_id = current_user.get("username", "")
    user_org_id = current_user.get("org_id")

    if payload.org_id:
        if payload.org_id != user_org_id:
            raise HTTPException(
                status_code=403,
                detail="Cannot create preset in another organization",
            )
        scope_user_id = None
        scope_org_id = payload.org_id
    else:
        scope_user_id = user_id
        scope_org_id = None

    query = select(SlashCommandPreset).where(
        and_(
            SlashCommandPreset.user_id == scope_user_id,
            SlashCommandPreset.org_id == scope_org_id,
            SlashCommandPreset.command == payload.command,
        )
    )
    result = await session.execute(query)
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=409,
            detail="Command already exists in this scope",
        )

    preset = SlashCommandPreset(
        command=payload.command,
        description=payload.description,
        prompt_template=payload.prompt_template,
        user_id=scope_user_id,
        org_id=scope_org_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    session.add(preset)
    try:
        await session.commit()
    except Exception as e:
        await session.rollback()
        logger.error("Failed to create preset: %s", str(e))
        raise HTTPException(status_code=400, detail="Failed to create preset")

    await session.refresh(preset)
    logger.info("Created preset %s for user %s", preset.id, user_id)
    return SlashCommandPresetResponse.model_validate(preset)


@router.put("/api/presets/{preset_id}", response_model=SlashCommandPresetResponse)
async def update_preset(
    preset_id: UUID,
    payload: SlashCommandPresetUpdate,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> SlashCommandPresetResponse:
    """Update an existing slash command preset (owned by user)."""
    user_id = current_user.get("username", "")

    query = select(SlashCommandPreset).where(
        and_(
            SlashCommandPreset.id == preset_id,
            SlashCommandPreset.user_id == user_id,
        )
    )
    result = await session.execute(query)
    preset = result.scalar_one_or_none()

    if preset is None:
        raise HTTPException(status_code=404, detail="Preset not found")

    if payload.description is not None:
        preset.description = payload.description
    if payload.prompt_template is not None:
        preset.prompt_template = payload.prompt_template
    preset.updated_at = datetime.now(timezone.utc)

    try:
        await session.commit()
    except Exception as e:
        await session.rollback()
        logger.error("Failed to update preset: %s", str(e))
        raise HTTPException(status_code=400, detail="Failed to update preset")

    await session.refresh(preset)
    logger.info("Updated preset %s for user %s", preset_id, user_id)
    return SlashCommandPresetResponse.model_validate(preset)


@router.delete("/api/presets/{preset_id}", status_code=204)
async def delete_preset(
    preset_id: UUID,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> Response:
    """Delete a slash command preset (owned by user)."""
    user_id = current_user.get("username", "")

    query = select(SlashCommandPreset).where(
        and_(
            SlashCommandPreset.id == preset_id,
            SlashCommandPreset.user_id == user_id,
        )
    )
    result = await session.execute(query)
    preset = result.scalar_one_or_none()

    if preset is None:
        raise HTTPException(status_code=404, detail="Preset not found")

    try:
        await session.delete(preset)
        await session.commit()
    except Exception as e:
        await session.rollback()
        logger.error("Failed to delete preset: %s", str(e))
        raise HTTPException(status_code=400, detail="Failed to delete preset")

    logger.info("Deleted preset %s for user %s", preset_id, user_id)
    return Response(status_code=204)
