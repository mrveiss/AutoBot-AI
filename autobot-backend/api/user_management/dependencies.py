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
from autobot_shared.auth.permissions import Permission, is_admin_role, role_has_permission
from user_management.database import get_async_session
from user_management.services import (
    OrganizationService,
    TeamService,
    TenantContext,
    UserService,
)

logger = logging.getLogger(__name__)

# Refusal details, shared by each gate and its claims-only pre-check below so the
# two can never drift: #15805 requires the earlier refusal to be byte-identical to
# the one it replaces, or "refused sooner" would read to a caller as "refused for a
# different reason".
_PLATFORM_ADMIN_DENIED = "Platform admin privileges required"
_REPORTING_LINE_WRITE_DENIED = "admin.reporting_line.write permission required"


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


def _is_platform_admin_claim(current_user: dict) -> bool:
    """Platform-admin status exactly as the caller's JWT attests it (#15805).

    ``TenantContext.is_platform_admin`` is derived from this and from nothing
    in the database, which is what makes ``require_platform_admin`` decidable
    before a session is acquired. Any future admin signal that needs a query
    belongs in ``get_tenant_context``, not here -- adding one here silently
    re-couples the pre-check to the pool.
    """
    if bool(current_user.get("is_platform_admin", False)):
        return True
    return is_admin_role(current_user.get("role"))


def _holds_reporting_line_write(current_user: dict) -> bool:
    """Whether the caller holds ``admin.reporting_line.write`` (#15765, #15805).

    ``role_has_permission`` answers from ``ROLE_PERMISSIONS`` alone, so this is
    a pure function of the JWT role claim -- no session, and no reporting-line
    data, which is the escalation guarantee #15765 established.
    """
    return role_has_permission(current_user.get("role"), Permission.ADMIN_REPORTING_LINE_WRITE.value)


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

    # Determine platform-admin status. Shared with ``require_platform_admin_claim``
    # so the pre-check and the context can never disagree about who is an admin.
    is_platform_admin = _is_platform_admin_claim(current_user)

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


def user_management_route_marker():
    """No-op route marker — performs no authentication or authorization check.

    Formerly named ``require_user_management_enabled``: AutoBot ran a
    ``single_user`` deployment mode that disabled user management entirely and
    this dependency returned a 503 while it was active. #10636 retired that
    mode outright (AutoBot always runs full, Postgres-backed user management),
    which left the function permanently passing — but its old name still read
    as a live gate to anyone tracing a route's authorization posture (#15737).

    It gates nothing and never has raised since #10636. Renamed rather than
    deleted: every ``/user-management/*`` route still carries it in its
    ``dependencies=[...]`` list as a grep-able marker of module membership, and
    removing it as part of a legibility-only change would touch every route's
    behaviour for no gain.

    Real authentication for these routes is enforced elsewhere — see
    ``docs/developer/AUTHENTICATION_RBAC.md``'s "Per-Route Enforcement for
    User-Management Routes" section, or trace ``get_current_user`` (this
    module, line 53) through ``get_tenant_context`` (line 157) and
    ``get_user_service``/``get_team_service``/``get_organization_service``
    (lines 306-326), which every route below actually depends on.
    """
    return None


async def require_org_context(
    context: TenantContext = Depends(get_tenant_context),
) -> TenantContext:
    """
    Dependency that requires organization context.

    Raises HTTPException if no org context is available (#12215): the detail
    message names the ``X-Organization-Id`` header explicitly, since routes
    whose path has no ``company_id``/``id`` param (see
    ``_extract_request_org_id``) cannot resolve org context from the URL and
    the caller's JWT carries no ``org_id`` claim. See
    ``docs/llc/tenant-context.md`` for the full resolution contract.

    Unlike ``require_platform_admin`` and ``require_reporting_line_write``, this
    gate cannot be pre-checked from the JWT (#15805): its decision IS the
    outcome of tenant resolution, so the session ``get_tenant_context`` may
    acquire is work this refusal genuinely depends on rather than work spent
    ahead of it.
    """
    if not context.org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Organization context required — supply an 'X-Organization-Id' "
                "request header (or a company_id path/query param, where the "
                "route has one). See docs/llc/tenant-context.md."
            ),
        )
    return context


