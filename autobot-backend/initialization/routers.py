# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Router Loading Module

This module handles the dynamic loading of core and optional API routers
for the AutoBot backend. It separates router configuration from the main
application factory to improve maintainability and organization.

Core routers are essential for basic functionality and should always load.
Optional routers provide enhanced features and gracefully fall back if unavailable.

The actual router definitions are organized into domain-specific modules
in the router_registry package to reduce coupling and improve maintainability.
"""

import logging

from initialization.router_registry import (
    load_analytics_routers,
    load_core_routers,
    load_feature_routers,
    load_mcp_routers,
    load_monitoring_routers,
    load_terminal_routers,
)

logger = logging.getLogger(__name__)


def load_optional_routers():
    """
    Dynamically load optional API routers with graceful fallback.

    Optional routers provide enhanced features but are not required for basic
    functionality. Each router is loaded in a try-except block to gracefully
    handle missing dependencies or implementation.

    This function aggregates routers from multiple domain-specific modules:
    - Analytics routers (code analysis, performance, etc.)
    - Terminal routers (terminal access, remote execution)
    - Monitoring routers (metrics, infrastructure monitoring)
    - Feature routers (various application features)
    - MCP routers (optional MCP protocol extensions)

    Returns:
        list: List of tuples in format (router, prefix, tags, name)
              Only includes routers that successfully imported.
    """
    optional_routers = []

    # Load routers from domain-specific modules
    optional_routers.extend(load_analytics_routers())
    optional_routers.extend(load_terminal_routers())
    optional_routers.extend(load_monitoring_routers())
    optional_routers.extend(load_feature_routers())
    optional_routers.extend(load_mcp_routers())

    logger.info("✅ Loaded %s optional routers", len(optional_routers))
    return optional_routers


# Export for backward compatibility
__all__ = ["load_core_routers", "load_optional_routers"]
