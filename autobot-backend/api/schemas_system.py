# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
System health, cache, NPU worker, wake-word, and feature-flag schemas.
"""

import re
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from api.schemas_common import SuccessDataResponse, SuccessMessageResponse
from api.system_health import HealthStatus
from constants.threshold_constants import RetryConfig
from services.audit_logger import AuditResult
from services.feature_flags import EnforcementMode
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

    Issue #6909: status uses probe vocabulary ("ok"/"degraded"/"down") — the
    legacy "healthy"/"unhealthy" mapping was removed. Extra fields
    (cpu_percent, memory_percent, probes, etc.) are allowed through.
    """

    model_config = {"extra": "allow"}

    status: HealthStatus
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

    Shape is defined by CacheCoordinator.get_cache_stats() — opaque.
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
    data: Any | None = None


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
    total_secrets: int | None = None
    storage_backend: str | None = None
    encryption_enabled: bool | None = None
    error: str | None = None
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
    last_error: str | None = None
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
    content: str | None = None
    is_text: bool


class FileRenameResponse(BaseModel):
    """Response for POST /files/rename."""

    message: str
    item_info: Any


class FilePreviewResponse(BaseModel):
    """Response for GET /files/preview."""

    type: str
    url: str
    content: str | None = None
    mime_type: str | None = None
    size: int | None = None
    name: str | None = None


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


# #6792: GitHubProviderInfo is identical in shape to VCSProviderInfo
# (id/name/description/required_settings/optional_settings). Aliased to the
# canonical VCS class to avoid drift; the only caller (api/integration_github.py)
# continues to import the GitHubProviderInfo name from this module so the
# OpenAPI label stays domain-specific while the runtime type is shared.
from api.schemas_workflows import VCSProviderInfo as GitHubProviderInfo  # noqa: E402, F401

# ---------------------------------------------------------------------------
# redis.py schemas  (Issue #5990)
# ---------------------------------------------------------------------------


class RedisConfigResponse(BaseModel):
    """Response for GET /config and POST /config in redis.py.

    ConfigService.get_redis_config() returns these fields; extra fields
    allowed for additional redis_config keys.
    """

    model_config = {"extra": "allow"}

    type: str | None = None
    host: str | None = None
    port: int | None = None


class RedisConnectionStatusResponse(BaseModel):
    """Response for GET /status, POST /test_connection in redis.py.

    ConnectionTester.test_redis_connection() returns status + message at minimum;
    connected path adds host/port/redis_search_module_loaded. Extra fields allowed.
    """

    model_config = {"extra": "allow"}

    status: str
    message: str | None = None


class RedisHealthResponse(BaseModel):
    """Response for GET /health in redis.py."""

    status: str
    redis_status: str | None = None
    message: str | None = None
    host: str | None = None
    port: int | None = None
    redis_search_module_loaded: bool = False


# ---------------------------------------------------------------------------
# services.py schemas  (Issue #5990)
# ---------------------------------------------------------------------------


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
    text_content: str | None = None
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
    region: Dict[str, Any] | None = None


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
    """Response for GET /vision/status (api/vision.py::get_vision_status).

    Success path: service, status, features, supported_element_types,
                  supported_interaction_types.
    Error path:   service, status, error  (features/counts absent).
    All success-only fields are Optional so the model validates both shapes.
    """

    service: str
    status: str
    features: VisionStatusFeaturesResponse | None = None
    supported_element_types: int | None = None
    supported_interaction_types: int | None = None
    # Present only on the error path
    error: str | None = None


class VMStatusItem(BaseModel):
    """A single VM entry in ServicesVMsStatusResponse."""

    name: str
    ip: str
    status: str
    services: List[Any] = []
    last_check: Any | None = None


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
    noise_tolerance: float | None = None
    max_cpu_percent: float | None = None


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
    vnc_port: int | None = None
    username: str
    os: str | None = None
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
    summary: Any | None = None


# ---------------------------------------------------------------------------
# project_state.py schemas  (Issue #5990)
# ---------------------------------------------------------------------------


class ProjectStateHealthResponse(BaseModel):
    """Response for GET /health in project_state.py."""

    status: str
    current_phase: str
    overall_completion: float
    timestamp: str | None = None


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
    redis_available: bool | None = None
    total_project_user_combinations: int | None = None
    ttl_seconds: int | None = None
    ttl_days: int | None = None
    error: str | None = None


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
    comment: str | None = None


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
    pattern: str | None = None
    description: str | None = None


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
    vnc_port_reachable: bool | None = None
    latency_ms: float | None = None
    websockify_running: bool | None = None
    websockify_processes: int | None = None


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
    x: int | None = None
    y: int | None = None
    confidence: float | None = None


class WaitForTextResponse(BaseModel):
    status: str
    found: bool
    message: str


class WaitForImageResponse(BaseModel):
    status: str
    found: bool
    message: str
    x: int | None = None
    y: int | None = None
    confidence: float | None = None


class RestoreStateResponse(BaseModel):
    status: str
    message: str
    state: Dict[str, Any] | None = None


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
    screenshot_path: str | None = None


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
    compression_level: int = Field(default=6, ge=0, le=9, description="Compression level (0=none, 9=max)")
    quality: int = Field(default=6, ge=0, le=9, description="JPEG quality (0=poor, 9=best)")
    encoding: str = Field(default="tight", description="Encoding method: tight, hextile, raw")


class ConnectionSettings(BaseModel):
    auto_reconnect: bool = Field(default=True, description="Enable auto-reconnect on disconnect")
    reconnect_delay_ms: int = Field(default=3000, ge=1000, le=30000, description="Delay before reconnect")
    max_reconnect_attempts: int = Field(default=10, ge=1, le=100, description="Max reconnect attempts")
    quality: ConnectionQualitySettings = Field(default_factory=ConnectionQualitySettings)


class MacroAction(BaseModel):
    action_type: str = Field(..., description="Action type: click, type, key, scroll, drag")
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
    scheduled_time: str | datetime
    priority: str = "normal"
    complexity: str = "simple"
    template_id: str | None = None
    variables: Metadata | None = None
    auto_approve: bool = False
    tags: List[str] | None = None
    dependencies: List[str] | None = None
    user_id: str | None = None
    estimated_duration_minutes: int = 30
    timeout_minutes: int = 120
    max_retries: int = RetryConfig.DEFAULT_RETRIES


class RescheduleRequest(BaseModel):
    new_scheduled_time: str | datetime
    new_priority: str | None = None


class QueueControlRequest(BaseModel):
    action: str
    value: int | None = None


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
    collection_interval: float | None = None


class CurrentMetricsResponse(BaseModel):
    timestamp: float
    metrics: Dict[str, Any]
    collection_successful: bool


class ThresholdUpdateResponse(BaseModel):
    status: str
    threshold_key: str
    new_value: float
    comparison: str
    old_value: float | None = None


class TestPerformanceResponse(BaseModel):
    message: str
    metrics_collected: bool
    timestamp: float


class ClaudeApiDetails(BaseModel):
    rate_limit_remaining: float | None = None
    requests_per_minute: float | None = None
    p95_latency_seconds: float | None = None
    failure_rate: float | None = None


class ClaudeApiStatusResponse(BaseModel):
    success: bool
    claude_api_status: ClaudeApiDetails
    timestamp: str


class GitHubApiDetails(BaseModel):
    rate_limit_remaining: float | None = None
    total_operations: float | None = None
    p95_latency_seconds: float | None = None


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
    categories: List[str] | None = Field(None, description="Metric categories to include")
    time_range_minutes: int = Field(10, ge=1, le=1440, description="Time range in minutes")
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
    duration_seconds: int = Field(5, description="How many seconds of recent activity to return")


class VncStatusMcpResponse(BaseModel):
    success: bool
    vnc_type: str
    accessible: bool
    endpoint: str | None = None
    status_code: int | None = None
    message: str
    error: str | None = None


class VncObservationMcpResponse(BaseModel):
    success: bool
    vnc_type: str
    duration_seconds: int
    observation_count: int
    observations: List[Dict[str, Any]]
    last_check: str | None = None
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
    image_data: str | None = None
    format: str | None = None


