# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Shared Pydantic response schemas for AutoBot API endpoints.

Provides typed response models for terminal.py and terminal_tools.py.
All models are used as response_model= on FastAPI router decorators so that
FastAPI generates accurate OpenAPI docs and validates outbound data.

Schema naming convention:
  <Domain><EntityOrAction>Response
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Generic / reusable
# ---------------------------------------------------------------------------


class SuccessResponse(BaseModel):
    """Minimal success/failure envelope used by several endpoints."""

    success: bool
    message: Optional[str] = None


# ---------------------------------------------------------------------------
# Terminal session schemas  (terminal.py — session lifecycle)
# ---------------------------------------------------------------------------


class TerminalSessionCreateResponse(BaseModel):
    """Response for POST /sessions."""

    session_id: str
    status: str
    security_level: str
    websocket_url: str
    created_at: str
    ssh_keys: Optional[Dict[str, Any]] = None


class TerminalSessionItem(BaseModel):
    """Single session entry within a list response."""

    session_id: str
    user_id: Optional[str] = None
    security_level: Optional[str] = None
    created_at: Optional[str] = None
    is_active: bool


class TerminalSessionListResponse(BaseModel):
    """Response for GET /sessions."""

    sessions: List[TerminalSessionItem]
    total: int
    active: int


class TerminalSessionDetailResponse(BaseModel):
    """Response for GET /sessions/{session_id}."""

    session_id: str
    config: Dict[str, Any]
    is_active: bool
    statistics: Dict[str, Any]


class TerminalSessionDeleteResponse(BaseModel):
    """Response for DELETE /sessions/{session_id}."""

    session_id: str
    status: str


# ---------------------------------------------------------------------------
# SSH key management schemas  (terminal.py — Issue #211)
# ---------------------------------------------------------------------------


class SSHKeyItem(BaseModel):
    """A single SSH key entry as returned by get_session_keys()."""

    name: str
    fingerprint: Optional[str] = None
    has_passphrase: Optional[bool] = None
    key_path: Optional[str] = None


class SSHKeyListResponse(BaseModel):
    """Response for GET /sessions/{session_id}/ssh-keys."""

    session_id: str
    keys: List[Any]  # key dicts are opaque — shape defined by terminal_secrets_service
    total: int


class SSHKeyAgentResponse(BaseModel):
    """Response for POST /sessions/{session_id}/ssh-keys/{key_name}/agent."""

    session_id: str
    key_name: str
    status: str
    message: str


class SSHKeyPathResponse(BaseModel):
    """Response for GET /sessions/{session_id}/ssh-keys/{key_name}/path."""

    session_id: str
    key_name: str
    key_path: str
    usage: str


# ---------------------------------------------------------------------------
# Command / input / signal schemas
# ---------------------------------------------------------------------------


class CommandAssessResponse(BaseModel):
    """Response for POST /command."""

    command: str
    risk_level: str
    status: str
    message: str
    requires_confirmation: bool


class TerminalInputResponse(BaseModel):
    """Response for POST /sessions/{session_id}/input."""

    session_id: str
    status: str
    input: str


class TerminalSignalResponse(BaseModel):
    """Response for POST /sessions/{session_id}/signal/{signal_name}."""

    session_id: str
    signal: str
    status: str


# ---------------------------------------------------------------------------
# History / audit schemas
# ---------------------------------------------------------------------------


class TerminalCommandHistoryResponse(BaseModel):
    """Response for GET /sessions/{session_id}/history."""

    session_id: str
    is_active: bool
    history: List[Any]
    total_commands: Optional[int] = None
    message: Optional[str] = None


class TerminalAuditLogResponse(BaseModel):
    """Response for GET /audit/{session_id}."""

    session_id: str
    audit_available: bool
    security_level: Optional[str] = None
    message: str


# ---------------------------------------------------------------------------
# Info / health / status schemas
# ---------------------------------------------------------------------------


