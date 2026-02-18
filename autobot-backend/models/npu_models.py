# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
NPU Worker Registry Pydantic Models

Data validation models for NPU worker management and load balancing.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from backend.constants.network_constants import NetworkConstants
from backend.constants.threshold_constants import CategoryDefaults
from pydantic import BaseModel, Field, validator

# Issue #380: Module-level tuple for URL scheme validation
_VALID_URL_SCHEMES = ("http://", "https://")


class WorkerStatus(str, Enum):
    """NPU worker status enumeration"""

    ONLINE = "online"
    OFFLINE = "offline"
    BUSY = "busy"
    ERROR = "error"
    UNKNOWN = "unknown"


class LoadBalancingStrategy(str, Enum):
    """Load balancing strategy enumeration"""

    ROUND_ROBIN = "round-robin"
    LEAST_LOADED = "least-loaded"
    WEIGHTED = "weighted"
    PRIORITY = "priority"


class NPUWorkerConfig(BaseModel):
    """NPU Worker Configuration Model"""

    id: str = Field(..., description="Unique worker identifier")
    name: str = Field(..., description="Human-readable worker name")
    url: str = Field(
        ...,
        description="Worker endpoint URL (see ServiceURLs.NPU_WORKER_WINDOWS_SERVICE)",
    )
    platform: str = Field(
        default="linux", description="Worker platform (linux, windows, macos)"
    )
    enabled: bool = Field(default=True, description="Whether worker is enabled")
    priority: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Worker priority (1-10, higher is more preferred)",
    )
    weight: int = Field(
        default=1, ge=1, le=100, description="Worker weight for weighted load balancing"
    )
    max_concurrent_tasks: int = Field(
        default=4, ge=1, description="Maximum concurrent tasks"
    )

    @validator("url")
    def validate_url(cls, v):
        """Validate URL format"""
        if not v.startswith(_VALID_URL_SCHEMES):  # Issue #380
            raise ValueError("URL must start with http:// or https://")
        return v.rstrip("/")

    @validator("id")
    def validate_id(cls, v):
        """Validate worker ID format"""
        if not v or len(v.strip()) == 0:
            raise ValueError("Worker ID cannot be empty")
        # Ensure ID is URL-safe
        if not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError(
                "Worker ID must contain only alphanumeric characters, hyphens, and underscores"
            )
        return v

    class Config:
        schema_extra = {
            "example": {
                "id": "npu-worker-1",
                "name": "Primary NPU Worker",
                "url": (
                    f"http://{NetworkConstants.MAIN_MACHINE_IP}:"
                    f"{NetworkConstants.NPU_WORKER_WINDOWS_PORT}"
                ),
                "platform": "linux",
                "enabled": True,
                "priority": 8,
                "weight": 2,
                "max_concurrent_tasks": 4,
            }
        }


class NPUWorkerStatus(BaseModel):
    """NPU Worker Runtime Status Model"""

    id: str = Field(..., description="Worker identifier")
    status: WorkerStatus = Field(
        default=WorkerStatus.UNKNOWN, description="Current worker status"
    )
    current_load: int = Field(
        default=0, ge=0, description="Current number of active tasks"
    )
    total_tasks_completed: int = Field(
        default=0, ge=0, description="Total tasks completed"
    )
    total_tasks_failed: int = Field(default=0, ge=0, description="Total tasks failed")
    uptime_seconds: float = Field(
        default=0.0, ge=0.0, description="Worker uptime in seconds"
    )
    last_heartbeat: Optional[datetime] = Field(
        default=None, description="Last successful heartbeat timestamp"
    )
    error_message: Optional[str] = Field(
        default=None, description="Latest error message if status is ERROR"
    )

    class Config:
        schema_extra = {
            "example": {
                "id": "npu-worker-1",
                "status": "online",
                "current_load": 2,
                "total_tasks_completed": 1523,
                "total_tasks_failed": 12,
                "uptime_seconds": 86400.5,
                "last_heartbeat": "2025-10-04T12:34:56Z",
                "error_message": None,
            }
        }


class NPUWorkerMetrics(BaseModel):
    """NPU Worker Performance Metrics Model"""

    id: str = Field(..., description="Worker identifier")
    avg_response_time_ms: float = Field(
        default=0.0, ge=0.0, description="Average response time in milliseconds"
    )
    success_rate: float = Field(
        default=100.0, ge=0.0, le=100.0, description="Success rate percentage"
    )
    requests_per_minute: float = Field(
        default=0.0, ge=0.0, description="Average requests per minute"
    )
    peak_load: int = Field(default=0, ge=0, description="Peak concurrent load observed")
    last_error_time: Optional[datetime] = Field(
        default=None, description="Timestamp of last error"
    )
    metrics_timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Metrics collection timestamp"
    )

    class Config:
        schema_extra = {
            "example": {
                "id": "npu-worker-1",
                "avg_response_time_ms": 245.8,
                "success_rate": 99.2,
                "requests_per_minute": 12.5,
                "peak_load": 4,
                "last_error_time": "2025-10-04T10:15:30Z",
                "metrics_timestamp": "2025-10-04T12:34:56Z",
            }
        }


class LoadBalancingConfig(BaseModel):
    """Load Balancing Configuration Model"""

    strategy: LoadBalancingStrategy = Field(
        default=LoadBalancingStrategy.LEAST_LOADED,
        description="Load balancing strategy to use",
    )
    health_check_interval: int = Field(
        default=30, ge=5, le=300, description="Health check interval in seconds (5-300)"
    )
    timeout_seconds: int = Field(
        default=10,
        ge=1,
        le=60,
        description="Worker health check timeout in seconds (1-60)",
    )
    retry_failed_workers: bool = Field(
        default=True,
        description="Automatically retry failed workers after cooldown period",
    )
    retry_cooldown_seconds: int = Field(
        default=60,
        ge=10,
        le=600,
        description="Cooldown period before retrying failed workers (10-600 seconds)",
    )

    class Config:
        schema_extra = {
            "example": {
                "strategy": "least-loaded",
                "health_check_interval": 30,
                "timeout_seconds": 10,
                "retry_failed_workers": True,
                "retry_cooldown_seconds": 60,
            }
        }


