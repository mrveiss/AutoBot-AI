# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
User Management API Dependencies

FastAPI dependencies for user management endpoints.
"""

import uuid

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth_middleware import auth_middleware
from src.user_management.config import DeploymentMode, get_deployment_config
from src.user_management.database import get_async_session
from src.user_management.services import (
    OrganizationService,
    TeamService,
    TenantContext,
    UserService,
)


async def get_db_session() -> AsyncSession:
    """
    Get database session dependency.

    Raises HTTPException if PostgreSQL is not enabled.
    """
    config = get_deployment_config()

    if not config.postgres_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"User management is not available in {config.mode.value} mode",
        )

    async for session in get_async_session():
        yield session


def get_current_user(request: Request) -> dict:
    """
    Get current authenticated user from request.

    Returns user data dict from auth middleware.
    In single_user mode, returns a default admin user (auth bypassed).
    """
    config = get_deployment_config()

    # In single_user mode, authentication is bypassed - return default admin
    if config.mode == DeploymentMode.SINGLE_USER:
        return {
            "username": "admin",
            "email": "admin@autobot.local",
            "role": "admin",
            "is_platform_admin": True,
            "auth_disabled": True,
        }

    user_data = auth_middleware.get_user_from_request(request)
    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return user_data


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

    Raises HTTPException if not in appropriate deployment mode.
    """
    config = get_deployment_config()

    if config.mode == DeploymentMode.SINGLE_USER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User management is disabled in single_user mode",
        )


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
