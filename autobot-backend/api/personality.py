# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Personality Profile API

REST endpoints for managing AutoBot personality profiles.
Mutations (create, update, delete, activate, reset, toggle) require admin.

Related Issue: #964 - Multi-profile personality system
"""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status

from api.schemas_agent import (
    PersonalityProfileCreate,
    PersonalityProfileDetail,
    PersonalityProfileSummary,
    PersonalityProfileUpdate,
    PersonalityStatusResponse,
    PersonalityToggleRequest,
)
from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from services.personality_service import SUPPORTED_LANGUAGES, get_personality_manager

logger = get_logger(__name__)
router = APIRouter(tags=["personality"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _profile_to_detail(p) -> PersonalityProfileDetail:
    return PersonalityProfileDetail(
        id=p.id,
        name=p.name,
        tagline=p.tagline,
        tone=p.tone,
        character_traits=p.character_traits,
        operating_style=p.operating_style,
        off_limits=p.off_limits,
        custom_notes=p.custom_notes,
        voice_id=p.voice_id,  # (#1135)
        voice_ids=p.voice_ids,  # (#1333)
        language_code=p.language_code,  # (#1324)
        is_system=p.is_system,
        created_by=p.created_by,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


def _not_found(pid: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Personality profile not found: {pid}",
    )


# ---------------------------------------------------------------------------
# Read endpoints (any authenticated user)
# ---------------------------------------------------------------------------


@router.get("/profiles", response_model=List[PersonalityProfileSummary])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_profiles",
    error_code_prefix="PERSONALITY",
)
async def list_profiles() -> List[Dict[str, Any]]:
    """List all personality profiles."""
    return get_personality_manager().list_profiles()


@router.get("/active", response_model=PersonalityProfileDetail | None)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_active",
    error_code_prefix="PERSONALITY",
)
async def get_active() -> PersonalityProfileDetail | None:
    """Return the active profile, or null if personality is disabled."""
    mgr = get_personality_manager()
    profile = mgr.get_active_profile()
    if profile is None:
        return None
    return _profile_to_detail(profile)


@router.get("/status", response_model=PersonalityStatusResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_status",
    error_code_prefix="PERSONALITY",
)
async def get_status() -> PersonalityStatusResponse:
    """Return enabled flag and active profile id."""
    mgr = get_personality_manager()
    index = mgr._read_index()
    return PersonalityStatusResponse(
        enabled=index.get("enabled", True),
        active_id=index.get("active_id"),
    )


@router.get("/languages", response_model=None)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_languages",
    error_code_prefix="PERSONALITY",
)
async def list_languages() -> Dict[str, str]:
    """Return the supported language codes and their display names."""
    return SUPPORTED_LANGUAGES


@router.get("/profiles/{pid}", response_model=PersonalityProfileDetail)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_profile",
    error_code_prefix="PERSONALITY",
)
async def get_profile(pid: str) -> PersonalityProfileDetail:
    """Fetch a single profile by id."""
    profile = get_personality_manager().get_profile(pid)
    if profile is None:
        raise _not_found(pid)
    return _profile_to_detail(profile)


# ---------------------------------------------------------------------------
# Mutating endpoints (admin only)
# ---------------------------------------------------------------------------


@router.post(
    "/profiles",
    response_model=PersonalityProfileDetail,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_admin_permission)],
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_profile",
    error_code_prefix="PERSONALITY",
)
async def create_profile(body: PersonalityProfileCreate) -> PersonalityProfileDetail:
    """Create a new user personality profile."""
    profile = get_personality_manager().create_profile(**body.model_dump())
    return _profile_to_detail(profile)


@router.put(
    "/profiles/{pid}",
    response_model=PersonalityProfileDetail,
    dependencies=[Depends(check_admin_permission)],
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_profile",
    error_code_prefix="PERSONALITY",
)
async def update_profile(pid: str, body: PersonalityProfileUpdate) -> PersonalityProfileDetail:
    """Update fields on an existing profile."""
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        profile = get_personality_manager().update_profile(pid, updates)
    except ValueError as exc:
        raise _not_found(pid) from exc
    return _profile_to_detail(profile)


@router.delete(
    "/profiles/{pid}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(check_admin_permission)],
    response_model=None,
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delete_profile",
    error_code_prefix="PERSONALITY",
)
async def delete_profile(pid: str) -> None:
    """Delete a user-created profile. System profiles cannot be deleted."""
    try:
        get_personality_manager().delete_profile(pid)
    except ValueError as exc:
        detail = str(exc)
        if "system profile" in detail:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from exc
        raise _not_found(pid) from exc


@router.post(
    "/profiles/{pid}/activate",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(check_admin_permission)],
    response_model=None,
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="activate_profile",
    error_code_prefix="PERSONALITY",
)
async def activate_profile(pid: str) -> None:
    """Set a profile as the active personality."""
    try:
        get_personality_manager().activate_profile(pid)
    except ValueError as exc:
        raise _not_found(pid) from exc


@router.post(
    "/profiles/{pid}/reset",
    response_model=PersonalityProfileDetail,
    dependencies=[Depends(check_admin_permission)],
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="reset_profile",
    error_code_prefix="PERSONALITY",
)
async def reset_profile(pid: str) -> PersonalityProfileDetail:
    """Reset a profile's content to match the default profile."""
    try:
        profile = get_personality_manager().reset_profile(pid)
    except ValueError as exc:
        raise _not_found(pid) from exc
    return _profile_to_detail(profile)


@router.post(
    "/toggle",
    response_model=PersonalityStatusResponse,
    dependencies=[Depends(check_admin_permission)],
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="toggle_personality",
    error_code_prefix="PERSONALITY",
)
async def toggle_personality(body: PersonalityToggleRequest) -> PersonalityStatusResponse:
    """Enable or disable the personality system globally."""
    mgr = get_personality_manager()
    mgr.set_enabled(body.enabled)
    index = mgr._read_index()
    return PersonalityStatusResponse(
        enabled=body.enabled,
        active_id=index.get("active_id"),
    )
