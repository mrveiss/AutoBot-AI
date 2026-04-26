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


# ---------------------------------------------------------------------------
# files.py schemas  (Issue #5960)
# ---------------------------------------------------------------------------



class FileViewResponse(BaseModel):
    """Response for GET /files/view/{path} — file info + optional text content."""

    file_info: Any
    content: Optional[str] = None
    is_text: bool



class FileRenameResponse(BaseModel):
    """Response for POST /files/rename."""

    message: str
    item_info: Any



class FilePreviewResponse(BaseModel):
    """Response for GET /files/preview."""

    type: str
    url: str
    content: Optional[str] = None
    mime_type: Optional[str] = None
    size: Optional[int] = None
    name: Optional[str] = None



class FileDeleteResponse(BaseModel):
    """Response for DELETE /files/delete.

    Returns message only; shape varies slightly between file and dir paths.
    """

    model_config = {"extra": "allow"}

    message: str



class DirectoryCreateResponse(BaseModel):
    """Response for POST /files/create_directory."""

    message: str
    directory_info: Any



class DirectoryTreeResponse(BaseModel):
    """Response for GET /files/tree."""

    path: str
    tree: List[Any]



class FileStatsResponse(BaseModel):
    """Response for GET /files/stats."""

    sandbox_root: str
    total_files: int
    total_directories: int
    total_size: int
    total_size_mb: float
    max_file_size_mb: int
    allowed_extensions: List[str]


# ---------------------------------------------------------------------------
# integration_github.py schemas  (Issue #5960)
# ---------------------------------------------------------------------------



class GitHubPullRequestsResponse(BaseModel):
    """Response for GET /{owner}/{repo}/pull-requests — opaque GitHub list."""

    model_config = {"extra": "allow"}



class GitHubPullRequestResponse(BaseModel):
    """Response for GET /{owner}/{repo}/pull-requests/{pull_number} — opaque."""

    model_config = {"extra": "allow"}



class GitHubPullRequestDiffResponse(BaseModel):
    """Response for GET /{owner}/{repo}/pull-requests/{pull_number}/diff — opaque."""

    model_config = {"extra": "allow"}



class GitHubPRCommentsResponse(BaseModel):
    """Response for GET /{owner}/{repo}/pull-requests/{pull_number}/comments — opaque."""

    model_config = {"extra": "allow"}



class GitHubPRCommentResponse(BaseModel):
    """Response for POST /{owner}/{repo}/pull-requests/{pull_number}/comments — opaque."""

    model_config = {"extra": "allow"}



class GitHubPRReviewResponse(BaseModel):
    """Response for POST /{owner}/{repo}/pull-requests/{pull_number}/reviews — opaque."""

    model_config = {"extra": "allow"}



class GitHubIssuesResponse(BaseModel):
    """Response for GET /{owner}/{repo}/issues — opaque GitHub list."""

    model_config = {"extra": "allow"}



class GitHubIssueResponse(BaseModel):
    """Response for GET /{owner}/{repo}/issues/{issue_number} — opaque."""

    model_config = {"extra": "allow"}



class GitHubRepositoryResponse(BaseModel):
    """Response for GET /{owner}/{repo} — opaque GitHub repo metadata."""

    model_config = {"extra": "allow"}



class GitHubCommitsResponse(BaseModel):
    """Response for GET /{owner}/{repo}/commits — opaque GitHub list."""

    model_config = {"extra": "allow"}



class GitHubCommitResponse(BaseModel):
    """Response for GET /{owner}/{repo}/commits/{ref} — opaque."""

    model_config = {"extra": "allow"}



class GitHubRepositoryTreeResponse(BaseModel):
    """Response for GET /{owner}/{repo}/tree/{tree_sha} — opaque."""

    model_config = {"extra": "allow"}



class GitHubFileContentsResponse(BaseModel):
    """Response for GET /{owner}/{repo}/contents/{path} — opaque."""

    model_config = {"extra": "allow"}



class GitHubProviderInfo(BaseModel):
    """Single provider descriptor returned by GET /providers."""

    id: str
    name: str
    description: str
    required_settings: List[str]
    optional_settings: List[str]


# ---------------------------------------------------------------------------
# redis.py schemas  (Issue #5990)
# ---------------------------------------------------------------------------


class RedisConfigResponse(BaseModel):
    """Response for GET /config and POST /config in redis.py.

    ConfigService.get_redis_config() returns these fields; extra fields
    allowed for additional redis_config keys.
    """

    model_config = {"extra": "allow"}

    type: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None


class RedisConnectionStatusResponse(BaseModel):
    """Response for GET /status, POST /test_connection in redis.py.

    ConnectionTester.test_redis_connection() returns status + message at minimum;
    connected path adds host/port/redis_search_module_loaded. Extra fields allowed.
    """

    model_config = {"extra": "allow"}

    status: str
    message: Optional[str] = None


class RedisHealthResponse(BaseModel):
    """Response for GET /health in redis.py."""

    status: str
    redis_status: Optional[str] = None
    message: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    redis_search_module_loaded: bool = False


