# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared helpers for voice bundle modules (GH#8980).

This module breaks the circular import between voice_bundle_user and voice_bundle_admin
by providing shared functionality that both modules depend on.
"""


def voice_bundle_user_id(user: dict) -> str | None:
    """The id a caller's voice bundle is keyed by: ``user_id``, else ``sub``, else ``username`` (#17325).

    The one definition shared by the bundle endpoints and the realtime tool list/call handlers, so the bundle a
    user sets is the bundle their realtime session resolves. ``None`` when the principal carries none of them.
    """
    value = user.get("user_id") or user.get("sub") or user.get("username")
    return str(value) if value else None


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