class DesktopObserveStateMcpResponse(BaseModel):
    success: bool
    action: str
    timestamp: str
    resolution: str | None = None
    active_window: str | None = None
    screenshot: str | None = None
    screenshot_format: str | None = None


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
    total_cache_keys: int | None = None
    total_hits: int | None = None
    total_misses: int | None = None
    global_hit_rate: str | None = None
    memory_usage: str | None = None
    configured_data_types: List[str] | None = None
    data_type_stats: Dict[str, Dict] | None = None


class CacheWarmingRequest(BaseModel):
    data_types: List[str]
    force_refresh: bool = False


class RedisDbInfo(BaseModel):
    database: int
    key_count: int
    memory_usage: str
    connected: bool
    error: str | None = None


class RedisClearEntry(BaseModel):
    name: str
    database: int
    keys_cleared: int
    error: str | None = None


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
    message: str | None = None
    config: Dict[str, Any]
    source: str | None = None


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
    user_id: str | None = None
    deleted_count: int


class ClearAllResponse(BaseModel):
    success: bool
    message: str
    total_deleted: int


class CacheHealthResponse(BaseModel):
    status: str
    redis_status: str | None = None
    total_keys: int | None = None
    memory_usage: str | None = None
    global_hit_rate: str | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# browser_mcp.py schemas (#6042)
# ---------------------------------------------------------------------------


class BrowserNavigateRequest(BaseModel):
    url: str = Field(..., description="URL to navigate to")
    wait_until: str | None = Field("load", description="Wait condition: 'load', 'domcontentloaded', 'networkidle'")
    timeout: int | None = Field(30000, description="Timeout in milliseconds")


class BrowserClickRequest(BaseModel):
    selector: str = Field(..., description="CSS selector for element to click")
    timeout: int | None = Field(5000, description="Timeout in milliseconds")


class BrowserFillRequest(BaseModel):
    selector: str = Field(..., description="CSS selector for input field")
    value: str = Field(..., description="Value to fill")
    timeout: int | None = Field(5000, description="Timeout in milliseconds")


class BrowserScreenshotRequest(BaseModel):
    selector: str | None = Field(None, description="CSS selector for element (full page if omitted)")
    full_page: bool | None = Field(False, description="Capture full scrollable page")


class BrowserEvaluateRequest(BaseModel):
    script: str = Field(..., description="JavaScript code to execute")


class BrowserWaitForSelectorRequest(BaseModel):
    selector: str = Field(..., description="CSS selector to wait for")
    timeout: int | None = Field(30000, description="Timeout in milliseconds")
    state: str | None = Field("visible", description="State: 'attached', 'detached', 'visible', 'hidden'")


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
    result: Any | None = None
    timestamp: str


class BrowserClickResponse(BaseModel):
    success: bool
    action: str
    selector: str
    result: Any | None = None
    timestamp: str


class BrowserFillResponse(BaseModel):
    success: bool
    action: str
    selector: str
    value_length: int
    result: Any | None = None
    timestamp: str


class BrowserScreenshotResponse(BaseModel):
    success: bool
    action: str
    selector: str | None = None
    full_page: bool | None = None
    base64_image: str | None = None
    mime_type: str
    timestamp: str


class BrowserEvaluateResponse(BaseModel):
    success: bool
    action: str
    script_preview: str
    result: Any | None = None
    timestamp: str


class BrowserWaitForSelectorResponse(BaseModel):
    success: bool
    action: str
    selector: str
    state: str | None = None
    result: Any | None = None
    timestamp: str


class BrowserGetTextResponse(BaseModel):
    success: bool
    action: str
    selector: str
    text: str | None = None
    timestamp: str


class BrowserGetAttributeResponse(BaseModel):
    success: bool
    action: str
    selector: str
    attribute: str
    value: str | None = None
    timestamp: str


class BrowserSelectResponse(BaseModel):
    success: bool
    action: str
    selector: str
    value: str
    result: Any | None = None
    timestamp: str


class BrowserHoverResponse(BaseModel):
    success: bool
    action: str
    selector: str
    result: Any | None = None
    timestamp: str


class BrowserMcpStatusResponse(BaseModel):
    success: bool
    bridge: str
    browser_vm: Dict[str, str]
    security: Dict[str, Any]
    rate_limit_status: Dict[str, Any]
    tools_available: int
    timestamp: str


class BrowserPageSnapshotRequest(BaseModel):
    """Request for POST /browser/mcp/page_snapshot (#5136 Phase 1)."""

    session_id: str


class BrowserPageSnapshotResponse(BaseModel):
    """Response for POST /browser/mcp/page_snapshot (#5136 Phase 1)."""

    success: bool
    action: str
    session_id: str
    accessibility_text: str
    timestamp: str


class BrowserInterceptApiRequest(BaseModel):
    """Request for POST /browser/mcp/intercept_api (#5136 Phase 1)."""

    session_id: str


class BrowserInterceptApiResponse(BaseModel):
    """Response for POST /browser/mcp/intercept_api (#5136 Phase 1)."""

    success: bool
    action: str
    session_id: str
    requests: List[Dict[str, Any]]
    timestamp: str


# ---------------------------------------------------------------------------
# settings.py schemas (#6042)
# ---------------------------------------------------------------------------


class SaveSettingsResponse(BaseModel):
    status: str | None = None
    message: str | None = None
    success: bool | None = None


class ClearCacheResponse(BaseModel):
    status: str
    message: str
    available_endpoints: dict | None = None


class SettingsTaskQueuedResponse(BaseModel):
    task_id: str
    status: str
    message: str
    dry_run: bool | None = None


class SettingsTaskStatusResponse(BaseModel):
    task_id: str
    status: str
    message: str | None = None
    progress: Any | None = None
    result: Any | None = None
    error: str | None = None


class RBACStatusResponse(BaseModel):
    initialized: bool
    message: str


class WorkerStatusResponse(BaseModel):
    available: bool
    message: str


class UpdateStatusResponse(BaseModel):
    last_update: str | None = None
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
            raise ValueError("Username must start with a letter and contain only letters, numbers, and underscores")
        return v

    def __init__(self, **data):
        super().__init__(**data)
        if self.create_admin:
            self.admin_username = self.validate_admin_username(self.admin_username)


class SystemUpdateRequest(BaseModel):
    update_type: str = "dependencies"
    target_groups: list | None = None
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
    url: str | None = Field(None, description="URL/host for the destination")
    api_key: str | None = Field(None, description="API key for authentication")
    username: str | None = Field(None, description="Username for authentication")
    password: str | None = Field(None, description="Password for authentication")
    index: str | None = Field("autobot-logs", description="Index name (Elasticsearch)")
    file_path: str | None = Field(None, description="File path (file destination)")
    min_level: str = Field("Information", description="Minimum log level to forward")
    batch_size: int = Field(10, ge=1, le=1000, description="Batch size for sending")
    batch_timeout: float = Field(5.0, ge=0.1, le=60.0, description="Batch timeout in seconds")
    retry_count: int = Field(3, ge=0, le=10, description="Number of retries on failure")
    retry_delay: float = Field(1.0, ge=0.1, le=30.0, description="Delay between retries")
    scope: str = Field("global", description="Scope: global (all hosts) or per_host")
    target_hosts: List[str] = Field(default_factory=list, description="Target hosts for per_host scope")
    syslog_protocol: str = Field("udp", description="Syslog protocol: udp, tcp, tcp_tls")
    ssl_verify: bool = Field(True, description="Verify SSL certificates for TLS")
    ssl_ca_cert: str | None = Field(None, description="Path to CA certificate")
    ssl_client_cert: str | None = Field(None, description="Path to client certificate")
    ssl_client_key: str | None = Field(None, description="Path to client key")


class LogFwdDestinationUpdate(BaseModel):
    enabled: bool | None = None
    url: str | None = None
    api_key: str | None = None
    username: str | None = None
    password: str | None = None
    index: str | None = None
    file_path: str | None = None
    min_level: str | None = None
    batch_size: int | None = None
    batch_timeout: float | None = None
    retry_count: int | None = None
    retry_delay: float | None = None
    scope: str | None = None
    target_hosts: List[str] | None = None
    syslog_protocol: str | None = None
    ssl_verify: bool | None = None
    ssl_ca_cert: str | None = None
    ssl_client_cert: str | None = None
    ssl_client_key: str | None = None


