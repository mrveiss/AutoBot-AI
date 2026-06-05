# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Shared helpers for voice bundle modules (GH#8980).

This module breaks the circular import between voice_bundle_user and voice_bundle_admin
by providing shared functionality that both modules depend on.
"""

from fastapi import Request

from auth_middleware import get_auth_middleware
from utils.catalog_http_exceptions import raise_auth_error


def _require_admin(request: Request) -> dict:
    """Verify current user is admin, return user_data or raise.

    FastAPI dependency for admin-only routes.
    Raises AUTH_0002 if not authenticated, AUTH_0003 if not admin.
    """
    user_data = get_auth_middleware().get_user_from_request(request)
    if not user_data:
        raise_auth_error("AUTH_0002", "Authentication required")
    if user_data.get("role") != "admin":
        raise_auth_error("AUTH_0003", "Admin permission required")
    return user_data


_tool_count_cache: dict[tuple[str, bool], int] = {}


async def _count_tools_for_bundle(bundle: str, is_admin: bool) -> int:
    """Return the number of tools available in this bundle (cached per bundle+role)."""
    key = (bundle, is_admin)
    if key not in _tool_count_cache:
        from api.redis_mcp.rbac import (  # noqa: PLC0415
            TOOL_ACCESS_MATRIX,
            filter_tools_for_bundle,
        )

        all_tools = list(TOOL_ACCESS_MATRIX.keys())
        _tool_count_cache[key] = len(filter_tools_for_bundle(all_tools, bundle=bundle, is_admin=is_admin))
    return _tool_count_cache[key]
