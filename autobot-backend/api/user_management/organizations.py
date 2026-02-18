# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Organizations API Endpoints

REST API for organization (tenant) management operations.
Used in multi_company and provider deployment modes.
"""

import logging
import uuid
from typing import List, Optional

from backend.api.user_management.dependencies import (
    get_organization_service,
    require_platform_admin,
    require_user_management_enabled,
)
from backend.user_management.services import OrganizationService
from backend.user_management.services.organization_service import (
    DuplicateOrganizationError,
    OrganizationNotFoundError,
)
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

router = APIRouter(prefix="/organizations", tags=["Organizations"])
logger = logging.getLogger(__name__)


# -------------------------------------------------------------------------
# Request/Response Models
# -------------------------------------------------------------------------


class OrganizationCreate(BaseModel):
    """Request model for creating an organization."""

    name: str = Field(
        ..., min_length=1, max_length=255, description="Organization name"
    )
    slug: Optional[str] = Field(
        None,
        max_length=100,
        description="URL-safe slug (auto-generated if not provided)",
    )
    description: Optional[str] = Field(None, max_length=500, description="Description")
    settings: Optional[dict] = Field(
        default_factory=dict, description="Organization settings"
    )
    subscription_tier: str = Field("free", description="Subscription tier")
    max_users: int = Field(-1, description="Maximum users (-1 for unlimited)")


class OrganizationUpdate(BaseModel):
    """Request model for updating an organization."""

    name: Optional[str] = Field(None, min_length=1, max_length=255, description="Name")
    description: Optional[str] = Field(None, max_length=500, description="Description")
    settings: Optional[dict] = Field(None, description="Settings")
    subscription_tier: Optional[str] = Field(None, description="Subscription tier")
    max_users: Optional[int] = Field(None, description="Maximum users")


class OrganizationResponse(BaseModel):
    """Response model for an organization."""

    id: uuid.UUID
    name: str
    slug: str
    description: Optional[str]
    settings: dict
    subscription_tier: str
    max_users: int
    is_active: bool
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class OrganizationListResponse(BaseModel):
    """Response model for paginated organization list."""

    organizations: List[OrganizationResponse]
    total: int
    limit: int
    offset: int


class OrganizationCreatedResponse(BaseModel):
    """Response for organization creation."""

    success: bool = True
    message: str
    organization: OrganizationResponse


class OrganizationDeletedResponse(BaseModel):
    """Response for organization deletion."""

    success: bool = True
    message: str


class OrganizationStatsResponse(BaseModel):
    """Response for organization statistics."""

    organization_id: str
    name: str
    slug: str
    subscription_tier: str
    users: dict
    teams: dict
    is_active: bool
    created_at: Optional[str]


# -------------------------------------------------------------------------
# Organization CRUD Endpoints
# -------------------------------------------------------------------------


@router.get(
    "",
    response_model=OrganizationListResponse,
    summary="List organizations",
    description="List all organizations (platform admin only).",
    dependencies=[
        Depends(require_user_management_enabled),
        Depends(require_platform_admin),
    ],
)
async def list_organizations(
    limit: int = Query(50, ge=1, le=100, description="Maximum number of organizations"),
    offset: int = Query(0, ge=0, description="Number of organizations to skip"),
    search: Optional[str] = Query(None, description="Search by name or slug"),
    include_inactive: bool = Query(False, description="Include inactive organizations"),
    org_service: OrganizationService = Depends(get_organization_service),
):
    """List organizations with pagination."""
    orgs, total = await org_service.list_organizations(
        limit=limit,
        offset=offset,
        search=search,
        include_inactive=include_inactive,
    )

    return OrganizationListResponse(
        organizations=[_org_to_response(org) for org in orgs],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "",
    response_model=OrganizationCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create organization",
    description="Create a new organization (platform admin only).",
    dependencies=[
        Depends(require_user_management_enabled),
        Depends(require_platform_admin),
    ],
)
async def create_organization(
    org_data: OrganizationCreate,
    org_service: OrganizationService = Depends(get_organization_service),
):
    """Create a new organization."""
    try:
        org = await org_service.create_organization(
            name=org_data.name,
            slug=org_data.slug,
            description=org_data.description,
            settings=org_data.settings,
            subscription_tier=org_data.subscription_tier,
            max_users=org_data.max_users,
        )

        return OrganizationCreatedResponse(
            message=f"Organization '{org.name}' created successfully",
            organization=_org_to_response(org),
        )

    except DuplicateOrganizationError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )


@router.get(
    "/{org_id}",
    response_model=OrganizationResponse,
    summary="Get organization",
    description="Get a specific organization by ID.",
    dependencies=[Depends(require_user_management_enabled)],
)
async def get_organization(
    org_id: uuid.UUID,
    org_service: OrganizationService = Depends(get_organization_service),
):
    """Get organization by ID."""
    org = await org_service.get_organization(org_id)
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization {org_id} not found",
        )

    return _org_to_response(org)


@router.get(
    "/slug/{slug}",
    response_model=OrganizationResponse,
    summary="Get organization by slug",
    description="Get a specific organization by slug.",
    dependencies=[Depends(require_user_management_enabled)],
)
async def get_organization_by_slug(
    slug: str,
    org_service: OrganizationService = Depends(get_organization_service),
):
    """Get organization by slug."""
    org = await org_service.get_organization_by_slug(slug)
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization with slug '{slug}' not found",
        )

    return _org_to_response(org)


@router.patch(
    "/{org_id}",
    response_model=OrganizationResponse,
    summary="Update organization",
    description="Update an organization's details.",
    dependencies=[
        Depends(require_user_management_enabled),
        Depends(require_platform_admin),
    ],
)
async def update_organization(
    org_id: uuid.UUID,
    org_data: OrganizationUpdate,
    org_service: OrganizationService = Depends(get_organization_service),
):
    """Update organization details."""
    try:
        org = await org_service.update_organization(
            org_id=org_id,
            name=org_data.name,
            description=org_data.description,
            settings=org_data.settings,
            subscription_tier=org_data.subscription_tier,
            max_users=org_data.max_users,
        )

        return _org_to_response(org)

    except OrganizationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization {org_id} not found",
        )


@router.delete(
    "/{org_id}",
    response_model=OrganizationDeletedResponse,
    summary="Delete organization",
    description="Delete an organization (soft delete by default).",
    dependencies=[
        Depends(require_user_management_enabled),
        Depends(require_platform_admin),
    ],
)
async def delete_organization(
    org_id: uuid.UUID,
    hard_delete: bool = Query(False, description="Permanently delete organization"),
    org_service: OrganizationService = Depends(get_organization_service),
):
    """Delete organization."""
    try:
        await org_service.delete_organization(org_id, hard_delete=hard_delete)
        return OrganizationDeletedResponse(
            message=f"Organization {org_id} deleted successfully",
        )

    except OrganizationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization {org_id} not found",
        )


# -------------------------------------------------------------------------
# Organization Status Endpoints
# -------------------------------------------------------------------------


@router.post(
    "/{org_id}/deactivate",
    response_model=OrganizationResponse,
    summary="Deactivate organization",
    description="Deactivate an organization.",
    dependencies=[
        Depends(require_user_management_enabled),
        Depends(require_platform_admin),
    ],
)
async def deactivate_organization(
    org_id: uuid.UUID,
    org_service: OrganizationService = Depends(get_organization_service),
):
    """Deactivate organization."""
    try:
        await org_service.deactivate_organization(org_id)
        org = await org_service.get_organization(org_id)
        return _org_to_response(org)

    except OrganizationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization {org_id} not found",
        )


# -------------------------------------------------------------------------
# Statistics Endpoint
# -------------------------------------------------------------------------


@router.get(
    "/{org_id}/stats",
    response_model=OrganizationStatsResponse,
    summary="Get organization statistics",
    description="Get usage statistics for an organization.",
    dependencies=[Depends(require_user_management_enabled)],
)
async def get_organization_stats(
    org_id: uuid.UUID,
    org_service: OrganizationService = Depends(get_organization_service),
):
    """Get organization statistics."""
    try:
        stats = await org_service.get_organization_stats(org_id)
        return OrganizationStatsResponse(**stats)

    except OrganizationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization {org_id} not found",
        )


# -------------------------------------------------------------------------
# Helper Functions
# -------------------------------------------------------------------------


def _org_to_response(org) -> OrganizationResponse:
    """Convert Organization model to OrganizationResponse schema."""
    return OrganizationResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        description=org.description,
        settings=org.settings or {},
        subscription_tier=org.subscription_tier or "free",
        max_users=org.max_users if org.max_users is not None else -1,
        is_active=org.is_active,
        created_at=org.created_at.isoformat() if org.created_at else "",
        updated_at=org.updated_at.isoformat() if org.updated_at else "",
    )
