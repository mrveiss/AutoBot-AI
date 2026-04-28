# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
System health, cache, NPU worker, wake-word, and feature-flag schemas.
"""

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

from api.schemas_common import SuccessDataResponse, SuccessMessageResponse
from constants.threshold_constants import RetryConfig
from type_defs.common import Metadata


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


# ---------------------------------------------------------------------------
# permissions.py schemas
# ---------------------------------------------------------------------------


class PermissionRuleMutateResponse(BaseModel):
    """Response for POST/DELETE /permissions/rules."""

    status: str
    message: str


class PermissionClearApprovalsResponse(BaseModel):
    """Response for DELETE /permissions/memory/{project_path}."""

    status: str
    message: str


class PermissionStoreApprovalResponse(BaseModel):
    """Response for POST /permissions/memory."""

    status: str
    message: str


class PermissionMemoryStatsResponse(BaseModel):
    """Response for GET /permissions/memory/stats."""

    enabled: bool
    redis_available: Optional[bool] = None
    total_project_user_combinations: Optional[int] = None
    ttl_seconds: Optional[int] = None
    ttl_days: Optional[int] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# permissions.py remaining schemas (#6042)
# ---------------------------------------------------------------------------


class PermissionModeResponse(BaseModel):
    mode: str
    enabled: bool
    is_admin_only: bool
    allowed_modes: List[str]


class PermissionModeRequest(BaseModel):
    mode: str = Field(..., description="Permission mode to set")


class PermissionRuleResponse(BaseModel):
    tool: str
    pattern: str
    action: str
    description: str


class PermissionRulesResponse(BaseModel):
    allow: List[PermissionRuleResponse]
    ask: List[PermissionRuleResponse]
    deny: List[PermissionRuleResponse]


class PermissionAddRuleRequest(BaseModel):
    tool: str = Field(default="Bash", description="Tool name")
    pattern: str = Field(..., description="Glob pattern")
    action: str = Field(..., description="allow, ask, or deny")
    description: str = Field(default="", description="Rule description")


class PermissionRemoveRuleRequest(BaseModel):
    tool: str = Field(default="Bash", description="Tool name")
    pattern: str = Field(..., description="Pattern to remove")


class ApprovalRecordResponse(BaseModel):
    pattern: str
    tool: str
    risk_level: str
    user_id: str
    created_at: float
    original_command: str
    comment: Optional[str] = None


class ProjectApprovalsResponse(BaseModel):
    project_path: str
    approvals: List[ApprovalRecordResponse]


class PermissionStatusResponse(BaseModel):
    enabled: bool
    mode: str
    approval_memory_enabled: bool
    approval_memory_ttl_days: int
    rules_file: str
    rules_count: dict


class CheckCommandRequest(BaseModel):
    command: str = Field(..., description="Command to check")
    tool: str = Field(default="Bash", description="Tool name")


class CheckCommandResponse(BaseModel):
    result: str
    pattern: Optional[str] = None
    description: Optional[str] = None


# ---------------------------------------------------------------------------
# vnc_manager.py schemas (#6042)
# ---------------------------------------------------------------------------


class VncRunningResponse(BaseModel):
    running: bool


class VncStatusMessageResponse(BaseModel):
    status: str
    message: str


class VncScreenshotResponse(BaseModel):
    status: str
    message: str
    image_data: str


class MacroStopResponse(BaseModel):
    status: str
    message: str
    action_count: int


class MacroListResponse(BaseModel):
    macros: List[Dict[str, Any]]


class VncQualityMetricsResponse(BaseModel):
    vnc_running: bool
    timestamp: str
    vnc_port_reachable: Optional[bool] = None
    latency_ms: Optional[float] = None
    websockify_running: Optional[bool] = None
    websockify_processes: Optional[int] = None


class VncDesktopContextResponse(BaseModel):
    system: Dict[str, str]
    desktop: Dict[str, str]
    processes: List[Dict[str, str]]
    timestamp: str


class VncOcrResponse(BaseModel):
    status: str
    text: str
    message: str


class VncFindImageResponse(BaseModel):
    status: str
    found: bool
    message: str
    x: Optional[int] = None
    y: Optional[int] = None
    confidence: Optional[float] = None


class WaitForTextResponse(BaseModel):
    status: str
    found: bool
    message: str


class WaitForImageResponse(BaseModel):
    status: str
    found: bool
    message: str
    x: Optional[int] = None
    y: Optional[int] = None
    confidence: Optional[float] = None


class RestoreStateResponse(BaseModel):
    status: str
    message: str
    state: Optional[Dict[str, Any]] = None


class SessionActionLogResponse(BaseModel):
    status: str
    actions: List[Dict[str, Any]]
    message: str


class SessionScreenshotsResponse(BaseModel):
    status: str
    screenshots: List[str]
    message: str


class SessionScreenshotSaveResponse(BaseModel):
    status: str
    message: str
    screenshot_path: Optional[str] = None


class MouseClickRequest(BaseModel):
    x: int = Field(..., ge=0, description="X coordinate")
    y: int = Field(..., ge=0, description="Y coordinate")
    button: str = Field(default="left", description="Mouse button: left, middle, right")


class KeyboardTypeRequest(BaseModel):
    text: str = Field(..., description="Text to type")


class SpecialKeyRequest(BaseModel):
    key: str = Field(..., description="Special key name (e.g., Return, Escape, ctrl+c)")


class MouseScrollRequest(BaseModel):
    direction: str = Field(..., description="Scroll direction: up or down")
    amount: int = Field(default=3, ge=1, le=10, description="Scroll amount (1-10)")


class MouseDragRequest(BaseModel):
    x1: int = Field(..., ge=0, description="Start X coordinate")
    y1: int = Field(..., ge=0, description="Start Y coordinate")
    x2: int = Field(..., ge=0, description="End X coordinate")
    y2: int = Field(..., ge=0, description="End Y coordinate")


class ClipboardSyncRequest(BaseModel):
    content: str = Field(..., description="Text content to copy to clipboard")


class ConnectionQualitySettings(BaseModel):
    compression_level: int = Field(
        default=6, ge=0, le=9, description="Compression level (0=none, 9=max)"
    )
    quality: int = Field(
        default=6, ge=0, le=9, description="JPEG quality (0=poor, 9=best)"
    )
    encoding: str = Field(
        default="tight", description="Encoding method: tight, hextile, raw"
    )


class ConnectionSettings(BaseModel):
    auto_reconnect: bool = Field(
        default=True, description="Enable auto-reconnect on disconnect"
    )
    reconnect_delay_ms: int = Field(
        default=3000, ge=1000, le=30000, description="Delay before reconnect"
    )
    max_reconnect_attempts: int = Field(
        default=10, ge=1, le=100, description="Max reconnect attempts"
    )
    quality: ConnectionQualitySettings = Field(
        default_factory=ConnectionQualitySettings
    )


class MacroAction(BaseModel):
    action_type: str = Field(
        ..., description="Action type: click, type, key, scroll, drag"
    )
    params: Dict = Field(default_factory=dict, description="Action parameters")
    timestamp: float = Field(..., description="Timestamp when action was recorded")


class MacroRecording(BaseModel):
    name: str = Field(..., description="Macro name")
    actions: List[MacroAction] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(tz=timezone.utc).isoformat())


# ---------------------------------------------------------------------------
# scheduler.py schemas (#6042)
# ---------------------------------------------------------------------------


class SchedulerWorkflowCreateResponse(BaseModel):
    success: bool
    workflow_id: str
    scheduled_workflow: Any


class SchedulerWorkflowListResponse(BaseModel):
    success: bool
    workflows: List[Any]
    total: int


class SchedulerWorkflowDetailResponse(BaseModel):
    success: bool
    workflow: Any


class SchedulerRescheduleWorkflowItem(BaseModel):
    id: str
    scheduled_time: str
    priority: str
    status: str
    complexity: str


class SchedulerRescheduleResponse(BaseModel):
    success: bool
    message: str
    workflow: SchedulerRescheduleWorkflowItem


class SchedulerCancelResponse(BaseModel):
    success: bool
    message: str
    workflow_id: str


class SchedulerStatusResponse(BaseModel):
    success: bool
    scheduler_status: Any


class SchedulerQueueWorkflowItem(BaseModel):
    id: str
    name: str
    priority: str
    complexity: str
    estimated_duration_minutes: int


class SchedulerQueueResponse(BaseModel):
    success: bool
    queue_status: Any
    queued_workflows: List[SchedulerQueueWorkflowItem]
    running_workflows: List[SchedulerQueueWorkflowItem]


class SchedulerQueueControlResponse(BaseModel):
    success: bool
    message: str
    queue_status: Any


class SchedulerStartResponse(BaseModel):
    success: bool
    message: str
    status: Any


class SchedulerStopResponse(BaseModel):
    success: bool
    message: str


class SchedulerTemplateWorkflowItem(BaseModel):
    id: str
    name: str
    scheduled_time: str
    priority: str
    status: str
    complexity: str


class SchedulerTemplateScheduleResponse(BaseModel):
    success: bool
    workflow_id: str
    template_info: Dict[str, Any]
    scheduled_workflow: SchedulerTemplateWorkflowItem


class SchedulerStatsResponse(BaseModel):
    success: bool
    statistics: Dict[str, Any]


class SchedulerBatchScheduleResponse(BaseModel):
    success: bool
    scheduled_workflows: List[str]
    errors: List[str]
    total_scheduled: int
    total_errors: int


class ScheduleWorkflowRequest(BaseModel):
    user_message: str
    scheduled_time: Union[str, datetime]
    priority: str = "normal"
    complexity: str = "simple"
    template_id: Optional[str] = None
    variables: Optional[Metadata] = None
    auto_approve: bool = False
    tags: Optional[List[str]] = None
    dependencies: Optional[List[str]] = None
    user_id: Optional[str] = None
    estimated_duration_minutes: int = 30
    timeout_minutes: int = 120
    max_retries: int = RetryConfig.DEFAULT_RETRIES


class RescheduleRequest(BaseModel):
    new_scheduled_time: Union[str, datetime]
    new_priority: Optional[str] = None


class QueueControlRequest(BaseModel):
    action: str
    value: Optional[int] = None


# ---------------------------------------------------------------------------
# monitoring.py schemas (#6042)
# ---------------------------------------------------------------------------


class ServicesSummaryResponse(BaseModel):
    total_services: int
    healthy_services: int
    degraded_services: int
    critical_services: int
    overall_status: str
    health_percentage: float
    services: List[Dict[str, Any]]


class MonitoringActionResponse(BaseModel):
    status: str
    message: str
    collection_interval: Optional[float] = None


class CurrentMetricsResponse(BaseModel):
    timestamp: float
    metrics: Dict[str, Any]
    collection_successful: bool


class ThresholdUpdateResponse(BaseModel):
    status: str
    threshold_key: str
    new_value: float
    comparison: str
    old_value: Optional[float] = None


class TestPerformanceResponse(BaseModel):
    message: str
    metrics_collected: bool
    timestamp: float


class ClaudeApiDetails(BaseModel):
    rate_limit_remaining: Optional[float] = None
    requests_per_minute: Optional[float] = None
    p95_latency_seconds: Optional[float] = None
    failure_rate: Optional[float] = None


class ClaudeApiStatusResponse(BaseModel):
    success: bool
    claude_api_status: ClaudeApiDetails
    timestamp: str


class GitHubApiDetails(BaseModel):
    rate_limit_remaining: Optional[float] = None
    total_operations: Optional[float] = None
    p95_latency_seconds: Optional[float] = None


class GitHubStatusResponse(BaseModel):
    success: bool
    github_status: GitHubApiDetails
    timestamp: str


class AlertSources(BaseModel):
    alertmanager: int
    performance_monitor: int


class AlertCheckResponse(BaseModel):
    timestamp: float
    alerts: List[Dict[str, Any]]
    total_count: int
    critical_count: int
    warning_count: int
    high_count: int
    sources: AlertSources


class AlertManagerSeverityCounts(BaseModel):
    critical: int
    high: int
    warning: int
    info: int


class AlertManagerResponse(BaseModel):
    timestamp: float
    source: str
    alertmanager_url: str
    alerts: List[Dict[str, Any]]
    total_count: int
    by_severity: AlertManagerSeverityCounts
    active_alerts: Dict[str, List[Dict[str, Any]]]


class MonitoringStatus(BaseModel):
    active: bool
    uptime_seconds: float
    collection_interval: float
    hardware_acceleration: Dict[str, bool]
    metrics_collected: int
    alerts_count: int


class PerformanceAlert(BaseModel):
    category: str
    severity: str
    message: str
    recommendation: str
    timestamp: float


class OptimizationRecommendation(BaseModel):
    category: str
    priority: str
    recommendation: str
    action: str
    expected_improvement: str


class MetricsQuery(BaseModel):
    categories: Optional[List[str]] = Field(
        None, description="Metric categories to include"
    )
    time_range_minutes: int = Field(
        10, ge=1, le=1440, description="Time range in minutes"
    )
    include_trends: bool = Field(True, description="Include trend analysis")
    include_alerts: bool = Field(True, description="Include recent alerts")


class ThresholdUpdate(BaseModel):
    category: str
    metric: str
    threshold: float
    comparison: str = Field(..., pattern="^(gt|lt|eq)$")


# ---------------------------------------------------------------------------
# vnc_mcp.py schemas (#6042)
# ---------------------------------------------------------------------------


class VncMCPTool(BaseModel):
    """VNC MCP tool definition (uses Metadata for input_schema)."""

    name: str
    description: str
    input_schema: Metadata


class VNCStatusRequest(BaseModel):
    vnc_type: str = Field("browser", description="VNC type: 'desktop' or 'browser'")


class VNCObservationRequest(BaseModel):
    vnc_type: str = Field("browser", description="VNC type: 'desktop' or 'browser'")
    duration_seconds: int = Field(
        5, description="How many seconds of recent activity to return"
    )


class VncStatusMcpResponse(BaseModel):
    success: bool
    vnc_type: str
    accessible: bool
    endpoint: Optional[str] = None
    status_code: Optional[int] = None
    message: str
    error: Optional[str] = None


class VncObservationMcpResponse(BaseModel):
    success: bool
    vnc_type: str
    duration_seconds: int
    observation_count: int
    observations: List[Dict[str, Any]]
    last_check: Optional[str] = None
    message: str


class BrowserVncContextResponse(BaseModel):
    success: bool
    timestamp: str
    playwright_state: Dict[str, Any]
    vnc_state: Dict[str, Any]


class VncRecordObservationResponse(BaseModel):
    success: bool
    recorded: bool


class DesktopClickMcpResponse(BaseModel):
    success: bool
    message: str
    action: str
    coordinates: Dict[str, int]
    button: str


class DesktopKeyboardTypeMcpResponse(BaseModel):
    success: bool
    message: str
    action: str
    text_length: int


class DesktopSpecialKeyMcpResponse(BaseModel):
    success: bool
    message: str
    action: str
    key: str


class DesktopScreenshotMcpResponse(BaseModel):
    success: bool
    message: str
    action: str
    image_data: Optional[str] = None
    format: Optional[str] = None


class DesktopObserveStateMcpResponse(BaseModel):
    success: bool
    action: str
    timestamp: str
    resolution: Optional[str] = None
    active_window: Optional[str] = None
    screenshot: Optional[str] = None
    screenshot_format: Optional[str] = None


class DesktopMouseClickRequest(BaseModel):
    x: int = Field(..., ge=0)
    y: int = Field(..., ge=0)
    button: str = Field(default="left")


class DesktopKeyboardTypeRequest(BaseModel):
    text: str


class DesktopSpecialKeyRequest(BaseModel):
    key: str


class DesktopObserveStateRequest(BaseModel):
    include_screenshot: bool = Field(default=True)


# ---------------------------------------------------------------------------
# cache_management.py schemas (#6042)
# ---------------------------------------------------------------------------


class CacheStatsResponse(BaseModel):
    status: str
    total_cache_keys: Optional[int] = None
    total_hits: Optional[int] = None
    total_misses: Optional[int] = None
    global_hit_rate: Optional[str] = None
    memory_usage: Optional[str] = None
    configured_data_types: Optional[List[str]] = None
    data_type_stats: Optional[Dict[str, Dict]] = None


class CacheWarmingRequest(BaseModel):
    data_types: List[str]
    force_refresh: bool = False


class RedisDbInfo(BaseModel):
    database: int
    key_count: int
    memory_usage: str
    connected: bool
    error: Optional[str] = None


class RedisClearEntry(BaseModel):
    name: str
    database: int
    keys_cleared: int
    error: Optional[str] = None


class RedisStatsResponse(BaseModel):
    status: str
    stats: Dict[str, Any]


class RedisClearResponse(BaseModel):
    status: str
    message: str
    cleared_databases: List[Dict[str, Any]]


class CacheClearTypeResponse(BaseModel):
    status: str
    message: str
    cache_type: str


class CacheConfigResponse(BaseModel):
    status: str
    message: Optional[str] = None
    config: Dict[str, Any]
    source: Optional[str] = None


class CacheWarmupResponse(BaseModel):
    status: str
    message: str
    warmed_caches: List[Dict[str, Any]]


class WarmCacheResponse(BaseModel):
    success: bool
    warmed_types: List[str]
    failed_types: List[str]
    total_warmed: int


class InvalidateCacheResponse(BaseModel):
    success: bool
    data_type: str
    key_pattern: str
    user_id: Optional[str] = None
    deleted_count: int


class ClearAllResponse(BaseModel):
    success: bool
    message: str
    total_deleted: int


class CacheHealthResponse(BaseModel):
    status: str
    redis_status: Optional[str] = None
    total_keys: Optional[int] = None
    memory_usage: Optional[str] = None
    global_hit_rate: Optional[str] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# browser_mcp.py schemas (#6042)
# ---------------------------------------------------------------------------


class BrowserNavigateRequest(BaseModel):
    url: str = Field(..., description="URL to navigate to")
    wait_until: Optional[str] = Field(
        "load", description="Wait condition: 'load', 'domcontentloaded', 'networkidle'"
    )
    timeout: Optional[int] = Field(30000, description="Timeout in milliseconds")


class BrowserClickRequest(BaseModel):
    selector: str = Field(..., description="CSS selector for element to click")
    timeout: Optional[int] = Field(5000, description="Timeout in milliseconds")


class BrowserFillRequest(BaseModel):
    selector: str = Field(..., description="CSS selector for input field")
    value: str = Field(..., description="Value to fill")
    timeout: Optional[int] = Field(5000, description="Timeout in milliseconds")


class BrowserScreenshotRequest(BaseModel):
    selector: Optional[str] = Field(
        None, description="CSS selector for element (full page if omitted)"
    )
    full_page: Optional[bool] = Field(False, description="Capture full scrollable page")


class BrowserEvaluateRequest(BaseModel):
    script: str = Field(..., description="JavaScript code to execute")


class BrowserWaitForSelectorRequest(BaseModel):
    selector: str = Field(..., description="CSS selector to wait for")
    timeout: Optional[int] = Field(30000, description="Timeout in milliseconds")
    state: Optional[str] = Field(
        "visible", description="State: 'attached', 'detached', 'visible', 'hidden'"
    )


class BrowserGetTextRequest(BaseModel):
    selector: str = Field(..., description="CSS selector for element")


class BrowserGetAttributeRequest(BaseModel):
    selector: str = Field(..., description="CSS selector for element")
    attribute: str = Field(..., description="Attribute name to retrieve")


class BrowserSelectRequest(BaseModel):
    selector: str = Field(..., description="CSS selector for select element")
    value: str = Field(..., description="Value to select")


class BrowserHoverRequest(BaseModel):
    selector: str = Field(..., description="CSS selector for element to hover")


class BrowserNavigateResponse(BaseModel):
    success: bool
    action: str
    url: str
    result: Optional[Any] = None
    timestamp: str


class BrowserClickResponse(BaseModel):
    success: bool
    action: str
    selector: str
    result: Optional[Any] = None
    timestamp: str


class BrowserFillResponse(BaseModel):
    success: bool
    action: str
    selector: str
    value_length: int
    result: Optional[Any] = None
    timestamp: str


class BrowserScreenshotResponse(BaseModel):
    success: bool
    action: str
    selector: Optional[str] = None
    full_page: Optional[bool] = None
    base64_image: Optional[str] = None
    mime_type: str
    timestamp: str


class BrowserEvaluateResponse(BaseModel):
    success: bool
    action: str
    script_preview: str
    result: Optional[Any] = None
    timestamp: str


class BrowserWaitForSelectorResponse(BaseModel):
    success: bool
    action: str
    selector: str
    state: Optional[str] = None
    result: Optional[Any] = None
    timestamp: str


class BrowserGetTextResponse(BaseModel):
    success: bool
    action: str
    selector: str
    text: Optional[str] = None
    timestamp: str


class BrowserGetAttributeResponse(BaseModel):
    success: bool
    action: str
    selector: str
    attribute: str
    value: Optional[str] = None
    timestamp: str


class BrowserSelectResponse(BaseModel):
    success: bool
    action: str
    selector: str
    value: str
    result: Optional[Any] = None
    timestamp: str


class BrowserHoverResponse(BaseModel):
    success: bool
    action: str
    selector: str
    result: Optional[Any] = None
    timestamp: str


class BrowserMcpStatusResponse(BaseModel):
    success: bool
    bridge: str
    browser_vm: Dict[str, str]
    security: Dict[str, Any]
    rate_limit_status: Dict[str, Any]
    tools_available: int
    timestamp: str


# ---------------------------------------------------------------------------
# settings.py schemas (#6042)
# ---------------------------------------------------------------------------


class SaveSettingsResponse(BaseModel):
    status: Optional[str] = None
    message: Optional[str] = None
    success: Optional[bool] = None


class ClearCacheResponse(BaseModel):
    status: str
    message: str
    available_endpoints: Optional[dict] = None


class SettingsTaskQueuedResponse(BaseModel):
    task_id: str
    status: str
    message: str
    dry_run: Optional[bool] = None


class SettingsTaskStatusResponse(BaseModel):
    task_id: str
    status: str
    message: Optional[str] = None
    progress: Optional[Any] = None
    result: Optional[Any] = None
    error: Optional[str] = None


class RBACStatusResponse(BaseModel):
    initialized: bool
    message: str


class WorkerStatusResponse(BaseModel):
    available: bool
    message: str


class UpdateStatusResponse(BaseModel):
    last_update: Optional[str] = None
    marker_exists: bool
    message: str


class RBACInitRequest(BaseModel):
    create_admin: bool = False
    admin_username: str = "admin"

    @classmethod
    def validate_admin_username(cls, v: str) -> str:
        if len(v) < 3 or len(v) > 32:
            raise ValueError("Username must be 3-32 characters")
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9_]*$", v):
            raise ValueError(
                "Username must start with a letter and contain only letters, numbers, and underscores"
            )
        return v

    def __init__(self, **data):
        super().__init__(**data)
        if self.create_admin:
            self.admin_username = self.validate_admin_username(self.admin_username)


class SystemUpdateRequest(BaseModel):
    update_type: str = "dependencies"
    target_groups: Optional[list] = None
    dry_run: bool = False
    force_update: bool = False

    def __init__(self, **data):
        super().__init__(**data)
        if self.update_type not in ("dependencies", "system"):
            raise ValueError("update_type must be 'dependencies' or 'system'")


class ConfigSyncRequest(BaseModel):
    settings: dict


class ConfigSyncResponse(BaseModel):
    status: str
    changed: dict
    unchanged_keys: int


_VALID_HARDWARE_TYPES = frozenset({"npu", "gpu", "cpu"})


class HardwarePriorityRequest(BaseModel):
    priority_order: List[str]

    def model_post_init(self, __context) -> None:  # noqa: ANN001
        given = set(self.priority_order)
        if given != _VALID_HARDWARE_TYPES or len(self.priority_order) != 3:
            raise ValueError(
                f"priority_order must be a permutation of {sorted(_VALID_HARDWARE_TYPES)}, "
                f"got {self.priority_order}"
            )


class HardwarePriorityResponse(BaseModel):
    status: str
    priority_order: List[str]
    changed: dict


# ---------------------------------------------------------------------------
# log_forwarding.py remaining schemas (#6042)
# ---------------------------------------------------------------------------


class LogFwdDestinationCreate(BaseModel):
    name: str = Field(..., description="Unique name for the destination")
    type: str = Field(
        ...,
        description="Destination type: seq, elasticsearch, loki, syslog, webhook, file",
    )
    enabled: bool = Field(True, description="Whether the destination is enabled")
    url: Optional[str] = Field(None, description="URL/host for the destination")
    api_key: Optional[str] = Field(None, description="API key for authentication")
    username: Optional[str] = Field(None, description="Username for authentication")
    password: Optional[str] = Field(None, description="Password for authentication")
    index: Optional[str] = Field(
        "autobot-logs", description="Index name (Elasticsearch)"
    )
    file_path: Optional[str] = Field(None, description="File path (file destination)")
    min_level: str = Field("Information", description="Minimum log level to forward")
    batch_size: int = Field(10, ge=1, le=1000, description="Batch size for sending")
    batch_timeout: float = Field(
        5.0, ge=0.1, le=60.0, description="Batch timeout in seconds"
    )
    retry_count: int = Field(3, ge=0, le=10, description="Number of retries on failure")
    retry_delay: float = Field(
        1.0, ge=0.1, le=30.0, description="Delay between retries"
    )
    scope: str = Field("global", description="Scope: global (all hosts) or per_host")
    target_hosts: List[str] = Field(
        default_factory=list, description="Target hosts for per_host scope"
    )
    syslog_protocol: str = Field(
        "udp", description="Syslog protocol: udp, tcp, tcp_tls"
    )
    ssl_verify: bool = Field(True, description="Verify SSL certificates for TLS")
    ssl_ca_cert: Optional[str] = Field(None, description="Path to CA certificate")
    ssl_client_cert: Optional[str] = Field(
        None, description="Path to client certificate"
    )
    ssl_client_key: Optional[str] = Field(None, description="Path to client key")


class LogFwdDestinationUpdate(BaseModel):
    enabled: Optional[bool] = None
    url: Optional[str] = None
    api_key: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    index: Optional[str] = None
    file_path: Optional[str] = None
    min_level: Optional[str] = None
    batch_size: Optional[int] = None
    batch_timeout: Optional[float] = None
    retry_count: Optional[int] = None
    retry_delay: Optional[float] = None
    scope: Optional[str] = None
    target_hosts: Optional[List[str]] = None
    syslog_protocol: Optional[str] = None
    ssl_verify: Optional[bool] = None
    ssl_ca_cert: Optional[str] = None
    ssl_client_cert: Optional[str] = None
    ssl_client_key: Optional[str] = None


class LogFwdDestinationResponse(BaseModel):
    name: str
    type: str
    enabled: bool
    url: Optional[str]
    index: Optional[str]
    file_path: Optional[str]
    min_level: str
    batch_size: int
    batch_timeout: float
    scope: str
    target_hosts: List[str]
    syslog_protocol: str
    ssl_verify: bool
    healthy: bool
    last_error: Optional[str]
    sent_count: int
    failed_count: int


class LogFwdMessageResponse(BaseModel):
    message: str


class LogFwdCreateUpdateResponse(BaseModel):
    message: str
    destination: Dict[str, Any]


class LogFwdTestResponse(BaseModel):
    name: str
    healthy: bool
    last_error: Optional[str] = None
    message: str


class LogFwdTestAllResponse(BaseModel):
    results: Dict[str, Any]
    total: int
    healthy: int
    unhealthy: int


class LogFwdDestinationStatusItem(BaseModel):
    name: str
    type: str
    enabled: bool
    healthy: bool
    last_error: Optional[str] = None
    sent_count: int
    failed_count: int
    scope: str


class LogFwdStatusResponse(BaseModel):
    running: bool
    hostname: str
    queue_size: int
    destinations: List[LogFwdDestinationStatusItem]
    total_destinations: int
    enabled_destinations: int
    healthy_destinations: int
    total_sent: int
    total_failed: int


class LogFwdDestinationTypesResponse(BaseModel):
    types: List[Any]
    scopes: List[Any]
    log_levels: List[str]
    syslog_protocols: List[Any]


class LogFwdKnownHostItem(BaseModel):
    hostname: str
    ip: Optional[str] = None
    description: str


class LogFwdKnownHostsResponse(BaseModel):
    hosts: List[LogFwdKnownHostItem]
    current_hostname: str


class LogFwdAutoStartResponse(BaseModel):
    auto_start: bool
    message: str


# security_assessment.py schemas (#6042)


class CreateAssessmentRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    target: str = Field(..., min_length=1, description="Target IP, CIDR, or hostname")
    scope: Optional[list[str]] = Field(None)
    training_mode: bool = Field(False)
    metadata: Optional[dict[str, Any]] = None


class AdvancePhaseRequest(BaseModel):
    reason: str = Field("", description="Reason for phase transition")
    target_phase: Optional[str] = Field(None)


class AddHostRequest(BaseModel):
    ip: str = Field(..., description="Host IP address")
    hostname: Optional[str] = None
    status: str = Field("up")
    metadata: Optional[dict[str, Any]] = None


class AddPortRequest(BaseModel):
    host_ip: str = Field(..., description="Host IP address")
    port: int = Field(..., ge=1, le=65535)
    protocol: str = Field("tcp")
    state: str = Field("open")
    service: Optional[str] = None
    version: Optional[str] = None


class AddVulnerabilityRequest(BaseModel):
    host_ip: str = Field(..., description="Affected host IP")
    cve_id: Optional[str] = None
    title: str = Field("")
    severity: str = Field("unknown")
    description: str = ""
    affected_service: Optional[str] = None
    affected_port: Optional[int] = None
    metadata: Optional[dict[str, Any]] = None


class AddFindingRequest(BaseModel):
    finding_type: str = Field(..., description="Type of finding")
    description: str = ""
    data: Optional[dict[str, Any]] = None


class ParseToolOutputRequest(BaseModel):
    output: str = Field(..., min_length=1, description="Raw tool output")
    tool: Optional[str] = Field(None, description="Tool name (auto-detect if not provided)")


class RecoverErrorRequest(BaseModel):
    target_phase: str = Field(..., description="Phase to recover to")
    reason: str = Field("Manual recovery")