# ---------------------------------------------------------------------------
# services.py schemas  (Issue #5990)
# ---------------------------------------------------------------------------


class ServicesHealthDeprecatedResponse(BaseModel):
    """Response for GET /health (deprecated) in services.py."""

    status: str
    deprecated: bool
    use_instead: str
    timestamp: Any


class ServicesHealthAggregateResponse(BaseModel):
    """Response for GET /services/health in services.py."""

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# vision.py schemas  (Issue #5991)
# ---------------------------------------------------------------------------


class VisionElementItem(BaseModel):
    """Single UI element entry in VisionDetectElementsResponse."""

    element_id: str
    element_type: str
    bbox: Any
    center_point: List[float]
    confidence: float
    text_content: Optional[str] = None
    possible_interactions: List[str]



class VisionDetectElementsResponse(BaseModel):
    """Response for POST /vision/elements."""

    total_detected: int
    filtered_count: int
    elements: List[VisionElementItem]
    filter_applied: Dict[str, Any]



class VisionOCRResponse(BaseModel):
    """Response for POST /vision/ocr."""

    region_specified: bool
    text_regions: List[Any]
    total_text_regions: int
    region: Optional[Dict[str, Any]] = None



class VisionAutomationOpportunitiesResponse(BaseModel):
    """Response for GET /vision/automation-opportunities."""

    opportunities: List[Any]
    total_opportunities: int
    context: Any
    confidence: float



class VisionElementTypeItem(BaseModel):
    """Single element-type descriptor."""

    value: str
    name: str
    description: str



class VisionElementTypesResponse(BaseModel):
    """Response for GET /vision/element-types."""

    element_types: List[VisionElementTypeItem]
    total_types: int



class VisionInteractionTypeItem(BaseModel):
    """Single interaction-type descriptor."""

    value: str
    name: str
    description: str



class VisionInteractionTypesResponse(BaseModel):
    """Response for GET /vision/interaction-types."""

    interaction_types: List[VisionInteractionTypeItem]
    total_types: int



class VisionLayoutResponse(BaseModel):
    """Response for GET /vision/layout."""

    layout_structure: Any
    dominant_colors: Any
    timestamp: Any



class VisionStatusFeaturesResponse(BaseModel):
    """Nested features dict in VisionStatusResponse."""

    screen_analysis: bool
    element_detection: bool
    ocr_extraction: bool
    template_matching: bool
    multimodal_processing: bool



class VisionStatusResponse(BaseModel):
    """Response for GET /vision/status.

    Error path returns only service+status+error — extra fields allowed.    """

    model_config = {"extra": "allow"}

    timestamp: Optional[float] = None
    overall_status: Optional[str] = None
    total_services: Optional[int] = None
    healthy_services: Optional[int] = None
    degraded_services: Optional[int] = None
    critical_services: Optional[int] = None


class VMStatusItem(BaseModel):
    """A single VM entry in ServicesVMsStatusResponse."""

    name: str
    ip: str
    status: str
    services: List[Any] = []
    last_check: Optional[Any] = None


class ServicesVMsStatusResponse(BaseModel):
    """Response for GET /vms/status in services.py."""

    vms: List[VMStatusItem]
    total_count: int
    online_count: int
    offline_count: int
    overall_status: str
    last_updated: Any


# ---------------------------------------------------------------------------
# wake_word.py schemas  (Issue #5990)
# ---------------------------------------------------------------------------


class WakeWordGetWordsResponse(BaseModel):
    """Response for GET /words in wake_word.py."""

    wake_words: List[str]
    total: int


class WakeWordGetConfigResponse(BaseModel):
    """Response for GET /config in wake_word.py.

    WakeWordDetector.get_config() returns these fields.
    """

    enabled: bool
    wake_words: List[str]
    confidence_threshold: float
    cooldown_seconds: float
    max_false_positive_rate: float
    adaptive_threshold: bool
    noise_tolerance: Optional[float] = None
    max_cpu_percent: Optional[float] = None


class WakeWordStatsResponse(BaseModel):
    """Response for GET /stats in wake_word.py.

    WakeWordDetector.get_stats() return shape.
    """

    total_detections: int
    true_positives: int
    false_positives: int
    accuracy: float
    average_confidence: float
    total_listening_time: float
    cpu_usage_percent: float


class WakeWordListeningStatusResponse(BaseModel):
    """Response for GET /listening/status in wake_word.py."""

    active: bool
    duty_cycle_ms: float
    sleep_ms: float
    chunks_processed: int
    throttle_events: int
    current_cpu_percent: float
    max_cpu_percent: float


# ---------------------------------------------------------------------------
# developer.py schemas  (Issue #5990)
# ---------------------------------------------------------------------------


class DeveloperEndpointsResponse(BaseModel):
    """Response for GET /endpoints in developer.py."""

    total_endpoints: int
    routers: List[str]
    endpoints: Dict[str, Any]


