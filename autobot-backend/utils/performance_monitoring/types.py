# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Performance Monitoring Types Module

Contains constants and type definitions for performance monitoring.

Extracted from performance_monitor.py as part of Issue #381 refactoring.
"""

from typing import FrozenSet

# Issue #380: Module-level frozenset for critical service status checks
CRITICAL_SERVICE_STATUSES: FrozenSet[str] = frozenset({"critical", "offline"})

# Default performance baselines and thresholds
DEFAULT_PERFORMANCE_BASELINES = {
    "gpu_utilization_target": 80.0,  # Target GPU utilization for AI workloads
    "npu_acceleration_target": 5.0,  # Target 5x speedup over CPU
    "multimodal_pipeline_efficiency": 85.0,  # Target pipeline efficiency
    "api_response_time_threshold": 200.0,  # 200ms threshold
    "memory_usage_warning": 80.0,  # 80% memory usage warning
    "cpu_load_warning": 16.0,  # Load average warning for 22-core system
}

# Collection settings
DEFAULT_COLLECTION_INTERVAL = 5.0  # Collect metrics every 5 seconds
DEFAULT_RETENTION_HOURS = 24

# AutoBot process keywords for identification
AUTOBOT_PROCESS_KEYWORDS = [
    "autobot",
    "fast_app_factory",
    "run_autobot",
    "npu-worker",
    "ai-stack",
    "browser-service",
    "redis-stack",
]
