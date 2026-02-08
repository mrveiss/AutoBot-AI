# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
API Keys API

Endpoints for managing long-lived API keys for programmatic access.
"""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from services.auth import get_current_user
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from user_management.database import get_slm_session
from user_management.models.api_key import API_KEY_SCOPES
from user_management.models.user import User
from user_management.schemas.api_key import (
    APIKeyCreate,
    APIKeyCreateResponse,
    APIKeyListResponse,
    APIKeyResponse,
    APIKeyUpdate,
    APIScopesResponse,
)
from user_management.services.api_key_service import (
    APIKeyNotFoundError,
    APIKeyService,
    APIKeyServiceError,
)
from user_management.services.base_service import TenantContext

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api-keys", tags=["api-keys"])


async def get_slm_db():
    """Dependency for SLM database session."""
    async with get_slm_session() as session:
        yield session


@router.post(
    "", response_model=APIKeyCreateResponse, status_code=status.HTTP_201_CREATED
)
async def create_api_key(
    request: APIKeyCreate,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_slm_db)],
) -> APIKeyCreateResponse:
    """Create a new API key for the current user."""
    context = TenantContext(is_platform_admin=True)
    api_key_service = APIKeyService(db, context)

    username = current_user.get("sub")
    user = await _get_user_by_username(db, username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        api_key, plaintext_key = await api_key_service.create_key(
            user_id=user.id,
            name=request.name,
            scopes=request.scopes,
            description=request.description,
            expires_days=request.expires_days,
        )

        logger.info("API key created for user %s: %s", username, api_key.name)

        return APIKeyCreateResponse(
            id=api_key.id,
            key=plaintext_key,
            key_prefix=api_key.key_prefix,
            name=api_key.name,
            scopes=api_key.scopes,
            expires_at=api_key.expires_at,
            created_at=api_key.created_at,
        )
    except APIKeyServiceError as e:
        logger.warning("API key creation error for %s: %s", username, e)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=APIKeyListResponse)
async def list_api_keys(
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_slm_db)],
) -> APIKeyListResponse:
    """List all API keys for the current user."""
    context = TenantContext(is_platform_admin=True)
    api_key_service = APIKeyService(db, context)

    username = current_user.get("sub")
    user = await _get_user_by_username(db, username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    keys = await api_key_service.list_keys(user.id)

    return APIKeyListResponse(
        keys=[APIKeyResponse.model_validate(key) for key in keys],
        total=len(keys),
    )


@router.get("/scopes", response_model=APIScopesResponse)
async def get_api_scopes() -> APIScopesResponse:
    """Get available API key scopes (no authentication required)."""
    return APIScopesResponse(scopes=API_KEY_SCOPES)


@router.get("/{key_id}", response_model=APIKeyResponse)
async def get_api_key(
    key_id: uuid.UUID,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_slm_db)],
) -> APIKeyResponse:
    """Get details of a specific API key."""
    context = TenantContext(is_platform_admin=True)
    api_key_service = APIKeyService(db, context)

    username = current_user.get("sub")
    user = await _get_user_by_username(db, username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    api_key = await api_key_service.get_key(key_id, user.id)
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")

    return APIKeyResponse.model_validate(api_key)


@router.patch("/{key_id}", response_model=APIKeyResponse)
async def update_api_key(
    key_id: uuid.UUID,
    request: APIKeyUpdate,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_slm_db)],
) -> APIKeyResponse:
    """Update API key metadata (name, description)."""
    context = TenantContext(is_platform_admin=True)
    api_key_service = APIKeyService(db, context)

    username = current_user.get("sub")
    user = await _get_user_by_username(db, username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        api_key = await api_key_service.update_key(
            key_id=key_id,
            user_id=user.id,
            name=request.name,
            description=request.description,
        )

        logger.info("API key updated for user %s: %s", username, key_id)
        return APIKeyResponse.model_validate(api_key)

    except APIKeyNotFoundError:
        raise HTTPException(status_code=404, detail="API key not found")
    except APIKeyServiceError as e:
        logger.warning("API key update error for %s: %s", username, e)
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_id: uuid.UUID,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_slm_db)],
) -> None:
    """Revoke an API key."""
    context = TenantContext(is_platform_admin=True)
    api_key_service = APIKeyService(db, context)

    username = current_user.get("sub")
    user = await _get_user_by_username(db, username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        await api_key_service.revoke_key(key_id, user.id)
        logger.info("API key revoked for user %s: %s", username, key_id)
    except APIKeyNotFoundError:
        raise HTTPException(status_code=404, detail="API key not found")
    except APIKeyServiceError as e:
        logger.warning("API key revoke error for %s: %s", username, e)
        raise HTTPException(status_code=400, detail=str(e))


async def _get_user_by_username(db: AsyncSession, username: str) -> User:
    """Get user by username."""
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()
