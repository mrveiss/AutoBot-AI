# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Authentication API

Handles login/logout for SLM admin users using the local database.
"""

import logging
from datetime import timedelta
from typing import Annotated, Optional

from api.security import create_audit_log
from fastapi import APIRouter, Depends, HTTPException, Request, status
from services.auth import auth_service, get_current_user
from services.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from user_management.database import get_slm_session
from user_management.models.user import User
from user_management.schemas.user import UserLogin
from user_management.services import TenantContext, UserService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/slm-auth", tags=["slm-auth"])


async def get_slm_db():
    """Dependency for SLM database session."""
    async with get_slm_session() as session:
        yield session


def _get_client_ip(http_request: Request) -> Optional[str]:
    """Extract client IP from request, respecting X-Forwarded-For."""
    forwarded_for = http_request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return http_request.client.host if http_request.client else None


@router.post("/login")
async def login(
    http_request: Request,
    request: UserLogin,
    db: Annotated[AsyncSession, Depends(get_slm_db)],
    audit_db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Authenticate SLM admin user and return JWT token."""
    context = TenantContext(is_platform_admin=True)
    user_service = UserService(db, context)
    client_ip = _get_client_ip(http_request)

    user = await user_service.authenticate(
        username_or_email=request.username_or_email,
        password=request.password,
    )

    if not user:
        # Issue #998: Record failed login attempt in audit log
        await create_audit_log(
            audit_db,
            category="authentication",
            action="login_failed",
            username=request.username_or_email,
            ip_address=client_ip,
            resource_type="session",
            description=f"Failed login attempt for '{request.username_or_email}'",
            request_method="POST",
            request_path="/api/slm-auth/login",
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

    # Check if MFA is enabled for this user
    if user.mfa_enabled:
        return _create_mfa_challenge(user)

    # Issue #998: Record successful login in audit log
    await create_audit_log(
        audit_db,
        category="authentication",
        action="login_success",
        user_id=str(user.id),
        username=user.username,
        ip_address=client_ip,
        resource_type="session",
        description=f"SLM admin '{user.username}' logged in successfully",
        request_method="POST",
        request_path="/api/slm-auth/login",
        response_status=200,
        success=True,
    )
    await audit_db.commit()

    logger.info("SLM admin logged in: %s", user.username)
    return await auth_service.create_token_response(user)


@router.get("/me")
async def get_current_user_info(
    current_user: Annotated[dict, Depends(get_current_user)],
) -> dict:
    """Get current SLM admin user information."""
    return {
        "username": current_user.get("sub"),
        "is_admin": current_user.get("admin", False),
        "user_type": "slm_admin",
    }


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    current_user: Annotated[dict, Depends(get_current_user)],
) -> None:
    """Logout (client-side token invalidation)."""
    logger.info("SLM admin logged out: %s", current_user.get("sub"))


def _create_mfa_challenge(user: User) -> dict:
    """Create MFA challenge response with temporary token.

    Helper for login endpoint (Issue #576 Phase 5).

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