class DeveloperConfigResponse(BaseModel):
    """Response for GET /config in developer.py."""

    enabled: bool
    enhanced_errors: bool
    endpoint_suggestions: bool
    debug_logging: bool


class DeveloperConfigUpdateResponse(BaseModel):
    """Response for POST /config in developer.py."""

    status: str
    config: Dict[str, Any]


class DeveloperSystemInfoResponse(BaseModel):
    """Response for GET /system-info in developer.py.

    Returns opaque config sections from unified_config_manager. Extra fields allowed.
    """

    model_config = {"extra": "allow"}

    config_loaded: bool
    available_routers: List[str]


# ---------------------------------------------------------------------------
# startup.py schemas  (Issue #5990)
# ---------------------------------------------------------------------------


class StartupStatusResponse(BaseModel):
    """Response for GET /status in startup.py."""

    current_phase: str
    progress: int
    messages: List[Any]
    elapsed_time: float
    is_ready: bool


# ---------------------------------------------------------------------------
# hot_reload.py schemas  (Issue #5990)
# ---------------------------------------------------------------------------


class HotReloadHealthResponse(BaseModel):
    """Response for GET /health in hot_reload.py."""

    status: str
    running: bool
    watched_modules: int
    watched_paths: int
    service: str


# ---------------------------------------------------------------------------
# service_monitor.py schemas  (Issue #5990)
# ---------------------------------------------------------------------------


class ServiceStatusItem(BaseModel):
    """A single service entry in ServiceMonitorServicesResponse."""

    status: str
    health: str


class ServiceMonitorServicesResponse(BaseModel):
    """Response for GET /services in service_monitor.py."""

    services: Dict[str, ServiceStatusItem]


class VMStatusListItem(BaseModel):
    """A single VM entry in ServiceMonitorVMsResponse."""

    name: str
    status: str
    message: str


class ServiceMonitorVMsResponse(BaseModel):
    """Response for GET /vms/status in service_monitor.py."""

    vms: List[VMStatusListItem]


# ---------------------------------------------------------------------------
# infrastructure.py schemas  (Issue #5990)
# ---------------------------------------------------------------------------


class InfrastructureHostItem(BaseModel):
    """A single infrastructure host entry.

    Derived from _load_secrets_hosts() in infrastructure.py.
    """

    id: str
    name: str
    host: str
    ssh_port: int
    vnc_port: Optional[int] = None
    username: str
    os: Optional[str] = None
    description: str
    capabilities: List[str]


class InfrastructureHostsResponse(BaseModel):
    """Response for GET /hosts in infrastructure.py."""

    hosts: List[InfrastructureHostItem]


# ---------------------------------------------------------------------------
# heartbeat.py schemas  (Issue #5990)
# ---------------------------------------------------------------------------


class HeartbeatWakeupQueuedResponse(BaseModel):
    """Response for POST /{agent_id}/wakeup in heartbeat.py."""

    id: str
    agent_id: str
    status: str


class HeartbeatTriggerResponse(BaseModel):
    """Response for POST /{agent_id}/trigger in heartbeat.py."""

    agent_id: str
    status: str


# ---------------------------------------------------------------------------
# alertmanager_webhook.py schemas  (Issue #5990)
# ---------------------------------------------------------------------------


class AlertManagerWebhookReceiveResponse(BaseModel):
    """Response for POST /alertmanager in alertmanager_webhook.py."""

    status: str
    processed: int
    timestamp: str


class AlertManagerWebhookHealthResponse(BaseModel):
    """Response for GET /alertmanager/health in alertmanager_webhook.py."""

    status: str
    endpoint: str
    websocket_manager: str
    timestamp: str


# ---------------------------------------------------------------------------
# overseer_handlers.py schemas  (Issue #5990)
# ---------------------------------------------------------------------------


class OverseerStatusResponse(BaseModel):
    """Response for GET /status/{session_id} in overseer_handlers.py."""

    active: bool
    summary: Optional[Any] = None


# ---------------------------------------------------------------------------
# project_state.py schemas  (Issue #5990)
# ---------------------------------------------------------------------------


class ProjectStateHealthResponse(BaseModel):
    """Response for GET /health in project_state.py."""

    status: str
    current_phase: str
    overall_completion: float
    timestamp: Optional[str] = None


# ---------------------------------------------------------------------------
# playwright.py embedded endpoints schemas  (Issue #5991)
# ---------------------------------------------------------------------------



class PlaywrightEmbeddedResultResponse(BaseModel):
    """Response for POST /playwright/search, /test-frontend, /send-test-message,
    and /screenshot.

    Shape comes from embedded Playwright service helpers and is opaque;
    extra fields allowed through.
    """

    model_config = {"extra": "allow"}

    success: bool


# ---------------------------------------------------------------------------
# multimodal.py schemas  (Issue #5991)
# ---------------------------------------------------------------------------



class MultimodalHealthResponse(BaseModel):
    """Response for GET /multimodal/health."""

    status: str
    timestamp: float
    gpu_available: bool
    processor_ready: bool
    performance_monitoring: bool
    mixed_precision_enabled: bool