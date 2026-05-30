# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""User endpoints for per-user voice bundle assignment (GH#8605).

Endpoints:
    GET  /api/voice/bundles                     — list available bundles (with descriptions)
    GET  /api/voice/users/{userId}/bundle       — get user's bundle assignment (self or admin)
    PUT  /api/voice/users/{userId}/bundle       — assign bundle to user (admin only, GH#8969)
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from api.redis_mcp.rbac import VALID_BUNDLES
from auth_middleware import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from services.audit.unified_audit import AuditCategory, AuditEvent, emit
from utils.catalog_http_exceptions import raise_auth_error

logger = get_logger(__name__)

router = APIRouter(tags=["voice", "rbac"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class BundleInfo(BaseModel):
    """Information about an available voice bundle."""

    name: str
    label: str
    description: str
    tool_count: int


class UserBundleResponse(BaseModel):
    """User's voice bundle assignment."""

    user_id: str
    bundle_name: Optional[str] = None


class BundleAssignRequest(BaseModel):
    """Request to assign or clear a bundle for a user."""

    bundle_name: Optional[str] = None  # None = clear override


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BUNDLE_DEFINITIONS: dict[str, dict[str, str]] = {
    "voice_safe": {
        "label": "Voice Safe",
        "description": "Basic voice commands for standard users",
    },
    "voice_extended": {
        "label": "Voice Extended",
        "description": "Extended voice commands with advanced features",
    },
    "voice_admin": {
        "label": "Voice Admin",
        "description": "Full voice command set for administrators",
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_tool_count_cache: dict[tuple[str, bool], int] = {}


async def _count_tools_for_bundle(bundle: str, is_admin: bool) -> int:
    """Return the number of tools available in this bundle (cached per bundle+role)."""
    key = (bundle, is_admin)
    if key not in _tool_count_cache:
        from api.redis_mcp.rbac import TOOL_ACCESS_MATRIX, filter_tools_for_bundle  # noqa: PLC0415

        all_tools = list(TOOL_ACCESS_MATRIX.keys())
        _tool_count_cache[key] = len(filter_tools_for_bundle(all_tools, bundle=bundle, is_admin=is_admin))
    return _tool_count_cache[key]


def _is_admin(user: dict) -> bool:
    return user.get("role") == "admin"


def _get_user_id(user: dict) -> str:
    """Extract user_id from auth payload."""
    return user.get("user_id") or user.get("sub") or user.get("username") or "unknown"


def _check_self_or_admin(request: Request, current_user: dict, target_user_id: str) -> bool:
    """Verify user can access target_user_id (self or admin)."""
    current_user_id = _get_user_id(current_user)
    return current_user_id == target_user_id or _is_admin(current_user)


# ---------------------------------------------------------------------------
# GET /voice/bundles — list available bundles
# ---------------------------------------------------------------------------


@router.get("/bundles", response_model=list[BundleInfo])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="voice_list_bundles",
    error_code_prefix="VOICE",
)
async def list_voice_bundles(
    current_user: dict = Depends(get_current_user),
) -> list[BundleInfo]:
    """Return list of available voice bundles with descriptions and tool counts.

    Filters bundles based on user role (admins see all, users see allowed).
    Results are sorted by bundle name for deterministic ordering.
    """
    is_admin = _is_admin(current_user)

    result = []
    for bundle_name in sorted(VALID_BUNDLES):
        defn = BUNDLE_DEFINITIONS.get(bundle_name, {})
        try:
            tool_count = await _count_tools_for_bundle(bundle_name, is_admin=is_admin)
        except Exception as exc:
            logger.warning("Failed to count tools for bundle %s: %s", bundle_name, exc)
            tool_count = 0
        result.append(
            BundleInfo(
                name=bundle_name,
                label=defn.get("label", bundle_name),
                description=defn.get("description", ""),
                tool_count=tool_count,
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

    Permission: self or admin only.
    """
    if not _check_self_or_admin(request, current_user, user_id):
        raise_auth_error("AUTH_0003", "Cannot access other user's bundle assignment")

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

    return UserBundleResponse(user_id=user_id, bundle_name=bundle_name)


# ---------------------------------------------------------------------------
# PUT /voice/users/{userId}/bundle — assign bundle to user (admin only)
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

    Admin-only. Bundle assignment changes a user's privilege level, so
    self-service is explicitly prohibited to prevent privilege escalation
    (GH#8969).
    """
    if not _is_admin(current_user):
        raise_auth_error("AUTH_0003", "Only admins may assign voice bundles")

    if body.bundle_name is not None and body.bundle_name not in VALID_BUNDLES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid bundle_name '{body.bundle_name}'. Valid: {sorted(VALID_BUNDLES)}",
        )

    current_user_id = _get_user_id(current_user)

    _audit_meta = {
        "target_user_id": user_id,
        "requested_bundle_name": body.bundle_name,
        "assignment_action": "clear" if body.bundle_name is None else "assign",
    }
    stored_bundle_name: Optional[str] = None

    try:
        from sqlalchemy import text  # noqa: PLC0415

        from user_management.database import get_async_session  # noqa: PLC0415

        async with get_async_session() as session:
            if body.bundle_name is None:
                await session.execute(
                    text("DELETE FROM user_voice_bundle WHERE user_id = :uid"),
                    {"uid": user_id},
                )
            else:
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
            # Re-read after commit so response reflects actual stored value.
            row = await session.execute(
                text("SELECT bundle_name FROM user_voice_bundle WHERE user_id = :uid"),
                {"uid": user_id},
            )
            result = row.fetchone()
            stored_bundle_name = result[0] if result else None
    except Exception as exc:
        try:
            emit(
                AuditEvent(
                    category=AuditCategory.SECURITY,
                    action="voice_bundle_assignment_changed",
                    actor_id=str(current_user_id),
                    resource_type="user_voice_bundle",
                    resource_id=user_id,
                    outcome="failure",
                    metadata={**_audit_meta, "error": str(exc)},
                )
            )
        except Exception:
            logger.warning("set_user_bundle: failed to emit failure audit", exc_info=True)
        logger.error("set_user_bundle: DB error: %s", exc)
        raise HTTPException(status_code=500, detail="Database error") from exc

    emit(
        AuditEvent(
            category=AuditCategory.SECURITY,
            action="voice_bundle_assignment_changed",
            actor_id=str(current_user_id),
            resource_type="user_voice_bundle",
            resource_id=user_id,
            outcome="success",
            metadata={**_audit_meta, "bundle_name": stored_bundle_name},
        )
    )

    logger.info(
        "voice_bundle user_id=%s target=%s bundle=%s",
        current_user_id,
        user_id,
        stored_bundle_name,
    )

    return UserBundleResponse(user_id=user_id, bundle_name=stored_bundle_name)
