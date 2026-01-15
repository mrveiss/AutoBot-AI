# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Settings API Routes
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import Setting
from models.schemas import SettingResponse, SettingUpdate
from services.auth import get_current_user, require_admin
from services.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=list[SettingResponse])
async def list_settings(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> list[SettingResponse]:
    """List all settings."""
    result = await db.execute(select(Setting).order_by(Setting.key))
    settings = result.scalars().all()
    return [SettingResponse.model_validate(s) for s in settings]


@router.get("/{key}", response_model=SettingResponse)
async def get_setting(
    key: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> SettingResponse:
    """Get a setting by key."""
    result = await db.execute(select(Setting).where(Setting.key == key))
    setting = result.scalar_one_or_none()

    if not setting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Setting not found",
        )

    return SettingResponse.model_validate(setting)


@router.put("/{key}", response_model=SettingResponse)
async def update_setting(
    key: str,
    setting_data: SettingUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(require_admin)],
) -> SettingResponse:
    """Update a setting (admin only)."""
    result = await db.execute(select(Setting).where(Setting.key == key))
    setting = result.scalar_one_or_none()

    if not setting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Setting not found",
        )

    setting.value = setting_data.value
    if setting_data.description is not None:
        setting.description = setting_data.description

    await db.commit()
    await db.refresh(setting)

    logger.info("Setting updated: %s = %s", key, setting_data.value)
    return SettingResponse.model_validate(setting)


@router.post("/{key}", response_model=SettingResponse, status_code=status.HTTP_201_CREATED)
async def create_setting(
    key: str,
    setting_data: SettingUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(require_admin)],
) -> SettingResponse:
    """Create a new setting (admin only)."""
    result = await db.execute(select(Setting).where(Setting.key == key))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Setting already exists",
        )

    setting = Setting(
        key=key,
        value=setting_data.value,
        description=setting_data.description,
    )
    db.add(setting)
    await db.commit()
    await db.refresh(setting)

    logger.info("Setting created: %s = %s", key, setting_data.value)
    return SettingResponse.model_validate(setting)


@router.delete("/{key}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_setting(
    key: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(require_admin)],
) -> None:
    """Delete a setting (admin only)."""
    protected_keys = {"initialized", "monitoring_location", "prometheus_url", "grafana_url"}

    if key in protected_keys:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete protected setting",
        )

    result = await db.execute(select(Setting).where(Setting.key == key))
    setting = result.scalar_one_or_none()

    if not setting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Setting not found",
        )

    await db.delete(setting)
    await db.commit()

    logger.info("Setting deleted: %s", key)