async def require_platform_admin_claim(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Refuse a non-admin from the JWT alone, before any session is acquired (#15805).

    Declared ahead of ``get_tenant_context`` in
    ``_tenant_context_for_platform_admin`` so FastAPI never reaches the session
    dependency for a caller this refuses.
    """
    if not _is_platform_admin_claim(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_PLATFORM_ADMIN_DENIED,
        )
    return current_user


async def _tenant_context_for_platform_admin(
    _granted: dict = Depends(require_platform_admin_claim),
    context: TenantContext = Depends(get_tenant_context),
) -> TenantContext:
    """Tenant context, resolved only once the platform-admin claim has passed.

    The parameter ORDER is the mechanism, not decoration: FastAPI's
    ``solve_dependencies`` walks ``dependant.dependencies`` in declaration order
    and an ``HTTPException`` from one aborts the walk, so ``_granted`` failing
    means ``get_tenant_context`` -- and therefore ``get_db_session`` -- is never
    solved. Reordering these two parameters silently restores #15805; the
    behavioural tests in ``dependencies_test.py`` count session acquisitions
    rather than inspect this signature, so they catch that.
    """
    return context


async def require_platform_admin(
    context: TenantContext = Depends(_tenant_context_for_platform_admin),
) -> TenantContext:
    """
    Dependency that requires platform admin privileges.

    Raises HTTPException if user is not a platform admin.

    The check below is retained rather than delegated to
    ``require_platform_admin_claim``: ``api/user_management/password_change.py``
    calls this function directly with a ``TenantContext`` it already holds, so
    the context-based check is the one that gate depends on. Under FastAPI the
    claim pre-check has already refused the same callers one hop earlier.
    """
    if not context.is_platform_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_PLATFORM_ADMIN_DENIED,
        )
    return context


async def require_reporting_line_write_grant(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Refuse a caller without the grant from the JWT alone (#15805).

    The decision needs identity and nothing else -- see
    ``_holds_reporting_line_write`` -- so it does not have to wait for tenant
    resolution, which does need a session.
    """
    if not _holds_reporting_line_write(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_REPORTING_LINE_WRITE_DENIED,
        )
    return current_user


async def _tenant_context_for_reporting_line_write(
    _granted: dict = Depends(require_reporting_line_write_grant),
    context: TenantContext = Depends(get_tenant_context),
) -> TenantContext:
    """Tenant context, resolved only once the reporting-line grant has passed.

    Same ordering contract as ``_tenant_context_for_platform_admin`` -- see its
    docstring for why the parameter order is load-bearing.
    """
    return context


async def require_reporting_line_write(
    context: TenantContext = Depends(_tenant_context_for_reporting_line_write),
    current_user: dict = Depends(get_current_user),
) -> TenantContext:
    """
    Dependency that requires the ``admin.reporting_line.write`` permission (#15765).

    Re-parenting a reporting line is an authority-granting operation, not
    ordinary data editing: once the hierarchy gates card edits (#15765, parent
    #13935), the new manager gains edit rights over the moved subject and, at
    depth two, over everyone that manager manages. The check below is therefore
    on the caller's *granted* permission only -- it never inspects reporting-line
    data, so a caller cannot acquire it by becoming someone's manager, which
    would otherwise let restructuring self-grant further authority.

    Raises HTTPException if the caller does not hold the permission.

    The check is duplicated in ``require_reporting_line_write_grant``, which
    ``context`` resolves through, so that the refusal happens before a session
    is acquired (#15805). This one is not redundant: it is what answers a direct
    call with a ``TenantContext`` and a ``current_user`` dict, which the unit
    tests and any non-FastAPI caller make. Both read the same predicate.
    """
    if not _holds_reporting_line_write(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_REPORTING_LINE_WRITE_DENIED,
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
