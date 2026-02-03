# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
MCP Router Loader

This module is intentionally minimal as MCP routers are already loaded
as part of the core routers module. This exists for organizational consistency
and future MCP router additions that may be optional.
"""

import logging

logger = logging.getLogger(__name__)


def load_mcp_routers():
    """
    Load optional MCP protocol routers.

    Note: Most MCP routers are loaded as core routers in core_routers.py.
    This function exists for any optional MCP routers that may be added in the future.

    Returns:
        list: List of tuples in format (router, prefix, tags, name)
              Currently returns empty list as all MCP routers are core.
    """
    optional_routers = []

    # All current MCP routers are in core_routers.py:
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

    # Future optional MCP routers can be added here
    logger.info("✅ MCP routers: All current MCP routers are loaded as core routers")

    return optional_routers
