# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Terminal and AgentTerminal session, SSH, command, and health schemas.
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Terminal schemas
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


class AgentTerminalSessionCreateResponse(BaseModel):
    """Response for POST /agent-terminal/sessions."""

    status: str
    session_id: str
    agent_id: str
    agent_role: str
    conversation_id: Optional[str] = None
    host: str
    state: str
    created_at: float
    pty_session_id: Optional[str] = None


class AgentTerminalSessionItem(BaseModel):
    """Single session entry within list response."""

    session_id: str
    agent_id: str
    agent_role: str
    conversation_id: Optional[str] = None
    host: str
    state: str
    created_at: float
    last_activity: Optional[float] = None
    command_count: int
    pty_session_id: Optional[str] = None


class AgentTerminalSessionListResponse(BaseModel):
    """Response for GET /agent-terminal/sessions."""

    status: str
    total: int
    sessions: List[AgentTerminalSessionItem]


class AgentTerminalSessionDetailResponse(BaseModel):
    """Response for GET /agent-terminal/sessions/{session_id}.

    session_info dict shape is opaque — extra fields allowed.
    """

    model_config = {"extra": "allow"}

    status: str


class AgentTerminalSessionDeleteResponse(BaseModel):
    """Response for DELETE /agent-terminal/sessions/{session_id}."""

    status: str
    session_id: str


class AgentTerminalCommandStateResponse(BaseModel):
    """Response for GET /agent-terminal/commands/{command_id}."""

    command_id: str
    terminal_session_id: Optional[str] = None
    chat_id: Optional[str] = None
    command: str
    purpose: Optional[str] = None
    state: str
    output: Optional[str] = None
    stderr: Optional[str] = None
    return_code: Optional[int] = None
    risk_level: str
    risk_reasons: Optional[List[str]] = None
    requested_at: Optional[float] = None
    approved_at: Optional[float] = None
    execution_started_at: Optional[float] = None
    execution_completed_at: Optional[float] = None
    approved_by_user_id: Optional[str] = None
    approval_comment: Optional[str] = None


class AgentTerminalInfoResponse(BaseModel):
    """Response for GET /agent-terminal/."""

    name: str
    version: str
    description: str
    features: List[str]
    agent_roles: List[str]
    session_states: List[str]
    endpoints: Dict[str, str]
    security_features: Dict[str, str]


class AgentTerminalToolApprovalResponse(BaseModel):
    """Response for POST /agent-terminal/tools/approve/{approval_id}."""

    status: str
    approval_id: str
    approved: bool


class AgentTerminalHostSelectionRequestResponse(BaseModel):
    """Response for POST /agent-terminal/host-selection/request."""

    request_id: str
    status: str
    message: str


class AgentTerminalHostSelectionGetResponse(BaseModel):
    """Response for GET /agent-terminal/host-selection/{request_id}."""

    request_id: str
    status: str
    selected_host_id: Optional[str] = None
    selected_host_name: Optional[str] = None
    connection_info: Optional[Dict[str, Any]] = None
    created_at: str
    updated_at: Optional[str] = None


class AgentTerminalHostSelectionSubmitResponse(BaseModel):
    """Response for POST /agent-terminal/host-selection/{request_id}/select."""

    status: str
    request_id: str
    selected_host_id: Optional[str] = None
    selected_host_name: Optional[str] = None
    connection_info: Optional[Dict[str, Any]] = None


class AgentTerminalHostSelectionCancelResponse(BaseModel):
    """Response for POST /agent-terminal/host-selection/{request_id}/cancel."""

    status: str
    request_id: str


class AgentTerminalPendingSelectionsResponse(BaseModel):
    """Response for GET /agent-terminal/host-selection."""

    status: str
    pending_count: int
    pending_selections: List[Dict[str, Any]]


# ---------------------------------------------------------------------------
# knowledge_metadata.py schemas  (Issue #5317)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# terminal_models.py classes (merged from terminal_models.py — Issue #5996)
# ---------------------------------------------------------------------------


class SecurityLevel(Enum):
    """Security levels for terminal access"""

    STANDARD = "standard"
    ELEVATED = "elevated"
    RESTRICTED = "restricted"


class CommandRiskLevel(Enum):
    """Risk assessment levels for commands"""

    SAFE = "safe"
    MODERATE = "moderate"
    HIGH = "high"
    DANGEROUS = "dangerous"


# Request/Response Models
class CommandRequest(BaseModel):
    command: str
    description: Optional[str] = None
    require_confirmation: Optional[bool] = True
    timeout: Optional[float] = 30.0
    working_directory: Optional[str] = None
    environment: Optional[Dict[str, str]] = None


class TerminalSessionRequest(BaseModel):
    user_id: Optional[str] = "default"
    conversation_id: Optional[str] = None  # Link to chat session for logging
    chat_id: Optional[str] = None  # For chat-scoped SSH keys (Issue #211)
    security_level: Optional[SecurityLevel] = SecurityLevel.STANDARD
    enable_logging: Optional[bool] = True
    enable_workflow_control: Optional[bool] = True
    initial_directory: Optional[str] = None
    setup_ssh_keys: Optional[bool] = False  # Auto-setup SSH keys (Issue #211)
    ssh_key_names: Optional[list] = None  # Specific SSH keys to load (Issue #211)


class TerminalInputRequest(BaseModel):
    text: str
    is_password: Optional[bool] = False


class WorkflowControlRequest(BaseModel):
    action: str  # pause, resume, approve_step, cancel
    workflow_id: Optional[str] = None
    step_id: Optional[str] = None
    data: Optional[Dict] = None


class ToolInstallRequest(BaseModel):
    tool_name: str
    package_name: Optional[str] = None
    install_method: Optional[str] = "auto"
    custom_command: Optional[str] = None
    update_first: Optional[bool] = True


class SSHKeySetupRequest(BaseModel):
    """Request model for SSH key setup in terminal sessions (Issue #211)."""

    chat_id: Optional[str] = None  # For chat-scoped keys
    include_general: Optional[bool] = True  # Include general-scoped keys
    key_names: Optional[list] = None  # Specific keys to load


class SSHKeyAgentRequest(BaseModel):
    """Request model for adding SSH key to ssh-agent (Issue #211)."""

    key_name: str
    passphrase: Optional[str] = None  # For encrypted keys


class AdminExecuteRequest(BaseModel):
    """Request body for SLM admin terminal command execution (Issue #983)."""

    command: str
    host: str = ""