class TerminalInfoResponse(BaseModel):
    """Response for GET /."""

    name: str
    version: str
    description: str
    features: List[str]
    endpoints: Dict[str, str]
    security_levels: List[str]
    notice: str


class TerminalHealthComponents(BaseModel):
    terminal_manager: str
    websocket_manager: str
    pty_system: str
    session_manager: str


class TerminalHealthMetrics(BaseModel):
    active_sessions: int
    manager_initialized: bool


class TerminalHealthResponse(BaseModel):
    """Response for GET /health (healthy path)."""

    status: str
    service: str
    components: Optional[TerminalHealthComponents] = None
    metrics: Optional[TerminalHealthMetrics] = None
    error: Optional[str] = None


class TerminalStatusFeatures(BaseModel):
    pty_support: bool
    websocket_support: bool
    command_validation: bool
    security_policies: bool
    approval_workflow: bool
    agent_integration: bool


class TerminalStatusSessionInfo(BaseModel):
    active_sessions: int
    max_concurrent_sessions: Optional[int] = None


class TerminalSystemStatusResponse(BaseModel):
    """Response for GET /status."""

    status: str
    terminal_types: Optional[List[str]] = None
    features: Optional[TerminalStatusFeatures] = None
    session_info: Optional[TerminalStatusSessionInfo] = None
    error: Optional[str] = None


class TerminalCapabilitiesResponse(BaseModel):
    """Response for GET /capabilities."""

    pty_management: bool
    websocket_streaming: bool
    command_execution: bool
    security_validation: bool
    session_management: bool
    terminal_types: Dict[str, Any]
    pty_features: Dict[str, Any]
    websocket_features: Dict[str, Any]


class TerminalSecurityPoliciesResponse(BaseModel):
    """Response for GET /security."""

    command_validation: str
    risk_assessment: str
    risk_levels: Dict[str, str]
    security_executor: str
    approval_workflow: Dict[str, Any]
    audit_logging: Dict[str, Any]


class TerminalImplementationItem(BaseModel):
    name: str
    description: str
    frontend_component: str
    backend_api: str
    approval_workflow: bool
    service_layer: Optional[str] = None


class TerminalFeaturesResponse(BaseModel):
    """Response for GET /features."""

    manager_class: str
    websocket_class: str
    pty_implementation: str
    implementations: List[TerminalImplementationItem]
    features: Dict[str, str]
    shared_infrastructure: Dict[str, str]


# ---------------------------------------------------------------------------
# Stats schema
# ---------------------------------------------------------------------------


class TerminalStatsResponse(BaseModel):
    """Response for GET /stats.

    The session manager returns an opaque dict whose shape varies between
    the 'all sessions' and 'single session' cases.  A permissive model
    lets FastAPI pass the dict through while still documenting the endpoint.
    """

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# Admin execute schema  (SLM admin terminal — Issue #983)
# ---------------------------------------------------------------------------


class AdminExecuteResponse(BaseModel):
    """Response for POST /execute."""

    stdout: str
    stderr: str
    exit_code: int


# ---------------------------------------------------------------------------
# terminal_tools.py schemas
# ---------------------------------------------------------------------------


class PackageManagersResponse(BaseModel):
    """Response for GET /terminal/package-managers."""

    detected: Optional[str] = None
    available: List[str]
    package_managers: Dict[str, Any]


# ---------------------------------------------------------------------------
# Generic data envelope  (ai_stack_integration, agent, etc.)
# ---------------------------------------------------------------------------


class DataResponse(BaseModel):
    """Generic envelope returned by create_success_response() helpers.

    Covers all endpoints that delegate to utils.response_helpers.create_success_response,
    which always produces {"success": True, "data": ..., "message": ..., "timestamp": ...}.
    """

    success: bool
    data: Optional[Any] = None
    message: Optional[str] = None
    timestamp: Optional[str] = None


# ---------------------------------------------------------------------------
# agent.py — simple message / approval responses
# ---------------------------------------------------------------------------


