# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Performance Monitoring Metrics Module

Contains dataclasses for performance metrics:
- GPUMetrics: GPU performance data
- NPUMetrics: Intel NPU acceleration data
- MultiModalMetrics: Multi-modal AI processing data
- SystemPerformanceMetrics: System resource data
- ServicePerformanceMetrics: Distributed service data

Extracted from performance_monitor.py as part of Issue #381 refactoring.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class GPUMetrics:
    """Comprehensive GPU performance metrics."""

    timestamp: float
    name: str
    utilization_percent: float
    memory_used_mb: int
    memory_total_mb: int
    memory_free_mb: int
    memory_utilization_percent: float
    temperature_celsius: int
    power_draw_watts: float
    gpu_clock_mhz: int
    memory_clock_mhz: int
    fan_speed_percent: Optional[int] = None
    encoder_utilization: Optional[int] = None
    decoder_utilization: Optional[int] = None
    performance_state: Optional[str] = None  # P0-P12
    thermal_throttling: bool = False
    power_throttling: bool = False

    def to_query_dict(self) -> Dict[str, Any]:
        """Convert to dict for query response (Issue #372 - reduces feature envy)."""
        return {
            "timestamp": self.timestamp,
            "utilization_percent": self.utilization_percent,
            "memory_utilization_percent": self.memory_utilization_percent,
            "temperature_celsius": self.temperature_celsius,
            "power_draw_watts": self.power_draw_watts,
        }


@dataclass
class NPUMetrics:
    """Intel NPU acceleration metrics."""

    timestamp: float
    hardware_detected: bool
    driver_available: bool
    openvino_support: bool
    utilization_percent: float
    inference_count: int
    average_inference_time_ms: float
    model_cache_hits: int
    model_cache_misses: int
    thermal_state: str  # "normal", "throttling", "critical"
    power_efficiency_rating: float  # 0-100
    acceleration_ratio: float  # NPU vs CPU speedup
    wsl_limitation: bool = False

    def to_query_dict(self) -> Dict[str, Any]:
        """Convert to dict for query response (Issue #372 - reduces feature envy)."""
        return {
            "timestamp": self.timestamp,
            "utilization_percent": self.utilization_percent,
            "acceleration_ratio": self.acceleration_ratio,
            "inference_count": self.inference_count,
            "average_inference_time_ms": self.average_inference_time_ms,
        }


@dataclass
class MultiModalMetrics:
    """Multi-modal AI processing performance metrics."""

    timestamp: float
    text_processing_time_ms: float
    image_processing_time_ms: float
    audio_processing_time_ms: float
    combined_processing_time_ms: float
    pipeline_efficiency: float  # 0-100
    memory_peak_usage_mb: float
    gpu_acceleration_used: bool
    npu_acceleration_used: bool
    batch_size: int
    throughput_items_per_second: float
    error_rate_percent: float


@dataclass
class SystemPerformanceMetrics:
    """Comprehensive system performance snapshot."""

    # ALL REQUIRED FIELDS FIRST (no default values)
    timestamp: float

    # CPU Performance (Intel Ultra 9 185H - 22 cores)
    cpu_usage_percent: float
    cpu_cores_physical: int
    cpu_cores_logical: int
    cpu_frequency_mhz: float
    cpu_load_1m: float
    cpu_load_5m: float
    cpu_load_15m: float

    # Memory Performance
    memory_total_gb: float
    memory_used_gb: float
    memory_available_gb: float
    memory_usage_percent: float
    swap_usage_percent: float

    # Storage I/O Performance
    disk_read_mb_s: float
    disk_write_mb_s: float
    disk_usage_percent: float
    disk_queue_depth: float

    # Network Performance
    network_upload_mb_s: float
    network_download_mb_s: float
    network_latency_ms: float
    network_packet_loss_percent: float

    # ALL OPTIONAL FIELDS LAST (with default values)
    # CPU Optional
    cpu_temperature_celsius: Optional[float] = None
    per_core_usage: List[float] = field(default_factory=list)

    # Memory Optional
    memory_bandwidth_gb_s: Optional[float] = None

    # Storage Optional
    nvme_temperature_celsius: Optional[float] = None

    # AutoBot Process Performance
    autobot_processes: List[Dict[str, Any]] = field(default_factory=list)
    autobot_memory_usage_mb: float = 0
    autobot_cpu_usage_percent: float = 0

    def to_query_dict(self) -> Dict[str, Any]:
        """Convert to dict for query response (Issue #372 - reduces feature envy)."""
        return {
            "timestamp": self.timestamp,
            "cpu_usage_percent": self.cpu_usage_percent,
            "memory_usage_percent": self.memory_usage_percent,
            "cpu_load_1m": self.cpu_load_1m,
            "network_latency_ms": self.network_latency_ms,
        }


@dataclass
class ServicePerformanceMetrics:
    """Distributed service performance metrics."""

    timestamp: float
    service_name: str
    host: str
    port: int
    status: str  # "healthy", "degraded", "critical", "offline"
    response_time_ms: float
    throughput_requests_per_second: float
    error_rate_percent: float
    uptime_hours: float
    memory_usage_mb: float
    cpu_usage_percent: float
    health_score: float  # 0-100
