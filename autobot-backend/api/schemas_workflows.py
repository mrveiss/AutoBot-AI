# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Workflow, registry, RUM, elevation, advanced-control, state-tracking, and validation schemas.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from api.schemas_common import SuccessMessageResponse


# ---------------------------------------------------------------------------
# Workflows schemas
# ---------------------------------------------------------------------------

class ValidationDashboardStatusResponse(BaseModel):
    """Response for GET /status (healthy path; unavailable path uses JSONResponse)."""

    status: str
    service: str
    output_directory: Optional[str] = None
    refresh_interval: Optional[int] = None
    data_retention_days: Optional[int] = None
    timestamp: str



class ValidationDashboardReportResponse(BaseModel):
    """Response for GET /report."""

    status: str
    report: Optional[Any] = None
    timestamp: str



class ValidationDashboardGenerateResponse(BaseModel):
    """Response for POST /generate."""

    status: str
    message: str
    settings: Dict[str, Any]
    timestamp: str



class ValidationDashboardMetricsResponse(BaseModel):
    """Response for GET /metrics."""

    status: str
    metrics: Dict[str, Any]
    timestamp: str



class ValidationDashboardTrendsResponse(BaseModel):
    """Response for GET /trends."""

    status: str
    trends: Optional[Any] = None
    timestamp: str



class ValidationDashboardAlertsResponse(BaseModel):
    """Response for GET /alerts."""

    status: str
    alerts: List[Any]
    alert_counts: Dict[str, int]
    timestamp: str



class ValidationDashboardRecommendationsResponse(BaseModel):
    """Response for GET /recommendations."""

    status: str
    recommendations: List[Any]
    recommendation_counts: Dict[str, int]
    timestamp: str



class ValidationJudgmentResponse(BaseModel):
    """Response for POST /judge_workflow_step and POST /judge_agent_response."""

    status: str
    judgment: Dict[str, Any]
    timestamp: str



class ValidationJudgeStatusResponse(BaseModel):
    """Response for GET /judge_status (healthy path; unavailable path uses JSONResponse)."""

    status: str
    service: str
    available_judges: List[str]
    judge_metrics: Dict[str, Any]
    timestamp: str



# ---------------------------------------------------------------------------
# templates.py schemas
# ---------------------------------------------------------------------------



class StateTrackingStatusResponse(BaseModel):
    """Response for GET /status."""

    status: str
    service: str
    timestamp: str
    tracking_active: bool
    snapshot_count: Optional[Any] = None
    change_count: Optional[Any] = None
    latest_snapshot: Optional[Any] = None



class StateTrackingSummaryResponse(BaseModel):
    """Response for GET /summary."""

    status: str
    summary: Dict[str, Any]
    timestamp: str



class StateTrackingSnapshotResponse(BaseModel):
    """Response for POST /snapshot."""

    status: str
    message: str
    timestamp: str



class StateTrackingChangeResponse(BaseModel):
    """Response for POST /change (success path only).

    JSONResponse(400) for invalid change_type bypasses response_model.
    """

    status: str
    message: str
    change_type: str
    timestamp: str



class StateTrackingMilestonesResponse(BaseModel):
    """Response for GET /milestones."""

    status: str
    milestones: Dict[str, Any]
    achieved_count: int
    total_count: int
    timestamp: str



class StateTrackingTrendsResponse(BaseModel):
    """Response for GET /trends/{metric} (success path only).

    JSONResponse(400) for invalid metrics bypasses response_model.
    """

    status: str
    metric: str
    days: int
    data_points: int
    trend_data: List[Any]
    timestamp: str



class StateTrackingChangesResponse(BaseModel):
    """Response for GET /changes."""

    status: str
    changes: List[Any]
    total_changes: int
    showing: int
    timestamp: str



class StateTrackingReportResponse(BaseModel):
    """Response for GET /report."""

    status: str
    report: str
    format: str
    timestamp: str



class StateTrackingExportResponse(BaseModel):
    """Response for POST /export."""

    status: str
    message: str
    filename: str
    path: str
    format: str
    timestamp: str



class StateTrackingMetricsAllResponse(BaseModel):
    """Response for GET /metrics/all."""

    status: str
    metrics: Dict[str, Any]
    available_metrics: List[str]
    timestamp: str



