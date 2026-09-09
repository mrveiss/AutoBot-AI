# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""NPU worker schemas (Issue #255 - NPU Fleet Integration).

Extracted verbatim from models/schemas.py, which sat at exactly its recorded
size ceiling (2335/2335). ``scripts/python_file_size_known_large.py`` says that
mapping ONLY SHRINKS -- "never add an entry to make a new file pass; split the
file instead" -- so the NPU block, which is self-contained and referenced
nowhere else in schemas.py, moves out whole. Pure move: no behaviour change.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, List

from pydantic import BaseModel, Field




class NPUDeviceType(str, Enum):
    """NPU device type enumeration."""

    INTEL_NPU = "intel-npu"
    NVIDIA_GPU = "nvidia-gpu"
    AMD_GPU = "amd-gpu"
    UNKNOWN = "unknown"


class NPULoadBalancingStrategy(str, Enum):
    """NPU load balancing strategy enumeration."""

    ROUND_ROBIN = "round-robin"
    LEAST_LOADED = "least-loaded"
    MODEL_AFFINITY = "model-affinity"


class NPUCapabilities(BaseModel):
    """NPU hardware capabilities."""

    models: List[str] = Field(default_factory=list)
    max_concurrent: int = Field(default=1, alias="maxConcurrent")
    memory_gb: float = Field(default=0.0, alias="memoryGB")
    device_type: str = Field(default="unknown", alias="deviceType")
    utilization: float = Field(default=0.0)

    model_config = {"populate_by_name": True}


class NPUNodeStatusResponse(BaseModel):
    """NPU node status response."""

    node_id: str
    capabilities: NPUCapabilities | None = None
    loaded_models: List[str] = Field(default_factory=list, alias="loadedModels")
    queue_depth: int = Field(default=0, alias="queueDepth")
    last_health_check: datetime | None = Field(None, alias="lastHealthCheck")
    detection_status: str = Field(default="pending", alias="detectionStatus")
    detection_error: str | None = Field(None, alias="detectionError")

    model_config = {"populate_by_name": True}


class NPULoadBalancingConfig(BaseModel):
    """NPU load balancing configuration."""

    strategy: str = "round-robin"
    model_affinity: Dict[str, List[str]] = Field(default_factory=dict, alias="modelAffinity")

    model_config = {"populate_by_name": True}


class NPUModelInfo(BaseModel):
    """NPU model information."""

    name: str
    size_mb: float = Field(default=0.0)
    loaded: bool = False
    inference_time_ms: float | None = None
    total_requests: int = 0


class NPUNodeListResponse(BaseModel):
    """List of NPU nodes with their status."""

    nodes: List[NPUNodeStatusResponse]
    total: int


class NPUDetectionRequest(BaseModel):
    """Request to trigger NPU capability detection."""

    force: bool = Field(default=False, description="Force re-detection")


class NPUDetectionResponse(BaseModel):
    """Response from NPU detection operation."""

    success: bool
    message: str
    node_id: str
    capabilities: NPUCapabilities | None = None


class NPURoleAssignResponse(BaseModel):
    """Response from NPU role assignment."""

    success: bool
    message: str
    node_id: str
    detection_triggered: bool = False


class NPUWorkerMetrics(BaseModel):
    """Performance metrics for an NPU worker node."""

    node_id: str
    utilization: float = 0.0
    temperature_celsius: float | None = None
    inference_count: int = 0
    avg_latency_ms: float = 0.0
    throughput_rps: float = 0.0
    queue_depth: int = 0
    memory_used_gb: float = 0.0
    memory_total_gb: float = 0.0
    uptime_seconds: int = 0
    error_count: int = 0
    timestamp: datetime | None = None

    model_config = {"populate_by_name": True}


class NPUFleetMetricsResponse(BaseModel):
    """Aggregate NPU fleet performance metrics."""

    total_nodes: int = 0
    online_nodes: int = 0
    total_inference_count: int = 0
    avg_utilization: float = 0.0
    avg_latency_ms: float = 0.0
    total_throughput_rps: float = 0.0
    total_queue_depth: int = 0
    node_metrics: List[NPUWorkerMetrics] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class NPUWorkerConfig(BaseModel):
    """Configuration for an individual NPU worker."""

    priority: int = Field(default=1, ge=1, le=10)
    weight: int = Field(default=1, ge=1, le=100)
    max_concurrent: int = Field(default=1, ge=1)
    failure_action: str = Field(default="retry")
    max_retries: int = Field(default=3, ge=0, le=10)
    assigned_models: List[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class NPUWorkerConfigResponse(BaseModel):
    """Response after updating worker config."""

    success: bool
    message: str
    node_id: str
    config: NPUWorkerConfig
