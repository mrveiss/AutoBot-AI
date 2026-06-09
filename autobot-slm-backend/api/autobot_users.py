# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
AutoBot Application User Management API

Manages users in the remote AutoBot database (AUTOBOT_DB_HOST:5432/autobot_users).
These are application users who access AutoBot features (chat, workflows, etc.).
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.auth.permissions import Permission
from services.auth import require_permission
from user_management.database import get_autobot_session
from user_management.schemas.user import (
    PasswordChange,
    UserCreate,
    UserListResponse,
    UserResponse,
    UserUpdate,
)
from user_management.services import TenantContext, UserService
from user_management.services.user_service import UserNotFoundError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/autobot-users", tags=["autobot-users"])


async def get_autobot_db():
    """Dependency for AutoBot database session."""
    async with get_autobot_session() as session:
        yield session


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_autobot_user(
    user_data: UserCreate,
    current_user: dict = Depends(require_permission(Permission.ADMIN_USERS_WRITE)),
    db: AsyncSession = Depends(get_autobot_db),
) -> UserResponse:
    """Create a new AutoBot application user."""
    logger.info("Creating AutoBot user: %s", user_data.username)
    context = TenantContext(is_platform_admin=True)
    user_service = UserService(db, context)

    try:
        user = await user_service.create_user(
            email=user_data.email,
            username=user_data.username,
            password=user_data.password,
            display_name=user_data.display_name,
            role_ids=user_data.role_ids,
        )
        return UserResponse.model_validate(user)
    except Exception as e:
        logger.error("Failed to create AutoBot user: %s", e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Internal server error") from e


@router.get("", response_model=UserListResponse)
async def list_autobot_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: str = Query(None),
    current_user: dict = Depends(require_permission(Permission.ADMIN_USERS_WRITE)),
    db: AsyncSession = Depends(get_autobot_db),
) -> UserListResponse:
    """List AutoBot application users with pagination and search."""
    logger.info("Listing AutoBot users (skip=%d, limit=%d, search=%s)", skip, limit, search)
    context = TenantContext(is_platform_admin=True)
    user_service = UserService(db, context)

    users, total = await user_service.list_users(limit=limit, offset=skip, search=search)
    return UserListResponse(
        users=[UserResponse.model_validate(user) for user in users],
        total=total,
        limit=limit,
        offset=skip,
    )


@router.get("/{user_id}", response_model=UserResponse)
async def get_autobot_user(
    user_id: uuid.UUID,
    current_user: dict = Depends(require_permission(Permission.ADMIN_USERS_WRITE)),
    db: AsyncSession = Depends(get_autobot_db),
) -> UserResponse:
    """Get AutoBot user by ID."""
    context = TenantContext(is_platform_admin=True)
    user_service = UserService(db, context)

    user = await user_service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserResponse.model_validate(user)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_autobot_user(
    user_id: uuid.UUID,
    updates: UserUpdate,
    current_user: dict = Depends(require_permission(Permission.ADMIN_USERS_WRITE)),
    db: AsyncSession = Depends(get_autobot_db),
) -> UserResponse:
    """Update AutoBot user."""
    logger.info("Updating AutoBot user: %s", user_id)
    context = TenantContext(is_platform_admin=True)
    user_service = UserService(db, context)

    try:
        user = await user_service.update_user(
            user_id=user_id,
            email=updates.email,
            username=updates.username,
            display_name=updates.display_name,
            bio=updates.bio,
            avatar_url=updates.avatar_url,
            preferences=updates.preferences,
        )
        return UserResponse.model_validate(user)
    except Exception as e:
        logger.error("Failed to update AutoBot user: %s", e)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Internal server error") from e


@router.post("/{user_id}/change-password", status_code=status.HTTP_200_OK)
async def change_autobot_user_password(
    user_id: uuid.UUID,
    payload: PasswordChange,
    current_user: dict = Depends(require_permission(Permission.ADMIN_USERS_WRITE)),
    db: AsyncSession = Depends(get_autobot_db),
) -> dict:
    """Reset an AutoBot user's password (admin action — no current password required)."""
    logger.info("Admin password reset for AutoBot user: %s", user_id)
    context = TenantContext(is_platform_admin=True)
    user_service = UserService(db, context)

    try:
        await user_service.change_password(
            user_id=user_id,
            current_password=payload.current_password,
            new_password=payload.new_password,
            require_current=False,
        )
        return {"message": "Password updated successfully"}
    except UserNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found") from e


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_autobot_user(
    user_id: uuid.UUID,
    current_user: dict = Depends(require_permission(Permission.ADMIN_USERS_WRITE)),
    db: AsyncSession = Depends(get_autobot_db),
) -> None:
    """Delete AutoBot user."""
    logger.info("Deleting AutoBot user: %s", user_id)
    context = TenantContext(is_platform_admin=True)
    user_service = UserService(db, context)

    try:
        await user_service.delete_user(user_id)
    except Exception as e:
        logger.error("Failed to delete AutoBot user: %s", e)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Internal server error") from e
