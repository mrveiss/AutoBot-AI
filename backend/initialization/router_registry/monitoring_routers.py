# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Monitoring Router Loader

This module handles loading of monitoring and infrastructure API routers.
These routers provide system monitoring, metrics, service health, and infrastructure management.

Issue #281: Refactored from 112 lines to use data-driven router loading.
"""

import importlib
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)

# Router configurations: (module_path, router_name, prefix, tags, display_name)
# Issue #281: Centralized router configuration for maintainability
MONITORING_ROUTER_CONFIGS = [
    ("backend.api.monitoring", "router", "/monitoring", ["monitoring"], "monitoring"),
    (
        "backend.api.infrastructure_monitor",
        "router",
        "/infrastructure",
        ["infrastructure"],
        "infrastructure_monitor",
    ),
    (
        "backend.api.service_monitor",
        "router",
        "/service-monitor",
        ["service-monitor"],
        "service_monitor",
    ),
    ("backend.api.metrics", "router", "/metrics", ["metrics"], "metrics"),
    (
        "backend.api.monitoring_alerts",
        "router",
        "/alerts",
        ["alerts"],
        "monitoring_alerts",
    ),
    (
        "backend.api.error_monitoring",
        "router",
        "/errors",
        ["errors"],
        "error_monitoring",
    ),
    ("backend.api.rum", "router", "/rum", ["rum"], "rum"),
    (
        "backend.api.infrastructure",
        "router",
        "/iac",
        ["Infrastructure as Code"],
        "infrastructure",
    ),
]


def _try_load_router(
    module_path: str, router_attr: str, prefix: str, tags: List[str], name: str
) -> Tuple:
    """
    Attempt to load a single router module with graceful fallback.

    Issue #281: Extracted from load_monitoring_routers to reduce repetition.

    Args:
        module_path: Full module path (e.g., 'backend.api.monitoring')
        router_attr: Attribute name for the router (usually 'router')
        prefix: API prefix for the router
        tags: OpenAPI tags for the router
        name: Display name for logging

    Returns:
        Tuple of (router, prefix, tags, name) if successful, None otherwise
    """
    try:
        module = importlib.import_module(module_path)
        router = getattr(module, router_attr)
        logger.info(f"✅ Optional router loaded: {name}")
        return (router, prefix, tags, name)
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: {name} - {e}")
        return None
    except AttributeError as e:
        logger.warning(f"⚠️ Router attribute missing: {name} - {e}")
        return None


def load_monitoring_routers() -> List[Tuple]:
    """
    Dynamically load monitoring and infrastructure API routers with graceful fallback.

    Issue #281: Refactored to use data-driven configuration and helper function.
    Reduced from 112 lines to ~30 lines.

    Returns:
        list: List of tuples in format (router, prefix, tags, name)
              Only includes routers that successfully imported.
    """
    optional_routers = []

    for config in MONITORING_ROUTER_CONFIGS:
        module_path, router_attr, prefix, tags, name = config
        result = _try_load_router(module_path, router_attr, prefix, tags, name)
        if result:
            optional_routers.append(result)

    return optional_routers
