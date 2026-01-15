# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Authentication API Routes
"""

import logging

from typing_extensions import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from models.schemas import TokenRequest, TokenResponse, UserCreate, UserResponse
from services.auth import auth_service, get_current_user, require_admin
from services.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    request: TokenRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """Authenticate and get access token."""
    user = await auth_service.authenticate_user(db, request.username, request.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    logger.info("User logged in: %s", user.username)
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