class StateTrackingPhaseHistoryResponse(BaseModel):
    """Response for GET /phase-history/{phase_name}."""

    status: str
    phase_name: str
    days: int
    data_points: int
    history: List[Any]
    timestamp: str


# ---------------------------------------------------------------------------
# secrets.py schemas  (all endpoints use JSONResponse → response_model=None)
# development_speedup.py schemas  (all endpoints use JSONResponse → response_model=None)
# No new Pydantic models needed for those two files.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# analytics_code_review.py schemas
# ---------------------------------------------------------------------------



class WorkflowExportResponse(BaseModel):
    """Response for GET /export/{workflow_id}."""

    success: bool
    export: Dict[str, Any]



class WorkflowValidateImportResponse(BaseModel):
    """Response for POST /validate."""

    success: bool
    valid: bool
    issues: List[Any]



class WorkflowImportResponse(BaseModel):
    """Response for POST /import and POST /share/{share_id}/clone."""

    success: bool
    workflow_id: str



class WorkflowShareResponse(BaseModel):
    """Response for POST /share."""

    success: bool
    share_id: str



class WorkflowUnshareResponse(BaseModel):
    """Response for DELETE /share/{share_id}."""

    success: bool
    share_id: str



class WorkflowListSharesResponse(BaseModel):
    """Response for GET /shares."""

    success: bool
    shares: List[Any]
    total_count: int


# ---------------------------------------------------------------------------
# rum.py schemas  (Issue #5317)
# ---------------------------------------------------------------------------



class RUMConfigResponse(BaseModel):
    """Response for POST /rum/config."""

    status: str
    message: str
    config: Dict[str, Any]



class RUMEventResponse(BaseModel):
    """Response for POST /rum/event (both success and disabled/error paths).

    'session_event_count' is absent on the disabled/error path — Optional.
    """

    status: str
    message: str
    session_event_count: Optional[int] = None



class RUMDisableResponse(BaseModel):
    """Response for POST /rum/disable."""

    status: str
    message: str



class RUMClearResponse(BaseModel):
    """Response for POST /rum/clear."""

    status: str
    message: str
    events_cleared: int
    sessions_cleared: int



class RUMStatusResponse(BaseModel):
    """Response for GET /rum/status."""

    status: str
    rum_status: Dict[str, Any]



class RUMMetricsResponse(BaseModel):
    """Response for POST /rum/metrics (both success and error paths).

    'metrics_recorded' is absent on the error path — Optional.
    """

    status: str
    message: str
    session_id: str
    metrics_recorded: Optional[int] = None


# ---------------------------------------------------------------------------
# registry.py schemas  (Issue #5317)
# ---------------------------------------------------------------------------



class RegistryEndpointsResponse(BaseModel):
    """Response for GET /endpoints."""

    endpoints: List[Any]
    total: int



class RegistryRouterDetailResponse(BaseModel):
    """Response for GET /router/{router_name}.

    Includes a possible 'error' key when not found; extra fields allowed.
    """

    model_config = {"extra": "allow"}



class RegistryTagsResponse(BaseModel):
    """Response for GET /tags."""

    tags: List[str]



class RegistryTagRoutersResponse(BaseModel):
    """Response for GET /tags/{tag}."""

    tag: str
    routers: List[Any]
    count: int



class RegistryValidateResponse(BaseModel):
    """Response for GET /validate."""

    valid: bool
    errors: Dict[str, Any]



class RegistryHealthResponse(BaseModel):
    """Response for GET /health."""

    status: str
    total_routers: int
    enabled_routers: int
    disabled_routers: int


# ---------------------------------------------------------------------------
# elevation.py schemas  (Issue #5317)
# ---------------------------------------------------------------------------



class ElevationRequestResponse(SuccessMessageResponse):
    """Response for POST /elevation/request."""

    request_id: str



class ElevationAuthorizeResponse(SuccessMessageResponse):
    """Response for POST /elevation/authorize."""

    session_token: str
    expires_in: int



class ElevationStatusResponse(BaseModel):
    """Response for GET /elevation/status/{request_id}."""

    success: bool
    request_id: str
    status: str
    operation: str
    timestamp: Any  # datetime object serialised as string by FastAPI



class ElevationExecuteResponse(BaseModel):
    """Response for POST /elevation/execute/{session_token}."""

    success: bool
    output: str
    error: str
    return_code: int