class LogFwdDestinationResponse(BaseModel):
    name: str
    type: str
    enabled: bool
    url: str | None
    index: str | None
    file_path: str | None
    min_level: str
    batch_size: int
    batch_timeout: float
    scope: str
    target_hosts: List[str]
    syslog_protocol: str
    ssl_verify: bool
    healthy: bool
    last_error: str | None
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
    last_error: str | None = None
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
    last_error: str | None = None
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
    ip: str | None = None
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
    scope: list[str] | None = Field(None)
    training_mode: bool = Field(False)
    metadata: dict[str, Any] | None = None


class AdvancePhaseRequest(BaseModel):
    reason: str = Field("", description="Reason for phase transition")
    target_phase: str | None = Field(None)


class AddHostRequest(BaseModel):
    ip: str = Field(..., description="Host IP address")
    hostname: str | None = None
    status: str = Field("up")
    metadata: dict[str, Any] | None = None


class AddPortRequest(BaseModel):
    host_ip: str = Field(..., description="Host IP address")
    port: int = Field(..., ge=1, le=65535)
    protocol: str = Field("tcp")
    state: str = Field("open")
    service: str | None = None
    version: str | None = None


class AddVulnerabilityRequest(BaseModel):
    host_ip: str = Field(..., description="Affected host IP")
    cve_id: str | None = None
    title: str = Field("")
    severity: str = Field("unknown")
    description: str = ""
    affected_service: str | None = None
    affected_port: int | None = None
    metadata: dict[str, Any] | None = None


class AddFindingRequest(BaseModel):
    finding_type: str = Field(..., description="Type of finding")
    description: str = ""
    data: dict[str, Any] | None = None


class ParseToolOutputRequest(BaseModel):
    output: str = Field(..., min_length=1, description="Raw tool output")
    tool: str | None = Field(None, description="Tool name (auto-detect if not provided)")


class RecoverErrorRequest(BaseModel):
    target_phase: str = Field(..., description="Phase to recover to")
    reason: str = Field("Manual recovery")


# security.py schemas (#6042)


class CommandApprovalRequest(BaseModel):
    command_id: str
    approved: bool


class CommandApprovalResponse(BaseModel):
    success: bool
    message: str


class SecurityStatusResponse(BaseModel):
    security_enabled: bool
    command_security_enabled: bool
    docker_sandbox_enabled: bool
    pending_approvals: List[Metadata]


class URLCheckRequest(BaseModel):
    url: str = Field(..., description="URL to check for threats")


class URLCheckResponse(BaseModel):
    success: bool
    url: str
    overall_score: float
    threat_level: str
    virustotal_score: float | None = None
    urlvoid_score: float | None = None
    sources_checked: int
    cached: bool
    message: str | None = None


class ThreatIntelStatusResponse(BaseModel):
    any_service_configured: bool
    virustotal: Dict[str, Any]
    urlvoid: Dict[str, Any]
    cache_stats: Dict[str, Any]


class DomainSecurityStatsResponse(BaseModel):
    success: bool
    stats: Dict[str, Any]


# ---------------------------------------------------------------------------
# agent_terminal.py schemas (#6042)
# ---------------------------------------------------------------------------


class TerminalCreateSessionRequest(BaseModel):
    """Request to create agent terminal session"""

    agent_id: str = Field(..., description="Unique identifier for the agent")
    agent_role: str = Field(
        ..., description="Role of the agent (chat_agent, automation_agent, system_agent, admin_agent)"
    )
    conversation_id: str | None = Field(None, description="Chat conversation ID to link")
    host: str = Field("main", description="Target host (main, frontend, npu-worker, redis, ai-stack, browser)")
    metadata: Dict | None = Field(None, description="Additional session metadata")


class TerminalExecuteCommandRequest(BaseModel):
    """Request to execute command in agent session"""

    command: str = Field(..., description="Command to execute")
    description: str | None = Field(None, description="Description of what command does")
    force_approval: bool = Field(False, description="Force user approval even for safe commands")


class TerminalApproveCommandRequest(BaseModel):
    """Request to approve/deny pending command"""

    approved: bool = Field(..., description="Whether command is approved")
    user_id: str | None = Field(None, description="User who made the decision")
    comment: str | None = Field(None, description="Optional comment or reason for the decision")
    auto_approve_future: bool = Field(False, description="Auto-approve similar commands in the future")
    remember_for_project: bool = Field(False, description="Remember approval for this project")
    project_path: str | None = Field(None, description="Project path for approval memory")


class TerminalToolApprovalRequest(BaseModel):
    """Request to approve/deny a pending agent tool (event-stream level approval)."""

    approved: bool = Field(..., description="Whether the tool execution is approved")
    comment: str | None = Field(None, description="Optional reason for the decision")
    task_id: str | None = Field(None, description="Task ID from the APPROVAL_REQUIRED event")


class TaskSteeringRequest(BaseModel):
    """Request to send a steering message to a running agent task (#10543).

    Steering amends the active plan without stopping the loop — the guidance
    is absorbed at the top of the next ANALYZE_EVENTS phase.
    """

    guidance: str = Field(..., description="Human correction or direction text injected into the running loop")
    task_id: str | None = Field(None, description="Task ID (also available from URL path)")


class TerminalInterruptRequest(BaseModel):
    """Request to interrupt agent and take control"""

    user_id: str = Field(..., description="User requesting control")


class TerminalHostSelectionRequest(BaseModel):
    """Request for agent to select an infrastructure host"""

    agent_session_id: str | None = Field(None, description="Agent terminal session ID")
    command: str | None = Field(None, description="Command to execute on host")
    purpose: str | None = Field(None, description="Purpose of the SSH action")
    preferred_host_id: str | None = Field(None, description="Preferred host ID if any")
    allow_auto_select: bool = Field(True, description="Allow auto-selection if default host is set")


class TerminalHostSelectionResponse(BaseModel):
    """Response to host selection request"""

    request_id: str = Field(..., description="Unique request ID for tracking")
    status: str = Field(..., description="pending_selection, selected, or cancelled")
    selected_host_id: str | None = Field(None, description="Selected host ID")
    selected_host_name: str | None = Field(None, description="Selected host name")
    connection_info: Dict | None = Field(None, description="Connection details (host, port, username)")


class HeartbeatConfigRequest(BaseModel):
    """Request body to configure heartbeat for an agent."""

    heartbeat_enabled: bool = False
    heartbeat_interval_seconds: int = Field(default=300, ge=10)
    max_run_duration_seconds: int = Field(default=600, ge=10)


class HeartbeatConfigResponse(BaseModel):
    """Response for agent heartbeat config / runtime state (GH#6476)."""

    agent_id: str
    heartbeat_enabled: bool
    status: str
    paused_reason: str | None = None
    paused_at: str | None = None
    paused_by: str | None = None
    error_detail: str | None = None
    error_at: str | None = None
    error_code: str | None = None
    heartbeat_interval_seconds: int
    max_run_duration_seconds: int
    current_task_id: str | None
    last_heartbeat_at: str | None
    session_params: Dict[str, Any] | None
    extra: Dict[str, Any] | None
    created_at: str | None
    updated_at: str | None


class AgentPauseRequest(BaseModel):
    """Request body for POST /heartbeat/{agent_id}/pause (GH#6476)."""

    reason: str | None = None
    paused_by: str | None = None


class AgentResumeRequest(BaseModel):
    """Request body for POST /heartbeat/{agent_id}/resume (GH#6476)."""


class AgentTerminateRequest(BaseModel):
    """Request body for POST /heartbeat/{agent_id}/terminate (GH#6476)."""

    reason: str | None = None


class AgentErrorRequest(BaseModel):
    """Request body for POST /heartbeat/{agent_id}/error (MVA-1411)."""

    error_detail: str | None = None
    error_code: str | None = None


class AgentRecoverRequest(BaseModel):
    """Request body for POST /heartbeat/{agent_id}/recover (MVA-1411)."""


class WakeupRequestCreate(BaseModel):
    """Request body to queue a wakeup for an agent."""

    priority: int = 0
    context: Dict[str, Any] | None = None
    reason: str | None = None


