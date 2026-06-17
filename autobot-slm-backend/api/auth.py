# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
SLM Authentication API Routes

Canonical login endpoint for all SLM clients. Supports username or email
login, MFA challenges (Issue #576 Phase 5), and audit logging (Issue #998).
Consolidated from legacy auth.py and slm_auth.py in Issue #1922.
"""

import logging
import time
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

from api.security import create_audit_log
from autobot_shared.auth.jwt_core import _peek_alg, decode_jwt_no_verify_exp
from autobot_shared.auth.permissions import Permission
from autobot_shared.proxy_utils import get_client_ip
from config import settings
from models.schemas import (
    MfaChallengeResponse,
    TokenRequest,
    TokenResponse,
    UserCreate,
    UserResponse,
)
from services.auth import auth_service, get_current_user, get_slm_db, require_permission
from services.database import get_db
from services.token_denylist import revoke_jti
from user_management.models.sso import UserSSOLink
from user_management.models.user import User
from user_management.services import TenantContext, UserService

_bearer = HTTPBearer()

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


async def _get_raw_token(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
) -> str:
    """Extract the raw bearer token string (for logout jti revocation)."""
    return credentials.credentials


def _create_mfa_challenge(user: User) -> MfaChallengeResponse:
    """Create MFA challenge response with temporary token (Issue #576 Phase 5).

    Args:
        user: User requiring MFA verification

    Returns:
        MfaChallengeResponse with temporary token
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
    return MfaChallengeResponse(temp_token=temp_token)


@router.post(
    "/login",
    response_model=TokenResponse | MfaChallengeResponse,
)
async def login(
    http_request: Request,
    body: TokenRequest,
    db: Annotated[AsyncSession, Depends(get_slm_db)],
    audit_db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse | MfaChallengeResponse:
    """Authenticate and get access token.

    Accepts username or email. Returns JWT token or MFA challenge.
    Records audit log entry (Issue #998). Consolidated in Issue #1922.
    """
    client_ip = get_client_ip(http_request, trusted_proxies=settings.trusted_proxies)
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
    _: Annotated[dict, Depends(require_permission(Permission.ADMIN_USERS_WRITE))],
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


def _build_end_session_url(link: "UserSSOLink") -> str | None:
    """Return the IdP end-session URL for *link*, or None if not configured."""
    endpoint = link.provider.config.get("end_session_endpoint") if link and link.provider else None
    if not endpoint:
        return None
    parts = [endpoint]
    post_logout = link.provider.config.get("post_logout_redirect_uri")
    if post_logout:
        parts.append(f"post_logout_redirect_uri={post_logout}")
    id_token = (link.sso_metadata or {}).get("id_token")
    if id_token:
        parts.append(f"id_token_hint={id_token}")
    separator = "&" if "?" in endpoint else "?"
    params = "&".join(parts[1:])
    return f"{endpoint}{separator}{params}" if params else endpoint


async def _get_user_sso_link(db: AsyncSession, username: str) -> "UserSSOLink | None":
    """Return the first active SSO link for *username*, or None."""
    result = await db.execute(
        select(UserSSOLink).join(User, UserSSOLink.user_id == User.id).where(User.username == username).limit(1)
    )
    return result.scalar_one_or_none()


@router.post("/logout")
async def logout(
    http_request: Request,
    current_user: Annotated[dict, Depends(get_current_user)],
    token: Annotated[str, Depends(_get_raw_token)],
    slm_db: Annotated[AsyncSession, Depends(get_slm_db)],
    audit_db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Revoke the presented token and return IdP logout URL if applicable.

    - Denylists the token's ``jti`` in Redis (HS256 tokens only).
    - Queries the user's SSO link for an ``end_session_endpoint``.
    - Returns ``{"logout_url": "<url>"}`` (url may be null when not SSO-linked).
    """
    client_ip = get_client_ip(http_request, trusted_proxies=settings.trusted_proxies)
    username = current_user.get("sub", "unknown")

    # Revoke the jti if this is an HS256 token with a jti claim
    if _peek_alg(token) == "HS256":
        try:
            claims = decode_jwt_no_verify_exp(token, secret=settings.secret_key)
            jti = claims.get("jti")
            exp = claims.get("exp")
            if jti and exp:
                ttl = max(1, int(exp) - int(time.time()))
                await revoke_jti(jti, ttl_seconds=ttl)
        except Exception:
            logger.warning("logout: could not decode token for jti revocation (user=%s)", username)

    # Audit the logout event
    await create_audit_log(
        audit_db,
        category="authentication",
        action="logout",
        username=username,
        ip_address=client_ip,
        resource_type="session",
        description=f"User '{username}' logged out",
        request_method="POST",
        request_path="/api/auth/logout",
        response_status=200,
        success=True,
    )
    await audit_db.commit()

    logger.info("User logged out: %s", username)

    # SSO RP-initiated logout
    link = await _get_user_sso_link(slm_db, username)
    logout_url = _build_end_session_url(link) if link else None
    return {"logout_url": logout_url}


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
