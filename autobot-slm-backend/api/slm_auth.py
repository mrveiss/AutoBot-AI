# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Authentication API

Handles login/logout for SLM admin users using the local database.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from services.auth import auth_service, get_current_user
from sqlalchemy.ext.asyncio import AsyncSession
from user_management.database import get_slm_session
from user_management.schemas.user import UserLogin
from user_management.services import TenantContext, UserService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/slm-auth", tags=["slm-auth"])


async def get_slm_db():
    """Dependency for SLM database session."""
    async with get_slm_session() as session:
        yield session


@router.post("/login")
async def login(
    request: UserLogin,
    db: Annotated[AsyncSession, Depends(get_slm_db)],
) -> dict:
    """Authenticate SLM admin user and return JWT token."""
    context = TenantContext(is_platform_admin=True)
    user_service = UserService(db, context)

    user = await user_service.authenticate(
        username_or_email=request.username_or_email,
        password=request.password,
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    logger.info("SLM admin logged in: %s", user.username)

    # Use existing auth service to create token
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
