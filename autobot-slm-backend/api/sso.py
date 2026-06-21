# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
SSO Provider Management API

Admin endpoints for managing SSO provider configurations.
"""

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.auth.permissions import Permission
from models.database import AuditLog
from services.auth import require_permission
from services.database import get_db
from user_management.database import get_slm_session
from user_management.schemas.sso import (
    SSOProviderCreate,
    SSOProviderHealthResponse,
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

# Configurable look-back window for the health dashboard (no hard-coded literal).
SSO_HEALTH_WINDOW_DAYS = int(os.getenv("SSO_HEALTH_WINDOW_DAYS", "7"))

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sso-providers", tags=["sso-providers"])


async def get_slm_db():
    """Dependency for SLM database session."""
    async with get_slm_session() as session:
        yield session


async def get_audit_db():
    """Dependency for the audit (main SLM security) database session."""
    async for session in get_db():
        yield session


def _derive_health_status(
    success_count: int,
    failure_count: int,
    last_success_at: datetime | None,
    window_start: datetime,
) -> str:
    """Derive a health_status label from aggregated SSO login counts.

    Returns one of: healthy | warning | error | unknown.
    """
    if success_count == 0 and failure_count == 0:
        return "unknown"
    if failure_count > 0 and success_count == 0:
        return "error"
    if failure_count > 0 and last_success_at and last_success_at >= window_start:
        return "warning"
    return "healthy"


@router.get("", response_model=SSOProviderListResponse)
async def list_providers(
    org_id: uuid.UUID | None = None,
    active_only: bool = False,
    current_user: dict = Depends(require_permission(Permission.SECURITY_MANAGE)),
    db: AsyncSession = Depends(get_slm_db),
) -> SSOProviderListResponse:
    """List SSO providers."""
    logger.info("Listing SSO providers (org_id=%s, active_only=%s)", org_id, active_only)
    context = TenantContext(is_platform_admin=True)
    sso_service = SSOService(db, context)

    providers, total = await sso_service.list_providers(org_id=org_id, active_only=active_only)
    return SSOProviderListResponse(
        providers=[SSOProviderResponse.model_validate(p) for p in providers],
        total=total,
    )


@router.post("", response_model=SSOProviderResponse, status_code=status.HTTP_201_CREATED)
async def create_provider(
    provider_data: SSOProviderCreate,
    current_user: dict = Depends(require_permission(Permission.SECURITY_MANAGE)),
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
            detail="Internal server error",
        ) from e


@router.get("/{provider_id}", response_model=SSOProviderResponse)
async def get_provider(
    provider_id: uuid.UUID,
    current_user: dict = Depends(require_permission(Permission.SECURITY_MANAGE)),
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
            detail="Internal server error",
        ) from e


@router.patch("/{provider_id}", response_model=SSOProviderResponse)
async def update_provider(
    provider_id: uuid.UUID,
    updates: SSOProviderUpdate,
    current_user: dict = Depends(require_permission(Permission.SECURITY_MANAGE)),
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
            detail="Internal server error",
        ) from e
    except Exception as e:
        logger.error("Failed to update SSO provider: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Internal server error",
        ) from e


@router.delete("/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider(
    provider_id: uuid.UUID,
    current_user: dict = Depends(require_permission(Permission.SECURITY_MANAGE)),
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
            detail="Internal server error",
        ) from e


@router.get("/{provider_id}/test", response_model=SSOTestResponse)
async def test_provider(
    provider_id: uuid.UUID,
    current_user: dict = Depends(require_permission(Permission.SECURITY_MANAGE)),
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
            detail="Internal server error",
        ) from e
    except SSOServiceError as e:
        logger.error("SSO provider test failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Internal server error",
        ) from e


@router.get("/provider-templates/{provider_type}", response_model=dict)
async def get_provider_template(
    provider_type: str,
    domain: str = Query("", description="Domain or tenant ID for endpoint URL construction"),
    current_user: dict = Depends(require_permission(Permission.SECURITY_MANAGE)),
) -> dict:
    """Get pre-filled endpoint template for a known SSO provider type."""
    return SSOService.get_provider_endpoint_template(provider_type, domain)


@router.get("/health", response_model=list[SSOProviderHealthResponse])
async def get_providers_health(
    current_user: dict = Depends(require_permission(Permission.SECURITY_MANAGE)),
    db: AsyncSession = Depends(get_slm_db),
    audit_db: AsyncSession = Depends(get_audit_db),
) -> list[SSOProviderHealthResponse]:
    """Return per-provider health summary (failed-auth counts + last-success).

    Aggregates audit_logs rows with category='sso', action='login' over the
    past SSO_HEALTH_WINDOW_DAYS days. Guarded by SECURITY_MANAGE permission.
    """
    context = TenantContext(is_platform_admin=True)
    sso_service = SSOService(db, context)
    providers, _ = await sso_service.list_providers()

    window_start = datetime.now(timezone.utc) - timedelta(days=SSO_HEALTH_WINDOW_DAYS)

    # Single grouped aggregation over the window
    agg_result = await audit_db.execute(
        select(
            AuditLog.resource_id,
            func.count(AuditLog.id).filter(AuditLog.success.is_(True)).label("success_count"),
            func.count(AuditLog.id).filter(AuditLog.success.is_(False)).label("failure_count"),
            func.max(AuditLog.timestamp).filter(AuditLog.success.is_(True)).label("last_success_at"),
        )
        .where(AuditLog.category == "sso")
        .where(AuditLog.action == "login")
        .where(AuditLog.timestamp >= window_start)
        .group_by(AuditLog.resource_id)
    )
    rows = {row.resource_id: row for row in agg_result.all()}

    results: list[SSOProviderHealthResponse] = []
    for provider in providers:
        pid_str = str(provider.id)
        row = rows.get(pid_str)
        success_count = int(row.success_count) if row else 0
        failure_count = int(row.failure_count) if row else 0
        last_success_at = row.last_success_at if row else None
        health_status = _derive_health_status(success_count, failure_count, last_success_at, window_start)
        results.append(
            SSOProviderHealthResponse(
                provider_id=provider.id,
                name=provider.name,
                success_count=success_count,
                failure_count=failure_count,
                last_success_at=last_success_at,
                health_status=health_status,
            )
        )

    return results
