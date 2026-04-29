# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Workflow, registry, RUM, elevation, advanced-control, state-tracking, and validation schemas.
"""

import re
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from api.schemas_common import SuccessMessageResponse
from autobot_shared.models.service_message import ServiceMessage
from constants.path_constants import PATH
from services.trigger_service import TriggerType
from autobot_shared.time_utils import now_utc
from models.approval import ApprovalType
from type_defs.common import Metadata


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


# ---------------------------------------------------------------------------
# workflow.py schemas (#6042)
# ---------------------------------------------------------------------------


class WorkflowApprovalRequest(BaseModel):
    workflow_id: str
    step_id: str
    step_description: str
    required_action: str
    context: Metadata
    timeout_seconds: int = 300


class WorkflowApprovalResponse(BaseModel):
    workflow_id: str
    step_id: str
    approved: bool
    user_input: Optional[Metadata] = None
    timestamp: float


class WorkflowStatusUpdate(BaseModel):
    workflow_id: str
    step_id: str
    status: str
    progress: float
    message: str
    timestamp: float


class WorkflowExecutionRequest(BaseModel):
    user_message: str
    workflow_id: Optional[str] = None
    auto_approve: bool = False


class WorkflowSummary(BaseModel):
    """Summary of a single workflow as returned by list/detail endpoints."""

    workflow_id: str
    user_message: str
    classification: str
    status: str
    total_steps: int
    current_step: int
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class WorkflowListResponse(BaseModel):
    """Response shape for GET /workflows."""

    success: bool
    active_workflows: int
    workflows: list[WorkflowSummary]


class WorkflowDetailResponse(BaseModel):
    """Response shape for GET /workflow/{workflow_id}."""

    success: bool
    workflow: Metadata


class WorkflowStatusResponse(BaseModel):
    """Response shape for GET /workflow/{workflow_id}/status."""

    success: bool
    workflow_id: str
    status: str
    current_step: int
    total_steps: int
    progress: float
    current_step_info: Optional[Metadata] = None
    estimated_remaining: Optional[str] = None


class WorkflowApproveResponse(BaseModel):
    """Response shape for POST /workflow/{workflow_id}/approve."""

    success: bool
    message: str
    next_action: str


class WorkflowCancelResponse(BaseModel):
    """Response shape for DELETE /workflow/{workflow_id}."""

    success: bool
    message: str


class PendingApprovalStep(BaseModel):
    """A single step awaiting user approval."""

    step_id: str
    description: str
    agent_type: str
    action: str
    context: Metadata


class WorkflowPendingApprovalsResponse(BaseModel):
    """Response shape for GET /workflow/{workflow_id}/pending_approvals."""

    success: bool
    workflow_id: str
    pending_approvals: list[PendingApprovalStep]


class WorkflowExecutionResponse(BaseModel):
    """Response shape for POST /execute (covers both simple and complex paths)."""

    success: bool
    type: str
    result: Optional[str] = None
    routing_method: Optional[str] = None
    workflow_id: Optional[str] = None
    execution_started: Optional[bool] = None
    status_endpoint: Optional[str] = None


# ---------------------------------------------------------------------------
# workflow_export.py schemas (#6042)
# ---------------------------------------------------------------------------


class ShareWorkflowRequest(BaseModel):
    """Request body for creating a workflow share (#2165)."""

    workflow_id: str = Field(..., description="ID of the workflow to share.")
    target_user_id: Optional[str] = Field(
        default=None,
        description="Share with a specific user.  Mutually optional with public.",
    )
    public: bool = Field(default=False, description="Make the share publicly accessible.")


class ImportWorkflowRequest(BaseModel):
    """Request body for importing a workflow from an export document (#2165)."""

    export_document: dict = Field(
        ...,
        description="WorkflowExportFormat.to_dict() payload produced by the export endpoint.",
    )
    session_id: Optional[str] = Field(
        default=None, description="Session to associate with the imported workflow."
    )


class CloneWorkflowRequest(BaseModel):
    """Request body for cloning a shared workflow (#2165)."""

    session_id: Optional[str] = Field(
        default=None, description="Session to associate with the cloned workflow."
    )


# ---------------------------------------------------------------------------
# workflow_permissions.py schemas (#6042)
# ---------------------------------------------------------------------------


class GrantPermissionRequest(BaseModel):
    """Request body for granting or updating a workflow role."""

    user_id: str = Field(..., description="User receiving the role")
    role: str = Field(..., description="owner | editor | runner | viewer")


class WorkflowPermissionResponse(BaseModel):
    """Serialised workflow permission entry."""

    workflow_id: str
    user_id: str
    role: str
    granted_by: Optional[str]
    created_at: str
    updated_at: str


class WorkflowAuditLogEntry(BaseModel):
    """Serialised workflow audit log entry."""

    id: str
    timestamp: str
    user_id: str
    workflow_id: str
    action: str
    details: Optional[dict]


# ---------------------------------------------------------------------------
# workflow_secrets.py schemas (#6042)
# ---------------------------------------------------------------------------

_WORKFLOW_SECRET_NAME_RE = re.compile(r"^[a-zA-Z0-9_\-\.]+$")


def _validate_workflow_secret_name(name: str) -> str:
    """Reject names containing characters outside the safe set. Issue #2153."""
    if not _WORKFLOW_SECRET_NAME_RE.match(name):
        raise ValueError(
            "Secret name must contain only alphanumeric characters, "
            "underscores, hyphens, and dots"
        )
    return name


class WorkflowSecretCreateRequest(BaseModel):
    """Request body for creating a workflow secret. Issue #2303: owner_id derived from auth."""

    name: str = Field(..., min_length=1, max_length=256)
    value: str = Field(..., min_length=1, max_length=65536)
    secret_type: str = Field(default="api_key", max_length=50)
    workflow_id: Optional[str] = Field(default=None, max_length=128)
    description: Optional[str] = Field(default=None, max_length=1024)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Reject unsafe characters in the secret name."""
        return _validate_workflow_secret_name(v)


class WorkflowSecretUpdateRequest(BaseModel):
    """Request body for updating a workflow secret's value. Issue #2303: owner_id from auth."""

    value: str = Field(..., min_length=1, max_length=65536)


class WorkflowSecretMetadata(BaseModel):
    """Safe metadata response — no value field. Issue #2153."""

    id: str
    name: str
    secret_type: str
    scope: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    description: Optional[str] = None


# ---------------------------------------------------------------------------
# workflow_state.py schemas (#6042)
# ---------------------------------------------------------------------------


class WorkflowState(BaseModel):
    """Persistent workflow state with explicit routing."""

    workflow_id: str
    goal: str
    current_step: str = "planning"
    active_service: str = "main-backend"
    steps_completed: List[str] = Field(default_factory=list)
    steps_remaining: List[Dict] = Field(default_factory=list)
    mailbox: List[ServiceMessage] = Field(default_factory=list)
    done: bool = False
    errors: List[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: now_utc().isoformat())
    updated_at: str = Field(default_factory=lambda: now_utc().isoformat())
    metadata: Dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# approval_gates.py schemas (#6042)
# ---------------------------------------------------------------------------


class AuthorTypeEnum(str, Enum):
    """Valid author types for approval comments."""

    HUMAN = "human"
    AGENT = "agent"
    SYSTEM = "system"


class CreateApprovalRequest(BaseModel):
    """Request body for creating an approval gate."""

    title: str
    approval_type: ApprovalType
    description: Optional[str] = None
    requested_by_agent: Optional[str] = None
    workflow_id: Optional[str] = None
    workflow_step: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    task_ids: Optional[List[str]] = None


class ApprovalTransitionRequest(BaseModel):
    """Request body for approve / reject / request-revision."""

    comment: Optional[str] = None


class ApprovalResubmitRequest(BaseModel):
    """Request body for resubmitting after revision."""

    description: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


class ApprovalAddCommentRequest(BaseModel):
    """Request body for adding a comment to an approval gate."""

    body: str
    author_type: AuthorTypeEnum = AuthorTypeEnum.HUMAN


class ApprovalLinkTaskRequest(BaseModel):
    """Request body for linking a task to an approval gate."""

    task_id: str
    task_type: str = "github_issue"


class TaskApprovalLinkResponse(BaseModel):
    """Response for a task-approval link."""

    id: str
    approval_id: str
    task_id: str
    task_type: str


class ApprovalCommentResponse(BaseModel):
    """Response for an approval gate comment."""

    id: str
    approval_id: str
    author: str
    author_type: str
    body: str
    created_at: Optional[str] = None


class ApprovalGateResponse(BaseModel):
    """Response for an approval gate."""

    id: str
    title: str
    description: Optional[str] = None
    approval_type: str
    status: str
    requested_by_agent: Optional[str] = None
    decided_by_user: Optional[str] = None
    workflow_id: Optional[str] = None
    workflow_step: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    decided_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    comments: List[ApprovalCommentResponse] = Field(default_factory=list)
    task_links: List[TaskApprovalLinkResponse] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# integration_project_management.py schemas
# ---------------------------------------------------------------------------


class ConnectionTestRequest(BaseModel):
    """Request to test project management connection."""

    provider: str = Field(..., description="Provider: jira, trello, or asana")
    base_url: Optional[str] = Field(None, description="Base URL for the service")
    api_key: Optional[str] = Field(None, description="API key")
    api_secret: Optional[str] = Field(None, description="API secret")
    token: Optional[str] = Field(None, description="Auth token")
    username: Optional[str] = Field(None, description="Username")
    password: Optional[str] = Field(None, description="Password")


class ProviderInfo(BaseModel):
    """Information about a supported provider."""

    provider: str
    name: str
    description: str
    auth_type: str
    base_url_required: bool
    documentation_url: str


class IssueCreateRequest(BaseModel):
    """Request to create a new issue/card/task."""

    title: str = Field(..., description="Issue title/name")
    description: Optional[str] = Field(None, description="Description")
    project_key: Optional[str] = Field(None, description="Project key (Jira) or ID (Trello/Asana)")
    issue_type: Optional[str] = Field("Task", description="Issue type (Jira)")
    list_id: Optional[str] = Field(None, description="List ID (Trello)")
    workspace_gid: Optional[str] = Field(None, description="Workspace GID (Asana)")


class IssueUpdateRequest(BaseModel):
    """Request to update an issue/card/task."""

    title: Optional[str] = Field(None, description="New title")
    description: Optional[str] = Field(None, description="New description")
    status: Optional[str] = Field(None, description="New status")
    transition_id: Optional[str] = Field(None, description="Transition ID (Jira)")
    list_id: Optional[str] = Field(None, description="Target list ID (Trello)")
    completed: Optional[bool] = Field(None, description="Completion status (Asana)")


class ProjectMgmtSearchRequest(BaseModel):
    """Request to search issues."""

    query: str = Field(..., description="Search query or JQL")
    max_results: Optional[int] = Field(50, description="Maximum results")


# ---------------------------------------------------------------------------
# triggers.py schemas
# ---------------------------------------------------------------------------


class TriggerCreateRequest(BaseModel):
    """Request body for POST /api/triggers."""

    trigger_type: TriggerType
    workflow_id: str = Field(..., min_length=1)
    config: Dict[str, Any] = Field(default_factory=dict)
    conditions: List[Dict[str, Any]] = Field(default_factory=list)
    enabled: bool = True

    @field_validator("workflow_id")
    @classmethod
    def workflow_id_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("workflow_id must not be empty or whitespace")
        return v


class TriggerCreateResponse(BaseModel):
    """Response body for POST /api/triggers."""

    trigger_id: str
    webhook_url: Optional[str] = None


class TriggerListResponse(BaseModel):
    """Response body for GET /api/triggers."""

    triggers: List[Dict[str, Any]]
    total: int


class FireTriggerRequest(BaseModel):
    """Optional request body for manually firing a trigger (internal/testing)."""

    payload: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# research_browser.py schemas
# ---------------------------------------------------------------------------


class BrowserResearchRequest(BaseModel):
    conversation_id: str
    url: str
    extract_content: bool = True


class SessionAction(BaseModel):
    session_id: str
    action: str
    timeout_seconds: Optional[int] = 300


class NavigationRequest(BaseModel):
    url: str


class CreateChatBrowserRequest(BaseModel):
    """Request to create/get browser session for chat."""

    conversation_id: str
    headless: bool = False
    initial_url: Optional[str] = None


# ---------------------------------------------------------------------------
# long_running_operations.py schemas
# ---------------------------------------------------------------------------


class CodebaseIndexingRequest(BaseModel):
    """Request model for codebase indexing operations."""

    codebase_path: str = Field(default=str(PATH.PROJECT_ROOT), description="Path to codebase to index")
    file_patterns: List[str] = Field(
        default=["*.py", "*.js", "*.vue", "*.ts", "*.jsx", "*.tsx"],
        description="File patterns to include",
    )
    include_tests: bool = Field(default=True, description="Include test files")
    include_docs: bool = Field(default=True, description="Include documentation files")
    max_file_size: int = Field(default=1024 * 1024, description="Maximum file size in bytes")
    priority: str = Field(default="normal", description="Operation priority")


class TestSuiteRequest(BaseModel):
    """Request model for comprehensive test suite operations."""

    test_path: str = Field(default=str(PATH.TESTS_DIR), description="Path to test directory")
    test_patterns: List[str] = Field(default=["test_*.py", "*_test.py"], description="Test file patterns")
    test_types: List[str] = Field(
        default=["unit", "integration", "performance"],
        description="Types of tests to run",
    )
    parallel_execution: bool = Field(default=True, description="Run tests in parallel")
    timeout_per_test: int = Field(default=300, description="Timeout per individual test in seconds")
    priority: str = Field(default="high", description="Operation priority")


class KnowledgeBaseRequest(BaseModel):
    """Request model for knowledge base operations."""

    source_paths: List[str] = Field(default=[str(PATH.PROJECT_ROOT)], description="Paths to populate from")
    document_types: List[str] = Field(default=["code", "docs", "config"], description="Document types to include")
    chunk_size: int = Field(default=1000, description="Chunk size for text processing")
    overlap: int = Field(default=200, description="Overlap between chunks")
    force_reindex: bool = Field(default=False, description="Force reindexing of existing documents")
    priority: str = Field(default="normal", description="Operation priority")


class SecurityScanRequest(BaseModel):
    """Request model for security scan operations."""

    scan_paths: List[str] = Field(default=[str(PATH.PROJECT_ROOT)], description="Paths to scan")
    scan_types: List[str] = Field(
        default=["vulnerability", "dependency", "secrets"],
        description="Types of security scans",
    )
    severity_threshold: str = Field(default="medium", description="Minimum severity to report")
    include_dependencies: bool = Field(default=True, description="Scan dependencies")
    priority: str = Field(default="high", description="Operation priority")


# ---------------------------------------------------------------------------
# integration_database.py schemas
# ---------------------------------------------------------------------------


class DatabaseConnectionRequest(BaseModel):
    """Request model for testing database connections."""

    provider: str = Field(..., description="Database provider (postgresql/mysql/mongodb)")
    host: str = Field("localhost", description="Database host")
    port: Optional[int] = Field(None, description="Database port (default: provider-specific)")
    username: Optional[str] = Field(None, description="Database username")
    password: Optional[str] = Field(None, description="Database password")
    database: str = Field("", description="Database name")


class DBIntegrationQueryRequest(BaseModel):
    """Request model for executing database queries."""

    query: str = Field(..., description="SQL query to execute (read-only)")
    database: str = Field("", description="Target database name")
    host: str = Field("localhost", description="Database host")
    port: Optional[int] = Field(None, description="Database port")
    username: Optional[str] = Field(None, description="Database username")
    password: Optional[str] = Field(None, description="Database password")


class MongoQueryRequest(BaseModel):
    """Request model for MongoDB collection queries."""

    database: str = Field(..., description="Database name")
    collection: str = Field(..., description="Collection name")
    filter: Dict[str, Any] = Field(default_factory=dict, description="Query filter")
    limit: int = Field(100, description="Maximum results to return")
    host: str = Field("localhost", description="MongoDB host")
    port: int = Field(27017, description="MongoDB port")
    username: Optional[str] = Field(None, description="MongoDB username")
    password: Optional[str] = Field(None, description="MongoDB password")


class DatabaseListRequest(BaseModel):
    """Request model for listing databases/tables."""

    host: str = Field("localhost", description="Database host")
    port: Optional[int] = Field(None, description="Database port")
    username: Optional[str] = Field(None, description="Database username")
    password: Optional[str] = Field(None, description="Database password")
    database: Optional[str] = Field(None, description="Database name (for table listing)")
