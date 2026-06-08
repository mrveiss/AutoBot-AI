# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
MCP Router Loader

This module is intentionally minimal as MCP routers are already loaded
as part of the core routers module. This exists for organizational consistency
and future MCP router additions that may be optional.
"""

import importlib
from typing import List, Tuple

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


def _load_single_mcp_router(module_path: str, prefix: str, tags: List[str], name: str) -> Tuple | None:
    """Load a single MCP router with graceful fallback."""
    try:
        module = importlib.import_module(module_path)
        router = getattr(module, "router")
        logger.info("✅ Optional MCP router loaded: %s", name)
        return (router, prefix, tags, name)
    except ImportError as e:
        logger.warning("⚠️ Optional MCP router not available: %s - %s", name, e)
        return None
    except AttributeError as e:
        logger.warning("⚠️ Router not found in module %s: %s - %s", module_path, name, e)
        return None


def load_mcp_routers():
    """
    Load optional MCP protocol routers.

    Note: Most MCP routers are loaded as core routers in core_routers.py.
    This function loads optional MCP routers.

    Returns:
        list: List of tuples in format (router, prefix, tags, name)
    """
    optional_routers = []

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
    # - mcp_registry

    # Optional MCP routers
    optional_mcp_configs = [
        ("api.manual_mcp", "", ["manual_mcp", "mcp"], "manual_mcp"),
        # Issue #5072: AutoBot MCP server HTTP transport (POST /api/mcp/tool)
        ("api.autobot_mcp_router", "", ["mcp", "autobot-mcp"], "autobot_mcp_server"),
        # Issue #6453: Admin endpoints to generate/revoke scoped MCP client tokens
        ("api.mcp_token_admin", "", ["mcp", "admin", "mcp-tokens"], "mcp_token_admin"),
    ]

    for module_path, prefix, tags, name in optional_mcp_configs:
        result = _load_single_mcp_router(module_path, prefix, tags, name)
        if result:
            optional_routers.append(result)

    if optional_routers:
        logger.info("✅ Loaded %s optional MCP routers", len(optional_routers))
    else:
        logger.info("✅ MCP routers: Core MCP routers are loaded from core_routers")

    return optional_routers
