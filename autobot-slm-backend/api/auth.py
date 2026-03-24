# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Authentication API Routes

Canonical login endpoint for all SLM clients. Supports username or email
login, MFA challenges (Issue #576 Phase 5), and audit logging (Issue #998).
Consolidated from legacy auth.py and slm_auth.py in Issue #1922.
"""

import ipaddress
import logging
from datetime import timedelta
from typing import Optional

from api.security import create_audit_log
from config import settings
from fastapi import APIRouter, Depends, HTTPException, Request, status
from models.schemas import TokenRequest, TokenResponse, UserCreate, UserResponse
from services.auth import auth_service, get_current_user, get_slm_db, require_admin
from services.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated
from user_management.models.user import User
from user_management.services import TenantContext, UserService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


def _normalize_ip(ip_str: str) -> str:
    """Normalize IP, mapping ::ffff:x.x.x.x to x.x.x.x (#2239)."""
    try:
        addr = ipaddress.ip_address(ip_str)
        if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
            return str(addr.ipv4_mapped)
        return str(addr)
    except ValueError:
        return ip_str


def _get_client_ip(http_request: Request) -> Optional[str]:
    """Extract the real client IP from the request.

    X-Forwarded-For is only trusted when the direct TCP peer is a known
    reverse proxy (Issue #2239).  An attacker connecting directly cannot
    spoof their IP via that header.
    """
    direct_ip = http_request.client.host if http_request.client else None
    forwarded_for = http_request.headers.get("X-Forwarded-For")
    if forwarded_for and direct_ip:
        normalized = _normalize_ip(direct_ip)
        trusted = {_normalize_ip(p) for p in settings.trusted_proxies}
        if normalized in trusted:
            candidate = forwarded_for.split(",")[0].strip()
            if candidate:
                return candidate
    return direct_ip


def _create_mfa_challenge(user: User) -> dict:
    """Create MFA challenge response with temporary token (Issue #576 Phase 5).

    Args:
        user: User requiring MFA verification

    Returns:
        Dict with requires_mfa flag and temporary token
    """
    temp_token_data = {
        "sub": user.username,
        "mfa_pending": True,
        "user_id": str(user.id),
        "admin": user.is_platform_admin,
    }
    temp_token = auth_service.create_access_token(
        data=temp_token_data,
        expires_delta=timedelta(minutes=5),
    )
    logger.info("MFA challenge issued for user: %s", user.username)
    return {"requires_mfa": True, "temp_token": temp_token}


@router.post("/login")
async def login(
    http_request: Request,
    body: TokenRequest,
    db: Annotated[AsyncSession, Depends(get_slm_db)],
    audit_db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Authenticate and get access token.

    Accepts username or email. Returns JWT token or MFA challenge.
    Records audit log entry (Issue #998). Consolidated in Issue #1922.
    """
    client_ip = _get_client_ip(http_request)
    context = TenantContext(is_platform_admin=True)
    user_service = UserService(db, context)

    user = await user_service.authenticate(
        username_or_email=body.username,
        password=body.password,
    )

    if not user:
        await create_audit_log(
            audit_db,
            category="authentication",
            action="login_failed",
            username=body.username,
            ip_address=client_ip,
            resource_type="session",
            description=f"Failed login attempt for '{body.username}'",
            request_method="POST",
            request_path="/api/auth/login",
            response_status=401,
            success=False,
            error_message="Invalid username or password",
        )
        await audit_db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.mfa_enabled:
        await create_audit_log(
            audit_db,
            category="authentication",
            action="mfa_challenge_issued",
            user_id=str(user.id),
            username=user.username,
            ip_address=client_ip,
            resource_type="session",
            description=f"MFA challenge issued for '{user.username}'",
            request_method="POST",
            request_path="/api/auth/login",
            response_status=200,
            success=True,
        )
        await audit_db.commit()
        return _create_mfa_challenge(user)

    logger.info("User logged in: %s", user.username)
    await create_audit_log(
        audit_db,
        category="authentication",
        action="login_success",
        user_id=str(user.id),
        username=user.username,
        ip_address=client_ip,
        resource_type="session",
        description=f"User '{user.username}' logged in successfully",
        request_method="POST",
        request_path="/api/auth/login",
        response_status=200,
        success=True,
    )
    await audit_db.commit()
    return await auth_service.create_token_response(user)


@router.post("/users", response_model=UserResponse)
async def create_user(
    user_data: UserCreate,
    db: Annotated[AsyncSession, Depends(get_slm_db)],
    _: Annotated[dict, Depends(require_admin)],
) -> UserResponse:
    """Create a new user (admin only)."""
    return await auth_service.create_user(db, user_data)


@router.get("/me", response_model=dict)
async def get_current_user_info(
    current_user: Annotated[dict, Depends(get_current_user)],
) -> dict:
    """Get current user information."""
    return {
        "username": current_user.get("sub"),
        "is_admin": current_user.get("admin", False),
        "user_type": "slm_admin",
    }


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_slm_db)],
) -> TokenResponse:
    """Refresh access token."""
    username = current_user.get("sub")
    user = await auth_service.get_user_by_username(db, username)

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    return await auth_service.create_token_response(user)
