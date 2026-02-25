# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Comprehensive Performance Monitoring System
Advanced GPU/NPU utilization tracking, multi-modal AI performance monitoring,
and real-time system optimization for Intel Ultra 9 185H + RTX 4070 hardware.

Note: This module has been refactored as part of Issue #381 god class refactoring.
All classes are now in the performance_monitoring/ package. This module provides
backward compatibility by re-exporting all classes.

FEATURES:
=========
- GPU/NPU utilization tracking
- Multi-modal AI performance metrics
- System resource monitoring (CPU, memory, disk, network)
- Distributed service health checks
- Alert generation and callbacks
- Performance recommendations
- Redis-based metric persistence
- Prometheus/Grafana integration support

USAGE:
======
from utils.performance_monitor import (
    PerformanceMonitor,
    GPUMetrics, NPUMetrics, SystemPerformanceMetrics,
    start_monitoring, stop_monitoring,
    get_performance_dashboard, collect_metrics,
    monitor_performance,  # decorator
)

# Get singleton instance
monitor = performance_monitor

# Start monitoring
await start_monitoring()

# Collect metrics manually
metrics = await collect_metrics()

# Get dashboard
dashboard = await get_performance_dashboard()

# Stop monitoring
await stop_monitoring()
"""

import logging
from typing import Any, Dict, List

from utils.performance_monitoring.analyzers import (
    AlertAnalyzer,
    RecommendationGenerator,
)
from utils.performance_monitoring.collectors import (
    GPUCollector,
    MultiModalCollector,
    NPUCollector,
    ServiceCollector,
    SystemCollector,
)
from utils.performance_monitoring.decorator import monitor_performance, set_redis_client
from utils.performance_monitoring.hardware import HardwareDetector
from utils.performance_monitoring.metrics import (
    GPUMetrics,
    MultiModalMetrics,
    NPUMetrics,
    ServicePerformanceMetrics,
    SystemPerformanceMetrics,
)
from utils.performance_monitoring.monitor import PerformanceMonitor

# Import all types, dataclasses, and classes from the package (Issue #381 refactoring)
from utils.performance_monitoring.types import (
    AUTOBOT_PROCESS_KEYWORDS,
    CRITICAL_SERVICE_STATUSES,
    DEFAULT_COLLECTION_INTERVAL,
    DEFAULT_PERFORMANCE_BASELINES,
    DEFAULT_RETENTION_HOURS,
)

logger = logging.getLogger(__name__)

# Re-export for backward compatibility
__all__ = [
    # Main class (renamed from Phase9PerformanceMonitor)
    "PerformanceMonitor",
    # Metrics dataclasses
    "GPUMetrics",
    "NPUMetrics",
    "MultiModalMetrics",
    "SystemPerformanceMetrics",
    "ServicePerformanceMetrics",
    # Collectors
    "GPUCollector",
    "NPUCollector",
    "SystemCollector",
    "ServiceCollector",
    "MultiModalCollector",
    # Analyzers
    "AlertAnalyzer",
    "RecommendationGenerator",
    # Hardware
    "HardwareDetector",
    # Decorator
    "monitor_performance",
    "set_redis_client",
    # Constants
    "CRITICAL_SERVICE_STATUSES",
    "DEFAULT_PERFORMANCE_BASELINES",
    "DEFAULT_COLLECTION_INTERVAL",
    "DEFAULT_RETENTION_HOURS",
    "AUTOBOT_PROCESS_KEYWORDS",
    # Singleton instance
    "performance_monitor",
    # Convenience functions
    "start_monitoring",
    "stop_monitoring",
    "get_performance_dashboard",
    "get_optimization_recommendations",
    "collect_metrics",
    "add_alert_callback",
]


# =============================================================================
# Global Performance Monitor Instance
# =============================================================================

performance_monitor = PerformanceMonitor()


# =============================================================================
# Convenience Functions (Clean Names)
# =============================================================================


async def start_monitoring():
    """Start comprehensive performance monitoring."""
    return await performance_monitor.start_monitoring()


async def stop_monitoring():
    """Stop performance monitoring."""
    await performance_monitor.stop_monitoring()


async def get_performance_dashboard() -> Dict[str, Any]:
    """Get performance dashboard."""
    return await performance_monitor.get_current_performance_dashboard()


async def get_optimization_recommendations() -> List[Dict[str, Any]]:
    """Get performance optimization recommendations."""
    return await performance_monitor.get_performance_optimization_recommendations()


async def collect_metrics() -> Dict[str, Any]:
    """Collect all performance metrics once."""
    return await performance_monitor.collect_all_metrics()


async def add_alert_callback(callback):
    """Add callback for performance alerts."""
    await performance_monitor.add_alert_callback(callback)


# =============================================================================
# Module Test
# =============================================================================

if __name__ == "__main__":
    import asyncio
    import json

    async def test_monitoring():
        """Test performance monitoring with metrics and recommendations."""
        print("Testing Performance Monitoring System...")  # noqa: print

        # Collect metrics
        metrics = await performance_monitor.collect_all_metrics()
        print(  # noqa: print
            f"Collected metrics: {json.dumps(metrics, indent=2, default=str)}"
        )  # noqa: print

        # Get dashboard
        dashboard = await performance_monitor.get_current_performance_dashboard()
        print(  # noqa: print
            f"Performance dashboard: {json.dumps(dashboard, indent=2, default=str)}"
        )  # noqa: print

        # Get recommendations
        recommendations = (
            await performance_monitor.get_performance_optimization_recommendations()
        )
        print(  # noqa: print
            f"Optimization recommendations: {json.dumps(recommendations, indent=2)}"
        )  # noqa: print

    # Run test
    asyncio.run(test_monitoring())