class ElevationPendingResponse(BaseModel):
    """Response for GET /elevation/pending."""

    success: bool
    pending_requests: Dict[str, Any]
    count: int



class ElevationHealthResponse(BaseModel):
    """Response for GET /elevation/health."""

    status: str
    service: str
    active_sessions: int
    pending_requests: int
    timestamp: str


# ---------------------------------------------------------------------------
# usage.py schemas  (Issue #5317)
# ---------------------------------------------------------------------------



class StructuredThinkingClearResponse(SuccessMessageResponse):
    """Response for POST /mcp/clear_history."""

    session_id: str
    thoughts_cleared: int



class StructuredThinkingSessionsResponse(BaseModel):
    """Response for GET /sessions."""

    session_count: int
    sessions: List[Any]


# ---------------------------------------------------------------------------
# advanced_control.py schemas  (Issue #5317)
# ---------------------------------------------------------------------------



class AdvancedControlStreamingTerminateResponse(BaseModel):
    """Response for DELETE /streaming/{session_id}."""

    success: bool
    session_id: str



class AdvancedControlStreamingSessionsResponse(BaseModel):
    """Response for GET /streaming/sessions."""

    sessions: List[Any]
    count: int



class AdvancedControlTakeoverRequestResponse(BaseModel):
    """Response for POST /takeover/request."""

    success: bool
    request_id: str



class AdvancedControlTakeoverApproveResponse(BaseModel):
    """Response for POST /takeover/{request_id}/approve."""

    success: bool
    session_id: str



class AdvancedControlTakeoverActionResponse(BaseModel):
    """Response for POST /takeover/sessions/{session_id}/action."""

    success: bool
    result: Any



class AdvancedControlTakeoverSessionStatusResponse(BaseModel):
    """Response for pause/resume/complete takeover session endpoints."""

    success: bool
    session_id: str
    status: str



class AdvancedControlPendingTakeoversResponse(BaseModel):
    """Response for GET /takeover/pending."""

    pending_requests: List[Any]
    count: int



class AdvancedControlActiveTakeoversResponse(BaseModel):
    """Response for GET /takeover/active."""

    active_sessions: List[Any]
    count: int



class AdvancedControlEmergencyStopResponse(SuccessMessageResponse):
    """Response for POST /system/emergency-stop."""

    takeover_request_id: str



class AdvancedControlSystemHealthResponse(BaseModel):
    """Response for GET /system/health."""

    status: str
    desktop_streaming_available: bool
    novnc_available: bool
    active_streaming_sessions: int
    pending_takeovers: int
    active_takeovers: int
    paused_tasks: int



class AdvancedControlInfoResponse(BaseModel):
    """Response for GET /."""

    name: str
    version: str
    features: List[str]
    endpoints: Dict[str, Any]


# ---------------------------------------------------------------------------
# skills.py schemas  (Issue #5912)
# ---------------------------------------------------------------------------



class SkillsListResponse(BaseModel):
    """Response for GET /skills/."""

    skills: List[Any]
    total: int
    categories: List[str]


class SkillsCategoriesResponse(BaseModel):
    """Response for GET /skills/categories."""

    categories: Dict[str, int]


class SkillsAllHealthResponse(BaseModel):
    """Response for GET /skills/health."""

    skills: Dict[str, Any]


class SkillsInitializeResponse(BaseModel):
    """Response for POST /skills/initialize.

    Shape from manager.initialize() — opaque; extra allowed.
    """

    model_config = {"extra": "allow"}


class SkillDetailResponse(BaseModel):
    """Response for GET /skills/{name}.

    Shape from registry.get_skill_detail() — opaque; extra allowed.
    """

    model_config = {"extra": "allow"}


class SkillHealthResponse(BaseModel):
    """Response for GET /skills/{name}/health.

    Shape from SkillHealth.model_dump() — opaque; extra allowed.
    """

    model_config = {"extra": "allow"}


class SkillActionsResponse(BaseModel):
    """Response for GET /skills/{name}/actions."""

    skill: str
    actions: List[Any]


class SkillMetricsResponse(BaseModel):
    """Response for GET /skills/{name}/metrics.

    Shape from SkillMetrics.get_metrics() with health_score added — opaque; extra allowed.
    """

    model_config = {"extra": "allow"}


