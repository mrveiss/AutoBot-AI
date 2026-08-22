# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Monitoring Router Loader

This module handles loading of monitoring API routers.
These routers provide system monitoring, metrics, service health, and error tracking.

Issue #281: Refactored from 112 lines to use data-driven router loading.
Issue #729: Infrastructure routers removed - now served by slm-server.
"""

from typing import List, Tuple

from .loader import load_router_group

# Router configurations: (module_path, router_name, prefix, tags, display_name)
# Issue #281: Centralized router configuration for maintainability
# Issue #729: Removed infrastructure routers - now served by slm-server
MONITORING_ROUTER_CONFIGS = [
    ("api.branch_health", "router", "", ["branch-health"], "branch_health"),
    ("api.monitoring", "router", "/monitoring", ["monitoring"], "monitoring"),
    # #12631: memory lifecycle read view. Registered here rather than under a new
    # group because it is observability, and the umbrella (#12630) composes it
    # into the same operator surface as the rest of monitoring.
    (
        "api.memory_lifecycle",
        "router",
        "/memory",
        ["memory-lifecycle"],
        "memory_lifecycle",
    ),
    ("api.metrics", "router", "/metrics", ["metrics"], "metrics"),
    # Issue #1288: Prometheus scrape endpoint at /api/metrics/prometheus
    # (no auth, used by Prometheus server). Moved from /metrics to avoid
    # sharing the same prefix as api.metrics JSON endpoints.
    (
        "api.prometheus_endpoint",
        "router",
        "/metrics/prometheus",
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
    # Issue #2267: GPU acceleration optimizer monitoring endpoints
    # Issue #2315: prefix changed from /monitoring to /monitoring/gpu to avoid
    # collision with api.monitoring (Issue #1288 anti-pattern)
    (
        "api.gpu_monitoring",
        "router",
        "/monitoring/gpu",
        ["gpu-monitoring"],
        "gpu_monitoring",
    ),
    # Issue #4069: Production diagnostic endpoints for causal inference
    # Issue #4254: Register diagnostics router
    ("api.diagnostics", "router", "", ["diagnostics"], "diagnostics"),
]


def load_monitoring_routers() -> List[Tuple]:
    """
    Dynamically load monitoring API routers with graceful fallback.

    Issue #281: Refactored to use data-driven configuration and helper function.
    Issue #729: Infrastructure routers removed - now served by slm-server.

    Returns:
        list: List of tuples in format (router, prefix, tags, name)
              Only includes routers that successfully imported.
    """
    return load_router_group("monitoring", MONITORING_ROUTER_CONFIGS)
