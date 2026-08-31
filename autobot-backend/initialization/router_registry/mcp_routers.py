# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
MCP Router Loader

This module is intentionally minimal as MCP routers are already loaded
as part of the core routers module. This exists for organizational consistency
and future MCP router additions that may be optional.
"""

from .loader import load_router_group


def load_mcp_routers():
    """
    Load optional MCP protocol routers.

    Note: Most MCP routers are loaded as core routers in core_routers.py.
    This function loads optional MCP routers.

    Returns:
        list: List of tuples in format (router, prefix, tags, name)
    """
    # All core MCP routers are in core_routers.py:
    # - knowledge_mcp
    # - vnc_mcp
    # - sequential_thinking_mcp
    # - structured_thinking_mcp
    # - filesystem_mcp
    # - browser_mcp
    # - http_client_mcp
    # - database_mcp
    # - git_mcp
    # - prometheus_mcp
    # - redis_mcp
    # - manual_mcp
    # - mcp_registry
    #
    # #14586: manual_mcp used to be listed again below, mounting the same
    # router twice (once here at prefix "", once in core_routers.py at
    # prefix "/manual") -- resolved to the single core registration above.

    # Optional MCP routers
    optional_mcp_configs = [
        # Issue #5072: AutoBot MCP server HTTP transport (POST /api/mcp/tool)
        ("api.autobot_mcp_router", "", ["mcp", "autobot-mcp"], "autobot_mcp_server"),
        # Issue #6453: Admin endpoints to generate/revoke scoped MCP client tokens
        ("api.mcp_token_admin", "", ["mcp", "admin", "mcp-tokens"], "mcp_token_admin"),
    ]

    return load_router_group("mcp", optional_mcp_configs)