class WakeupRequestResponse(BaseModel):
    """Response for a queued wakeup request."""

    id: str
    agent_id: str
    priority: int
    context: Dict[str, Any] | None
    reason: str | None
    consumed: bool
    consumed_at: str | None
    created_at: str | None
    merged_count: int = 0


class RunEventResponse(BaseModel):
    """Response for a single run event."""

    id: str
    event_type: str
    message: str | None
    payload: Dict[str, Any] | None
    occurred_at: str


class HeartbeatRunResponse(BaseModel):
    """Response for a single heartbeat run."""

    id: str
    agent_id: str
    status: str
    trigger: str
    wakeup_context: Dict[str, Any] | None
    started_at: str | None
    finished_at: str | None
    tokens_used: int | None
    cost_usd: float | None
    model: str | None
    provider: str | None
    error_message: str | None
    created_at: str | None
    events: List[RunEventResponse] = []


class StreamingSessionRequest(BaseModel):
    user_id: str
    resolution: str = "1024x768"
    depth: int = 24


class StreamingSessionResponse(BaseModel):
    session_id: str
    vnc_port: int
    novnc_port: int | None
    display: str
    vnc_url: str
    web_url: str | None
    websocket_endpoint: str


class TakeoverRequest(BaseModel):
    trigger: str
    reason: str
    requesting_agent: str | None = None
    affected_tasks: List[str] | None = None
    priority: str = "HIGH"
    timeout_minutes: int | None = None
    auto_approve: bool = False


class TakeoverApprovalRequest(BaseModel):
    human_operator: str
    takeover_scope: Metadata | None = None


class TakeoverActionRequest(BaseModel):
    action_type: str
    action_data: Metadata


class SystemMonitoringResponse(BaseModel):
    system_status: Metadata
    active_sessions: List[Metadata]
    pending_takeovers: List[Metadata]
    active_takeovers: List[Metadata]
    resource_usage: Metadata


class ScreenAnalysisRequest(BaseModel):
    """Request for screen analysis"""

    session_id: str | None = Field(None, description="Optional session ID for context")
    include_multimodal: bool = Field(True, description="Include multi-modal analysis")


class ElementDetectionRequest(BaseModel):
    """Request for element detection"""

    element_type: str | None = Field(None, description="Filter by element type")
    min_confidence: float = Field(0.5, ge=0.0, le=1.0, description="Minimum confidence threshold")
    session_id: str | None = None


class OCRRequest(BaseModel):
    """Request for OCR text extraction"""

    region: Dict[str, int] | None = Field(
        None,
        description=("Region to extract text from {x, y, width, height}. If None," "analyzes full screen."),
    )
    session_id: str | None = None


class ElementInteractionRequest(BaseModel):
    """Request for element interaction validation"""

    element_id: str = Field(..., description="ID of element to interact with")
    interaction_type: str = Field(..., description="Type of interaction to perform")
    parameters: Metadata | None = Field(None, description="Additional interaction parameters")


class UIElementResponse(BaseModel):
    """Response model for UI element"""

    element_id: str
    element_type: str
    bbox: Dict[str, int]
    center_point: List[int]
    confidence: float
    text_content: str
    attributes: Metadata
    possible_interactions: List[str]


class ScreenAnalysisResponse(BaseModel):
    """Response model for screen analysis"""

    timestamp: float
    ui_elements: List[UIElementResponse]
    text_regions: List[Metadata]
    dominant_colors: List[Metadata]
    layout_structure: Metadata
    automation_opportunities: List[Metadata]
    context_analysis: Metadata
    confidence_score: float
    multimodal_analysis: List[Metadata] | None = None


class VisionHealthResponse(BaseModel):
    """Health check response"""

    status: str
    analyzer_ready: bool
    capabilities: List[str]
    element_types_supported: List[str]
    interaction_types_supported: List[str]


class WakeWordCheckRequest(BaseModel):
    """Request to check text for wake word"""

    text: str = Field(..., description="Text to check for wake word")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Recognition confidence")


class WakeWordCheckResponse(BaseModel):
    """Response for wake word check"""

    detected: bool
    wake_word: str = ""
    confidence: float = 0.0
    timestamp: float = 0.0
    metadata: Metadata = {}


class WakeWordConfigRequest(BaseModel):
    """Request to update wake word configuration"""

    enabled: bool = None
    wake_words: List[str] = None
    confidence_threshold: float = None
    cooldown_seconds: float = None
    adaptive_threshold: bool = None
    max_false_positive_rate: float = None
    max_cpu_percent: float = None


class AddWakeWordRequest(BaseModel):
    """Request to add a new wake word"""

    wake_word: str = Field(..., min_length=2, max_length=50)


class WakeWordReportFeedbackRequest(BaseModel):
    """Request to report wake word detection feedback"""

    is_correct: bool = Field(..., description="True if detection was correct, False if false positive")


# ---------------------------------------------------------------------------
# prometheus_mcp.py schemas
# ---------------------------------------------------------------------------


class PrometheusMCPTool(BaseModel):
    """Standard MCP tool definition (Prometheus)"""

    name: str
    description: str
    input_schema: Metadata


class QueryMetricRequest(BaseModel):
    """Request model for Prometheus metric query"""

    query: str = Field(..., description="PromQL query expression")


class QueryRangeRequest(BaseModel):
    """Request model for Prometheus range query"""

    query: str = Field(..., description="PromQL query expression")
    duration: str = Field("1h", description="Time duration (e.g., '1h', '6h', '1d')")
    step: str = Field("15s", description="Query resolution step (e.g., '15s', '1m')")


class GetVMMetricsRequest(BaseModel):
    """Request model for VM metrics"""

    vm_ip: str = Field(..., description="VM IP address")


class ListMetricsRequest(BaseModel):
    """Request model for listing metrics"""

    filter: str = Field("", description="Optional filter pattern (e.g., 'autobot_', 'node_')")


# ---------------------------------------------------------------------------
# service_messages.py schemas
# ---------------------------------------------------------------------------


class ServiceMessageResponse(BaseModel):
    """Single serialised ServiceMessage."""

    msg_id: str
    ts: str
    sender: str
    receiver: str
    msg_type: str
    content: str
    correlation_id: str
    meta: dict = Field(default_factory=dict)


class LatestMessagesResponse(BaseModel):
    """Response for GET /latest."""

    success: bool
    count: int
    messages: List[ServiceMessageResponse]


class SingleMessageResponse(BaseModel):
    """Response for GET /{msg_id}."""

    success: bool
    message: ServiceMessageResponse | None = None


class CorrelationChainResponse(BaseModel):
    """Response for GET /chain/{correlation_id}."""

    success: bool
    correlation_id: str
    count: int
    messages: List[ServiceMessageResponse]


# ---------------------------------------------------------------------------
# project_state.py schemas
# ---------------------------------------------------------------------------


class PhaseStatus(BaseModel):
    name: str
    completion: float
    is_active: bool
    is_completed: bool
    capabilities: int
    implemented_capabilities: int


class ProjectStatus(BaseModel):
    current_phase: str
    total_phases: int
    completed_phases: int
    active_phases: int
    overall_completion: float
    next_suggested_phase: str | None
    phases: Dict[str, PhaseStatus]


class ValidationResultModel(BaseModel):
    check_name: str
    status: str
    score: float
    details: str
    timestamp: str


class PhaseValidationModel(BaseModel):
    phase_name: str
    completion_percentage: float
    is_completed: bool
    capabilities: List[str]
    validation_results: List[ValidationResultModel]


# ---------------------------------------------------------------------------
# services.py schemas
# ---------------------------------------------------------------------------


class ServiceStatus(BaseModel):
    """Service status model."""

    name: str
    status: str = Field(..., description="Service status: healthy, warning, error")
    message: str = Field(..., description="Status description")
    last_check: datetime | None = None
    response_time_ms: float | None = None


class SystemInfo(BaseModel):
    """System information model."""

    version: str
    build: str
    environment: str
    uptime: float
    services_count: int


class VMStatus(BaseModel):
    """VM status model."""

    name: str
    ip: str
    status: str = Field(..., description="VM status: online, offline, unknown")
    services: List[str] = Field(default_factory=list)
    last_check: datetime | None = None


