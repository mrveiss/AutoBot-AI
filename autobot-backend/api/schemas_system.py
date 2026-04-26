# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
System health, cache, NPU worker, wake-word, and feature-flag schemas.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from api.schemas_common import SuccessDataResponse, SuccessMessageResponse


# ---------------------------------------------------------------------------
# System schemas
# ---------------------------------------------------------------------------

class SystemFrontendConfigResponse(BaseModel):
    """Response for GET /frontend-config."""

    status: str
    config: Dict[str, Any]
    timestamp: str



class SystemHealthResponse(BaseModel):
    """Response for GET /health and GET /system/health.

    Shape varies between healthy/degraded/unhealthy paths — extra fields
    (cpu_percent, memory_percent, services, etc.) are allowed through.
    """

    model_config = {"extra": "allow"}

    status: str
    timestamp: str



class SystemInfoResponse(BaseModel):
    """Response for GET /info."""

    name: str
    version: str
    python_version: str
    timestamp: str
    features: Dict[str, Any]



class SystemReloadConfigResponse(BaseModel):
    """Response for POST /reload_config."""

    status: str
    message: str
    timestamp: str



class SystemPromptReloadResponse(BaseModel):
    """Response for GET /prompt_reload."""

    status: str
    message: str
    timestamp: str



class SystemAdminCheckResponse(BaseModel):
    """Response for GET /admin_check."""

    user: str
    admin: bool
    timestamp: str



class SystemDynamicImportResponse(BaseModel):
    """Response for POST /dynamic_import."""

    status: str
    message: str
    module_info: Dict[str, Any]
    timestamp: str



class SystemCacheStatsResponse(BaseModel):
    """Response for GET /cache/stats.

    Redis info and performance sections are dynamic — extra fields allowed.
    """

    model_config = {"extra": "allow"}

    timestamp: str
    cache: Dict[str, Any]



class SystemCacheActivityResponse(BaseModel):
    """Response for GET /cache/activity."""

    model_config = {"extra": "allow"}

    timestamp: str
    activity: Dict[str, Any]



class SystemMetricsResponse(BaseModel):
    """Response for GET /metrics.

    psutil-derived payload is dynamic; extra fields allowed through.
    """

    model_config = {"extra": "allow"}

    timestamp: str



class SystemCacheCoordinatorStatsResponse(BaseModel):
    """Response for GET /api/cache/stats.

    Shape is defined by CacheCoordinator.get_unified_stats() — opaque.
    """

    model_config = {"extra": "allow"}



class SystemCacheEvictResponse(BaseModel):
    """Response for POST /api/cache/evict."""

    status: str
    evicted: int
    timestamp: str



class SystemCacheClearResponse(BaseModel):
    """Response for POST /api/cache/clear/{cache_name}."""

    status: str
    cache: str
    timestamp: str



class SystemBackupStatusResponse(BaseModel):
    """Response for GET /system/backup/status.

    BackupScheduler.get_status() returns an opaque dict with a timestamp added.
    """

    model_config = {"extra": "allow"}

    timestamp: str


# ---------------------------------------------------------------------------
# agent_terminal.py schemas
# ---------------------------------------------------------------------------



class FeatureFlagStatusResponse(BaseModel):
    """Response for GET /feature-flags/status."""

    success: bool
    data: Optional[Any] = None



class FeatureFlagEnforcementModeResponse(SuccessDataResponse):
    """Response for PUT /feature-flags/enforcement-mode."""



class FeatureFlagEndpointSetResponse(SuccessDataResponse):
    """Response for PUT /feature-flags/endpoint/{endpoint:path}."""



class FeatureFlagEndpointRemoveResponse(SuccessDataResponse):
    """Response for DELETE /feature-flags/endpoint/{endpoint:path}."""



class NPUStatusResponse(BaseModel):
    """Response for GET /npu/status."""

    status: str
    total_workers: int
    online_workers: int
    offline_workers: int
    total_capacity: int
    current_load: int
    utilization_percent: float
    load_balancing_strategy: str



class NPUWorkerUnpairResponse(SuccessMessageResponse):
    """Response for POST /npu/workers/{worker_id}/unpair."""

    worker_id: str



class NPUWorkerRepairResponse(SuccessMessageResponse):
    """Response for POST /npu/workers/{worker_id}/repair."""

    old_worker_id: str
    new_worker_id: str
    config: Dict[str, Any]
    server_timestamp: str



class NPUWorkerPairResponse(SuccessMessageResponse):
    """Response for POST /npu/workers/pair."""

    worker_id: str
    url: str
    platform: str
    device_info: Dict[str, Any]
    paired_at: str



class NPUWorkerHeartbeatResponse(BaseModel):
    """Response for POST /npu/workers/heartbeat."""

    acknowledged: bool
    worker_id: str
    server_timestamp: str
    message: str



class NPUPoolWorkersResponse(BaseModel):
    """Response for GET /npu/pool/workers."""

    workers: List[Any]



class NPUPoolReloadResponse(SuccessMessageResponse):
    """Response for POST /npu/pool/reload."""

    workers_loaded: int




# ---------------------------------------------------------------------------
# wake_word.py schemas  (Issue #5317)
# ---------------------------------------------------------------------------



class WakeWordListResponse(BaseModel):
    """Response for GET /words."""

    wake_words: List[str]
    total: int



class WakeWordMutateResponse(SuccessMessageResponse):
    """Response for POST /words and DELETE /words/{wake_word}."""

    wake_words: List[str]



class WakeWordConfigUpdateResponse(SuccessMessageResponse):
    """Response for PUT /config."""

    config: Dict[str, Any]



class WakeWordStatsResetResponse(SuccessMessageResponse):
    """Response for POST /stats/reset."""

    stats: Dict[str, Any]



class WakeWordFeedbackResponse(SuccessMessageResponse):
    """Response for POST /feedback."""

    stats: Dict[str, Any]



class WakeWordToggleResponse(SuccessMessageResponse):
    """Response for POST /enable and POST /disable."""

    config: Dict[str, Any]



class WakeWordListeningToggleResponse(SuccessMessageResponse):
    """Response for POST /listening/start and POST /listening/stop."""

    status: Dict[str, Any]


# ---------------------------------------------------------------------------
# analytics_cost.py schemas  (Issue #5317)
# ---------------------------------------------------------------------------



class AdminFileListResponse(BaseModel):
    """Response for GET /files (admin list directory)."""

    files: List[Any]



class AdminFileReadResponse(BaseModel):
    """Response for GET /files/read (admin read file)."""

    content: str


# ---------------------------------------------------------------------------
# secrets.py schemas  (Issue #5912)
# ---------------------------------------------------------------------------



class SecretsStatusResponse(BaseModel):
    """Response for GET /secrets/status."""

    status: str
    service: str
    total_secrets: Optional[int] = None
    storage_backend: Optional[str] = None
    encryption_enabled: Optional[bool] = None
    error: Optional[str] = None
    timestamp: str


# ---------------------------------------------------------------------------
# log_forwarding.py schemas  (Issue #5912)
# ---------------------------------------------------------------------------



class LogForwardingDestinationItem(BaseModel):
    """Single destination entry in list/detail responses.

    Shape from dest.config.to_dict_sanitized() + extra health fields.
    Extra fields allowed to handle dynamic config dict.
    """

    model_config = {"extra": "allow"}

    healthy: bool
    last_error: Optional[str] = None
    sent_count: int
    failed_count: int


class LogForwardingDestinationsListResponse(BaseModel):
    """Response for GET /log-forwarding/destinations — returns a list directly."""

    model_config = {"extra": "allow"}
