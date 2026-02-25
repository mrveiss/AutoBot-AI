# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Monitoring Router Loader

This module handles loading of monitoring API routers.
These routers provide system monitoring, metrics, service health, and error tracking.

Issue #281: Refactored from 112 lines to use data-driven router loading.
Issue #729: Infrastructure routers removed - now served by slm-server.
"""

import importlib
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)

# Router configurations: (module_path, router_name, prefix, tags, display_name)
# Issue #281: Centralized router configuration for maintainability
# Issue #729: Removed infrastructure routers - now served by slm-server
MONITORING_ROUTER_CONFIGS = [
    ("api.monitoring", "router", "/monitoring", ["monitoring"], "monitoring"),
    ("api.metrics", "router", "/metrics", ["metrics"], "metrics"),
    # Prometheus scrape endpoint at /api/metrics (no auth, used by Prometheus server)
    (
        "api.prometheus_endpoint",
        "router",
        "/metrics",
        ["metrics"],
        "prometheus_endpoint",
    ),
    # Issue #69: monitoring_alerts removed - replaced by Prometheus AlertManager
    # Alerts now handled via alertmanager_webhook router (Issue #346)
    (
        "api.error_monitoring",
        "router",
        "/errors",
        ["errors"],
        "error_monitoring",
    ),
    ("api.rum", "router", "/rum", ["rum"], "rum"),
    # Issue #925: service-monitor re-added for frontend health status widget
    (
        "api.service_monitor",
        "router",
        "/service-monitor",
        ["service-monitor"],
        "service_monitor",
    ),
    # Issue #729: vm_services removed - VM service monitoring now in slm-server
    # AlertManager webhook integration (Issue #346)
    (
        "api.alertmanager_webhook",
        "router",
        "",  # Router already has /webhook prefix
        ["webhooks", "alertmanager"],
        "alertmanager_webhook",
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
        logger.info("✅ Optional router loaded: %s", name)
        return (router, prefix, tags, name)
    except ImportError as e:
        logger.warning("⚠️ Optional router not available: %s - %s", name, e)
        return None
    except AttributeError as e:
        logger.warning("⚠️ Router attribute missing: %s - %s", name, e)
        return None


def load_monitoring_routers() -> List[Tuple]:
    """
    Dynamically load monitoring API routers with graceful fallback.

    Issue #281: Refactored to use data-driven configuration and helper function.
    Issue #729: Infrastructure routers removed - now served by slm-server.

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
