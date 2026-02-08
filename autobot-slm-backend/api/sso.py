# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SSO Provider Management API

Admin endpoints for managing SSO provider configurations.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from services.auth import require_admin
from sqlalchemy.ext.asyncio import AsyncSession
from user_management.database import get_slm_session
from user_management.schemas.sso import (
    SSOProviderCreate,
    SSOProviderListResponse,
    SSOProviderResponse,
    SSOProviderUpdate,
    SSOTestResponse,
)
from user_management.services.base_service import TenantContext
from user_management.services.sso_service import (
    SSOProviderNotFoundError,
    SSOService,
    SSOServiceError,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sso-providers", tags=["sso-providers"])


async def get_slm_db():
    """Dependency for SLM database session."""
    async with get_slm_session() as session:
        yield session


@router.get("", response_model=SSOProviderListResponse)
async def list_providers(
    org_id: uuid.UUID | None = None,
    active_only: bool = False,
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_slm_db),
) -> SSOProviderListResponse:
    """List SSO providers."""
    logger.info(
        "Listing SSO providers (org_id=%s, active_only=%s)", org_id, active_only
    )
    context = TenantContext(is_platform_admin=True)
    sso_service = SSOService(db, context)

    providers, total = await sso_service.list_providers(
        org_id=org_id, active_only=active_only
    )
    return SSOProviderListResponse(
        providers=[SSOProviderResponse.model_validate(p) for p in providers],
        total=total,
    )


@router.post(
    "", response_model=SSOProviderResponse, status_code=status.HTTP_201_CREATED
)
async def create_provider(
    provider_data: SSOProviderCreate,
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_slm_db),
) -> SSOProviderResponse:
    """Create a new SSO provider."""
    logger.info(
        "Creating SSO provider: %s (%s)",
        provider_data.name,
        provider_data.provider_type,
    )
    context = TenantContext(is_platform_admin=True)
    sso_service = SSOService(db, context)

    try:
        provider = await sso_service.create_provider(provider_data)
        return SSOProviderResponse.model_validate(provider)
    except Exception as e:
        logger.error("Failed to create SSO provider: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.get("/{provider_id}", response_model=SSOProviderResponse)
async def get_provider(
    provider_id: uuid.UUID,
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_slm_db),
) -> SSOProviderResponse:
    """Get SSO provider by ID."""
    context = TenantContext(is_platform_admin=True)
    sso_service = SSOService(db, context)

    try:
        provider = await sso_service.get_provider(provider_id)
        return SSOProviderResponse.model_validate(provider)
    except SSOProviderNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e


@router.patch("/{provider_id}", response_model=SSOProviderResponse)
async def update_provider(
    provider_id: uuid.UUID,
    updates: SSOProviderUpdate,
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_slm_db),
) -> SSOProviderResponse:
    """Update SSO provider."""
    logger.info("Updating SSO provider: %s", provider_id)
    context = TenantContext(is_platform_admin=True)
    sso_service = SSOService(db, context)

    try:
        provider = await sso_service.update_provider(provider_id, updates)
        return SSOProviderResponse.model_validate(provider)
    except SSOProviderNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.error("Failed to update SSO provider: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.delete("/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider(
    provider_id: uuid.UUID,
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_slm_db),
) -> None:
    """Delete SSO provider."""
    logger.info("Deleting SSO provider: %s", provider_id)
    context = TenantContext(is_platform_admin=True)
    sso_service = SSOService(db, context)

    try:
        await sso_service.delete_provider(provider_id)
    except SSOProviderNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e


@router.get("/{provider_id}/test", response_model=SSOTestResponse)
async def test_provider(
    provider_id: uuid.UUID,
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_slm_db),
) -> SSOTestResponse:
    """Test SSO provider connection."""
    logger.info("Testing SSO provider: %s", provider_id)
    context = TenantContext(is_platform_admin=True)
    sso_service = SSOService(db, context)

    try:
        result = await sso_service.test_provider_connection(provider_id)
        return SSOTestResponse(**result)
    except SSOProviderNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e
    except SSOServiceError as e:
        logger.error("SSO provider test failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