class ServicesResponse(BaseModel):
    """Services list response."""

    services: List[ServiceStatus]
    total_count: int
    healthy_count: int
    error_count: int
    warning_count: int
    last_updated: datetime


# ---------------------------------------------------------------------------
# structured_thinking_mcp.py schemas
# ---------------------------------------------------------------------------


class ThinkingStage(str, Enum):
    """Five cognitive stages for structured thinking."""

    PROBLEM_DEFINITION = "Problem Definition"
    RESEARCH = "Research"
    ANALYSIS = "Analysis"
    SYNTHESIS = "Synthesis"
    CONCLUSION = "Conclusion"


class StructuredThinkingMCPTool(BaseModel):
    """Standard MCP tool definition (structured thinking)."""

    name: str
    description: str
    input_schema: Metadata


class ProcessThoughtRequest(BaseModel):
    """Request model for processing a thought in structured framework."""

    thought: str = Field(..., description="The content of the thought")
    thought_number: int = Field(..., ge=1, description="Position in the thinking sequence")
    total_thoughts: int = Field(..., ge=1, description="Expected total number of thoughts")
    next_thought_needed: bool = Field(..., description="Whether more thoughts will follow")
    stage: ThinkingStage = Field(..., description="Cognitive stage for this thought")
    tags: List[str] | None = Field(None, description="Keywords or categories for this thought")
    axioms_used: List[str] | None = Field(None, description="Fundamental principles applied")
    assumptions_challenged: List[str] | None = Field(None, description="Assumptions being questioned")
    session_id: str | None = Field("default", description="Thinking session identifier")

    def to_thought_record(self) -> Metadata:
        """Convert request to thought record for storage."""
        return {
            "thought_number": self.thought_number,
            "thought": self.thought,
            "total_thoughts": self.total_thoughts,
            "next_thought_needed": self.next_thought_needed,
            "stage": self.stage.value,
            "tags": self.tags or [],
            "axioms_used": self.axioms_used or [],
            "assumptions_challenged": self.assumptions_challenged or [],
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        }

    def get_progress_percentage(self) -> float:
        """Calculate progress percentage."""
        return (self.thought_number / self.total_thoughts) * 100

    def get_session_key(self) -> str:
        """Get session key with fallback."""
        return self.session_id or "default"

    def is_thinking_complete(self) -> bool:
        """Check if thinking process is complete."""
        return not self.next_thought_needed

    def get_progress_message(self) -> str:
        """Get formatted progress message."""
        return f"Processed thought {self.thought_number}/{self.total_thoughts} " f"in {self.stage.value} stage"


class GenerateSummaryRequest(BaseModel):
    """Request model for generating thinking summary."""

    session_id: str | None = Field("default", description="Session to summarize")


class ClearHistoryRequest(BaseModel):
    """Request model for clearing thinking history."""

    session_id: str | None = Field("default", description="Session to clear")


# ---------------------------------------------------------------------------
# audit.py schemas
# ---------------------------------------------------------------------------


class AuditQueryRequest(BaseModel):
    """Audit log query parameters."""

    start_time: datetime | None = Field(None, description="Start of time range")
    end_time: datetime | None = Field(None, description="End of time range")
    operation: str | None = Field(None, description="Filter by operation type")
    user_id: str | None = Field(None, description="Filter by user")
    session_id: str | None = Field(None, description="Filter by session")
    vm_name: str | None = Field(None, description="Filter by VM source")
    result: AuditResult | None = Field(None, description="Filter by result")
    limit: int = Field(100, ge=1, le=1000, description="Maximum entries to return")
    offset: int = Field(0, ge=0, description="Pagination offset")


class AuditQueryResponse(BaseModel):
    """Audit log query response."""

    success: bool
    total_returned: int
    has_more: bool
    entries: List[dict]
    query: dict


class AuditStatisticsResponse(BaseModel):
    """Audit statistics response."""

    success: bool
    statistics: dict
    vm_info: dict


class AuditCleanupRequest(BaseModel):
    """Audit log cleanup request."""

    days_to_keep: int = Field(90, ge=7, le=365, description="Days of logs to retain")
    confirm: bool = Field(False, description="Confirm cleanup operation")


# ---------------------------------------------------------------------------
# alertmanager_webhook.py schemas
# ---------------------------------------------------------------------------


class AlertAnnotations(BaseModel):
    """Alert annotations from AlertManager."""

    summary: str
    description: str
    recommendation: str | None = None


class AlertLabels(BaseModel):
    """Alert labels from AlertManager."""

    alertname: str
    severity: str
    component: str
    resource: str | None = None
    service: str | None = None


class AlertInstance(BaseModel):
    """Single alert instance from AlertManager."""

    status: str
    labels: Dict[str, str]
    annotations: Dict[str, str]
    startsAt: str
    endsAt: str | None = None
    generatorURL: str
    fingerprint: str


class AlertManagerWebhook(BaseModel):
    """AlertManager webhook payload structure."""

    version: str
    groupKey: str
    truncatedAlerts: int = 0
    status: str
    receiver: str
    groupLabels: Dict[str, str]
    commonLabels: Dict[str, str]
    commonAnnotations: Dict[str, str]
    externalURL: str
    alerts: List[AlertInstance]


# ---------------------------------------------------------------------------
# files.py schemas
# ---------------------------------------------------------------------------


class FileInfo(BaseModel):
    """File information model."""

    name: str
    path: str
    is_directory: bool
    size: int | None = None
    mime_type: str | None = None
    last_modified: datetime
    permissions: str
    extension: str | None = None


class DirectoryListing(BaseModel):
    """Directory listing response model."""

    current_path: str
    parent_path: str | None = None
    files: List[FileInfo]
    total_files: int
    total_directories: int
    total_size: int


class FilesAPIUploadResponse(BaseModel):
    """File upload response model."""

    success: bool
    message: str
    file_info: FileInfo | None = None
    upload_id: str | None = None


class FileOperation(BaseModel):
    """File operation request model."""

    path: str

    @field_validator("path")
    @classmethod
    def validate_path(cls, v):
        """Validate path to prevent directory traversal attacks."""
        if not v or ".." in v or v.startswith("/"):
            raise ValueError("Invalid path")
        return v


# ---------------------------------------------------------------------------
# data_storage.py schemas
# ---------------------------------------------------------------------------


class StorageCategory(BaseModel):
    """Storage category with size info."""

    name: str
    path: str
    size_bytes: int
    size_human: str
    file_count: int
    description: str
    can_cleanup: bool = True
    cleanup_type: str = "manual"


class StorageStats(BaseModel):
    """Overall storage statistics."""

    total_size_bytes: int
    total_size_human: str
    total_files: int
    total_directories: int
    categories: List[StorageCategory]
    last_cleanup: str | None = None


class StorageCleanupRequest(BaseModel):
    """Cleanup request model."""

    category: str
    older_than_days: int = 0
    dry_run: bool = True


class CleanupResult(BaseModel):
    """Cleanup operation result."""

    category: str
    files_removed: int
    bytes_freed: int
    bytes_freed_human: str
    dry_run: bool
    errors: List[str] = []


# ---------------------------------------------------------------------------
# project.py schemas
# ---------------------------------------------------------------------------


class PhaseStatusItem(BaseModel):
    name: str
    completion: float
    is_active: bool
    is_completed: bool
    capabilities: int
    implemented_capabilities: int


class ProjectStatusResponse(BaseModel):
    current_phase: str
    total_phases: int
    completed_phases: int
    active_phases: int
    overall_completion: float
    next_suggested_phase: str | None
    phases: Dict[str, PhaseStatusItem]


class ProjectReportResponse(BaseModel):
    status: str
    overall_completion: float
    current_phase: str
    total_phases: int
    completed_phases: int
    generated_at: str


# ---------------------------------------------------------------------------
# phases.py schemas
# ---------------------------------------------------------------------------


class PhaseEntry(BaseModel):
    id: str
    name: str
    completion: float
    is_active: bool
    is_completed: bool


class PhasesStatusResponse(BaseModel):
    status: str
    service: str
    phases: List[PhaseEntry]
    timestamp: str


class ValidationRunResponse(BaseModel):
    status: str
    message: str
    timestamp: str


# ---------------------------------------------------------------------------
# redis_service.py schemas
# ---------------------------------------------------------------------------


