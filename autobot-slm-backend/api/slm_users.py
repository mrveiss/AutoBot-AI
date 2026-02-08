# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Admin User Management API

Manages users in the local SLM database (172.16.168.19:5432/slm_users).
These are fleet administrators who can access the SLM admin dashboard.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from services.auth import require_admin
from sqlalchemy.ext.asyncio import AsyncSession
from user_management.database import get_slm_session
from user_management.schemas.user import (
    UserCreate,
    UserListResponse,
    UserResponse,
    UserUpdate,
)
from user_management.services import TenantContext, UserService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/slm-users", tags=["slm-users"])


async def get_slm_db():
    """Dependency for SLM database session."""
    async with get_slm_session() as session:
        yield session


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_slm_user(
    user_data: UserCreate,
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_slm_db),
) -> UserResponse:
    """Create a new SLM admin user."""
    logger.info("Creating SLM user: %s", user_data.username)
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
        logger.error("Failed to create SLM user: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from e


@router.get("", response_model=UserListResponse)
async def list_slm_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: str = Query(None),
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_slm_db),
) -> UserListResponse:
    """List SLM admin users with pagination and search."""
    logger.info("Listing SLM users (skip=%d, limit=%d, search=%s)", skip, limit, search)
    context = TenantContext(is_platform_admin=True)
    user_service = UserService(db, context)

    users, total = await user_service.list_users(
        limit=limit, offset=skip, search=search
    )
    return UserListResponse(
        users=[UserResponse.model_validate(user) for user in users],
        total=total,
        limit=limit,
        offset=skip,
    )


@router.get("/{user_id}", response_model=UserResponse)
async def get_slm_user(
    user_id: uuid.UUID,
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_slm_db),
) -> UserResponse:
    """Get SLM user by ID."""
    context = TenantContext(is_platform_admin=True)
    user_service = UserService(db, context)

    user = await user_service.get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return UserResponse.model_validate(user)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_slm_user(
    user_id: uuid.UUID,
    updates: UserUpdate,
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_slm_db),
) -> UserResponse:
    """Update SLM user."""
    logger.info("Updating SLM user: %s", user_id)
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
        logger.error("Failed to update SLM user: %s", e)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_slm_user(
    user_id: uuid.UUID,
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_slm_db),
) -> None:
    """Delete SLM user."""
    logger.info("Deleting SLM user: %s", user_id)
    context = TenantContext(is_platform_admin=True)
    user_service = UserService(db, context)

    try:
        await user_service.delete_user(user_id)
    except Exception as e:
        logger.error("Failed to delete SLM user: %s", e)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
