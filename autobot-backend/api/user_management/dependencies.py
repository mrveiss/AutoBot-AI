# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
User Management API Dependencies

FastAPI dependencies for user management endpoints.
"""

import logging
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

logger = logging.getLogger(__name__)


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


def _parse_uuid_safe(value: Optional[str]) -> Optional[uuid.UUID]:
    """Parse a string as UUID, returning None on failure (no error raised)."""
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


def _extract_request_org_id(request: Request) -> Optional[uuid.UUID]:
    """Extract org_id from the request using precedence rules (#10750 A5).

    Precedence (first non-None valid UUID wins):
      1. ``X-Organization-Id`` request header
      2. ``company_id`` path parameter (e.g. /companies/{company_id}/...)
      3. ``company_id`` query parameter (?company_id=...)

    Returns None if no parseable org UUID is found in any location.
    """
    # 1. Header takes highest priority
    header_val = request.headers.get("X-Organization-Id")
    parsed = _parse_uuid_safe(header_val)
    if parsed is not None:
        return parsed

    # 2. Path param (present on routes like /companies/{company_id}/portfolios)
    path_val = request.path_params.get("company_id") or request.path_params.get("id")
    parsed = _parse_uuid_safe(path_val)
    if parsed is not None:
        return parsed

    # 3. Query param (?company_id=...)
    query_val = request.query_params.get("company_id")
    parsed = _parse_uuid_safe(query_val)
    if parsed is not None:
        return parsed

    return None


async def _check_org_membership(
    session: AsyncSession,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
) -> bool:
    """Return True if *user_id* is a member of *org_id* (LLC company).

    Uses a lightweight SELECT EXISTS query against ``llc_company_memberships``
    rather than constructing the full MembershipService, to avoid DI overhead
    and keep this dependency lean (#10750 A5).
    """
    from sqlalchemy import select  # local import avoids module-level circularity

    from llc.models.membership import LLCCompanyMembership

    result = await session.execute(
        select(LLCCompanyMembership.id).where(
            LLCCompanyMembership.company_id == org_id,
            LLCCompanyMembership.user_id == user_id,
        )
    )
    return result.first() is not None


async def get_tenant_context(
    request: Request,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> TenantContext:
    """Build tenant context from current request and user (#10750 A5).

    Resolution precedence for ``org_id``:
      1. ``X-Organization-Id`` request header (frontend sends the selected
         company id here).
      2. ``company_id`` path param or query param (many LLC routes pass it
         directly, e.g. ``/companies/{company_id}/portfolios``).
      3. ``org_id`` JWT claim (preserved for backward compatibility).

    Security — org spoofing prevention:
      - Platform admins (``role == "admin"`` or ``is_platform_admin == True``)
        may supply any org_id without membership verification.
      - All other users: if an org_id is taken from the request (sources 1 or
        2) a membership check against ``llc_company_memberships`` is performed.
        If the user is not a member, HTTP 403 is raised so the caller knows
        exactly why they were rejected (not silently treated as unauthenticated).
      - If the org_id comes only from the JWT claim (source 3) it is accepted
        as-is, mirroring prior behaviour.
    """
    user_id: Optional[uuid.UUID] = None
    is_platform_admin = False

    # Resolve user_id from JWT
    raw_user_id = current_user.get("user_id") or current_user.get("id") or current_user.get("sub")
    if raw_user_id:
        user_id = _parse_uuid_safe(str(raw_user_id))

    # Determine platform-admin status
    is_platform_admin = bool(current_user.get("is_platform_admin", False))
    if current_user.get("role") == "admin":
        is_platform_admin = True

    # --- org_id resolution ---

    # Sources 1 & 2: from the request itself
    request_org_id = _extract_request_org_id(request)

    if request_org_id is not None:
        if is_platform_admin:
            # Platform admins are trusted to access any org
            return TenantContext(
                org_id=request_org_id,
                user_id=user_id,
                is_platform_admin=is_platform_admin,
            )

        # Non-admin: verify membership before accepting the request-supplied org
        if user_id is not None:
            is_member = await _check_org_membership(session, request_org_id, user_id)
            if is_member:
                return TenantContext(
                    org_id=request_org_id,
                    user_id=user_id,
                    is_platform_admin=is_platform_admin,
                )

        # Supplied an org but is not a member (or has no user_id) → 403
        logger.warning(
            "Tenant context: user %s is not a member of org %s (requested via header/path/query)",
            user_id,
            request_org_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of the requested organization",
        )

    # Source 3: JWT claim fallback (existing behaviour, no extra DB check)
    jwt_org_id = _parse_uuid_safe(current_user.get("org_id"))

    return TenantContext(
        org_id=jwt_org_id,
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


async def require_org_context(
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


async def require_platform_admin(
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
