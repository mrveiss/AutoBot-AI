# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Router Registry Package

This package contains domain-specific router loader modules that organize
the router imports into logical groups to reduce coupling and improve maintainability.
"""

from .core_routers import load_core_routers
from .analytics_routers import load_analytics_routers
from .mcp_routers import load_mcp_routers
from .terminal_routers import load_terminal_routers
from .monitoring_routers import load_monitoring_routers
from .feature_routers import load_feature_routers

__all__ = [
    "load_core_routers",
    "load_analytics_routers",
    "load_mcp_routers",
    "load_terminal_routers",
    "load_monitoring_routers",
    "load_feature_routers",
]
