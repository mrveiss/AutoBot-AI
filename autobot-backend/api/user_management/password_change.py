# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Password Change API Endpoint

REST API for changing a user's password.

Split out of ``users.py`` (#15743): the account-takeover fix here needed a
caller-identity gate of its own, and ``users.py`` was already at the
repo's file-size ceiling (``scripts/check_python_file_size.py``), so this
stays a sibling router (mirrors ``organizations.py`` / ``teams.py``)
rather than growing that file past it.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from api.schemas_agent import PasswordChangedResponse
from api.user_management.dependencies import (
    get_current_user,
    get_tenant_context,
    get_user_service,
    require_platform_admin,
    require_user_management_enabled,
)
from autobot_shared.logging_manager import get_logger
from user_management.middleware.rate_limit import (
    PasswordChangeRateLimiter,
    RateLimitExceeded,
)
from user_management.schemas import PasswordChange
from user_management.services import TenantContext, UserService
from user_management.services.user_service import (
    InvalidCredentialsError,
    UserNotFoundError,
)

router = APIRouter(prefix="/users", tags=["Users"])
logger = get_logger(__name__)


async def _authorize_password_change(user_id: uuid.UUID, context: TenantContext) -> bool:
    """Gate change-password by the caller's identity, never the request body.

    Issue #15743: the request used to control ``require_current`` directly
    (omit ``current_password`` and verification switched itself off), and
    nothing compared the caller to the path's ``user_id`` at all.

    Self-service (caller == target) always re-verifies the current
    password. Any other target requires an actual platform-admin check --
    the same ``require_platform_admin`` gate ``set_user_role`` uses, reused
    here rather than a second admin check -- and only then skips
    verification (the admin-reset path), never the other way around.
    """
    if context.user_id == user_id:
        return True

    await require_platform_admin(context)
    return False


@router.post(
    "/{user_id}/change-password",
    response_model=PasswordChangedResponse,
    summary="Change password",
    description="Change a user's password.",
    dependencies=[Depends(require_user_management_enabled)],
)
async def change_password(
    user_id: uuid.UUID,
    password_data: PasswordChange,
    user_service: UserService = Depends(get_user_service),
    current_user: dict = Depends(get_current_user),
    context: TenantContext = Depends(get_tenant_context),
):
    """Change a password: self-service with the current one, or an actual
    platform admin resetting another user's without it (#15743)."""
    require_current = await _authorize_password_change(user_id, context)

    rate_limiter = PasswordChangeRateLimiter()

    # Check rate limit before attempting password change.
    # The limiter's message carries the caller-facing retry window ("Too many
    # attempts. Try again in N minutes.") and discloses nothing sensitive, so
    # it is returned verbatim — the previous "Internal server error" detail
    # contradicted the 429 status and stripped the retry guidance.
    try:
        await rate_limiter.check_rate_limit(user_id, actor_id=context.user_id)
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc

    try:
        # Extract current token to preserve this session
        current_token = current_user.get("token")

        await user_service.change_password(
            user_id=user_id,
            current_password=password_data.current_password,
            new_password=password_data.new_password,
            require_current=require_current,
            current_token=current_token,
        )

        # Record successful attempt (clears rate limit counters)
        await rate_limiter.record_attempt(user_id, success=True, actor_id=context.user_id)

        return PasswordChangedResponse(
            message="Password changed successfully",
        )

    except UserNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )
    except InvalidCredentialsError:
        # Record failed attempt
        await rate_limiter.record_attempt(user_id, success=False, actor_id=context.user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        )