class NPUWorkerDetails(BaseModel):
    """Combined Worker Configuration and Status"""

    config: NPUWorkerConfig = Field(..., description="Worker configuration")
    status: NPUWorkerStatus = Field(..., description="Worker runtime status")
    metrics: Optional[NPUWorkerMetrics] = Field(
        default=None, description="Worker performance metrics"
    )

    def to_event_dict(self) -> Dict[str, Any]:
        """Convert to event dictionary format (Issue #372 - reduces feature envy)."""
        # Parse IP and port from URL
        ip_address = ""
        port = 0
        if "://" in self.config.url:
            url_parts = self.config.url.split("/")
            if len(url_parts) > 1:
                host_part = url_parts[2] if len(url_parts) > 2 else url_parts[1]
                if ":" in host_part:
                    ip_address = host_part.split(":")[0]
                    try:
                        port = int(host_part.split(":")[-1])
                    except ValueError:
                        port = 0

        return {
            "id": self.config.id,
            "name": self.config.name,
            "platform": self.config.platform,
            "ip_address": ip_address,
            "port": port,
            "status": self.status.status.value,
            "current_load": self.status.current_load,
            "max_capacity": self.config.max_concurrent_tasks,
            "uptime": f"{int(self.status.uptime_seconds)}s",
            "performance_metrics": self.metrics.dict() if self.metrics else {},
            "priority": self.config.priority,
            "weight": self.config.weight,
            "last_heartbeat": (
                self.status.last_heartbeat.isoformat() + "Z"
                if self.status.last_heartbeat
                else ""
            ),
            "created_at": "",  # Not tracked in current model
        }

    class Config:
        schema_extra = {
            "example": {
                "config": {
                    "id": "npu-worker-1",
                    "name": "Primary NPU Worker",
                    "url": (
                        f"http://{NetworkConstants.MAIN_MACHINE_IP}:"
                        f"{NetworkConstants.NPU_WORKER_WINDOWS_PORT}"
                    ),
                    "platform": "linux",
                    "enabled": True,
                    "priority": 8,
                    "weight": 2,
                    "max_concurrent_tasks": 4,
                },
                "status": {
                    "id": "npu-worker-1",
                    "status": "online",
                    "current_load": 2,
                    "total_tasks_completed": 1523,
                    "total_tasks_failed": 12,
                    "uptime_seconds": 86400.5,
                    "last_heartbeat": "2025-10-04T12:34:56Z",
                },
                "metrics": {
                    "id": "npu-worker-1",
                    "avg_response_time_ms": 245.8,
                    "success_rate": 99.2,
                    "requests_per_minute": 12.5,
                    "peak_load": 4,
                    "metrics_timestamp": "2025-10-04T12:34:56Z",
                },
            }
        }


class WorkerHeartbeat(BaseModel):
    """Heartbeat message from NPU worker for active telemetry"""

    worker_id: str = Field(..., description="Worker identifier")
    status: str = Field(default="online", description="Current worker status")
    platform: str = Field(
        default=CategoryDefaults.UNKNOWN,
        description="Worker platform (linux, windows, macos)",
    )
    url: str = Field(..., description="Worker's accessible URL for health checks")
    current_load: int = Field(
        default=0, ge=0, description="Current number of active tasks"
    )
    total_tasks_completed: int = Field(
        default=0, ge=0, description="Total tasks completed"
    )
    total_tasks_failed: int = Field(default=0, ge=0, description="Total tasks failed")
    uptime_seconds: float = Field(
        default=0.0, ge=0.0, description="Worker uptime in seconds"
    )
    npu_available: bool = Field(
        default=False, description="Whether NPU hardware is available"
    )
    loaded_models: list = Field(
        default_factory=list, description="List of loaded model names"
    )
    metrics: Optional[Dict[str, Any]] = Field(
        default=None, description="Performance metrics"
    )

    class Config:
        schema_extra = {
            "example": {
                "worker_id": "windows_npu_worker_abc123",
                "status": "online",
                "platform": "windows",
                "url": "http://192.168.168.21:8082",
                "current_load": 1,
                "total_tasks_completed": 42,
                "total_tasks_failed": 2,
                "uptime_seconds": 3600.5,
                "npu_available": True,
                "loaded_models": ["nomic-embed-text"],
                "metrics": {"avg_response_time_ms": 25.5, "cache_hit_rate": 85.2},
            }
        }


class WorkerTestResult(BaseModel):
    """Result of worker connection test"""

    worker_id: str = Field(..., description="Worker identifier")
    success: bool = Field(..., description="Whether test succeeded")
    response_time_ms: Optional[float] = Field(
        default=None, description="Response time in milliseconds"
    )
    status_code: Optional[int] = Field(default=None, description="HTTP status code")
    error_message: Optional[str] = Field(
        default=None, description="Error message if test failed"
    )
    health_data: Optional[Dict] = Field(
        default=None, description="Health check response data"
    )

    class Config:
        schema_extra = {
            "example": {
                "worker_id": "npu-worker-1",
                "success": True,
                "response_time_ms": 152.3,
                "status_code": 200,
                "error_message": None,
                "health_data": {
                    "status": "healthy",
                    "models_loaded": 2,
                    "available_memory_gb": 8.5,
                },
            }
        }
