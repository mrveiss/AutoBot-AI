# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared helpers for voice bundle modules (GH#8980).

This module breaks the circular import between voice_bundle_user and voice_bundle_admin
by providing shared functionality that both modules depend on.
"""

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
