# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Admin + user endpoints for per-user voice bundle assignment (GH#8605).

Endpoints:
    GET  /api/voice/realtime/bundle/me          — resolved bundle for caller
    GET  /api/admin/voice/bundle/{user_id}      — admin: get user's assignment
    PUT  /api/admin/voice/bundle/{user_id}      — admin: set/clear user's assignment
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from api.voice_bundle_constants import VALID_BUNDLES, BundleAssignRequest
from api.voice_bundle_helpers import _count_tools_for_bundle, _require_admin
from auth_middleware import get_current_user
from autobot_shared.logging_manager import get_logger
from services.event_log import EventType, emit
from utils.catalog_http_exceptions import raise_auth_error

logger = get_logger(__name__)

# Router for authenticated users
bundle_me_router = APIRouter(tags=["voice", "rbac"])

# Router for admin operations
bundle_admin_router = APIRouter(prefix="/admin", tags=["admin", "voice", "rbac"])

# Combined router for feature_routers.py discovery (GH#8605)
router = APIRouter()
router.include_router(bundle_me_router, prefix="/voice")
router.include_router(bundle_admin_router)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class BundleMeResponse(BaseModel):
    bundle_name: str
    tool_count: int
    resolution: str  # 'user_override' | 'role_default' | 'global_env'


class BundleAssignmentResponse(BaseModel):
    user_id: str
    bundle_name: Optional[str]


# ---------------------------------------------------------------------------
# GET /voice/realtime/bundle/me
# ---------------------------------------------------------------------------


@bundle_me_router.get("/realtime/bundle/me", response_model=BundleMeResponse)
async def get_my_bundle(
    request: Request,
    current_user: dict = Depends(get_current_user),
) -> BundleMeResponse:
    """Return the resolved voice bundle for the authenticated caller."""
    from api.redis_mcp.rbac import resolve_bundle_for_user  # noqa: PLC0415

    user_id = current_user.get("user_id") or current_user.get("sub") or current_user.get("username")
    role = current_user.get("role", "user")
    is_admin = role == "admin"

    bundle_name, resolution = await resolve_bundle_for_user(str(user_id), role=role)
    tool_count = await _count_tools_for_bundle(bundle_name, is_admin=is_admin)

    return BundleMeResponse(
        bundle_name=bundle_name,
        tool_count=tool_count,
        resolution=resolution,
    )


# ---------------------------------------------------------------------------
# GET /admin/voice/bundle/{user_id}
# ---------------------------------------------------------------------------


@bundle_admin_router.get("/voice/bundle/{user_id}", response_model=BundleAssignmentResponse)
async def get_user_bundle(
    user_id: str,
    request: Request,
    _admin: dict = Depends(_require_admin),
) -> BundleAssignmentResponse:
    """Return the explicit bundle assignment for a user (admin only)."""
    try:
        from sqlalchemy import text  # noqa: PLC0415

        from user_management.database import get_async_session  # noqa: PLC0415

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

    return BundleAssignmentResponse(user_id=user_id, bundle_name=bundle_name)


# ---------------------------------------------------------------------------
# PUT /admin/voice/bundle/{user_id}
# ---------------------------------------------------------------------------


@bundle_admin_router.put("/voice/bundle/{user_id}", response_model=BundleAssignmentResponse)
async def set_user_bundle(
    user_id: str,
    body: BundleAssignRequest,
    request: Request,
    admin_user: dict = Depends(_require_admin),
) -> BundleAssignmentResponse:
    """Assign or clear a voice bundle override for a user (admin only)."""
    if body.bundle_name is not None and body.bundle_name not in VALID_BUNDLES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid bundle_name '{body.bundle_name}'. Valid: {sorted(VALID_BUNDLES)}",
        )

    admin_id = admin_user.get("user_id") or admin_user.get("sub") or admin_user.get("username") or "unknown"

    try:
        from sqlalchemy import text  # noqa: PLC0415

        from user_management.database import get_async_session  # noqa: PLC0415

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
                    {"uid": user_id, "bundle": body.bundle_name, "by": str(admin_id)},
                )
            await session.commit()
    except Exception as exc:
        logger.error("set_user_bundle: DB error: %s", exc)
        raise HTTPException(status_code=500, detail="Database error") from exc

    # Audit log
    emit(
        EventType.CONFIG_CHANGED,
        user_id=str(admin_id),
        resource_type="user_voice_bundle",
        resource_id=user_id,
        metadata={
            "target_user_id": user_id,
            "bundle_name": body.bundle_name,
            "action": "clear" if body.bundle_name is None else "assign",
        },
    )

    logger.info(
        "voice_bundle admin_id=%s target=%s bundle=%s",
        admin_id,
        user_id,
        body.bundle_name,
    )

    return BundleAssignmentResponse(user_id=user_id, bundle_name=body.bundle_name)
