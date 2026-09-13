# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
``GET /api/auth/me``: who the caller is, and what they may do (#16270).

Split out of ``api/auth.py``, which is frozen at its file-size ceiling. This
follows the ``password_change.py`` precedent (#15743). ``auth.py`` includes
this router, so the path is unchanged.

#16270 adds ``permissions`` and ``is_admin`` so the frontend can gate on the
server's answer instead of on its own copy of the role map (#16243). Both are
required. Superadmin holds no granular permissions by design (#13854), so a
frontend that gated on ``permissions`` alone would hide everything from a
superadmin. ``is_admin`` carries the other kind of server check.
"""

from typing import List

from fastapi import APIRouter, HTTPException, Request

from api.schemas_agent import AuthUserInfoResponse
from auth_middleware import get_auth_middleware
from autobot_shared.auth.permissions import Permission, Role, is_admin_role, role_has_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger

router = APIRouter()
logger = get_logger(__name__)


class AuthMeResponse(AuthUserInfoResponse):
    """Response for GET /auth/me: the identity fields, plus the caller's effective authority (#16270)."""

    permissions: List[str]
    is_admin: bool


def effective_permissions(role: str) -> List[str]:
    """Return every ``Permission`` value *role* holds, as ``role_has_permission`` answers it.

    That is the function the permission gates consult, so ``/me`` cannot
    report a grant the gates would refuse, or miss one they would allow.
    This does not keep a second copy of the rule.
    """
    return sorted(p.value for p in Permission if role_has_permission(role, p.value))


@router.get("/me", response_model=AuthMeResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_current_user_info",
    error_code_prefix="AUTH",
)
async def get_current_user_info(request: Request):
    """Get the current authenticated user, with their effective permissions (#16270)."""
    try:
        from user_management.config import get_deployment_config

        config = get_deployment_config()
        user_data = get_auth_middleware().get_user_from_request(request)

        if not user_data:
            raise HTTPException(status_code=401, detail="Not authenticated")

        # #12135: use .get() with safe fallbacks, not hard `[...]` access.
        # Every _extract_user_from_* path is expected to populate
        # "username"/"role". But a valid, already-authenticated request must
        # never 500 on an unexpected claim shape, so degrade gracefully instead.
        # This matches the sub/user_id/username fallback convention used
        # elsewhere, e.g. api/documents.py and api/voice.py.
        role = user_data.get("role", Role.USER.value)
        return {
            "username": user_data.get("username") or user_data.get("sub") or user_data.get("user_id", "unknown"),
            "role": role,
            "email": user_data.get("email", ""),
            "auth_method": user_data.get("auth_method", "unknown"),
            "authenticated": True,
            "deployment_mode": config.mode.value,
            "permissions": effective_permissions(role),
            "is_admin": is_admin_role(role),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting user info: %s", e)
        raise HTTPException(status_code=500, detail="Error retrieving user information")
