# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""User endpoints for per-user voice bundle assignment (GH#8605).

Endpoints:
    GET  /api/voice/bundles              — list available bundles
    GET  /api/voice/users/{userId}/bundle  — get user's bundle assignment
    PUT  /api/voice/users/{userId}/bundle  — assign bundle to user
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from auth_middleware import get_auth_middleware, get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from utils.catalog_http_exceptions import raise_auth_error

logger = get_logger(__name__)

router = APIRouter(tags=["voice", "rbac"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class BundleInfo(BaseModel):
    name: str
    label: str
    tool_count: int


class UserBundleResponse(BaseModel):
    user_id: str
    bundle_name: Optional[str]


class BundleAssignRequest(BaseModel):
    bundle_name: Optional[str] = None  # None = clear override


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_BUNDLES = {"voice_safe", "voice_extended", "voice_admin"}
ADMIN_ONLY_BUNDLES = {"voice_admin"}  # Non-admins may not self-assign these

BUNDLE_LABELS = {
    "voice_safe": "Voice Safe",
    "voice_extended": "Voice Extended",
    "voice_admin": "Voice Admin",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _count_tools_for_bundle(bundle: str, is_admin: bool) -> int:
    """Return the number of tools available in this bundle."""
    from api.redis_mcp.rbac import TOOL_ACCESS_MATRIX, filter_tools_for_bundle  # noqa: PLC0415

    all_tools = list(TOOL_ACCESS_MATRIX.keys())
    return len(filter_tools_for_bundle(all_tools, bundle=bundle, is_admin=is_admin))


def _get_user_id(user: dict) -> str:
    """Extract user_id from auth payload."""
    return user.get("user_id") or user.get("sub") or user.get("username") or "unknown"


def _check_self_or_admin(request: Request, current_user: dict, target_user_id: str) -> bool:
    """Verify user can access target_user_id (self or admin)."""
    current_user_id = _get_user_id(current_user)
    is_admin = current_user.get("role") == "admin"
    return current_user_id == target_user_id or is_admin


# ---------------------------------------------------------------------------
# GET /voice/bundles — list available bundles
# ---------------------------------------------------------------------------


@router.get("/bundles", response_model=List[BundleInfo])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="voice_list_bundles",
    error_code_prefix="VOICE",
)
async def list_voice_bundles(
    current_user: dict = Depends(get_current_user),
) -> List[BundleInfo]:
    """Return list of available voice bundles.

    Filters bundles based on user role (admins see all, users see allowed).
    """
    role = current_user.get("role", "user")
    is_admin = role == "admin"

    result = []
    for bundle_name in VALID_BUNDLES:
        try:
            tool_count = await _count_tools_for_bundle(bundle_name, is_admin=is_admin)
            label = BUNDLE_LABELS.get(bundle_name, bundle_name)
            result.append(
                BundleInfo(
                    name=bundle_name,
                    label=label,
                    tool_count=tool_count,
                )
            )
        except Exception as exc:
            logger.warning("Failed to count tools for bundle %s: %s", bundle_name, exc)
            # Include bundle even if tool count fails
            label = BUNDLE_LABELS.get(bundle_name, bundle_name)
            result.append(
                BundleInfo(
                    name=bundle_name,
                    label=label,
                    tool_count=0,
                )
            )

    return result


# ---------------------------------------------------------------------------
# GET /voice/users/{userId}/bundle — get user's bundle assignment
# ---------------------------------------------------------------------------


@router.get("/users/{user_id}/bundle", response_model=UserBundleResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="voice_get_user_bundle",
    error_code_prefix="VOICE",
)
async def get_user_bundle(
    user_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
) -> UserBundleResponse:
    """Return the explicit bundle assignment for a user.

    Users can only view their own assignment (or admins can view any user).
    """
    if not _check_self_or_admin(request, current_user, user_id):
        raise_auth_error("AUTH_0003", "Cannot access other user's bundle assignment")

    try:
        from database.session import get_async_session  # noqa: PLC0415
        from sqlalchemy import text  # noqa: PLC0415

        async with get_async_session() as session:
            row = await session.execute(
                text("SELECT bundle_name FROM user_voice_bundle WHERE user_id = :uid"),
                {"uid": user_id},
            )
            result = row.fetchone()
            bundle_name = result[0] if result else None
    except Exception as exc:
        logger.error("get_user_bundle: DB error: %s", exc)
        raise HTTPException(status_code=500, detail="Database error") from exc

    return UserBundleResponse(user_id=user_id, bundle_name=bundle_name)


# ---------------------------------------------------------------------------
# PUT /voice/users/{userId}/bundle — assign bundle to user
# ---------------------------------------------------------------------------


@router.put("/users/{user_id}/bundle", response_model=UserBundleResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="voice_set_user_bundle",
    error_code_prefix="VOICE",
)
async def set_user_bundle(
    user_id: str,
    body: BundleAssignRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
) -> UserBundleResponse:
    """Assign or clear a voice bundle override for a user.

    Users can only manage their own assignment (admins can manage any user).
    """
    if not _check_self_or_admin(request, current_user, user_id):
        raise_auth_error("AUTH_0003", "Cannot assign bundles to other users")

    if body.bundle_name is not None and body.bundle_name not in VALID_BUNDLES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid bundle_name '{body.bundle_name}'. Valid: {sorted(VALID_BUNDLES)}",
        )

    is_admin = current_user.get("role") == "admin"
    if body.bundle_name in ADMIN_ONLY_BUNDLES and not is_admin:
        raise_auth_error("AUTH_0003", "Only admins may assign the voice_admin bundle")

    current_user_id = _get_user_id(current_user)

    try:
        from database.session import get_async_session  # noqa: PLC0415
        from sqlalchemy import text  # noqa: PLC0415

        async with get_async_session() as session:
            if body.bundle_name is None:
                # Clear override
                await session.execute(
                    text("DELETE FROM user_voice_bundle WHERE user_id = :uid"),
                    {"uid": user_id},
                )
            else:
                # Upsert
                await session.execute(
                    text("""
                        INSERT INTO user_voice_bundle (user_id, bundle_name, assigned_by, assigned_at)
                        VALUES (:uid, :bundle, :by, NOW())
                        ON CONFLICT (user_id) DO UPDATE
                          SET bundle_name = EXCLUDED.bundle_name,
                              assigned_by = EXCLUDED.assigned_by,
                              assigned_at = EXCLUDED.assigned_at
                        """),
                    {"uid": user_id, "bundle": body.bundle_name, "by": str(current_user_id)},
                )
            await session.commit()
    except Exception as exc:
        logger.error("set_user_bundle: DB error: %s", exc)
        raise HTTPException(status_code=500, detail="Database error") from exc

    # Audit log
    from services.event_log import EventType, emit  # noqa: PLC0415

    emit(
        EventType.CONFIG_CHANGED,
        user_id=str(current_user_id),
        resource_type="user_voice_bundle",
        resource_id=user_id,
        metadata={
            "target_user_id": user_id,
            "bundle_name": body.bundle_name,
            "action": "clear" if body.bundle_name is None else "assign",
        },
    )

    logger.info(
        "voice_bundle user_id=%s target=%s bundle=%s",
        current_user_id,
        user_id,
        body.bundle_name,
    )

    return UserBundleResponse(user_id=user_id, bundle_name=body.bundle_name)