class AgentMessageResponse(BaseModel):
    """Response for /goal, /pause, /resume — plain {"message": str}."""

    message: str


class AgentCommandApprovalResponse(BaseModel):
    """Response for POST /command_approval."""

    message: str
    task_id: str
    approved: bool


class AgentCommandExecuteResponse(BaseModel):
    """Response for POST /execute_command — success path returns {"message", "output", "status"}."""

    message: str
    output: Optional[str] = None
    status: Optional[str] = None


class AgentHealthResponse(BaseModel):
    """Response for GET /health/enhanced."""

    status: str
    ai_stack_available: bool
    multi_agent_coordination: bool
    enhanced_capabilities: bool
    timestamp: str
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# enhanced_memory.py schemas
# ---------------------------------------------------------------------------


class MemoryStatisticsResponse(BaseModel):
    """Response for GET /statistics."""

    period_days: int
    timestamp: str
    task_execution: Optional[Any] = None
    markdown_system: Optional[Any] = None
    active_tasks: Optional[Any] = None
    performance_insights: Optional[Any] = None


class MemoryTaskHistoryResponse(BaseModel):
    """Response for GET /tasks/history."""

    total_records: int
    filter_criteria: Dict[str, Any]
    tasks: List[Any]


class MemoryTaskCreateResponse(BaseModel):
    """Response for POST /tasks."""

    task_id: str
    status: str
    timestamp: str


class MemoryTaskUpdateResponse(BaseModel):
    """Response for PUT /tasks/{task_id}."""

    task_id: str
    status: str
    timestamp: str


class MemoryMarkdownReferenceResponse(BaseModel):
    """Response for POST /tasks/{task_id}/markdown-reference."""

    task_id: str
    markdown_file: str
    reference_type: str
    status: str
    timestamp: str


class MemoryMarkdownScanResponse(BaseModel):
    """Response for GET /markdown/scan."""

    status: str
    scan_results: Optional[Any] = None
    timestamp: str


class MemoryMarkdownSearchResponse(BaseModel):
    """Response for GET /markdown/search."""

    query: str
    filters: Dict[str, Any]
    total_results: int
    results: List[Any]


class MemoryDocumentReferencesResponse(BaseModel):
    """Response for GET /markdown/{file_path}/references."""

    file_path: str
    timestamp: str
    references: Optional[Any] = None


class MemoryEmbeddingCacheStatsResponse(BaseModel):
    """Response for GET /embeddings/cache-stats."""

    cache_size: Optional[Any] = None
    timestamp: str
    status: str


class MemoryCleanupResponse(BaseModel):
    """Response for DELETE /cleanup."""

    status: str
    cleanup_results: Dict[str, Any]
    days_kept: int
    timestamp: str


class MemoryActiveTasksResponse(BaseModel):
    """Response for GET /active-tasks."""

    count: int
    active_tasks: List[Any]
    timestamp: str


# ---------------------------------------------------------------------------
# agent_config.py schemas
# ---------------------------------------------------------------------------


class AgentConfigEnableDisableResponse(BaseModel):
    """Response for POST /agents/{agent_id}/enable and /disable."""

    status: str
    message: str
    agent_name: str


class AgentConfigUpdateModelResponse(BaseModel):
    """Response for POST /agents/{agent_id}/model."""

    status: str
    message: str
    updated_config: Dict[str, Any]


class AgentConfigHealthResponse(BaseModel):
    """Response for GET /agents/{agent_id}/health."""

    agent_id: str
    agent_name: str
    status: str
    enabled: bool
    model: Optional[str] = None
    checks: Dict[str, Any]
    timestamp: str
    response_time: float


class AgentConfigOverviewResponse(BaseModel):
    """Response for GET /status/overview."""

    total_agents: int
    enabled_agents: int
    healthy_agents: int
    unhealthy_agents: int
    disabled_agents: int
    overall_health: str
    agents: List[Any]
    timestamp: str
