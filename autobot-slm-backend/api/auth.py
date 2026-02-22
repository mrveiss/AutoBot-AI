# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Authentication API Routes
"""

import logging

from api.security import create_audit_log
from fastapi import APIRouter, Depends, HTTPException, Request, status
from models.schemas import TokenRequest, TokenResponse, UserCreate, UserResponse
from services.auth import auth_service, get_current_user, require_admin
from services.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    http_request: Request,
    body: TokenRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """Authenticate and get access token. Records audit log entry (Issue #998)."""
    client_ip = http_request.client.host if http_request.client else None
    user = await auth_service.authenticate_user(db, body.username, body.password)

    if not user:
        await create_audit_log(
            db,
            category="auth",
            action="login",
            username=body.username,
            ip_address=client_ip,
            request_method="POST",
            request_path="/api/auth/login",
            response_status=401,
            success=False,
            error_message="Invalid username or password",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    logger.info("User logged in: %s", user.username)
    await create_audit_log(
        db,
        category="auth",
        action="login",
        user_id=str(user.id),
        username=user.username,
        ip_address=client_ip,
        request_method="POST",
        request_path="/api/auth/login",
        response_status=200,
        success=True,
    )
    return await auth_service.create_token_response(user)


@router.post("/users", response_model=UserResponse)
async def create_user(
    user_data: UserCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
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
    }


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
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
