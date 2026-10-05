# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Metric record types for the SLM monitoring modules (#16282).

Extracted from `performance_monitor.py`, which carries a recorded file-size
ceiling it may not exceed. These four are pure data -- no behaviour, no
imports beyond typing -- so they are the cheapest cohesive piece to lift out,
and lifting them is what makes room for changes inside the module.

Note for anyone searching: `models/schemas.py` defines a DIFFERENT
`SystemMetrics`, a pydantic `BaseModel` for the API surface. These are the
monitoring dataclasses; the two are unrelated and neither imports the other.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class SystemMetrics:
    """System performance metrics data class."""

    timestamp: str
    hostname: str
    cpu_percent: float
    memory_percent: float
    memory_available_gb: float
    disk_percent: float
    disk_free_gb: float
    load_average: List[float]
    network_sent_mb: float
    network_recv_mb: float
    process_count: int
    gpu_utilization: float | None = None
    gpu_memory_used: float | None = None
    npu_utilization: float | None = None


@dataclass
class ServiceMetrics:
    """Service-specific performance metrics."""

    timestamp: str
    service_name: str
    response_time: float
    status_code: int | None
    is_healthy: bool
    error_message: str | None = None
    custom_metrics: Dict[str, Any] | None = None


@dataclass
class DatabaseMetrics:
    """Database performance metrics."""

    timestamp: str
    database_type: str
    connection_time: float
    query_count: int
    memory_usage_mb: float
    operations_per_second: float
    error_count: int = 0
    database_size_mb: float | None = None


@dataclass
class InterVMMetrics:
    """Inter-VM communication performance metrics."""

    timestamp: str
    source_vm: str
    target_vm: str
    latency_ms: float
    throughput_mbps: float
    packet_loss_percent: float
    jitter_ms: float
