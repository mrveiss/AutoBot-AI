# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
User preferences API endpoints.

Provides:
- GET /api/users/me/preferences - Retrieve user preferences
- PATCH /api/users/me/preferences - Update user preferences
- GET/PUT/DELETE /api/users/me/dashboard-layouts/{page} - Per-user dashboard layout (#18242)
"""

from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError
from redis.exceptions import RedisError

from api.schemas_common import DataResponse
from api.schemas_users_dashboard_layouts import (
    DASHBOARD_PAGES,
    MAX_LAYOUT_BYTES,
    DashboardLayout,
    DashboardLayoutData,
)
from auth_middleware import get_current_user
from autobot_shared.error_boundaries import with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import RedisDatabase, get_async_redis_client

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
        pattern=r"^(low|medium|high|auto)\z",
        description="Default reasoning effort level (low, medium, high, auto)",
    )
    theme: str = Field(
        "light",
        pattern=r"^(light|dark|contrast|mono|system)\z",
        description="Base theme (light, dark, contrast, mono, system); light is the Refined default (#18223)",
    )
    accent_color: str = Field(
        "theme",
        pattern=r"^(theme|blue|green|purple|orange|pink|teal|indigo|red)\z",
        description="Accent color preset; 'theme' sets none, so the theme's own primary stands (#18223)",
    )
    layout_density: str = Field(
        "comfortable",
        pattern=r"^(compact|comfortable|spacious)\z",
        description="Layout density (compact, comfortable, spacious)",
    )
    font_size: str = Field(
        "medium",
        pattern=r"^(small|medium|large)\z",
        description="Base font size (small, medium, large)",
    )
    theme_preset: str = Field(
        "auto",
        max_length=64,
        description="Selected named theme preset (e.g. catppuccin-mocha); 'auto' when none",
    )
    ui_mode: str = Field(
        "full",
        pattern=r"^(minimal|full)\z",
        description="Shell UI mode (minimal, full)",
    )
    ui_start: str = Field(
        "last",
        pattern=r"^(last|minimal|full)\z",
        description="Which UI mode to open in on sign-in (last, minimal, full)",
    )
    theme_variant: str = Field(
        "default",
        max_length=64,
        pattern=r"^[a-z0-9][a-z0-9_-]{0,62}\z",  # same charset as theme_install._ID
        description="Theme variant id: 'default', a built-in, or an installed theme id",
    )
    # Additional preferences can be added here in the future


# Appearance fields persisted alongside reasoning_effort (#8988).
_APPEARANCE_FIELDS = (
    "theme",
    "accent_color",
    "layout_density",
    "font_size",
    "theme_preset",
    "ui_mode",
    "ui_start",
    "theme_variant",
)
_ALL_FIELDS = ("reasoning_effort", *_APPEARANCE_FIELDS)


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
        redis_client = await get_async_redis_client(database=RedisDatabase.MAIN)

        async def _read(field: str) -> str | None:
            raw = await redis_client.get(f"user:{user_id}:preferences:{field}")
            if raw is None:
                return None
            return raw.decode("utf-8") if isinstance(raw, bytes) else raw

        defaults = UserPreferences()
        values: Dict[str, str] = {}
        for field in _ALL_FIELDS:
            stored = await _read(field)
            values[field] = stored if stored is not None else getattr(defaults, field)

        return UserPreferences(**values)

    except RedisError as e:
        logger.error(f"Redis error retrieving user preferences: {e}")
        # Return defaults on error
        return UserPreferences()


async def _store_user_preferences_to_redis(
    user_id: str, preferences: UserPreferences, fields: tuple[str, ...] | None = None
) -> None:
    """
    Store user preferences to Redis.

    Args:
        user_id: User ID
        preferences: UserPreferences object to store
        fields: Only these fields are written (partial PATCH); None writes all

    Raises:
        RedisError: If Redis operation fails
    """
    redis_client = await get_async_redis_client(database=RedisDatabase.MAIN)

    # Store each preference under its own key (no expiration - permanent preference)
    for field in fields if fields is not None else _ALL_FIELDS:
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
    Update current user's preferences (partial: omitted fields keep stored values).

    Args:
        preferences: Preference values; only fields present in the body are written

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
        sent = tuple(f for f in _ALL_FIELDS if f in preferences.model_fields_set)
        await _store_user_preferences_to_redis(user_id, preferences, sent)
        merged = await _get_user_preferences_from_redis(user_id)
    except RedisError as e:
        logger.error(f"Failed to update user preferences: {e}")
        raise HTTPException(status_code=500, detail="Failed to update preferences")

    return DataResponse(
        success=True,
        data=UserPreferencesData(
            user_id=user_id,
            preferences=merged,
        ),
        message="User preferences updated successfully",
    )


# --- Dashboard layouts (#18242): one JSON document per user and page ---


def _layout_key(user_id: str, page: str) -> str:
    return f"user:{user_id}:dashboard_layout:{page}"


def _require_user_and_page(current_user: Dict, page: str) -> str:
    user_id = current_user.get("user_id") or current_user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="User ID not found in token")
    if page not in DASHBOARD_PAGES:
        raise HTTPException(status_code=404, detail="Unknown dashboard page")
    return user_id


def _reject_duplicate_ids(layout: DashboardLayout) -> None:
    dash_ids = [d.id for d in layout.dashboards]
    if len(dash_ids) != len(set(dash_ids)):
        raise HTTPException(status_code=422, detail="Duplicate dashboard id")
    for dash in layout.dashboards:
        widget_ids = [w.id for w in dash.widgets]
        if len(widget_ids) != len(set(widget_ids)):
            raise HTTPException(status_code=422, detail="Duplicate widget id in dashboard")


async def _layout_store():
    """The Redis client that holds layouts; 503 when Redis is disabled or its breaker is open."""
    client = await get_async_redis_client(database=RedisDatabase.MAIN)
    if client is None:
        logger.warning("Dashboard layout store unavailable: no Redis client")
        raise HTTPException(status_code=503, detail="Dashboard layout storage unavailable")
    return client


def _layout_response(page: str, layout: DashboardLayout, message: str) -> DataResponse[DashboardLayoutData]:
    return DataResponse(success=True, data=DashboardLayoutData(page=page, layout=layout), message=message)


@router.get("/me/dashboard-layouts/{page}", response_model=DataResponse[DashboardLayoutData])
@with_error_handling()
async def get_dashboard_layout(
    page: str, request: Request, current_user: Dict = Depends(get_current_user)
) -> DataResponse[DashboardLayoutData]:
    """Return the caller's stored layout for ``page``; no dashboards when none is stored."""
    user_id = _require_user_and_page(current_user, page)
    redis_client = await _layout_store()
    raw = await redis_client.get(_layout_key(user_id, page))
    if raw is None:
        return _layout_response(page, DashboardLayout(), "No stored layout; defaults apply")
    try:
        layout = DashboardLayout.model_validate_json(raw)
    except ValidationError:
        logger.warning("Stored dashboard layout for %s/%s is invalid; defaults apply", user_id, page)
        return _layout_response(page, DashboardLayout(), "Stored layout was invalid; defaults apply")
    return _layout_response(page, layout, "Dashboard layout retrieved")


@router.put("/me/dashboard-layouts/{page}", response_model=DataResponse[DashboardLayoutData])
@with_error_handling()
async def put_dashboard_layout(
    page: str, layout: DashboardLayout, request: Request, current_user: Dict = Depends(get_current_user)
) -> DataResponse[DashboardLayoutData]:
    """Replace the caller's layout for ``page``."""
    user_id = _require_user_and_page(current_user, page)
    _reject_duplicate_ids(layout)
    payload = layout.model_dump_json()
    if len(payload.encode("utf-8")) > MAX_LAYOUT_BYTES:
        raise HTTPException(status_code=413, detail="Dashboard layout too large")
    redis_client = await _layout_store()
    await redis_client.set(_layout_key(user_id, page), payload)
    return _layout_response(page, layout, "Dashboard layout saved")


@router.delete("/me/dashboard-layouts/{page}", response_model=DataResponse[DashboardLayoutData])
@with_error_handling()
async def reset_dashboard_layout(
    page: str, request: Request, current_user: Dict = Depends(get_current_user)
) -> DataResponse[DashboardLayoutData]:
    """Drop the caller's stored layout for ``page`` so the defaults apply again."""
    user_id = _require_user_and_page(current_user, page)
    redis_client = await _layout_store()
    await redis_client.delete(_layout_key(user_id, page))
    return _layout_response(page, DashboardLayout(), "Dashboard layout reset to defaults")
