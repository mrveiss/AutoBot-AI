# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
User preferences API endpoints.

Provides:
- GET /api/users/me/preferences - Retrieve user preferences
- PATCH /api/users/me/preferences - Update user preferences
"""

from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from redis.exceptions import RedisError

from api.schemas_common import DataResponse
from auth_middleware import get_current_user
from autobot_shared.error_boundaries import with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import RedisDatabase, get_redis_client

logger = get_logger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


class UserPreferences(BaseModel):
    """User preferences model.

    Appearance fields (#8988) persist UI theme/accent/density per user account so
    choices follow the user across devices. localStorage remains a write-through
    cache on the frontend; the account is the source of truth.
    """

    reasoning_effort: str = Field(
        "auto",
        pattern="^(low|medium|high|auto)$",
        description="Default reasoning effort level (low, medium, high, auto)",
    )
    theme: str = Field(
        "dark",
        pattern="^(dark|light|system)$",
        description="Base theme mode (dark, light, system)",
    )
    accent_color: str = Field(
        "blue",
        pattern="^(blue|green|purple|orange|pink|teal|indigo|red)$",
        description="Accent color preset",
    )
    layout_density: str = Field(
        "comfortable",
        pattern="^(compact|comfortable|spacious)$",
        description="Layout density (compact, comfortable, spacious)",
    )
    font_size: str = Field(
        "medium",
        pattern="^(small|medium|large)$",
        description="Base font size (small, medium, large)",
    )
    theme_preset: str = Field(
        "auto",
        max_length=64,
        description="Selected named theme preset (e.g. catppuccin-mocha); 'auto' when none",
    )
    # Additional preferences can be added here in the future


# Appearance fields persisted alongside reasoning_effort (#8988).
_APPEARANCE_FIELDS = ("theme", "accent_color", "layout_density", "font_size", "theme_preset")


class UserPreferencesData(BaseModel):
    """Data payload for user preferences endpoints."""

    user_id: str
    preferences: UserPreferences


async def _get_user_preferences_from_redis(user_id: str) -> UserPreferences:
    """
    Retrieve user preferences from Redis.

    Args:
        user_id: User ID

    Returns:
        UserPreferences object with stored or default values
    """
    try:
        redis_client = await get_redis_client(async_client=True, database=RedisDatabase.MAIN)

        async def _read(field: str) -> str | None:
            raw = await redis_client.get(f"user:{user_id}:preferences:{field}")
            if raw is None:
                return None
            return raw.decode("utf-8") if isinstance(raw, bytes) else raw

        defaults = UserPreferences()
        values: Dict[str, str] = {}
        for field in ("reasoning_effort", *_APPEARANCE_FIELDS):
            stored = await _read(field)
            values[field] = stored if stored is not None else getattr(defaults, field)

        return UserPreferences(**values)

    except RedisError as e:
        logger.error(f"Redis error retrieving user preferences: {e}")
        # Return defaults on error
        return UserPreferences()


async def _store_user_preferences_to_redis(user_id: str, preferences: UserPreferences) -> None:
    """
    Store user preferences to Redis.

    Args:
        user_id: User ID
        preferences: UserPreferences object to store

    Raises:
        RedisError: If Redis operation fails
    """
    redis_client = await get_redis_client(async_client=True, database=RedisDatabase.MAIN)

    # Store each preference under its own key (no expiration - permanent preference)
    for field in ("reasoning_effort", *_APPEARANCE_FIELDS):
        await redis_client.set(f"user:{user_id}:preferences:{field}", getattr(preferences, field))

    logger.info(
        "Stored user preferences for user %s: reasoning_effort=%s theme=%s accent=%s density=%s",
        user_id,
        preferences.reasoning_effort,
        preferences.theme,
        preferences.accent_color,
        preferences.layout_density,
    )


@router.get("/me/preferences", response_model=DataResponse[UserPreferencesData])
@with_error_handling()
async def get_user_preferences(
    request: Request,
    current_user: Dict = Depends(get_current_user),
) -> DataResponse[UserPreferencesData]:
    """
    Get current user's preferences.

    Returns:
        DataResponse with user preferences

    Raises:
        HTTPException: 401 if not authenticated
    """
    user_id = current_user.get("user_id") or current_user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="User ID not found in token")

    preferences = await _get_user_preferences_from_redis(user_id)

    return DataResponse(
        success=True,
        data=UserPreferencesData(
            user_id=user_id,
            preferences=preferences,
        ),
        message="User preferences retrieved successfully",
    )


@router.patch("/me/preferences", response_model=DataResponse[UserPreferencesData])
@with_error_handling()
async def update_user_preferences(
    preferences: UserPreferences,
    request: Request,
    current_user: Dict = Depends(get_current_user),
) -> DataResponse[UserPreferencesData]:
    """
    Update current user's preferences.

    Args:
        preferences: New preference values

    Returns:
        DataResponse with updated preferences

    Raises:
        HTTPException: 401 if not authenticated
        HTTPException: 500 if Redis operation fails
    """
    user_id = current_user.get("user_id") or current_user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="User ID not found in token")

    try:
        await _store_user_preferences_to_redis(user_id, preferences)
    except RedisError as e:
        logger.error(f"Failed to update user preferences: {e}")
        raise HTTPException(status_code=500, detail="Failed to update preferences")

    return DataResponse(
        success=True,
        data=UserPreferencesData(
            user_id=user_id,
            preferences=preferences,
        ),
        message="User preferences updated successfully",
    )