class SkillSuggestionsResponse(BaseModel):
    """Response for GET /skills/{name}/suggestions.

    Shape from SkillFeedbackAnalyzer.get_refinement_suggestions() — opaque; extra allowed.
    """

    model_config = {"extra": "allow"}


class MCPSpanResponse(BaseModel):
    """Single MCP tool-call span returned by the traces API (Issue #4413)."""

    trace_id: str
    skill_name: str
    tool_name: str
    started_at: float
    ended_at: Optional[float]
    input_params: Dict[str, Any]
    output: Optional[Dict[str, Any]]
    error: Optional[str]
    pid: int


class SkillTracesResponse(BaseModel):
    """Response for GET /skills/traces (Issue #4413)."""

    skill: Optional[str]
    traces: List[MCPSpanResponse]
    total: int


# ---------------------------------------------------------------------------
# structured_thinking_mcp.py schemas  (Issue #5912)
# ---------------------------------------------------------------------------



class StructuredThinkingSessionDetailResponse(BaseModel):
    """Response for GET /structured-thinking/sessions/{session_id}."""

    session_id: str
    thought_count: int
    thoughts: List[Any]
    stage_analysis: Dict[str, Any]
    started_at: Optional[str] = None
    last_thought_at: Optional[str] = None
    complete: bool


# ---------------------------------------------------------------------------
# batch_jobs.py schemas  (Issue #5989)
# ---------------------------------------------------------------------------


class BatchJobDeleteResponse(BaseModel):
    """Response for DELETE /{job_id} — cancel and delete a batch job."""

    status: str
    job_id: str
    message: str


class BatchTemplateDeleteResponse(BaseModel):
    """Response for DELETE /templates/{template_id}."""

    status: str
    template_id: str


class BatchScheduleDeleteResponse(BaseModel):
    """Response for DELETE /schedules/{schedule_id}."""

    status: str
    schedule_id: str


class BatchJobsHealthResponse(BaseModel):
    """Response for GET /health — batch jobs service health."""

    status: str
    service: str
    redis_connected: bool
    timestamp: str
    capabilities: List[str]


class BatchStatusResponse(BaseModel):
    """Response for GET /status — legacy batch processor status."""

    status: str
    service: str
    capabilities: List[str]
    max_batch_size: int
    timeout: int
    timestamp: str


class BatchLoadResponse(BaseModel):
    """Response for POST /load — multi-endpoint batch execution."""

    responses: Any
    errors: Any
    timing: Any


class BatchChatInitResponse(BaseModel):
    """Response for GET/POST /chat-init — optimized chat initialization."""

    chat_sessions: Any
    system_health: Any
    service_health: Any
    settings: Any
    timing: Any


# ---------------------------------------------------------------------------
# advanced_control.py schemas  (Issue #5989)
# ---------------------------------------------------------------------------


class AdvancedControlStreamingSessionListResponse(BaseModel):
    """Response for GET /streaming/sessions."""

    sessions: List[Any]
    count: int


class AdvancedControlStreamingCapabilitiesResponse(BaseModel):
    """Response for GET /streaming/capabilities.

    Shape is opaque (from get_system_capabilities()) — extra fields allowed.
    """

    model_config = {"extra": "allow"}


class AdvancedControlPendingTakeoversListResponse(BaseModel):
    """Response for GET /takeover/pending."""

    pending_requests: List[Any]
    count: int


class AdvancedControlActiveTakeoversListResponse(BaseModel):
    """Response for GET /takeover/active."""

    active_sessions: List[Any]
    count: int


class AdvancedControlTakeoverSystemStatusResponse(BaseModel):
    """Response for GET /takeover/status.

    Shape is opaque (from get_system_status()) — extra fields allowed.
    """

    model_config = {"extra": "allow"}


class AdvancedControlHealthResponse(BaseModel):
    """Response for GET /system/health."""

    status: str
    desktop_streaming_available: bool
    novnc_available: bool
    active_streaming_sessions: int
    pending_takeovers: int
    active_takeovers: int
    paused_tasks: int


class AdvancedControlInfoResponse(BaseModel):
    """Response for GET / — advanced control capabilities info."""

    name: str
    version: str
    features: List[str]
    endpoints: Any


# ---------------------------------------------------------------------------
# long_running_operations.py schemas  (Issue #5989)
# ---------------------------------------------------------------------------


