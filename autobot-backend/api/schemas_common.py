# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Shared Pydantic response models for AutoBot API endpoints.

These models are used across multiple API modules to ensure consistent
response shapes for FastAPI response_model= annotations.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class SuccessResponse(BaseModel):
    """Generic success/failure response."""

    success: bool
    message: Optional[str] = None


class StatusResponse(BaseModel):
    """Response with a status string and optional message."""

    status: str
    message: Optional[str] = None


class ErrorResponse(BaseModel):
    """Error response with detail."""

    error: str
    details: Optional[str] = None


# ---------------------------------------------------------------------------
# Terminal session responses
# ---------------------------------------------------------------------------


class TerminalSessionCreatedResponse(BaseModel):
    """Response from POST /terminal/sessions."""

    session_id: str
    status: str
    security_level: str
    websocket_url: str
    created_at: str
    ssh_keys: Optional[Dict[str, Any]] = None


class TerminalSessionEntry(BaseModel):
    """Single entry in the session list."""

    session_id: str
    user_id: Optional[str] = None
    security_level: Optional[str] = None
    created_at: Optional[str] = None
    is_active: bool


class TerminalSessionListResponse(BaseModel):
    """Response from GET /terminal/sessions."""

    sessions: List[TerminalSessionEntry]
    total: int
    active: int


class TerminalSessionDetailResponse(BaseModel):
    """Response from GET /terminal/sessions/{session_id}."""

    session_id: str
    config: Dict[str, Any]
    is_active: bool
    statistics: Dict[str, Any]


class TerminalSessionDeletedResponse(BaseModel):
    """Response from DELETE /terminal/sessions/{session_id}."""

    session_id: str
    status: str


class SSHKeyListResponse(BaseModel):
    """Response from GET /terminal/sessions/{session_id}/ssh-keys."""

    session_id: str
    keys: List[Any]
    total: int


class SSHKeyAgentResponse(BaseModel):
    """Response from POST /terminal/sessions/{session_id}/ssh-keys/{key_name}/agent."""

    session_id: str
    key_name: str
    status: str
    message: str


class SSHKeyPathResponse(BaseModel):
    """Response from GET /terminal/sessions/{session_id}/ssh-keys/{key_name}/path."""

    session_id: str
    key_name: str
    key_path: str
    usage: str


class CommandAssessmentResponse(BaseModel):
    """Response from POST /terminal/command (risk assessment only)."""

    command: str
    risk_level: str
    status: str
    message: str
    requires_confirmation: bool


class TerminalInputResponse(BaseModel):
    """Response from POST /terminal/sessions/{session_id}/input."""

    session_id: str
    status: str
    input: str


class TerminalSignalResponse(BaseModel):
    """Response from POST /terminal/sessions/{session_id}/signal/{signal_name}."""

    session_id: str
    signal: str
    status: str


class TerminalHistoryResponse(BaseModel):
    """Response from GET /terminal/sessions/{session_id}/history."""

    session_id: str
    is_active: bool
    history: List[Any]
    total_commands: Optional[int] = None
    message: Optional[str] = None


class TerminalAuditResponse(BaseModel):
    """Response from GET /terminal/audit/{session_id}."""

    session_id: str
    audit_available: bool
    security_level: Optional[str] = None
    message: str


class AdminExecuteResponse(BaseModel):
    """Response from POST /terminal/execute (SLM admin terminal)."""

    stdout: str
    stderr: str
    exit_code: int


# ---------------------------------------------------------------------------
# Agent terminal responses
# ---------------------------------------------------------------------------


class AgentSessionCreatedResponse(BaseModel):
    """Response from POST /agent-terminal/sessions."""

    status: str
    session_id: str
    agent_id: str
    agent_role: str
    conversation_id: Optional[str] = None
    host: str
    state: str
    created_at: Any
    pty_session_id: Optional[str] = None


class AgentSessionEntry(BaseModel):
    """Single session in the agent session list."""

    session_id: str
    agent_id: str
    agent_role: str
    conversation_id: Optional[str] = None
    host: str
    state: str
    created_at: Any
    last_activity: Any
    command_count: int
    pty_session_id: Optional[str] = None


class AgentSessionListResponse(BaseModel):
    """Response from GET /agent-terminal/sessions."""

    status: str
    total: int
    sessions: List[AgentSessionEntry]


class AgentSessionDeletedResponse(BaseModel):
    """Response from DELETE /agent-terminal/sessions/{session_id}."""

    status: str
    session_id: str


class ToolApprovalResponse(BaseModel):
    """Response from POST /agent-terminal/tools/approve/{approval_id}."""

    status: str
    approval_id: str
    approved: bool


class HostSelectionRequestResponse(BaseModel):
    """Response from POST /agent-terminal/host-selection/request."""

    request_id: str
    status: str
    message: str


class HostSelectionStatusResponse(BaseModel):
    """Response from GET /agent-terminal/host-selection/{request_id}."""

    request_id: str
    status: str
    selected_host_id: Optional[str] = None
    selected_host_name: Optional[str] = None
    connection_info: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class HostSelectionSubmitResponse(BaseModel):
    """Response from POST /agent-terminal/host-selection/{request_id}/select."""

    status: str
    request_id: str
    selected_host_id: Optional[str] = None
    selected_host_name: Optional[str] = None
    connection_info: Optional[Dict[str, Any]] = None


class HostSelectionCancelResponse(BaseModel):
    """Response from POST /agent-terminal/host-selection/{request_id}/cancel."""

    status: str
    request_id: str


class PendingHostSelectionEntry(BaseModel):
    """Single entry in pending host selection list."""

    request_id: str
    command: Optional[str] = None
    purpose: Optional[str] = None
    created_at: Optional[str] = None


class PendingHostSelectionsResponse(BaseModel):
    """Response from GET /agent-terminal/host-selection."""

    status: str
    pending_count: int
    pending_selections: List[PendingHostSelectionEntry]


class CommandStateResponse(BaseModel):
    """Response from GET /agent-terminal/commands/{command_id}."""

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
    requested_at: Optional[Any] = None
    approved_at: Optional[Any] = None
    execution_started_at: Optional[Any] = None
    execution_completed_at: Optional[Any] = None
    approved_by_user_id: Optional[str] = None
    approval_comment: Optional[str] = None


# ---------------------------------------------------------------------------
# Terminal tools responses
# ---------------------------------------------------------------------------


class PackageManagersResponse(BaseModel):
    """Response from GET /terminal/package-managers."""

    detected: Optional[str] = None
    available: List[str]
    package_managers: Dict[str, Any]


class ToolCheckResponse(BaseModel):
    """Response from POST /terminal/check-tool."""

    installed: bool
    command: Optional[str] = None
    message: str


class CommandValidationResponse(BaseModel):
    """Response from POST /terminal/validate-command."""

    safe: bool
    risk_level: str
    issues: List[str]
    recommendation: str
