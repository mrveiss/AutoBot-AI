# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Monitoring Router Loader

This module handles loading of monitoring and infrastructure API routers.
These routers provide system monitoring, metrics, service health, and infrastructure management.
"""

import logging

logger = logging.getLogger(__name__)


def load_monitoring_routers():
    """
    Dynamically load monitoring and infrastructure API routers with graceful fallback.

    Returns:
        list: List of tuples in format (router, prefix, tags, name)
              Only includes routers that successfully imported.
    """
    optional_routers = []

    # Monitoring router
    try:
        from backend.api.monitoring import router as monitoring_router

        optional_routers.append(
            (monitoring_router, "/monitoring", ["monitoring"], "monitoring")
        )
        logger.info("✅ Optional router loaded: monitoring")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: monitoring - {e}")

    # Infrastructure Monitor router
    try:
        from backend.api.infrastructure_monitor import (
            router as infrastructure_monitor_router,
        )

        optional_routers.append(
            (
                infrastructure_monitor_router,
                "/infrastructure",
                ["infrastructure"],
                "infrastructure_monitor",
            )
        )
        logger.info("✅ Optional router loaded: infrastructure_monitor")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: infrastructure_monitor - {e}")

    # Service Monitor router
    try:
        from backend.api.service_monitor import router as service_monitor_router

        optional_routers.append(
            (
                service_monitor_router,
                "/service-monitor",
                ["service-monitor"],
                "service_monitor",
            )
        )
        logger.info("✅ Optional router loaded: service_monitor")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: service_monitor - {e}")

    # Metrics router
    try:
        from backend.api.metrics import router as metrics_router

        optional_routers.append((metrics_router, "/metrics", ["metrics"], "metrics"))
        logger.info("✅ Optional router loaded: metrics")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: metrics - {e}")

    # Monitoring Alerts router
    try:
        from backend.api.monitoring_alerts import router as monitoring_alerts_router

        optional_routers.append(
            (monitoring_alerts_router, "/alerts", ["alerts"], "monitoring_alerts")
        )
        logger.info("✅ Optional router loaded: monitoring_alerts")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: monitoring_alerts - {e}")

    # Error Monitoring router
    try:
        from backend.api.error_monitoring import router as error_monitoring_router

        optional_routers.append(
            (error_monitoring_router, "/errors", ["errors"], "error_monitoring")
        )
        logger.info("✅ Optional router loaded: error_monitoring")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: error_monitoring - {e}")

    # RUM (Real User Monitoring) router
    try:
        from backend.api.rum import router as rum_router

        optional_routers.append((rum_router, "/rum", ["rum"], "rum"))
        logger.info("✅ Optional router loaded: rum")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: rum - {e}")

    # Infrastructure router
    try:
        from backend.api.infrastructure import router as infrastructure_router

        optional_routers.append(
            (
                infrastructure_router,
                "/iac",
                ["Infrastructure as Code"],
                "infrastructure",
            )
        )
        logger.info("✅ Optional router loaded: infrastructure")
    except ImportError as e:
        logger.warning(f"⚠️ Optional router not available: infrastructure - {e}")

    return optional_routers