class LongRunningOperationMigrateResponse(BaseModel):
    """Response for POST /migrate/existing."""

    operation_id: str
    status: str


class LongRunningOperationStatusResponse(BaseModel):
    """Response for GET /{operation_id} — opaque shape from _convert_operation_to_response."""

    model_config = {"extra": "allow"}


class LongRunningOperationListResponse(BaseModel):
    """Response for GET / — list operations."""

    operations: List[Any]
    total_count: int
    active_count: int
    completed_count: int
    failed_count: int


class LongRunningOperationCancelResponse(BaseModel):
    """Response for POST /{operation_id}/cancel."""

    status: str
    operation_id: str


class LongRunningOperationResumeResponse(BaseModel):
    """Response for POST /{operation_id}/resume."""

    status: str
    new_operation_id: str
    resumed_from: str
    original_operation_id: str


class LongRunningOperationHealthResponse(BaseModel):
    """Response for GET /health — long-running operations service health.

    JSONResponse(503/500) paths bypass response_model; success path only.
    """

    status: str
    active_operations: int
    total_operations: int
    redis_connected: bool
    background_processor_running: bool


# ---------------------------------------------------------------------------
# error_resilience.py schemas  (Issue #5989)
# ---------------------------------------------------------------------------


class ResilienceHealthResponse(BaseModel):
    """Response for GET /health — system resilience health."""

    status: str
    circuit_breakers: Any
    error_budgets: Any
    fallback_chains: Any


class CircuitBreakerStatusResponse(BaseModel):
    """Response for GET /circuit-breakers — opaque shape from manager.get_status()."""

    model_config = {"extra": "allow"}


class ErrorBudgetStatusResponse(BaseModel):
    """Response for GET /error-budgets — opaque shape from tracker.get_status()."""

    model_config = {"extra": "allow"}


class CircuitBreakerResetResponse(BaseModel):
    """Response for POST /circuit-breakers/{service_name}/reset."""

    message: str


class ErrorBudgetResetResponse(BaseModel):
    """Response for POST /error-budgets/{component}/reset."""

    message: str


# ---------------------------------------------------------------------------
# system_validation.py schemas  (Issue #5989)
# ---------------------------------------------------------------------------


class SystemValidationHealthResponse(BaseModel):
    """Response for GET /health — validation system health."""

    status: str
    message: str
    validator_initialized: bool
    timestamp: Optional[str] = None


class SystemValidationQuickResponse(BaseModel):
    """Response for GET /validate/quick."""

    status: str
    overall_score: float
    components: Any
    timestamp: str


class SystemValidationComponentResponse(BaseModel):
    """Response for GET /validate/component/{component_name}."""

    component: str
    status: str
    score: float
    details: Any
    timestamp: str


class SystemValidationRecommendationsResponse(BaseModel):
    """Response for GET /validate/recommendations."""

    total_recommendations: int
    recommendations: List[Any]
    timestamp: str


class SystemValidationStatusResponse(BaseModel):
    """Response for GET /validate/status."""

    validation_system: str
    available_validations: List[str]
    last_validation: Optional[Any] = None
    system_health: str
    timestamp: str


class SystemValidationBenchmarkResponse(BaseModel):
    """Response for POST /validate/benchmark."""

    benchmark_status: str
    benchmarks: Any
    overall_performance_score: float
    timestamp: str


# ---------------------------------------------------------------------------
# sequential_thinking_mcp.py schemas  (Issue #5989)
# ---------------------------------------------------------------------------


class SequentialThinkingMCPToolsResponse(BaseModel):
    """Response for GET /mcp/tools — list of MCP tools (each has name/description/input_schema)."""

    model_config = {"extra": "allow"}


class SequentialThinkingResponse(BaseModel):
    """Response for POST /mcp/sequential_thinking."""

    success: bool
    session_id: str
    thought_number: int
    total_thoughts: int
    progress_percentage: float
    thinking_complete: bool
    session_thought_count: int
    message: str
    revision_info: Optional[Any] = None
    branch_info: Optional[Any] = None
    summary: Optional[Any] = None


class SequentialThinkingSessionResponse(BaseModel):
    """Response for GET /sessions/{session_id}."""

    session_id: str
    thought_count: int
    thoughts: List[Any]
    revisions: List[Any]
    branches: List[Any]
    started_at: Optional[str] = None
    last_thought_at: Optional[str] = None


