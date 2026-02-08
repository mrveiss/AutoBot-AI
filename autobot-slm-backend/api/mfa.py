# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
MFA API

Multi-Factor Authentication endpoints for TOTP setup and verification.
"""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from services.auth import auth_service, get_current_user
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from user_management.database import get_slm_session
from user_management.models.user import User
from user_management.schemas.mfa import (
    BackupCodesResponse,
    MFADisableRequest,
    MFASetupResponse,
    MFAStatusResponse,
    MFAVerifyRequest,
)
from user_management.services.base_service import TenantContext
from user_management.services.mfa_service import (
    InvalidTOTPError,
    MFANotEnabledError,
    MFAService,
    MFAServiceError,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/mfa", tags=["mfa"])


async def get_slm_db():
    """Dependency for SLM database session."""
    async with get_slm_session() as session:
        yield session


@router.post("/setup", response_model=MFASetupResponse)
async def setup_mfa(
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_slm_db)],
) -> MFASetupResponse:
    """Set up TOTP-based MFA for the current user."""
    context = TenantContext(is_platform_admin=True)
    mfa_service = MFAService(db, context)

    username = current_user.get("sub")
    user = await _get_user_by_username(db, username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        result = await mfa_service.setup_totp(user.id)
        logger.info("MFA setup initiated for user: %s", username)
        return MFASetupResponse(**result)
    except MFAServiceError as e:
        logger.warning("MFA setup error for %s: %s", username, e)
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/verify-setup")
async def verify_mfa_setup(
    request: MFAVerifyRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_slm_db)],
) -> dict:
    """Verify MFA setup with initial TOTP code."""
    context = TenantContext(is_platform_admin=True)
    mfa_service = MFAService(db, context)

    username = current_user.get("sub")
    user = await _get_user_by_username(db, username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        await mfa_service.verify_setup(user.id, request.code)
        logger.info("MFA enabled for user: %s", username)
        return {"success": True, "message": "MFA enabled"}
    except InvalidTOTPError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except MFAServiceError as e:
        logger.warning("MFA verification error for %s: %s", username, e)
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/verify-login")
async def verify_mfa_login(
    request: MFAVerifyRequest,
    temp_token: str,
    db: Annotated[AsyncSession, Depends(get_slm_db)],
) -> dict:
    """Verify MFA code during login (no auth required, uses temp token)."""
    payload = auth_service.decode_token(temp_token)
    if not payload or not payload.get("mfa_pending"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired temporary token",
        )

    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid token payload")

    context = TenantContext(is_platform_admin=True)
    mfa_service = MFAService(db, context)

    try:
        user_uuid = uuid.UUID(user_id)
        verified = await mfa_service.verify_login(user_uuid, request.code)

        if not verified:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid MFA code",
            )

        user = await _get_user_by_id(db, user_uuid)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        logger.info("MFA login verified for user: %s", user.username)
        return await auth_service.create_token_response(user)

    except MFANotEnabledError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID")


@router.post("/disable")
async def disable_mfa(
    request: MFADisableRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_slm_db)],
) -> dict:
    """Disable MFA for the current user (requires password)."""
    context = TenantContext(is_platform_admin=True)
    mfa_service = MFAService(db, context)

    username = current_user.get("sub")
    user = await _get_user_by_username(db, username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        await mfa_service.disable(user.id, request.password)
        logger.info("MFA disabled for user: %s", username)
        return {"success": True, "message": "MFA disabled"}
    except MFAServiceError as e:
        logger.warning("MFA disable error for %s: %s", username, e)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/status", response_model=MFAStatusResponse)
async def get_mfa_status(
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_slm_db)],
) -> MFAStatusResponse:
    """Get MFA status for the current user."""
    context = TenantContext(is_platform_admin=True)
    mfa_service = MFAService(db, context)

    username = current_user.get("sub")
    user = await _get_user_by_username(db, username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    status_dict = await mfa_service.get_status(user.id)
    return MFAStatusResponse(**status_dict)


@router.post("/backup-codes", response_model=BackupCodesResponse)
async def regenerate_backup_codes(
    request: MFADisableRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_slm_db)],
) -> BackupCodesResponse:
    """Regenerate backup codes (requires password)."""
    context = TenantContext(is_platform_admin=True)
    mfa_service = MFAService(db, context)

    username = current_user.get("sub")
    user = await _get_user_by_username(db, username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        codes = await mfa_service.regenerate_backup_codes(user.id, request.password)
        logger.info("Backup codes regenerated for user: %s", username)
        return BackupCodesResponse(backup_codes=codes)
    except MFAServiceError as e:
        logger.warning("Backup code regeneration error for %s: %s", username, e)
        raise HTTPException(status_code=400, detail=str(e))


async def _get_user_by_username(db: AsyncSession, username: str) -> User:
    """Get user by username."""
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def _get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User:
    """Get user by ID."""
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()