class ServiceOperationResponse(BaseModel):
    """Service operation response."""

    success: bool
    operation: str = Field(..., description="Operation type: start, stop, restart")
    message: str
    duration_seconds: float
    timestamp: datetime
    new_status: str = Field(..., description="New service status: running, stopped, failed, unknown")
    error: str | None = None


class ServiceStatusResponse(BaseModel):
    """Service status response."""

    status: str = Field(..., description="Service status: running, stopped, failed, unknown")
    pid: int | None = None
    uptime_seconds: float | None = None
    memory_mb: float | None = None
    last_check: datetime


class HealthStatusResponse(BaseModel):
    """Health status response."""

    overall_status: str = Field(..., description="Overall health: healthy, degraded, critical")
    service_running: bool
    connectivity: bool
    response_time_ms: float
    last_successful_command: datetime | None = None
    error_count_last_hour: int = 0
    recommendations: list = Field(default_factory=list)


# ---------------------------------------------------------------------------
# process_management.py schemas
# ---------------------------------------------------------------------------


class SpawnRequest(BaseModel):
    """Body for POST /processes/spawn."""

    agent_id: str = Field(..., description="Agent that owns the process")
    command: str = Field(..., description="Executable path or name")
    args: List[str] = Field(default_factory=list, description="Command arguments")
    timeout_seconds: int = Field(default=300, ge=1, le=86400)
    task_id: str | None = Field(default=None, description="Optional parent task ID")


class SignalRequest(BaseModel):
    """Body for POST /processes/{process_id}/signal."""

    signal: str = Field(..., description="Signal name: SIGTERM or SIGKILL")


class SpawnResponse(BaseModel):
    """Response for a successful spawn."""

    process_id: str
    status: str
    message: str


# ---------------------------------------------------------------------------
# diagnostics.py schemas
# ---------------------------------------------------------------------------


class FailureAnalysisRequest(BaseModel):
    """Request to analyze a task failure."""

    task_id: str
    error_description: str | None = None


class FailureAnalysisResponse(BaseModel):
    """Response from failure analysis."""

    data: dict


class HealthCheckResponse(BaseModel):
    """Health check response."""

    status: str
    engine_ready: bool


# ---------------------------------------------------------------------------
# cache_management.py schemas
# ---------------------------------------------------------------------------


class SemanticCacheConfigUpdate(BaseModel):
    """Request body for semantic cache config update."""

    similarity_threshold: float | None = None
    max_collection_size: int | None = None
    response_ttl: int | None = None
    enabled: bool | None = None


class SufficiencyConfigUpdate(BaseModel):
    """Request body for sufficiency evaluator config update."""

    enabled: bool | None = None
    keyword_threshold: float | None = None
    enable_llm_pass: bool | None = None
    llm_timeout: float | None = None


class TopicCacheConfigUpdate(BaseModel):
    """Request body for topic cache config update."""

    similarity_threshold: float | None = None
    max_topics: int | None = None
    ttl: int | None = None
    enabled: bool | None = None


# ---------------------------------------------------------------------------
# feature_flags.py schemas
# ---------------------------------------------------------------------------


class EnforcementModeUpdate(BaseModel):
    """Update enforcement mode request."""

    mode: EnforcementMode = Field(..., description="New enforcement mode")


class FeatureFlagInfo(BaseModel):
    """Feature flag information."""

    name: str
    current_mode: str
    description: str
    available_modes: List[str]


class ViolationStatistics(BaseModel):
    """Access control violation statistics."""

    total_violations: int
    period_days: int
    by_endpoint: Dict[str, int]
    by_user: Dict[str, int]
    by_day: Dict[str, int]
    current_mode: str


# ---------------------------------------------------------------------------
# secrets.py enums + schemas
# ---------------------------------------------------------------------------

_SECRET_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\.]+$")


def _validate_secret_name(name: str) -> str:
    """Validate and sanitize secret name."""
    if not _SECRET_NAME_PATTERN.match(name):
        raise ValueError("Secret name must contain only alphanumeric characters, " "underscores, hyphens, and dots")
    return name


class SecretScope(str, Enum):
    """Secret scope enumeration."""

    CHAT = "chat"
    GENERAL = "general"
    USER = "user"
    SESSION = "session"
    SHARED = "shared"
    GROUP = "group"
    ORGANIZATION = "organization"


class SecretType(str, Enum):
    """Secret type enumeration."""

    SSH_KEY = "ssh_key"
    PASSWORD = "password"  # nosec B105 - enum value  # nosemgrep: autobot-hardcoded-secret-key  # nosemgrep
    API_KEY = "api_key"  # nosemgrep: autobot-hardcoded-secret-key  # nosemgrep
    TOKEN = "token"  # nosec B105 - enum value  # nosemgrep: autobot-hardcoded-secret-key  # nosemgrep
    CERTIFICATE = "certificate"
    DATABASE_URL = "database_url"
    INFRASTRUCTURE_HOST = "infrastructure_host"
    OTHER = "other"