class SequentialThinkingSessionListResponse(BaseModel):
    """Response for GET /sessions — list all thinking sessions."""

    session_count: int
    sessions: List[Any]


# ---------------------------------------------------------------------------
# structured_thinking_mcp.py schemas  (Issue #5989)
# ---------------------------------------------------------------------------


class StructuredThinkingProcessThoughtResponse(BaseModel):
    """Response for POST /mcp/process_thought."""

    success: bool
    session_id: str
    thought_number: int
    total_thoughts: int
    progress_percentage: float
    current_stage: str
    thinking_complete: bool
    stage_distribution: Any
    session_thought_count: int
    message: str
    related_thoughts: Optional[List[Any]] = None
    completion_summary: Optional[Any] = None


# ---------------------------------------------------------------------------
# prompts.py schemas  (Issue #5989)
# ---------------------------------------------------------------------------


class PromptsListResponse(BaseModel):
    """Response for GET / — list all prompts with defaults."""

    prompts: List[Any]
    defaults: Any


class PromptsCacheClearResponse(BaseModel):
    """Response for POST /cache/clear."""

    status: str
    message: str


class PromptSaveResponse(BaseModel):
    """Response for POST/{PUT /{prompt_id} — save or update prompt."""

    id: str
    name: str
    type: str
    path: str
    content: str


class PromptRevertResponse(BaseModel):
    """Response for POST /{prompt_id}/revert."""

    id: str
    name: str
    type: str
    path: str
    content: str


# ---------------------------------------------------------------------------
# registry.py schemas  (Issue #5989)
# ---------------------------------------------------------------------------


class RegistryRoutersResponse(BaseModel):
    """Response for GET /routers — all registered routers with full config.

    Keyed by router name; each value is a router config dict.
    """

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# rum.py schemas  (Issue #5989)
# ---------------------------------------------------------------------------


class RUMExportResponse(BaseModel):
    """Response for GET /export — export RUM data for analysis."""

    status: str
    data: Any


# ---------------------------------------------------------------------------
# data_storage.py schemas  (Issue #5989)
# ---------------------------------------------------------------------------


class DataStorageDeleteConversationResponse(BaseModel):
    """Response for DELETE /conversations/{conversation_id}."""

    conversation_id: str
    files_deleted: List[str]
    errors: List[str]
    success: bool


class DataStorageDatabasesResponse(BaseModel):
    """Response for GET /databases — database files in data directory."""

    databases: List[Any]
    total_count: int
    total_size_bytes: int
    total_size_human: str


class DataStorageCategoryDetailResponse(BaseModel):
    """Response for GET /category/{category_path}."""

    category: str
    total_size_bytes: int
    total_size_human: str
    total_files: int
    files: List[Any]
    showing: int


class DataStorageOldBackupsResponse(BaseModel):
    """Response for POST /cleanup/old-backups."""

    directories_found: List[Any]
    total_count: int
    bytes_freed: int
    bytes_freed_human: str
    dry_run: bool
    message: str


class DataStorageConversationsSummaryResponse(BaseModel):
    """Response for GET /conversations/summary."""

    unique_conversations: int
    transcripts: Any
    chats: Any
    total_size_bytes: int
    total_size_human: str


# ---------------------------------------------------------------------------
# collaboration.py schemas  (Issue #5989)
# ---------------------------------------------------------------------------


class SessionPresenceResponse(BaseModel):
    """Response for GET /{session_id}/presence."""

    session_id: str
    online_users: List[Any]
    count: int


class SessionShareSecretResponse(BaseModel):
    """Response for POST /{session_id}/secrets/share."""

    success: bool
    secret_id: str
    shared_with_count: int


# ---------------------------------------------------------------------------
# analytics.py schemas  (Issue #5317)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# marketplace.py schemas  (Issue #5991)
# ---------------------------------------------------------------------------



class MarketplaceCategoriesResponse(BaseModel):
    """Response for GET /marketplace/categories."""

    categories: List[str]
    sort_options: List[str]



class MarketplaceInstalledResponse(BaseModel):
    """Response for GET /marketplace/installed."""

    installed: List[str]



class MarketplacePluginActionResponse(BaseModel):
    """Response for POST /marketplace/install and DELETE /marketplace/install/{plugin_name}."""

    status: str
    plugin: str
