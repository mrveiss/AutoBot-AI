# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Workflow, registry, RUM, elevation, advanced-control, state-tracking, and validation schemas.
"""

import re
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator

from api.schemas_common import SuccessMessageResponse
from autobot_shared.models.service_message import ServiceMessage
from autobot_shared.time_utils import now_utc
from constants.path_constants import PATH
from models.approval import ApprovalType
from services.trigger_service import TriggerType
from type_defs.common import Metadata

# ---------------------------------------------------------------------------
# Workflows schemas
# ---------------------------------------------------------------------------


class ValidationDashboardStatusResponse(BaseModel):
    """Response for GET /status (healthy path; unavailable path uses JSONResponse)."""

    status: str
    service: str
    output_directory: str | None = None
    refresh_interval: int | None = None
    data_retention_days: int | None = None
    timestamp: str


class ValidationDashboardReportResponse(BaseModel):
    """Response for GET /report."""

    status: str
    report: Any | None = None
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
    trends: Any | None = None
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
    snapshot_count: Any | None = None
    change_count: Any | None = None
    latest_snapshot: Any | None = None


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
    session_event_count: int | None = None


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
    metrics_recorded: int | None = None


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
    ended_at: float | None
    input_params: Dict[str, Any]
    output: Dict[str, Any] | None
    error: str | None
    pid: int


class SkillTracesResponse(BaseModel):
    """Response for GET /skills/traces (Issue #4413)."""

    skill: str | None
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
    started_at: str | None = None
    last_thought_at: str | None = None
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
    timestamp: str | None = None


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
    last_validation: Any | None = None
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
    revision_info: Any | None = None
    branch_info: Any | None = None
    summary: Any | None = None


class SequentialThinkingSessionResponse(BaseModel):
    """Response for GET /sessions/{session_id}."""

    session_id: str
    thought_count: int
    thoughts: List[Any]
    revisions: List[Any]
    branches: List[Any]
    started_at: str | None = None
    last_thought_at: str | None = None


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
    related_thoughts: List[Any] | None = None
    completion_summary: Any | None = None


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
    user_input: Metadata | None = None
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
    workflow_id: str | None = None
    auto_approve: bool = False


class WorkflowSummary(BaseModel):
    """Summary of a single workflow as returned by list/detail endpoints."""

    workflow_id: str
    user_message: str
    classification: str
    status: str
    total_steps: int
    current_step: int
    started_at: str | None = None
    completed_at: str | None = None


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
    current_step_info: Metadata | None = None
    estimated_remaining: str | None = None


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
    result: str | None = None
    routing_method: str | None = None
    workflow_id: str | None = None
    execution_started: bool | None = None
    status_endpoint: str | None = None


# ---------------------------------------------------------------------------
# workflow_export.py schemas (#6042)
# ---------------------------------------------------------------------------


class ShareWorkflowRequest(BaseModel):
    """Request body for creating a workflow share (#2165)."""

    workflow_id: str = Field(..., description="ID of the workflow to share.")
    target_user_id: str | None = Field(
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
    session_id: str | None = Field(default=None, description="Session to associate with the imported workflow.")


class CloneWorkflowRequest(BaseModel):
    """Request body for cloning a shared workflow (#2165)."""

    session_id: str | None = Field(default=None, description="Session to associate with the cloned workflow.")


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
    granted_by: str | None
    created_at: str
    updated_at: str


class WorkflowAuditLogEntry(BaseModel):
    """Serialised workflow audit log entry."""

    id: str
    timestamp: str
    user_id: str
    workflow_id: str
    action: str
    details: dict | None


# ---------------------------------------------------------------------------
# workflow_secrets.py schemas (#6042)
# ---------------------------------------------------------------------------

_WORKFLOW_SECRET_NAME_RE = re.compile(r"^[a-zA-Z0-9_\-\.]+$")


def _validate_workflow_secret_name(name: str) -> str:
    """Reject names containing characters outside the safe set. Issue #2153."""
    if not _WORKFLOW_SECRET_NAME_RE.match(name):
        raise ValueError("Secret name must contain only alphanumeric characters, " "underscores, hyphens, and dots")
    return name


class WorkflowSecretCreateRequest(BaseModel):
    """Request body for creating a workflow secret. Issue #2303: owner_id derived from auth."""

    name: str = Field(..., min_length=1, max_length=256)
    value: str = Field(..., min_length=1, max_length=65536)
    secret_type: str = Field(default="api_key", max_length=50)
    workflow_id: str | None = Field(default=None, max_length=128)
    description: str | None = Field(default=None, max_length=1024)

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
    created_at: str | None = None
    updated_at: str | None = None
    description: str | None = None


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
    description: str | None = None
    requested_by_agent: str | None = None
    workflow_id: str | None = None
    workflow_step: str | None = None
    context: Dict[str, Any] | None = None
    task_ids: List[str] | None = None


class ApprovalTransitionRequest(BaseModel):
    """Request body for approve / reject / request-revision."""

    comment: str | None = None


class ApprovalResubmitRequest(BaseModel):
    """Request body for resubmitting after revision."""

    description: str | None = None
    context: Dict[str, Any] | None = None


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
    created_at: str | None = None


class ApprovalGateResponse(BaseModel):
    """Response for an approval gate."""

    id: str
    title: str
    description: str | None = None
    approval_type: str
    status: str
    requested_by_agent: str | None = None
    decided_by_user: str | None = None
    workflow_id: str | None = None
    workflow_step: str | None = None
    context: Dict[str, Any] | None = None
    decided_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    comments: List[ApprovalCommentResponse] = Field(default_factory=list)
    task_links: List[TaskApprovalLinkResponse] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# integration_project_management.py schemas
# ---------------------------------------------------------------------------


class ConnectionTestRequest(BaseModel):
    """Request to test project management connection."""

    provider: str = Field(..., description="Provider: jira, trello, or asana")
    base_url: str | None = Field(None, description="Base URL for the service")
    api_key: str | None = Field(None, description="API key")
    api_secret: str | None = Field(None, description="API secret")
    token: str | None = Field(None, description="Auth token")
    username: str | None = Field(None, description="Username")
    password: str | None = Field(None, description="Password")


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
    description: str | None = Field(None, description="Description")
    project_key: str | None = Field(None, description="Project key (Jira) or ID (Trello/Asana)")
    issue_type: str | None = Field("Task", description="Issue type (Jira)")
    list_id: str | None = Field(None, description="List ID (Trello)")
    workspace_gid: str | None = Field(None, description="Workspace GID (Asana)")


class IssueUpdateRequest(BaseModel):
    """Request to update an issue/card/task."""

    title: str | None = Field(None, description="New title")
    description: str | None = Field(None, description="New description")
    status: str | None = Field(None, description="New status")
    transition_id: str | None = Field(None, description="Transition ID (Jira)")
    list_id: str | None = Field(None, description="Target list ID (Trello)")
    completed: bool | None = Field(None, description="Completion status (Asana)")


class ProjectMgmtSearchRequest(BaseModel):
    """Request to search issues."""

    query: str = Field(..., description="Search query or JQL")
    max_results: int | None = Field(50, description="Maximum results")


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
    webhook_url: str | None = None


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
    timeout_seconds: int | None = 300


class NavigationRequest(BaseModel):
    url: str


class CreateChatBrowserRequest(BaseModel):
    """Request to create/get browser session for chat."""

    conversation_id: str
    headless: bool = False
    initial_url: str | None = None


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
    port: int | None = Field(None, description="Database port (default: provider-specific)")
    username: str | None = Field(None, description="Database username")
    password: str | None = Field(None, description="Database password")
    database: str = Field("", description="Database name")


class DBIntegrationQueryRequest(BaseModel):
    """Request model for executing database queries."""

    query: str = Field(..., description="SQL query to execute (read-only)")
    database: str = Field("", description="Target database name")
    host: str = Field("localhost", description="Database host")
    port: int | None = Field(None, description="Database port")
    username: str | None = Field(None, description="Database username")
    password: str | None = Field(None, description="Database password")


class MongoQueryRequest(BaseModel):
    """Request model for MongoDB collection queries."""

    database: str = Field(..., description="Database name")
    collection: str = Field(..., description="Collection name")
    filter: Dict[str, Any] = Field(default_factory=dict, description="Query filter")
    limit: int = Field(100, description="Maximum results to return")
    host: str = Field("localhost", description="MongoDB host")
    port: int = Field(27017, description="MongoDB port")
    username: str | None = Field(None, description="MongoDB username")
    password: str | None = Field(None, description="MongoDB password")


class DatabaseListRequest(BaseModel):
    """Request model for listing databases/tables."""

    host: str = Field("localhost", description="Database host")
    port: int | None = Field(None, description="Database port")
    username: str | None = Field(None, description="Database username")
    password: str | None = Field(None, description="Database password")
    database: str | None = Field(None, description="Database name (for table listing)")


# ---------------------------------------------------------------------------
# integration_communication.py schemas
# ---------------------------------------------------------------------------


class TestConnectionRequest(BaseModel):
    """Request model for testing communication provider connections."""

    provider: str = Field(..., description="Provider name: slack, teams, or discord")
    token: str | None = Field(None, description="Bot token or API token")
    webhook_url: str | None = Field(None, description="Webhook URL (for Teams)")
    base_url: str | None = Field(None, description="Custom base URL (optional)")


class SendMessageRequest(BaseModel):
    """Request model for sending messages."""

    channel: str | None = Field(None, description="Channel ID or name (Slack)")
    channel_id: str | None = Field(None, description="Channel ID (Discord)")
    text: str | None = Field(None, description="Message text")
    content: str | None = Field(None, description="Message content (Discord)")
    title: str | None = Field(None, description="Message title (Teams)")


class CommProviderInfo(BaseModel):
    """Information about a supported communication provider."""

    name: str
    description: str
    auth_type: str
    required_fields: List[str]


class WebhookMessageRequest(BaseModel):
    """Request model for webhook messages."""

    webhook_url: str = Field(..., description="Teams webhook URL")
    text: str = Field(..., description="Message text")
    title: str | None = Field(None, description="Message title")


# ---------------------------------------------------------------------------
# sandbox.py schemas
# ---------------------------------------------------------------------------


class SandboxExecuteRequest(BaseModel):
    command: str
    security_level: str = "high"
    timeout: int = 300
    execution_mode: str = "command"
    enable_network: bool = False
    environment: dict | None = None


class SandboxScriptRequest(BaseModel):
    script_content: str
    language: str = "bash"
    security_level: str = "high"
    timeout: int = 300
    enable_network: bool = False
    environment: dict | None = None


class SandboxBatchRequest(BaseModel):
    commands: List[str]
    security_level: str = "high"
    timeout: int = 600
    stop_on_error: bool = True
    enable_network: bool = False


# ---------------------------------------------------------------------------
# marketplace.py schemas
# ---------------------------------------------------------------------------


class MarketplaceEntry(BaseModel):
    """A single marketplace catalog entry."""

    name: str
    version: str
    display_name: str
    description: str
    author: str
    category: str
    tags: List[str] = Field(default_factory=list)
    entry_point: str
    dependencies: List[str] = Field(default_factory=list)
    hooks: List[str] = Field(default_factory=list)
    downloads: int = 0
    rating: float = 0.0
    source_url: str = ""


class MarketplaceCatalogResponse(BaseModel):
    """Response for catalog list."""

    entries: List[MarketplaceEntry]
    total: int
    category: str
    sort_by: str


class InstallRequest(BaseModel):
    """Request body for installing a marketplace plugin."""

    plugin_name: str = Field(..., description="Name of the plugin to install from catalog")
    # #6524: source_id required so install resolves against the same catalog
    # the user was browsing. Without it, custom marketplace plugins all
    # 404'd because we'd resolve against the built-in catalog only.
    source_id: str = Field(
        default="builtin",
        description="Marketplace source id; 'builtin' or a user-added source UUID (#6481)",
    )


# ---------------------------------------------------------------------------
# integration_github.py schemas
# ---------------------------------------------------------------------------


class GitHubConnectionTestRequest(BaseModel):
    """Request body for testing a GitHub token."""

    token: str = Field(..., description="GitHub Personal Access Token")
    base_url: str | None = Field(None, description="Custom GitHub API base URL (e.g. GitHub Enterprise)")


class GitHubReviewRequest(BaseModel):
    """Request body for submitting a PR review."""

    token: str = Field(..., description="GitHub Personal Access Token")
    owner: str = Field(..., description="Repository owner (user or org)")
    repo: str = Field(..., description="Repository name")
    pull_number: int = Field(..., description="Pull request number")
    body: str = Field(..., description="Review body text")
    event: str = Field("COMMENT", description="Review event: APPROVE, REQUEST_CHANGES, or COMMENT")


class GitHubCommentRequest(BaseModel):
    """Request body for posting a PR comment."""

    token: str = Field(..., description="GitHub Personal Access Token")
    owner: str = Field(..., description="Repository owner")
    repo: str = Field(..., description="Repository name")
    pull_number: int = Field(..., description="Pull request number")
    body: str = Field(..., description="Comment body text")


# ---------------------------------------------------------------------------
# integration_cicd.py schemas
# ---------------------------------------------------------------------------


CICDProvider = Literal["jenkins", "gitlab", "circleci"]


class CICDConnectionTestRequest(BaseModel):
    """Request model for testing CI/CD connection."""

    provider: CICDProvider = Field(..., description="CI/CD provider type")
    base_url: str = Field(..., description="Base URL of the CI/CD service")
    credentials: Dict[str, str] = Field(..., description="Authentication credentials")


class PipelineTriggerRequest(BaseModel):
    """Request model for triggering a pipeline."""

    confirm: bool = Field(False, description="Confirmation flag - must be true to trigger")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Pipeline parameters")


class CICDProviderInfo(BaseModel):
    """CI/CD provider information."""

    id: str = Field(..., description="Provider identifier")
    name: str = Field(..., description="Provider display name")
    description: str = Field(..., description="Provider description")
    auth_type: str = Field(..., description="Authentication type")


# ---------------------------------------------------------------------------
# enterprise_features.py schemas
# ---------------------------------------------------------------------------


class FeatureEnableRequest(BaseModel):
    feature_name: str
    force: bool | None = False


class BulkFeatureRequest(BaseModel):
    features: List[str]
    enable_dependencies: bool | None = True


class PerformanceOptimizationRequest(BaseModel):
    target_metrics: dict
    optimization_level: str | None = "balanced"


# ---------------------------------------------------------------------------
# integration_cloud.py schemas
# ---------------------------------------------------------------------------


class CloudProviderInfo(BaseModel):
    """Information about a supported cloud provider."""

    provider: str
    name: str
    description: str
    required_fields: List[str]


class CloudConnectionTestRequest(BaseModel):
    """Request model for testing cloud provider connection."""

    provider: str = Field(..., description="Cloud provider (aws, azure, gcp)")
    api_key: str | None = Field(None, description="API key or access key")
    api_secret: str | None = Field(None, description="API secret key")
    token: str | None = Field(None, description="Access token")
    extra: Dict[str, Any] = Field(default_factory=dict, description="Provider-specific config")


class ResourceListRequest(BaseModel):
    """Request model for listing cloud resources."""

    provider: str
    api_key: str | None = None
    api_secret: str | None = None
    token: str | None = None
    extra: Dict[str, Any] = Field(default_factory=dict)
    resource_type: str = Field(..., description="Type of resource (instances, vms, storage)")


# ---------------------------------------------------------------------------
# integration_monitoring.py schemas
# ---------------------------------------------------------------------------


class MonitoringConnectionTestRequest(BaseModel):
    """Request model for testing monitoring connection."""

    provider: str = Field(..., description="Monitoring provider")
    api_key: str = Field(..., description="API key")
    app_key: str | None = Field(None, description="Application key (Datadog only)")
    account_id: str | None = Field(None, description="Account ID (New Relic only)")

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        if v not in ["datadog", "new_relic"]:
            raise ValueError("Provider must be 'datadog' or 'new_relic'")
        return v


class MetricsQueryRequest(BaseModel):
    """Request model for querying metrics."""

    query: str = Field(..., description="Metric query")
    from_time: int | None = Field(None, description="Start time (unix timestamp)")
    to_time: int | None = Field(None, description="End time (unix timestamp)")
    since: str | None = Field(None, description="Relative time (e.g., '1 hour ago')")

    @field_validator("from_time")
    @classmethod
    def validate_from_time(cls, v: int | None) -> int | None:
        from datetime import datetime, timezone

        if v and v > int(datetime.now(tz=timezone.utc).timestamp()):
            raise ValueError("from_time cannot be in the future")
        return v

    @field_validator("to_time")
    @classmethod
    def validate_to_time(cls, v: int | None, info) -> int | None:
        from_time = info.data.get("from_time")
        if v and from_time:
            if v < from_time:
                raise ValueError("to_time must be after from_time")
            if v - from_time > 86400:
                raise ValueError("Time range cannot exceed 24 hours")
        return v


class EventsQueryRequest(BaseModel):
    """Request model for querying events."""

    start: int | None = Field(None, description="Start time (unix timestamp)")
    end: int | None = Field(None, description="End time (unix timestamp)")

    @field_validator("end")
    @classmethod
    def validate_time_range(cls, v: int | None, info) -> int | None:
        start = info.data.get("start")
        if v and start and v - start > 86400:
            raise ValueError("Time range cannot exceed 24 hours")
        return v


class MonitorCreateRequest(BaseModel):
    """Request model for creating a monitor."""

    type: str = Field(..., description="Monitor type")
    query: str = Field(..., description="Monitor query")
    name: str = Field(..., description="Monitor name")
    message: str = Field(..., description="Notification message")


# ---------------------------------------------------------------------------
# marketplace_sources.py schemas
# ---------------------------------------------------------------------------


class MarketplaceSource(BaseModel):
    id: str = Field(..., description="Unique source ID; 'builtin' for the default")
    name: str = Field(..., description="Display name shown in the UI")
    url: str | None = Field(default=None, description="Catalog URL; null for the built-in source")
    description: str | None = Field(default=None)
    is_builtin: bool = Field(default=False)
    created_at: str | None = Field(default=None)


class MarketplaceSourceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    url: HttpUrl
    description: str | None = Field(default=None, max_length=200)


class MarketplaceSourcesResponse(BaseModel):
    sources: List[MarketplaceSource]


class CatalogPlugin(BaseModel):
    """A single plugin entry as listed in an external marketplace catalog."""

    name: str
    version: str
    description: str = ""
    author: str = ""
    git_url: str
    ref: str | None = None
    category: str = "other"
    tags: List[str] = Field(default_factory=list)


class CatalogDocument(BaseModel):
    """The schema an external marketplace URL must return."""

    name: str
    version: str = "1"
    plugins: List[CatalogPlugin]


# ---------------------------------------------------------------------------
# batch_jobs.py enums + schemas
# ---------------------------------------------------------------------------


class BatchJobStatus(str, Enum):
    """Status of a batch job."""

    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class BatchJobType(str, Enum):
    """Type of batch job."""

    data_processing = "data_processing"
    file_conversion = "file_conversion"
    report_generation = "report_generation"
    backup = "backup"
    custom = "custom"


class BatchJobCreate(BaseModel):
    """Request model for creating a batch job."""

    name: str = Field(..., description="Human-readable name for the job")
    job_type: BatchJobType = Field(..., description="Type of batch job")
    parameters: Dict = Field(default_factory=dict, description="Job-specific parameters")
    schedule: str | None = Field(None, description="Optional cron expression for scheduling")
    template_id: str | None = Field(None, description="Optional template ID to use")


class BatchJob(BaseModel):
    """Batch job model."""

    job_id: str
    name: str
    job_type: BatchJobType
    status: BatchJobStatus
    progress: int = Field(0, ge=0, le=100, description="Progress percentage")
    parameters: Dict
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    result: Dict | None = None


class BatchTemplate(BaseModel):
    """Batch job template model."""

    template_id: str
    name: str
    job_type: BatchJobType
    parameters: Dict
    created_at: datetime


class BatchSchedule(BaseModel):
    """Batch job schedule model."""

    schedule_id: str
    job_id: str
    cron_expression: str
    enabled: bool
    next_run: datetime


class BatchJobList(BaseModel):
    """Response model for job list."""

    jobs: List[BatchJob]
    total_count: int
    status_counts: Dict[str, int]


class BatchLogEntry(BaseModel):
    """Log entry model."""

    timestamp: datetime
    level: str
    message: str


class APIBatchRequest(BaseModel):
    """Request multiple endpoints in one call."""

    requests: List[Dict]


class APIBatchResponse(BaseModel):
    """Combined response from multiple endpoints."""

    responses: Dict
    errors: Dict[str, str]
    timing: Dict[str, float]


# ---------------------------------------------------------------------------
# captcha.py schemas
# ---------------------------------------------------------------------------


class CaptchaResolutionRequest(BaseModel):
    """Request model for CAPTCHA resolution."""

    notes: str | None = None


class CaptchaResolutionResponse(BaseModel):
    """Response model for CAPTCHA resolution."""

    success: bool
    captcha_id: str
    status: str
    message: str
    timestamp: str | None = None


# ---------------------------------------------------------------------------
# elevation.py schemas
# ---------------------------------------------------------------------------


class ElevationRequest(BaseModel):
    """Request to escalate privileges for a system operation."""

    operation: str
    command: str
    reason: str
    risk_level: str = "MEDIUM"


class ElevationAuthorization(BaseModel):
    """Authorization payload for an existing elevation request."""

    request_id: str
    password: str
    remember_session: bool = False


# ---------------------------------------------------------------------------
# validation_dashboard.py schemas
# ---------------------------------------------------------------------------


class DashboardGenerateRequest(BaseModel):
    """Request body for validation dashboard generation."""

    include_trends: bool = True
    include_recommendations: bool = True
    refresh_interval: int = 30  # seconds


# ---------------------------------------------------------------------------
# integration_version_control.py schemas
# ---------------------------------------------------------------------------


class VCSConnectionTestRequest(BaseModel):
    """Request model for testing VCS connection (#6604).

    Renamed from `ConnectionTestRequest` to disambiguate from the project-
    management variant defined earlier in this module — same name, different
    shape, last-definition-wins was masking the project-management caller.
    """

    provider: str = Field(..., description="VCS provider (gitlab, bitbucket)")
    api_key: str = Field(..., description="API key or access token")
    settings: Dict[str, Any] = Field(default_factory=dict, description="Provider-specific settings")


class VCSProviderInfo(BaseModel):
    """Information about a VCS provider (#6604).

    Renamed from `ProviderInfo` to disambiguate from the project-management
    `ProviderInfo` defined earlier in this module — same name, different shape,
    last-definition-wins was masking the project-management caller.
    """

    id: str = Field(..., description="Provider identifier")
    name: str = Field(..., description="Provider display name")
    description: str = Field(..., description="Provider description")
    required_settings: List[str] = Field(default_factory=list, description="Required configuration settings")
    optional_settings: List[str] = Field(default_factory=list, description="Optional configuration settings")


# ---------------------------------------------------------------------------
# orchestration.py schemas
# ---------------------------------------------------------------------------


class WorkflowRequest(BaseModel):
    """Request body for orchestration workflow execution."""

    goal: str
    strategy: str | None = None
    context: dict | None = None
    max_parallel_tasks: int | None = 5


class AgentRecommendationRequest(BaseModel):
    """Request body for agent recommendations from orchestrator."""

    task_type: str
    capabilities_needed: List[str]


# ---------------------------------------------------------------------------
# sequential_thinking_mcp.py schemas
# ---------------------------------------------------------------------------


class SequentialThinkingMCPTool(BaseModel):
    """Standard MCP tool definition for sequential thinking."""

    name: str
    description: str
    input_schema: Metadata


class SequentialThinkingRequest(BaseModel):
    """Request model for sequential thinking tool."""

    thought: str = Field(..., description="Current thinking step and analysis")
    thought_number: int = Field(..., ge=1, description="Current thought number in sequence")
    total_thoughts: int = Field(..., ge=1, description="Estimated total thoughts needed")
    next_thought_needed: bool = Field(..., description="Whether another thought step is needed")

    is_revision: bool | None = Field(False, description="Whether this revises previous thinking")
    revises_thought: int | None = Field(None, ge=1, description="Which thought is being reconsidered")
    branch_from_thought: int | None = Field(None, ge=1, description="Branching point thought number")
    branch_id: str | None = Field(None, description="Branch identifier")
    needs_more_thoughts: bool | None = Field(False, description="If more thoughts are needed beyond initial estimate")

    session_id: str | None = Field("default", description="Thinking session identifier")

    def to_thought_record(self) -> Metadata:
        """Convert to thought record for storage."""
        from datetime import datetime, timezone

        return {
            "thought_number": self.thought_number,
            "thought": self.thought,
            "total_thoughts": self.total_thoughts,
            "next_thought_needed": self.next_thought_needed,
            "is_revision": self.is_revision,
            "revises_thought": self.revises_thought,
            "branch_from_thought": self.branch_from_thought,
            "branch_id": self.branch_id,
            "needs_more_thoughts": self.needs_more_thoughts,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        }

    def get_progress_percentage(self) -> float:
        """Calculate progress percentage."""
        return (self.thought_number / self.total_thoughts) * 100

    def get_session_key(self) -> str:
        """Get session key with fallback."""
        return self.session_id or "default"

    def is_valid_thought_number(self) -> bool:
        """Check if thought number is valid."""
        return self.thought_number <= self.total_thoughts or self.needs_more_thoughts

    def has_revision(self) -> bool:
        """Check if this is a revision."""
        return bool(self.is_revision)

    def get_revision_info(self) -> Metadata | None:
        """Get revision info dict if this is a revision."""
        if not self.is_revision:
            return None
        return {
            "is_revision": True,
            "revises_thought": self.revises_thought,
        }

    def has_branch(self) -> bool:
        """Check if this is a branch."""
        return bool(self.branch_from_thought)

    def get_branch_info(self) -> Metadata | None:
        """Get branch info dict if this is a branch."""
        if not self.branch_from_thought:
            return None
        return {
            "branched": True,
            "branch_from_thought": self.branch_from_thought,
            "branch_id": self.branch_id,
        }

    def get_progress_message(self) -> str:
        """Get progress message string."""
        return f"Recorded thought {self.thought_number}/{self.total_thoughts}"


# ---------------------------------------------------------------------------
# state_tracking.py schemas
# ---------------------------------------------------------------------------


class StateChangeRequest(BaseModel):
    """Request body for tracking a state change."""

    change_type: str
    description: str
    after_state: Metadata
    before_state: Metadata | None = None
    user_id: str | None = "system"
    metadata: Metadata | None = None


class StateTrackingExportRequest(BaseModel):
    """Request body for state-tracking export."""

    format: str = "json"  # json or markdown
    include_history: bool = True
    time_range_days: int | None = None


# ---------------------------------------------------------------------------
# system_validation.py schemas
# ---------------------------------------------------------------------------


class SystemValidationRequestModel(BaseModel):
    """Request model for system validation."""

    validation_type: str = "comprehensive"
    include_performance_tests: bool = True
    include_stress_tests: bool = False
    timeout_seconds: int = 300


class SystemValidationResultModel(BaseModel):
    """Response model for system validation results."""

    validation_id: str
    status: str
    overall_score: float
    component_scores: Dict[str, float]
    recommendations: List[str]
    test_results: Metadata
    execution_time: float
    timestamp: str


# ---------------------------------------------------------------------------
# web_research_settings.py schemas
# ---------------------------------------------------------------------------


class WebResearchSettings(BaseModel):
    """Web research settings model."""

    enabled: bool
    require_user_confirmation: bool = True
    preferred_method: str = "basic"
    max_results: int = 5
    timeout_seconds: int = 30
    auto_research_threshold: float = 0.3
    rate_limit_requests: int = 5
    rate_limit_window: int = 60


class ResearchPreferences(BaseModel):
    """User research preferences."""

    auto_research_enabled: bool = False
    daily_limit: int = 50
    quality_threshold: float = 0.5
    store_results_in_kb: bool = True
    filter_adult_content: bool = True
    anonymize_requests: bool = True


# ---------------------------------------------------------------------------
# http_client_mcp.py schemas
# ---------------------------------------------------------------------------

from pydantic import field_validator as _http_client_field_validator

from type_defs.common import JSONObject as _HTTPClientJSONObject

_HTTP_CLIENT_VALID_URL_SCHEMES = ("http://", "https://")
_HTTP_CLIENT_DEFAULT_TIMEOUT = 30  # seconds
_HTTP_CLIENT_MAX_TIMEOUT = 120  # seconds


class HTTPClientMCPTool(BaseModel):
    """Standard MCP tool definition for HTTP client (renamed to avoid collision
    with SequentialThinkingMCPTool)."""

    name: str
    description: str
    input_schema: _HTTPClientJSONObject


class HTTPRequestBase(BaseModel):
    """Base model for HTTP requests."""

    url: str = Field(..., description="Target URL for the request")
    headers: Dict[str, str] | None = Field(default=None, description="Optional HTTP headers")
    timeout: int | None = Field(
        default=_HTTP_CLIENT_DEFAULT_TIMEOUT,
        ge=1,
        le=_HTTP_CLIENT_MAX_TIMEOUT,
        description=f"Request timeout in seconds (1-{_HTTP_CLIENT_MAX_TIMEOUT})",
    )

    @_http_client_field_validator("url")
    @classmethod
    def validate_url_format(cls, v):
        """Ensure URL is properly formatted."""
        if not v.startswith(_HTTP_CLIENT_VALID_URL_SCHEMES):
            raise ValueError("URL must start with http:// or https://")
        return v


class HTTPGetRequest(HTTPRequestBase):
    """GET request model."""

    params: Dict[str, str] | None = Field(default=None, description="Query parameters")


class HTTPPostRequest(HTTPRequestBase):
    """POST request model."""

    json_body: _HTTPClientJSONObject | None = Field(default=None, description="JSON request body")
    form_data: Dict[str, str] | None = Field(default=None, description="Form data (mutually exclusive with json_body)")


class HTTPPutRequest(HTTPRequestBase):
    """PUT request model."""

    json_body: _HTTPClientJSONObject | None = Field(default=None, description="JSON request body")


class HTTPPatchRequest(HTTPRequestBase):
    """PATCH request model."""

    json_body: _HTTPClientJSONObject | None = Field(default=None, description="JSON request body for partial update")


class HTTPDeleteRequest(HTTPRequestBase):
    """DELETE request model."""


class HTTPHeadRequest(HTTPRequestBase):
    """HEAD request model."""


# ---------------------------------------------------------------------------
# orchestration.py schemas (GH #6509 Batch D)
# ---------------------------------------------------------------------------


class OrchestrationWorkflowPlanResponse(BaseModel):
    """Response for POST /workflow/plan."""

    status: str
    plan: Dict[str, Any] = Field(default_factory=dict)
    task_count: int = 0
    message: str = ""


class OrchestrationAgentPerformanceResponse(BaseModel):
    """Response for GET /agents/performance."""

    status: str
    performance_data: Dict[str, Any] = Field(default_factory=dict)


class OrchestrationAgentRecommendResponse(BaseModel):
    """Response for POST /agents/recommend."""

    status: str
    task_type: str = ""
    capabilities_requested: List[str] = Field(default_factory=list)
    recommended_agents: List[Any] = Field(default_factory=list)
    agent_count: int = 0


class OrchestrationActiveWorkflowsResponse(BaseModel):
    """Response for GET /workflow/active."""

    status: str
    active_count: int = 0
    workflows: List[Dict[str, Any]] = Field(default_factory=list)


class OrchestrationStrategiesResponse(BaseModel):
    """Response for GET /strategies."""

    strategies: Dict[str, Any] = Field(default_factory=dict)
    default: str = "adaptive"


class OrchestrationCapabilitiesResponse(BaseModel):
    """Response for GET /capabilities."""

    capability_coverage: Dict[str, Any] = Field(default_factory=dict)
    agents: Dict[str, Any] = Field(default_factory=dict)
    total_agents: int = 0


class OrchestrationStatusResponse(BaseModel):
    """Response for GET /status."""

    status: str
    active_workflows: int = 0
    max_parallel_tasks: int = 0
    total_agents: int = 0
    capabilities: Dict[str, Any] = Field(default_factory=dict)


class OrchestrationExamplesResponse(BaseModel):
    """Response for GET /examples."""

    examples: Dict[str, Any] = Field(default_factory=dict)
    usage_tips: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# llm.py response data schemas (GH #6509)
# ---------------------------------------------------------------------------


class LLMDeprecatedData(BaseModel):
    """Response data for deprecated LLM config write endpoints (HTTP 410)."""

    detail: str
    redirect: str


class LLMComprehensiveStatusData(BaseModel):
    """Response data for get_comprehensive_llm_status."""

    provider_type: str
    providers: Dict[str, Any]
    active_provider: Dict[str, Any]
    settings: Dict[str, Any]


class LLMQuickStatusData(BaseModel):
    """Response data for get_quick_llm_status and get_llm_status."""

    status: str
    provider_type: str
    model: str
    timestamp: str
    error: str | None = None


class LLMProvidersHealthData(BaseModel):
    """Response data for get_all_providers_health."""

    overall_status: str
    available_providers: int
    total_providers: int
    providers: Dict[str, Any]
    cache_stats: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str
    error: str | None = None


class LLMProviderHealthData(BaseModel):
    """Response data for get_provider_health."""

    provider: str
    status: str
    available: bool
    message: str
    response_time_ms: float
    details: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str
    error: str | None = None


class LLMCacheClearData(BaseModel):
    """Response data for clear_provider_health_cache."""

    success: bool
    message: str
    cache_stats: Dict[str, Any] = Field(default_factory=dict)


class LLMTieredRoutingMetricsData(BaseModel):
    """Response data for get_tiered_routing_metrics."""

    enabled: bool
    metrics: Dict[str, Any] | None = None
    message: str | None = None


class LLMTieredRoutingConfigData(BaseModel):
    """Response data for get_tiered_routing_config."""

    enabled: bool
    complexity_threshold: float | None = None
    models: Dict[str, str] | None = None
    fallback_to_complex: bool | None = None
    logging: Dict[str, Any] | None = None
    message: str | None = None


class LLMTieredRoutingUpdateData(BaseModel):
    """Response data for update_tiered_routing_config."""

    success: bool
    message: str
    config: Dict[str, Any]


class LLMTieredMetricsResetData(BaseModel):
    """Response data for reset_tiered_routing_metrics."""

    success: bool
    message: str
    metrics: Dict[str, Any]


# ---------------------------------------------------------------------------
# research_browser.py response data schemas (GH #6509)
# ---------------------------------------------------------------------------


class BrowserSessionStatusData(BaseModel):
    """Response data for get_session_status."""

    session_id: str
    conversation_id: str
    status: str
    current_url: str | None = None
    interaction_required: bool = False
    interaction_message: str | None = None
    created_at: str
    last_activity: str
    mhtml_files_count: int = 0


class BrowserSessionListData(BaseModel):
    """Response data for list_sessions."""

    sessions: List[Dict[str, Any]]
    total_sessions: int


class BrowserSessionActionData(BaseModel):
    """Response data for handle_session_action."""

    success: bool
    session_id: str
    interaction_complete: bool | None = None
    status: str | None = None
    message: str | None = None
    mhtml_path: str | None = None
    browser_accessible: bool | None = None
    current_url: str | None = None
    content: Any | None = None
    error: str | None = None


class BrowserInfoData(BaseModel):
    """Response data for get_browser_info."""

    session_id: str
    conversation_id: str
    status: str
    current_url: str | None = None
    interaction_required: bool
    interaction_message: str | None = None
    docker_browser: Dict[str, Any]
    actions: List[Dict[str, Any]]


class ChatBrowserSessionData(BaseModel):
    """Response data for chat browser session endpoints."""

    session_id: str
    conversation_id: str
    browser_status: str
    current_url: str | None = None
    interaction_required: bool = False
    interaction_message: str | None = None
    created_at: str | None = None
    last_activity: str | None = None
    docker_browser: Dict[str, Any] | None = None
    status: str | None = None


class BrowserSessionCleanupData(BaseModel):
    """Response data for cleanup_session and delete_chat_browser_session."""

    success: bool | None = None
    message: str | None = None
    session_id: str | None = None
    conversation_id: str | None = None
    status: str | None = None


# ---------------------------------------------------------------------------
# web_research_settings.py response data schemas (GH #6509)
# ---------------------------------------------------------------------------


class WebResearchStatusData(BaseModel):
    """Response data for get_research_status."""

    status: str
    enabled: bool
    preferred_method: str | None = None
    health: Dict[str, Any] | None = None
    circuit_breakers: Dict[str, Any] | None = None
    cache_stats: Dict[str, Any] | None = None
    timestamp: str
    message: str | None = None


class WebResearchToggleData(BaseModel):
    """Response data for enable_web_research and disable_web_research."""

    status: str
    message: str
    enabled: bool
    timestamp: str


class WebResearchSettingsData(BaseModel):
    """Response data for get_research_settings."""

    status: str
    settings: Dict[str, Any]
    timestamp: str


class WebResearchSettingsUpdateData(BaseModel):
    """Response data for update_research_settings."""

    status: str
    message: str
    settings: Dict[str, Any]
    timestamp: str


class WebResearchTestData(BaseModel):
    """Response data for test_web_research."""

    status: str
    test_query: str
    result: Any | None = None
    error: str | None = None
    timestamp: str


class WebResearchCacheClearData(BaseModel):
    """Response data for clear_research_cache and reset_circuit_breakers."""

    status: str
    message: str
    timestamp: str


class WebResearchUsageStatsData(BaseModel):
    """Response data for get_usage_stats."""

    status: str
    stats: Dict[str, Any]
    timestamp: str


# ---------------------------------------------------------------------------
# manual_mcp.py / structured_thinking_mcp.py / sequential_thinking_mcp.py
# schemas (GH #6509 Batch E)
# ---------------------------------------------------------------------------


class ManPageLookupData(BaseModel):
    """Response data for POST /mcp/lookup_man_page."""

    success: bool = True
    command: str = ""
    section: str = ""
    result: Dict[str, Any] | None = None
    error: str | None = None


class ManPageSearchData(BaseModel):
    """Response data for POST /mcp/search_man_pages and /mcp/get_doc_index."""

    success: bool = True
    query: str = ""
    count: int = 0
    results: List[Any] = Field(default_factory=list)
    error: str | None = None


class StructuredThinkingOverview(BaseModel):
    """Overview section of structured thinking summary."""

    total_thoughts: int = 0
    started_at: str = ""
    last_thought_at: str = ""
    complete: bool = False


class StructuredThinkingSummaryData(BaseModel):
    """Response data for POST /mcp/generate_summary."""

    success: bool = True
    session_id: str = ""
    message: str = ""
    thought_count: int = 0
    overview: StructuredThinkingOverview = Field(default_factory=StructuredThinkingOverview)
    stage_distribution: Dict[str, int] = Field(default_factory=dict)
    stage_progression: List[Any] = Field(default_factory=list)
    metadata_analysis: Dict[str, Any] = Field(default_factory=dict)


class SequentialThinkingClearData(BaseModel):
    """Response data for DELETE /sessions/{session_id}."""

    success: bool = True
    session_id: str = ""
    thoughts_cleared: int = 0
    message: str = ""
