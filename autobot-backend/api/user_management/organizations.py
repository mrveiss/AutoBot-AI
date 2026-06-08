# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Organizations API Endpoints

REST API for organization (tenant) management operations.
Used in multi_company and provider deployment modes.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.schemas_agent import (
    OrganizationCreate,
    OrganizationCreatedResponse,
    OrganizationDeletedResponse,
    OrganizationListResponse,
    OrganizationResponse,
    OrganizationStatsResponse,
    OrganizationUpdate,
)
from api.user_management.dependencies import (
    get_organization_service,
    require_platform_admin,
    require_user_management_enabled,
)
from autobot_shared.logging_manager import get_logger
from autobot_shared.models.pagination import PaginationParams
from user_management.services import OrganizationService
from user_management.services.organization_service import (
    DuplicateOrganizationError,
    OrganizationNotFoundError,
)

router = APIRouter(prefix="/organizations", tags=["Organizations"])
logger = get_logger(__name__)


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
    pagination: PaginationParams = Depends(),
    search: str | None = Query(None, description="Search by name or slug"),
    include_inactive: bool = Query(False, description="Include inactive organizations"),
    org_service: OrganizationService = Depends(get_organization_service),
):
    """List organizations with pagination."""
    orgs, total = await org_service.list_organizations(
        limit=pagination.limit,
        offset=pagination.offset,
        search=search,
        include_inactive=include_inactive,
    )

    return OrganizationListResponse(
        organizations=[_org_to_response(org) for org in orgs],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
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

    except DuplicateOrganizationError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Internal server error",
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
