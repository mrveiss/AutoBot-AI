# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
System Secrets API Routes (#1417)

Encrypted storage for internal system tokens (HF_TOKEN, API keys, etc.).
Admin-only — secrets are not exposed to end users.
"""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from models.database import SystemSecret
from models.schemas import SecretCreate, SecretResponse, SecretUpdate
from services.auth import require_admin
from services.database import get_db
from services.encryption import decrypt_data, encrypt_data
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/secrets", tags=["secrets"])


@router.get("", response_model=List[SecretResponse])
async def list_secrets(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(require_admin)],
) -> List[SecretResponse]:
    """List all system secrets (values never returned)."""
    result = await db.execute(select(SystemSecret).order_by(SystemSecret.key))
    return [SecretResponse.model_validate(s) for s in result.scalars().all()]


@router.post(
    "",
    response_model=SecretResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_secret(
    data: SecretCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(require_admin)],
) -> SecretResponse:
    """Create a new system secret (admin only)."""
    existing = await db.execute(
        select(SystemSecret).where(SystemSecret.key == data.key)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Secret '{data.key}' already exists",
        )

    secret = SystemSecret(
        key=data.key,
        encrypted_value=encrypt_data(data.value),
        category=data.category,
        description=data.description,
    )
    db.add(secret)
    await db.commit()
    await db.refresh(secret)

    logger.info("System secret created: %s [%s]", data.key, data.category)
    return SecretResponse.model_validate(secret)


@router.get("/{key}", response_model=SecretResponse)
async def get_secret(
    key: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(require_admin)],
) -> SecretResponse:
    """Get a system secret metadata (value never returned)."""
    result = await db.execute(select(SystemSecret).where(SystemSecret.key == key))
    secret = result.scalar_one_or_none()
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Secret not found",
        )
    return SecretResponse.model_validate(secret)


@router.get("/{key}/value")
async def get_secret_value(
    key: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(require_admin)],
) -> dict:
    """Get a decrypted secret value (admin only, for fleet provisioning)."""
    result = await db.execute(select(SystemSecret).where(SystemSecret.key == key))
    secret = result.scalar_one_or_none()
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Secret not found",
        )
    return {"key": secret.key, "value": decrypt_data(secret.encrypted_value)}


@router.put("/{key}", response_model=SecretResponse)
async def update_secret(
    key: str,
    data: SecretUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(require_admin)],
) -> SecretResponse:
    """Update a system secret (admin only)."""
    result = await db.execute(select(SystemSecret).where(SystemSecret.key == key))
    secret = result.scalar_one_or_none()
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Secret not found",
        )

    if data.value is not None:
        secret.encrypted_value = encrypt_data(data.value)
    if data.category is not None:
        secret.category = data.category
    if data.description is not None:
        secret.description = data.description

    await db.commit()
    await db.refresh(secret)

    logger.info("System secret updated: %s", key)
    return SecretResponse.model_validate(secret)


@router.delete("/{key}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_secret(
    key: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(require_admin)],
) -> None:
    """Delete a system secret (admin only)."""
    result = await db.execute(select(SystemSecret).where(SystemSecret.key == key))
    secret = result.scalar_one_or_none()
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Secret not found",
        )

    await db.delete(secret)
    await db.commit()
    logger.info("System secret deleted: %s", key)
