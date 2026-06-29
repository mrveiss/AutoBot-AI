# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
User Management API Dependencies

FastAPI dependencies for user management endpoints.
"""

import uuid
from typing import AsyncGenerator, Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth_middleware import get_auth_middleware
from user_management.database import get_async_session
from user_management.services import (
    OrganizationService,
    TeamService,
    TenantContext,
    UserService,
)


async def get_db_session() -> AsyncSession:
    """
    Get database session dependency.

    PostgreSQL is always required (#10636), so this always yields a session.
    """
    async for session in get_async_session():
        yield session


async def get_optional_db_session() -> AsyncGenerator[Optional[AsyncSession], None]:
    """Get a database session.

    Retained as a distinct dependency (yielding ``Optional[AsyncSession]``) for
    endpoints that defensively guard their DB operations with
    ``if session is not None``.  PostgreSQL is always enabled (#10636), so a
    session is always yielded.
    """
    async for session in get_async_session():
        yield session


def get_current_user(request: Request) -> dict:
    """
    Get current authenticated user from request.

    Returns user data dict from auth middleware.
    """
    user_data = get_auth_middleware().get_user_from_request(request)
    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return user_data


def get_current_user_id(
    current_user: dict = Depends(get_current_user),
) -> uuid.UUID:
    """Resolve the authenticated user's UUID id.

    GH#9037: per-user resources (e.g. provider credentials) key on the user's
    UUID. Real authenticated users carry an ``id``/``user_id``/``sub`` claim;
    service/internal principals do not, so they are rejected here.
    """
    raw = current_user.get("id") or current_user.get("user_id") or current_user.get("sub")
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User identity required",
        )
    try:
        return uuid.UUID(str(raw))
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User identity is not a valid id",
        ) from exc


def get_tenant_context(
    request: Request,
    current_user: dict = Depends(get_current_user),
) -> TenantContext:
    """
    Build tenant context from current request and user.

    Extracts org_id and user_id from JWT claims or session.
    """
    # Extract org_id from JWT claims if present
    org_id = None
    user_id = None
    is_platform_admin = False

    # Check for org_id in user data (from JWT or session)
    if "org_id" in current_user and current_user["org_id"]:
        try:
            org_id = uuid.UUID(current_user["org_id"])
        except (ValueError, TypeError):
            pass

    if "user_id" in current_user and current_user["user_id"]:
        try:
            user_id = uuid.UUID(current_user["user_id"])
        except (ValueError, TypeError):
            pass

    # Check for platform admin flag
    is_platform_admin = current_user.get("is_platform_admin", False)

    # For backward compatibility, check role
    if current_user.get("role") == "admin":
        is_platform_admin = True

    return TenantContext(
        org_id=org_id,
        user_id=user_id,
        is_platform_admin=is_platform_admin,
    )


def require_user_management_enabled():
    """
    Dependency that ensures user management is enabled.

    AutoBot always runs full, Postgres-backed user management (#10636), so this
    gate always passes.  Retained as a dependency hook for the user-management
    routers.
    """
    return None


def require_org_context(
    context: TenantContext = Depends(get_tenant_context),
) -> TenantContext:
    """
    Dependency that requires organization context.

    Raises HTTPException if no org context is available.
    """
    if not context.org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Organization context required",
        )
    return context


def require_platform_admin(
    context: TenantContext = Depends(get_tenant_context),
) -> TenantContext:
    """
    Dependency that requires platform admin privileges.

    Raises HTTPException if user is not a platform admin.
    """
    if not context.is_platform_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform admin privileges required",
        )
    return context


async def get_user_service(
    session: AsyncSession = Depends(get_db_session),
    context: TenantContext = Depends(get_tenant_context),
) -> UserService:
    """Get UserService with session and context."""
    return UserService(session, context)


async def get_team_service(
    session: AsyncSession = Depends(get_db_session),
    context: TenantContext = Depends(get_tenant_context),
) -> TeamService:
    """Get TeamService with session and context."""
    return TeamService(session, context)


async def get_organization_service(
    session: AsyncSession = Depends(get_db_session),
    context: TenantContext = Depends(get_tenant_context),
) -> OrganizationService:
    """Get OrganizationService with session and context."""
    return OrganizationService(session, context)