class SecretModel(BaseModel):
    """Secret data model."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    type: SecretType
    scope: SecretScope
    chat_id: str | None = None
    description: str | None = ""
    tags: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    expires_at: datetime | None = None
    metadata: Metadata = Field(default_factory=dict)


class SecretCreateRequest(BaseModel):
    """Request model for creating secrets."""

    name: str = Field(..., min_length=1, max_length=256)
    type: SecretType
    scope: SecretScope
    value: str = Field(..., min_length=1, max_length=65536)
    chat_id: str | None = Field(None, max_length=128)
    description: str | None = Field("", max_length=1024)
    tags: List[str] = Field(default_factory=list)
    expires_at: datetime | None = None
    metadata: Metadata = Field(default_factory=dict)
    owner_id: str | None = Field(None, max_length=128, description="Owner user ID")
    org_id: str | None = Field(None, max_length=128, description="Organization ID for org-level secrets")
    team_ids: List[str] = Field(default_factory=list, description="Team IDs for group-level secrets")
    shared_with: List[str] = Field(default_factory=list, description="User IDs to share with")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return _validate_secret_name(v)

    def to_secret_model(self, secret_id: str | None = None) -> "SecretModel":
        """Convert request to SecretModel."""
        return SecretModel(
            id=secret_id or str(uuid.uuid4()),
            name=self.name,
            type=self.type,
            scope=self.scope,
            chat_id=self.chat_id if self.scope == SecretScope.CHAT else None,
            description=self.description,
            tags=self.tags,
            expires_at=self.expires_at,
            metadata=self.metadata,
        )

    def is_chat_scoped(self) -> bool:
        return self.scope == SecretScope.CHAT

    def requires_chat_id(self) -> bool:
        return self.is_chat_scoped() and not self.chat_id

    def get_log_summary(self) -> str:
        return f"{self.scope.value} secret '{self.name}'"


class SecretUpdateRequest(BaseModel):
    """Request model for updating secrets."""

    name: str | None = Field(None, min_length=1, max_length=256)
    description: str | None = Field(None, max_length=1024)
    tags: List[str] | None = None
    expires_at: datetime | None = None
    metadata: Metadata | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str | None) -> str | None:
        if v is not None:
            return _validate_secret_name(v)
        return v


class SecretTransferRequest(BaseModel):
    """Request model for transferring secrets between scopes."""

    secret_ids: List[str]
    target_scope: SecretScope
    target_chat_id: str | None = None


# ---------------------------------------------------------------------------
# vnc_manager.py schemas
# ---------------------------------------------------------------------------


class VNCOCRRequest(BaseModel):
    """OCR text recognition request (VNC desktop)."""

    region: Dict[str, int] = Field(
        default_factory=dict,
        description="Optional region {x, y, width, height}, empty for full screen",
    )


class FindImageRequest(BaseModel):
    """Find image on screen request."""

    template_data: str = Field(..., description="Base64-encoded template image (PNG)")
    threshold: float = Field(default=0.8, ge=0.0, le=1.0, description="Match confidence threshold (0-1)")


class WaitForTextRequest(BaseModel):
    """Wait for text to appear request."""

    text: str = Field(..., description="Text to wait for")
    timeout_seconds: int = Field(default=30, ge=1, le=300, description="Timeout in seconds")
    region: Dict[str, int] = Field(default_factory=dict, description="Optional region to search")


class WaitForImageRequest(BaseModel):
    """Wait for image to appear request."""

    template_data: str = Field(..., description="Base64-encoded template image")
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    threshold: float = Field(default=0.8, ge=0.0, le=1.0)


class DesktopSessionState(BaseModel):
    """Desktop state tied to a chat session."""

    session_id: str = Field(..., description="Chat session ID")
    window_layout: Dict = Field(default_factory=dict, description="Window positions and sizes")
    active_applications: List[str] = Field(default_factory=list, description="Running applications")
    screenshots: List[str] = Field(default_factory=list, description="Screenshot file paths")
    action_log: List[Dict] = Field(default_factory=list, description="VNC actions performed")
    last_updated: str = Field(default_factory=lambda: datetime.now(tz=timezone.utc).isoformat())


class SessionActionLog(BaseModel):
    """Log entry for VNC action in a session."""

    action_type: str = Field(..., description="Type of action performed")
    params: Dict = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.now(tz=timezone.utc).isoformat())
    result: str = Field(default="success", description="Action result: success/error")


# ---------------------------------------------------------------------------
# branch_health.py schemas
# ---------------------------------------------------------------------------


class BranchDivergenceResponse(BaseModel):
    """Branch divergence metrics response."""

    branch: str
    ahead: int
    behind: int
    total_commits_diverged: int
    conflicting_files: List[str] = Field(default_factory=list)


class BranchHealthResponse(BaseModel):
    """Branch health metrics response."""

    branch: str
    divergence: BranchDivergenceResponse
    days_since_activity: float
    is_stale: bool
    health_score: float
    last_activity: str = Field(None, description="ISO format datetime or null")


# ---------------------------------------------------------------------------
# hot_reload.py schemas
# ---------------------------------------------------------------------------


class ReloadRequest(BaseModel):
    """Request model for module reload."""

    module_name: str = None
    force: bool = False


class ReloadResponse(BaseModel):
    """Response model for reload operations."""

    success: bool
    message: str
    results: Metadata = {}
    reloaded_modules: list = []
    errors: list = []


# ---------------------------------------------------------------------------
# config_revisions.py schemas
# ---------------------------------------------------------------------------


class ConfigRevisionResponse(BaseModel):
    """Response for a single config revision."""

    id: str
    entity_type: str
    entity_id: str
    before_config: Dict[str, Any] | None = None
    after_config: Dict[str, Any]
    changed_keys: List[str] = Field(default_factory=list)
    source: str
    created_by: str
    created_at: str | None = None
    updated_at: str | None = None


# ---------------------------------------------------------------------------
# gpu_monitoring.py schemas
# ---------------------------------------------------------------------------


class GPUConfigUpdateRequest(BaseModel):
    """Request body for GPU optimization configuration updates."""

    updates: Dict[str, Any]


# ---------------------------------------------------------------------------
# startup.py schemas
# ---------------------------------------------------------------------------

from enum import Enum as _StartupEnum


class StartupPhase(str, _StartupEnum):
    """Lifecycle phase the backend reports during boot."""

    INITIALIZING = "initializing"
    STARTING_SERVICES = "starting_services"
    CONNECTING_BACKEND = "connecting_backend"
    LOADING_KNOWLEDGE = "loading_knowledge"
    READY = "ready"
    ERROR = "error"


class StartupMessage(BaseModel):
    """Startup status message broadcast to UI clients during boot."""

    phase: StartupPhase
    message: str
    progress: int  # 0-100
    timestamp: str
    icon: str
    details: str | None = None


# ---------------------------------------------------------------------------
# vnc_proxy.py schemas
# ---------------------------------------------------------------------------


class VncProxyStatusResponse(BaseModel):
    """Response for VNC proxy status check."""

    vnc_type: str
    endpoint: str
    accessible: bool
    status: int | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# onboarding.py schemas
# ---------------------------------------------------------------------------


class ApplyPresetRequest(BaseModel):
    """Request body for applying an onboarding preset."""

    preset_name: str
    overrides: Dict[str, Any] = Field(default_factory=dict)


class OnboardingStatus(BaseModel):
    """Response model for GET /api/onboarding/status."""

    preset_applied: bool


# ---------------------------------------------------------------------------
# security_assessment.py response data schemas (GH #6509)
# ---------------------------------------------------------------------------


class AssessmentData(BaseModel):
    """Assessment entity from SecurityWorkflowManager.to_dict()."""

    model_config = {"extra": "allow"}
    id: str
    name: str
    target: str
    phase: str
    training_mode: bool = False
    hosts: List[Dict[str, Any]] = Field(default_factory=list)
    findings: List[Dict[str, Any]] = Field(default_factory=list)
    actions: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None


class AssessmentListData(BaseModel):
    """Response data for list_assessments."""

    assessments: List[Dict[str, Any]]
    count: int


class AssessmentPhaseData(BaseModel):
    """Response data for get_current_phase."""

    current_phase: str
    description: str = ""
    available_actions: List[str] = Field(default_factory=list)
    valid_transitions: List[str] = Field(default_factory=list)
    training_mode: bool = False


class AssessmentFindingsData(BaseModel):
    """Response data for get_findings."""

    findings: List[Dict[str, Any]]
    vulnerabilities: List[Dict[str, Any]]
    total_findings: int
    total_vulnerabilities: int


class ParseToolOutputData(BaseModel):
    """Response data for parse_and_store_tool_output."""

    tool: str
    scan_type: str | None = None
    hosts_added: int
    ports_added: int
    vulnerabilities_added: int
    parsed_data: Dict[str, Any] = Field(default_factory=dict)


class AssessmentPhaseDefinitionsData(BaseModel):
    """Response data for get_phase_definitions."""

    phases: Dict[str, Any]
    transitions: Dict[str, Any]


# ---------------------------------------------------------------------------
# secrets.py response data schemas (GH #6509)
# ---------------------------------------------------------------------------


class SecretCreatedData(BaseModel):
    """Response data for create_secret and update_secret."""

    status: str
    message: str
    secret: Dict[str, Any]


class SecretsListData(BaseModel):
    """Response data for list_secrets."""

    secrets: List[Dict[str, Any]]
    total_count: int
    filters: Dict[str, Any] = Field(default_factory=dict)


class SecretTypesData(BaseModel):
    """Response data for get_secret_types."""

    types: List[Dict[str, str]]
    scopes: List[Dict[str, str]]


class SecretsStatsData(BaseModel):
    """Response data for get_secrets_stats."""

    total_secrets: int
    by_scope: Dict[str, int]
    by_type: Dict[str, int]
    by_chat: Dict[str, int] = Field(default_factory=dict)
    expired_count: int


class SecretTransferData(BaseModel):
    """Response data for transfer_secrets."""

    status: str
    message: str
    result: Dict[str, Any]


class ChatSecretsDeleteData(BaseModel):
    """Response data for delete_chat_secrets."""

    status: str
    message: str
    result: Dict[str, Any]


# ---------------------------------------------------------------------------
# security.py response data schemas (GH #6509)
# ---------------------------------------------------------------------------


class PendingApprovalsData(BaseModel):
    """Response data for get_pending_approvals."""

    success: bool = True
    pending_approvals: List[Dict[str, Any]]
    count: int


class CommandHistoryData(BaseModel):
    """Response data for get_command_history."""

    success: bool = True
    command_history: List[Dict[str, Any]]
    count: int


class AuditLogData(BaseModel):
    """Response data for get_audit_log."""

    success: bool = True
    audit_entries: List[Dict[str, Any]]
    count: int
    preset_name: str | None = None


# ---------------------------------------------------------------------------
# project_state.py schemas (GH #6509 Batch D)
# ---------------------------------------------------------------------------


class ProjectStateValidateResponse(BaseModel):
    """Response for POST /validate."""

    success: bool
    message: str = ""
    results: Dict[str, Any] = Field(default_factory=dict)


class ProjectStateReportResponse(BaseModel):
    """Response for GET /report."""

    success: bool
    report: str = ""
    generated_at: str | None = None


class ProjectStatePhasesResponse(BaseModel):
    """Response for GET /phases."""

    success: bool
    current_phase: str = ""
    phases: Dict[str, Any] = Field(default_factory=dict)


class ProjectStateActivatePhaseResponse(BaseModel):
    """Response for POST /phase/{phase_id}/activate."""

    success: bool
    message: str = ""
    current_phase: str = ""


class ProjectStateAutoProgressResponse(BaseModel):
    """Response for POST /auto-progress."""

    success: bool
    message: str = ""
    progression_result: Any = None


# ---------------------------------------------------------------------------
# gpu_monitoring.py schemas (GH #6509 Batch D)
# ---------------------------------------------------------------------------


class GPUEfficiencyResponse(BaseModel):
    """Response for GET /efficiency."""

    success: bool
    efficiency: Dict[str, Any] = Field(default_factory=dict)


class GPUCapabilitiesResponse(BaseModel):
    """Response for GET /capabilities."""

    success: bool
    capabilities: Dict[str, Any] = Field(default_factory=dict)


class GPUBenchmarkResponse(BaseModel):
    """Response for POST /benchmark."""

    success: bool
    benchmark: Dict[str, Any] = Field(default_factory=dict)


class GPUOptimizeResponse(BaseModel):
    """Response for POST /optimize."""

    success: bool
    optimization: Dict[str, Any] = Field(default_factory=dict)


class GPUConfigUpdateResponse(BaseModel):
    """Response for PATCH /config."""

    success: bool
    updated_keys: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# auth.py / audit.py / hot_reload.py / startup.py / process_management.py /
# captcha.py / models.py / llm_providers.py / security_assessment.py schemas
# (GH #6509 Batch E)
# ---------------------------------------------------------------------------


class AuthLogoutData(BaseModel):
    """Response data for POST /auth/logout."""

    success: bool = True
    message: str = ""


class AuthRefreshData(BaseModel):
    """Response data for POST /auth/refresh."""

    success: bool = True
    token: str = ""
    expiresIn: int = 0


class AuditCleanupData(BaseModel):
    """Response data for POST /audit/cleanup."""

    success: bool = True
    message: str = ""
    days_retained: int = 0


class AuditOperationsData(BaseModel):
    """Response data for GET /audit/operations."""

    success: bool = True
    categories: Dict[str, List[str]] = Field(default_factory=dict)
    total_operations: int = 0


class HotReloadStatusData(BaseModel):
    """Response data for POST /hot-reload/start and /stop."""

    success: bool = True
    message: str = ""


class StartupPhaseUpdateData(BaseModel):
    """Response data for POST /startup/phase."""

    success: bool = True
    phase: str = ""
    progress: int = 0
    error: str | None = None


class ProcessStatusData(BaseModel):
    """Response data for GET /processes/{process_id}."""

    process_id: str = ""
    status: str = ""
    command: str | None = None
    log_excerpt: str | None = None
    log_path: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


class ProcessSignalData(BaseModel):
    """Response data for POST /processes/{process_id}/signal."""

    process_id: str = ""
    signal: str = ""
    delivered: bool = False


class AgentProcessesData(BaseModel):
    """Response data for GET /agents/{agent_id}/processes."""

    agent_id: str = ""
    processes: List[Dict[str, Any]] = Field(default_factory=list)
    total: int = 0


class CaptchaPendingData(BaseModel):
    """Response data for GET /captcha/pending."""

    success: bool = True
    pending_captchas: List[Any] = Field(default_factory=list)
    count: int = 0
    timestamp: str = ""


class ModelsAvailableData(BaseModel):
    """Response data for GET /models/available."""

    models: List[Dict[str, Any]] = Field(default_factory=list)


class LLMProviderSwitchData(BaseModel):
    """Response data for POST /llm/switch."""

    success: bool = True
    provider: str = ""
    model: str = ""


class LLMProviderListData(BaseModel):
    """Response data for GET /llm/providers."""

    active_provider: str = ""
    providers: List[Dict[str, Any]] = Field(default_factory=list)


class LLMProviderTestData(BaseModel):
    """Response data for POST /llm/providers/{provider_name}/test."""

    provider: str = ""
    available: bool = False
    error: str | None = None


class AssessmentMutationData(BaseModel):
    """Response data for assessment mutation endpoints (delete/add host/port/vulnerability/finding)."""

    success: bool = True
    message: str = ""
    request_id: str = ""


# ---------------------------------------------------------------------------
# Telegram Bot (MVA-2074)
# ---------------------------------------------------------------------------


class TelegramWebhookUpdate(BaseModel):
    """Telegram webhook update object."""

    update_id: int
    message: Optional[Dict[str, Any]] = None
    edited_message: Optional[Dict[str, Any]] = None
    channel_post: Optional[Dict[str, Any]] = None
    edited_channel_post: Optional[Dict[str, Any]] = None
    callback_query: Optional[Dict[str, Any]] = None


class TelegramBotConfigRequest(BaseModel):
    """Request to configure Telegram bot."""

    bot_token: str = Field(..., description="Telegram Bot API token")
    webhook_url: Optional[str] = Field(None, description="Webhook URL (optional)")


class TelegramBotConfigResponse(BaseModel):
    """Response for Telegram bot configuration."""

    status: str
    message: str
    webhook_url: Optional[str] = None


class WhatsAppConfigRequest(BaseModel):
    """Request to configure the WhatsApp Business API channel (GH#9007)."""

    access_token: str = Field(..., description="Meta WhatsApp Business API access token")
    phone_number_id: str = Field(..., description="WhatsApp Business phone number ID")
    app_secret: str = Field(..., description="Meta app secret for webhook signature verification")
    verify_token: str = Field(..., description="Token echoed during Meta webhook subscription challenge")
    business_account_id: Optional[str] = Field(None, description="WhatsApp Business Account ID (optional)")
    base_url: Optional[str] = Field(None, description="Override API base URL for self-hosted deployments")


class WhatsAppConfigResponse(BaseModel):
    """Response for WhatsApp Business API configuration (GH#9007)."""

    status: str
    message: str
    phone_number: Optional[str] = None


# ---------------------------------------------------------------------------
# Execution Snapshot schemas (GH#4458, MVA-2227)
# ---------------------------------------------------------------------------


class CreateSnapshotRequest(BaseModel):
    """Request for POST /execution/snapshots."""

    container_id: str = Field(..., description="Docker container ID to snapshot")
    session_id: str = Field("", description="Optional agent session identifier")


class SnapshotMetadata(BaseModel):
    """Snapshot metadata returned by list/create endpoints."""

    snapshot_id: str
    session_id: str
    container_id: str
    image_name: str
    created_at: str
    size_bytes: int
    labels: Dict[str, str] = Field(default_factory=dict)
    user_id: str = ""


class CreateSnapshotResponse(BaseModel):
    """Response for POST /execution/snapshots."""

    success: bool
    snapshot: SnapshotMetadata
    message: str = ""


class SnapshotListResponse(BaseModel):
    """Response for GET /execution/snapshots."""

    success: bool
    snapshots: List[SnapshotMetadata]
    count: int


class RestoreSnapshotResponse(BaseModel):
    """Response for POST /execution/snapshots/{id}/restore."""

    success: bool
    container_id: str = Field(..., description="ID of the restored container")
    snapshot_id: str
    message: str = ""


class DeleteSnapshotResponse(BaseModel):
    """Response for DELETE /execution/snapshots/{id}."""

    success: bool
    message: str


# ==================== Telemetry Settings (Issue #9035) ====================


class TelemetrySettingsResponse(BaseModel):
    """Response for GET /api/settings/telemetry - Issue #9035."""

    enabled: bool = Field(..., description="Whether telemetry is enabled")
    anonymous_usage_stats: bool = Field(..., description="Record anonymous usage metrics locally (never transmitted)")
    first_run_prompt_shown: bool = Field(..., description="First-run prompt has been shown")


class TelemetrySettingsRequest(BaseModel):
    """Request for POST /api/settings/telemetry - Issue #9035."""

    enabled: bool = Field(..., description="Enable/disable telemetry collection")
    anonymous_usage_stats: bool = Field(
        default=True,
        description="Record anonymous usage metrics locally (never transmitted)",
    )
    first_run_prompt_shown: bool = Field(
        default=False,
        description="Mark first-run prompt as shown",
    )
