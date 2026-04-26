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
# analytics.py schemas  (Issue #5317)
# ---------------------------------------------------------------------------
