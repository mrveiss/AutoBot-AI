# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Performance Monitoring Package

This package contains the performance monitoring system for AutoBot.
It was split from the monolithic performance_monitor.py as part of Issue #381.

Package Structure:
- types.py: Constants and type definitions
- metrics.py: Dataclasses for all metric types
- hardware.py: Hardware detection utilities
- collectors.py: Metric collection classes
- analyzers.py: Alert analysis and recommendations
- decorator.py: Performance monitoring decorator
- monitor.py: Main PerformanceMonitor class

Usage:
    from utils.performance_monitoring import (
        # Main monitor class
        PerformanceMonitor,
        # Metrics dataclasses
        GPUMetrics, NPUMetrics, MultiModalMetrics,
        SystemPerformanceMetrics, ServicePerformanceMetrics,
        # Collectors
        GPUCollector, NPUCollector, SystemCollector,
        ServiceCollector, MultiModalCollector,
        # Analyzers
        AlertAnalyzer, RecommendationGenerator,
        # Hardware detection
        HardwareDetector,
        # Decorator
        monitor_performance,
        # Constants
        CRITICAL_SERVICE_STATUSES, DEFAULT_PERFORMANCE_BASELINES,
    )

For backward compatibility, the original performance_monitor.py module
still exports all classes and functions directly.
"""

# Analyzers
from backend.utils.performance_monitoring.analyzers import (
    AlertAnalyzer,
    RecommendationGenerator,
)

# Collectors
from backend.utils.performance_monitoring.collectors import (
    GPUCollector,
    MultiModalCollector,
    NPUCollector,
    ServiceCollector,
    SystemCollector,
)

# Decorator
from backend.utils.performance_monitoring.decorator import (
    monitor_performance,
    set_redis_client,
)

# Hardware detection
from backend.utils.performance_monitoring.hardware import HardwareDetector

# Metrics dataclasses
from backend.utils.performance_monitoring.metrics import (
    GPUMetrics,
    MultiModalMetrics,
    NPUMetrics,
    ServicePerformanceMetrics,
    SystemPerformanceMetrics,
)

# Main monitor class
from backend.utils.performance_monitoring.monitor import PerformanceMonitor

# Types and constants
from backend.utils.performance_monitoring.types import (
    AUTOBOT_PROCESS_KEYWORDS,
    CRITICAL_SERVICE_STATUSES,
    DEFAULT_COLLECTION_INTERVAL,
    DEFAULT_PERFORMANCE_BASELINES,
    DEFAULT_RETENTION_HOURS,
)

# Re-export for convenience
__all__ = [
    # Main class
    "PerformanceMonitor",
    # Metrics
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
]
