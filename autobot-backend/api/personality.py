# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Personality Profile API

REST endpoints for managing AutoBot personality profiles.
Mutations (create, update, delete, activate, reset, toggle) require admin.

Related Issue: #964 - Multi-profile personality system
"""

import logging
from typing import Any, Dict, List, Optional

from auth_middleware import check_admin_permission
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator

from backend.services.personality_service import get_personality_manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["personality"])

_VALID_TONES = {"direct", "professional", "casual", "technical"}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ProfileSummary(BaseModel):
    id: str
    name: str
    is_system: bool
    active: bool


class ProfileDetail(BaseModel):
    id: str
    name: str
    tagline: str
    tone: str
    character_traits: List[str]
    operating_style: List[str]
    off_limits: List[str]
    custom_notes: str
    is_system: bool
    created_by: str
    created_at: str
    updated_at: str


class ProfileCreate(BaseModel):
    name: str
    tagline: str = ""
    tone: str = "direct"
    character_traits: List[str] = []
    operating_style: List[str] = []
    off_limits: List[str] = []
    custom_notes: str = ""

    @field_validator("tone")
    @classmethod
    def tone_must_be_valid(cls, v: str) -> str:
        if v not in _VALID_TONES:
            raise ValueError(f"tone must be one of {sorted(_VALID_TONES)}")
        return v


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    tagline: Optional[str] = None
    tone: Optional[str] = None
    character_traits: Optional[List[str]] = None
    operating_style: Optional[List[str]] = None
    off_limits: Optional[List[str]] = None
    custom_notes: Optional[str] = None

    @field_validator("tone")
    @classmethod
    def tone_must_be_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _VALID_TONES:
            raise ValueError(f"tone must be one of {sorted(_VALID_TONES)}")
        return v


class ToggleRequest(BaseModel):
    enabled: bool


class StatusResponse(BaseModel):
    enabled: bool
    active_id: Optional[str]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _profile_to_detail(p) -> ProfileDetail:
    return ProfileDetail(
        id=p.id,
        name=p.name,
        tagline=p.tagline,
        tone=p.tone,
        character_traits=p.character_traits,
        operating_style=p.operating_style,
        off_limits=p.off_limits,
        custom_notes=p.custom_notes,
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


@router.get("/profiles", response_model=List[ProfileSummary])
async def list_profiles() -> List[Dict[str, Any]]:
    """List all personality profiles."""
    return get_personality_manager().list_profiles()


@router.get("/active", response_model=Optional[ProfileDetail])
async def get_active() -> Optional[ProfileDetail]:
    """Return the active profile, or null if personality is disabled."""
    mgr = get_personality_manager()
    profile = mgr.get_active_profile()
    if profile is None:
        return None
    return _profile_to_detail(profile)


@router.get("/status", response_model=StatusResponse)
async def get_status() -> StatusResponse:
    """Return enabled flag and active profile id."""
    mgr = get_personality_manager()
    index = mgr._read_index()
    return StatusResponse(
        enabled=index.get("enabled", True),
        active_id=index.get("active_id"),
    )


@router.get("/profiles/{pid}", response_model=ProfileDetail)
async def get_profile(pid: str) -> ProfileDetail:
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
    response_model=ProfileDetail,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_admin_permission)],
)
async def create_profile(body: ProfileCreate) -> ProfileDetail:
    """Create a new user personality profile."""
    profile = get_personality_manager().create_profile(**body.model_dump())
    return _profile_to_detail(profile)


@router.put(
    "/profiles/{pid}",
    response_model=ProfileDetail,
    dependencies=[Depends(check_admin_permission)],
)
async def update_profile(pid: str, body: ProfileUpdate) -> ProfileDetail:
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
)
async def delete_profile(pid: str) -> None:
    """Delete a user-created profile. System profiles cannot be deleted."""
    try:
        get_personality_manager().delete_profile(pid)
    except ValueError as exc:
        detail = str(exc)
        if "system profile" in detail:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=detail
            ) from exc
        raise _not_found(pid) from exc


@router.post(
    "/profiles/{pid}/activate",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(check_admin_permission)],
)
async def activate_profile(pid: str) -> None:
    """Set a profile as the active personality."""
    try:
        get_personality_manager().activate_profile(pid)
    except ValueError as exc:
        raise _not_found(pid) from exc


@router.post(
    "/profiles/{pid}/reset",
    response_model=ProfileDetail,
    dependencies=[Depends(check_admin_permission)],
)
async def reset_profile(pid: str) -> ProfileDetail:
    """Reset a profile's content to match the default profile."""
    try:
        profile = get_personality_manager().reset_profile(pid)
    except ValueError as exc:
        raise _not_found(pid) from exc
    return _profile_to_detail(profile)


@router.post(
    "/toggle",
    response_model=StatusResponse,
    dependencies=[Depends(check_admin_permission)],
)
async def toggle_personality(body: ToggleRequest) -> StatusResponse:
    """Enable or disable the personality system globally."""
    mgr = get_personality_manager()
    mgr.set_enabled(body.enabled)
    index = mgr._read_index()
    return StatusResponse(
        enabled=body.enabled,
        active_id=index.get("active_id"),
    )
