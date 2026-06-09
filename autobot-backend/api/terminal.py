# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Terminal API - Unified Terminal System for AutoBot

This module provides the core terminal infrastructure used by both Tools Terminal
and Chat Terminal. It implements WebSocket-based PTY (pseudo-terminal) access with
real-time bidirectional communication.

Architecture:
-----------
┌────────────────────────────────────────────────────────────┐
│ Tools Terminal (Standalone) │ Chat Terminal (AI-Integrated)│
└────────────┬────────────────┴──────────────┬───────────────┘
             │                               │
             │  Both use this module         │
             └───────────────┬───────────────┘
                             │
         ┌───────────────────▼────────────────────┐
         │  backend/api/terminal.py               │
         │  • REST API for session management     │
         │  • WebSocket for real-time I/O         │
         │  • PTY process management              │
         │  • Output buffering for chat           │
         └───────────────────┬────────────────────┘
                             │
         ┌───────────────────▼────────────────────┐
         │  backend/services/simple_pty.py        │
         │  • Real PTY creation (pty.openpty())   │
         │  • /bin/bash process spawning          │
         │  • Input/output queues                 │
         └────────────────────────────────────────┘

Key Components:
--------------
1. ConsolidatedTerminalWebSocket
   - WebSocket handler for real-time terminal I/O
   - Manages PTY process lifecycle
   - Buffers output for chat integration
   - Sends output to ChatHistoryManager when linked to conversation

2. ConsolidatedTerminalManager
   - Session registry and lifecycle management
   - Signal handling (SIGINT, SIGTERM, etc.)
   - Session cleanup and resource management

3. REST API Endpoints
   - POST /api/terminal/sessions - Create new session
   - GET /api/terminal/sessions - List active sessions
   - GET /api/terminal/sessions/{id} - Get session details
   - POST /api/terminal/sessions/{id}/input - Send input
   - POST /api/terminal/sessions/{id}/signal/{name} - Send signal
   - GET /api/terminal/sessions/{id}/history - Get command history

4. WebSocket Endpoints
   - /api/terminal/ws/{session_id} - Primary WebSocket endpoint
   - /api/terminal/ws/simple/{session_id} - Simple WebSocket (legacy)
   - /api/terminal/ws/secure/{session_id} - Secure WebSocket (legacy)

Message Protocol:
----------------
Client → Server:
    {"type": "input", "text": "ls -la\\n"}
    {"type": "resize", "rows": 24, "cols": 80}
    {"type": "ping"}

Server → Client:
    {"type": "output", "content": "file1.txt\\nfile2.txt\\n"}
    {"type": "connected", "content": "Connected to terminal"}
    {"type": "error", "content": "Terminal error message"}
    {"type": "pong"}

Chat Integration:
----------------
When conversation_id is provided:
1. All terminal output is buffered
2. Output saved to ChatHistoryManager every 500ms or 1000 chars
3. Commands logged with TerminalLogger
4. Provides complete terminal transcript in chat history

Usage Examples:
--------------
# Tools Terminal (Standalone)
1. POST /api/terminal/sessions
   → { session_id, websocket_url }
2. WebSocket /api/terminal/ws/{session_id}
3. Send/receive terminal I/O

# Chat Terminal (AI-Integrated)
1. POST /api/agent-terminal/sessions (creates agent session)
   → { session_id, pty_session_id }
2. WebSocket /api/terminal/ws/{pty_session_id} (uses this module)
3. Output automatically saved to chat history

Security:
--------
- Command validation via SecureCommandExecutor (optional)
- Security levels: STANDARD, ELEVATED, RESTRICTED
- Audit logging for sensitive operations
- Session isolation (each PTY is independent)

See Also:
--------
- backend/api/agent_terminal.py - Agent terminal with approval workflow
- backend/services/agent_terminal_service.py - Agent terminal business logic
- backend/services/simple_pty.py - PTY implementation
- docs/architecture/TERMINAL_ARCHITECTURE_DIAGRAM.md - Architecture details
"""

import asyncio
import json
import shlex
import signal
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect

# Import models from dedicated module (Issue #185 - split oversized files)
# Response schemas for OpenAPI documentation and response validation
from api.schemas_terminal import (
    AdminExecuteRequest,
    AdminExecuteResponse,
    CommandAssessResponse,
    CommandRequest,
    CommandRiskLevel,
    SecurityLevel,
    SSHKeyAgentRequest,
    SSHKeyAgentResponse,
    SSHKeyListResponse,
    SSHKeyPathResponse,
    SSHKeySetupRequest,
    TerminalAuditLogResponse,
    TerminalCapabilitiesResponse,
    TerminalCommandHistoryResponse,
    TerminalFeaturesResponse,
    TerminalInfoResponse,
    TerminalInputRequest,
    TerminalInputResponse,
    TerminalSecurityPoliciesResponse,
    TerminalSessionCreateResponse,
    TerminalSessionDeleteResponse,
    TerminalSessionDetailResponse,
    TerminalSessionListResponse,
    TerminalSessionRequest,
    TerminalSignalResponse,
    TerminalStatsResponse,
    TerminalSystemStatusResponse,
)
from api.system_health import ComponentHealth, register_health_probe
from auth_middleware import check_admin_permission, get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.error_utils import safe_http_detail
from autobot_shared.logging_manager import get_logger
from constants.error_constants import ERR_SESSION_NOT_FOUND
from constants.terminal_constants import MODERATE_RISK_PATTERNS, RISKY_COMMAND_PATTERNS
from services.simple_pty import simple_pty_manager

# Import terminal secrets service for SSH key integration (Issue #211)
from services.terminal_secrets_service import get_terminal_secrets_service

logger = get_logger(__name__)

# Create router for consolidated terminal API
router = APIRouter(
    tags=["terminal"],
    dependencies=[Depends(check_admin_permission)],
)


# SSH terminal stub classes — previously in api/ssh_terminal_handlers.py.
# Issue #729: SSH operations to infrastructure hosts are now handled by slm-server.
# Issue #3383: Inlined here to eliminate the competing module.


class SSHTerminalWebSocket:
    """
    Stub SSH terminal handler — redirects to SLM for infrastructure connections.

    Issue #729: SSH connections to infrastructure hosts are now managed by slm-server.
    This class provides a backward-compatible interface that returns a deprecation message.
    """

    def __init__(
        self,
        websocket: WebSocket,
        session_id: str,
        host_id: str,
        conversation_id: str | None = None,
        redis_client=None,
    ):
        """Initialize SSH terminal handler stub."""
        self.websocket = websocket
        self.session_id = session_id
        self.host_id = host_id
        self.conversation_id = conversation_id
        self.active = False
        self.command_history: list = []
        self.session_start_time = datetime.now(tz=timezone.utc)

    async def start(self) -> bool:
        """Start SSH terminal session — returns deprecation message."""
        self.active = False
        await self._send_error(
            "SSH terminal connections to infrastructure hosts have been moved to SLM.\n"
            "Please use slm-admin \u2192 Tools \u2192 Terminal to connect to infrastructure hosts,\n"
            "or call the SLM API directly at: /api/terminal/ssh/{host_id}\n\n"
            "This is part of the layer separation (#729) — infrastructure operations\n"
            "are now managed exclusively by slm-server."
        )
        return False

    async def cleanup(self) -> None:
        """Clean up resources."""
        self.active = False
        logger.info("SSH terminal stub session cleaned up: %s", self.session_id)

    async def send_message(self, message: dict) -> None:
        """Send message to WebSocket client."""
        try:
            await self.websocket.send_text(json.dumps(message))
        except Exception as e:
            logger.error("Error sending message: %s", e)

    async def _send_error(self, content: str) -> None:
        """Send error message to client."""
        await self.send_message(
            {
                "type": "error",
                "content": content,
                "timestamp": time.time(),
                "redirect": {
                    "type": "slm",
                    "message": "Use SLM for infrastructure SSH connections",
                    "url": "/api/terminal/ssh/{host_id}",
                },
            }
        )

    async def send_to_terminal(self, text: str) -> None:
        """Send text input — not supported, redirects to SLM."""
        await self._send_error("SSH terminal not available. Use SLM for infrastructure connections.")

    async def send_output(self, content: str) -> None:
        """Send terminal output — stub."""

    async def handle_message(self, message: dict) -> None:
        """Handle incoming WebSocket message — returns deprecation notice."""
        await self._send_error("SSH terminal moved to SLM server (#729)")


class _SSHTerminalManager:
    """Manager for SSH terminal sessions — stub implementation."""

    def __init__(self) -> None:
        """Initialize SSH terminal manager."""
        self.active_sessions: Dict[str, SSHTerminalWebSocket] = {}
        self._lock = asyncio.Lock()

    async def add_session(self, session_id: str, terminal: SSHTerminalWebSocket) -> None:
        """Add an SSH terminal session."""
        async with self._lock:
            self.active_sessions[session_id] = terminal

    async def remove_session(self, session_id: str) -> None:
        """Remove an SSH terminal session."""
        async with self._lock:
            self.active_sessions.pop(session_id, None)

    async def get_session(self, session_id: str) -> SSHTerminalWebSocket | None:
        """Get an SSH terminal session."""
        async with self._lock:
            return self.active_sessions.get(session_id)

    async def close_session(self, session_id: str) -> None:
        """Close and clean up an SSH terminal session."""
        terminal: SSHTerminalWebSocket | None = None
        async with self._lock:
            terminal = self.active_sessions.get(session_id)
        if terminal:
            await terminal.cleanup()
            await self.remove_session(session_id)

    def list_sessions(self) -> Dict[str, Dict[str, Any]]:
        """List all active SSH terminal sessions."""
        return {
            sid: {
                "host_id": t.host_id,
                "conversation_id": t.conversation_id,
                "start_time": t.session_start_time.isoformat(),
                "active": t.active,
            }
            for sid, t in self.active_sessions.items()
        }


ssh_terminal_manager = _SSHTerminalManager()


# Import handler classes (extracted from this file - Issue #210)
from api.terminal_handlers import ConsolidatedTerminalWebSocket, session_manager

# Import tool management router (extracted from this file - Issue #185)
from api.terminal_tools import router as tools_router

# Include tool management router
router.include_router(tools_router, prefix="/terminal")


# REST API Endpoints


@router.post("/sessions", response_model=TerminalSessionCreateResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_terminal_session",
    error_code_prefix="TERMINAL",
)
async def create_terminal_session(
    request: TerminalSessionRequest,
    current_user: dict = Depends(get_current_user),
):
    """Create a new terminal session with enhanced security options.

    Supports automatic SSH key injection from secrets management (Issue #211).
    Issue #744: Requires authenticated user.
    """
    session_id = str(uuid.uuid4())

    # Store session configuration for WebSocket connection
    session_config = {
        "session_id": session_id,
        "user_id": request.user_id,
        "conversation_id": (request.conversation_id),  # For linking chat to terminal logging
        "chat_id": request.chat_id,  # For chat-scoped SSH keys (Issue #211)
        "security_level": request.security_level,
        "enable_logging": request.enable_logging,
        "enable_workflow_control": request.enable_workflow_control,
        "initial_directory": request.initial_directory,
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
    }

    # Store in session manager (you would use a proper store in production)
    session_manager.session_configs[session_id] = session_config

    # Setup SSH keys if requested (Issue #211)
    ssh_key_result = None
    if request.setup_ssh_keys:
        try:
            terminal_secrets = get_terminal_secrets_service()
            ssh_key_result = await terminal_secrets.setup_ssh_keys(
                session_id=session_id,
                chat_id=request.chat_id,
                include_general=True,
                specific_key_names=request.ssh_key_names,
            )
            logger.info(
                "SSH keys setup for session %s: %d keys loaded",
                session_id,
                ssh_key_result.get("keys_loaded", 0),
            )
        except Exception as e:
            logger.warning("Failed to setup SSH keys for session %s: %s", session_id, e)
            ssh_key_result = {"error": "Internal server error"}

    logger.info("Created terminal session: %s", session_id)

    response = {
        "session_id": session_id,
        "status": "created",
        "security_level": request.security_level.value,
        "websocket_url": f"/api/terminal/ws/{session_id}",
        "created_at": session_config["created_at"],
    }

    if ssh_key_result:
        response["ssh_keys"] = ssh_key_result

    return response


@router.get("/sessions", response_model=TerminalSessionListResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_terminal_sessions",
    error_code_prefix="TERMINAL",
)
async def list_terminal_sessions(
    current_user: dict = Depends(get_current_user),
):
    """List all active terminal sessions
    Issue #744: Requires authenticated user.
    """
    sessions = []
    for session_id, config in session_manager.session_configs.items():
        is_active = session_manager.has_connection(session_id)
        sessions.append(
            {
                "session_id": session_id,
                "user_id": config.get("user_id"),
                "security_level": config.get("security_level"),
                "created_at": config.get("created_at"),
                "is_active": is_active,
            }
        )

    return {
        "sessions": sessions,
        "total": len(sessions),
        "active": sum(1 for s in sessions if s["is_active"]),
    }


@router.get("/sessions/{session_id}", response_model=TerminalSessionDetailResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_terminal_session",
    error_code_prefix="TERMINAL",
)
async def get_terminal_session(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Get information about a specific terminal session
    Issue #744: Requires authenticated user.
    """
    config = session_manager.session_configs.get(session_id)
    if not config:
        raise HTTPException(status_code=404, detail=ERR_SESSION_NOT_FOUND)

    is_active = session_manager.has_connection(session_id)

    # Get session statistics if active
    stats = {}
    if is_active and hasattr(session_manager, "get_session_stats"):
        stats = session_manager.get_session_stats(session_id)

    return {
        "session_id": session_id,
        "config": config,
        "is_active": is_active,
        "statistics": stats,
    }


@router.delete("/sessions/{session_id}", response_model=TerminalSessionDeleteResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delete_terminal_session",
    error_code_prefix="TERMINAL",
)
async def delete_terminal_session(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Delete a terminal session and close any active connections.

    Also cleans up any SSH keys loaded for this session (Issue #211).
    Issue #744: Requires authenticated user.
    """
    config = session_manager.session_configs.get(session_id)
    if not config:
        raise HTTPException(status_code=404, detail=ERR_SESSION_NOT_FOUND)

    # Close WebSocket connection if active
    if session_manager.has_connection(session_id):
        await session_manager.close_connection(session_id)

    # Cleanup SSH keys for this session (Issue #211)
    try:
        terminal_secrets = get_terminal_secrets_service()
        await terminal_secrets.cleanup_session_keys(session_id)
    except Exception as e:
        logger.warning("Failed to cleanup SSH keys for session %s: %s", session_id, e)

    # Remove session configuration
    del session_manager.session_configs[session_id]

    logger.info("Deleted terminal session: %s", session_id)

    return {"session_id": session_id, "status": "deleted"}


# SSH Key Management Endpoints (Issue #211)


@router.post("/sessions/{session_id}/ssh-keys", response_model=SSHKeyListResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="setup_ssh_keys",
    error_code_prefix="TERMINAL",
)
async def setup_ssh_keys(
    session_id: str,
    request: SSHKeySetupRequest,
    current_user: dict = Depends(get_current_user),
):
    """Setup SSH keys for an existing terminal session.
    Issue #744: Requires authenticated user.

    Retrieves SSH keys from secrets storage and makes them available
    for use in SSH commands. Keys are written to temporary files with
    proper permissions.

    Args:
        session_id: Terminal session ID
        request: SSH key setup options

    Returns:
        Dictionary with setup results including available keys
    """
    config = session_manager.session_configs.get(session_id)
    if not config:
        raise HTTPException(status_code=404, detail=ERR_SESSION_NOT_FOUND)

    try:
        terminal_secrets = get_terminal_secrets_service()
        result = await terminal_secrets.setup_ssh_keys(
            session_id=session_id,
            chat_id=request.chat_id or config.get("chat_id"),
            include_general=request.include_general,
            specific_key_names=request.key_names,
        )
        return result
    except Exception as e:
        logger.error("Failed to setup SSH keys: %s", e)
        raise HTTPException(status_code=500, detail="SSH key setup failed")


@router.get("/sessions/{session_id}/ssh-keys", response_model=SSHKeyListResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_session_ssh_keys",
    error_code_prefix="TERMINAL",
)
async def list_session_ssh_keys(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Get list of SSH keys available for a terminal session.

    Returns information about loaded SSH keys including name,
    fingerprint, and whether a passphrase is required.
    Issue #744: Requires authenticated user.
    """
    config = session_manager.session_configs.get(session_id)
    if not config:
        raise HTTPException(status_code=404, detail=ERR_SESSION_NOT_FOUND)

    terminal_secrets = get_terminal_secrets_service()
    keys = terminal_secrets.get_session_keys(session_id)

    return {
        "session_id": session_id,
        "keys": keys,
        "total": len(keys),
    }


@router.post("/sessions/{session_id}/ssh-keys/{key_name}/agent", response_model=SSHKeyAgentResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="add_key_to_ssh_agent",
    error_code_prefix="TERMINAL",
)
async def add_key_to_ssh_agent(
    session_id: str,
    key_name: str,
    request: SSHKeyAgentRequest,
    current_user: dict = Depends(get_current_user),
):
    """Add an SSH key to ssh-agent for easier authentication.

    For keys that require a passphrase, the passphrase must be provided.
    The key remains in the agent until the session ends.
    Issue #744: Requires authenticated user.
    """
    config = session_manager.session_configs.get(session_id)
    if not config:
        raise HTTPException(status_code=404, detail=ERR_SESSION_NOT_FOUND)

    terminal_secrets = get_terminal_secrets_service()
    success = await terminal_secrets.add_key_to_agent(
        session_id=session_id,
        key_name=key_name,
        passphrase=request.passphrase,
    )

    if success:
        return {
            "session_id": session_id,
            "key_name": key_name,
            "status": "added",
            "message": f"Key '{key_name}' added to ssh-agent",
        }
    else:
        raise HTTPException(status_code=400, detail=f"Failed to add key '{key_name}' to ssh-agent")


@router.get("/sessions/{session_id}/ssh-keys/{key_name}/path", response_model=SSHKeyPathResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_ssh_key_path",
    error_code_prefix="TERMINAL",
)
async def get_ssh_key_path(
    session_id: str,
    key_name: str,
    current_user: dict = Depends(get_current_user),
):
    """Get the file path for an SSH key in a terminal session.

    Returns the temporary file path where the key is stored.
    Use this path with ssh -i option for explicit key specification.
    Issue #744: Requires authenticated user.
    """
    config = session_manager.session_configs.get(session_id)
    if not config:
        raise HTTPException(status_code=404, detail=ERR_SESSION_NOT_FOUND)

    terminal_secrets = get_terminal_secrets_service()
    key_path = terminal_secrets.get_key_path(session_id, key_name)

    if key_path:
        return {
            "session_id": session_id,
            "key_name": key_name,
            "key_path": key_path,
            "usage": f"ssh -i {key_path} user@host",
        }
    else:
        raise HTTPException(status_code=404, detail=f"Key '{key_name}' not found")


@router.post("/command", response_model=CommandAssessResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="execute_single_command",
    error_code_prefix="TERMINAL",
)
async def execute_single_command(
    request: CommandRequest,
    current_user: dict = Depends(get_current_user),
):
    """Execute a single command with security assessment
    Issue #744: Requires authenticated user.
    """
    # Assess command for security risk

    # Assess command risk
    risk_level = CommandRiskLevel.SAFE
    command_lower = request.command.lower().strip()

    for pattern in RISKY_COMMAND_PATTERNS:
        if pattern in command_lower:
            risk_level = CommandRiskLevel.DANGEROUS
            break
    else:
        for pattern in MODERATE_RISK_PATTERNS:
            if pattern in command_lower:
                risk_level = CommandRiskLevel.MODERATE
                break

    # Log command execution attempt
    logger.info(f"Single command execution: {request.command} (risk: {risk_level.value})")

    # For now, return the assessment (actual execution would need subprocess)
    return {
        "command": request.command,
        "risk_level": risk_level.value,
        "status": "assessed",
        "message": f"Command assessed as {risk_level.value} risk",
        "requires_confirmation": risk_level != CommandRiskLevel.SAFE,
    }


@router.post("/sessions/{session_id}/input", response_model=TerminalInputResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="send_terminal_input",
    error_code_prefix="TERMINAL",
)
async def send_terminal_input(
    session_id: str,
    request: TerminalInputRequest,
    current_user: dict = Depends(get_current_user),
):
    """Send input to a specific terminal session
    Issue #744: Requires authenticated user.
    """
    if not session_manager.has_connection(session_id):
        raise HTTPException(status_code=404, detail="Session not active")

    # Send input to the WebSocket connection
    # This would be implemented through the session manager
    success = await session_manager.send_input(session_id, request.text)

    if success:
        return {
            "session_id": session_id,
            "status": "sent",
            "input": request.text if not request.is_password else "***",
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to send input")


@router.post("/sessions/{session_id}/signal/{signal_name}", response_model=TerminalSignalResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="send_terminal_signal",
    error_code_prefix="TERMINAL",
)
async def send_terminal_signal(
    session_id: str,
    signal_name: str,
    current_user: dict = Depends(get_current_user),
):
    """Send a signal to a terminal session
    Issue #744: Requires authenticated user.
    """
    if not session_manager.has_connection(session_id):
        raise HTTPException(status_code=404, detail="Session not active")

    # Map signal names to signal constants
    signal_map = {
        "SIGINT": signal.SIGINT,
        "SIGTERM": signal.SIGTERM,
        "SIGKILL": signal.SIGKILL,
        "SIGSTOP": signal.SIGSTOP,
        "SIGCONT": signal.SIGCONT,
    }

    if signal_name not in signal_map:
        raise HTTPException(status_code=400, detail=f"Invalid signal: {signal_name}")

    success = await session_manager.send_signal(session_id, signal_map[signal_name])

    if success:
        return {"session_id": session_id, "signal": signal_name, "status": "sent"}
    else:
        raise HTTPException(status_code=500, detail="Failed to send signal")


@router.get("/sessions/{session_id}/history", response_model=TerminalCommandHistoryResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_terminal_command_history",
    error_code_prefix="TERMINAL",
)
async def get_terminal_command_history(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Get command history for a terminal session
    Issue #744: Requires authenticated user.
    """
    config = session_manager.session_configs.get(session_id)
    if not config:
        raise HTTPException(status_code=404, detail=ERR_SESSION_NOT_FOUND)

    # Check if session has active connection
    is_active = session_manager.has_connection(session_id)

    if not is_active:
        return {
            "session_id": session_id,
            "is_active": False,
            "history": [],
            "message": "Session is not active, no command history available",
        }

    # Get command history from active terminal
    history = session_manager.get_command_history(session_id)

    return {
        "session_id": session_id,
        "is_active": True,
        "history": history,
        "total_commands": len(history),
    }


@router.get("/audit/{session_id}", response_model=TerminalAuditLogResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_session_audit_log",
    error_code_prefix="TERMINAL",
)
async def get_session_audit_log(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Get security audit log for a session (elevated access required)
    Issue #744: Requires authenticated user.
    """
    config = session_manager.session_configs.get(session_id)
    if not config:
        raise HTTPException(status_code=404, detail=ERR_SESSION_NOT_FOUND)

    # In a real implementation, you'd check user permissions here
    # For now, return basic audit information

    return {
        "session_id": session_id,
        "audit_available": config.get("enable_logging", False),
        "security_level": config.get("security_level"),
        "message": "Audit log access requires elevated permissions",
    }


# WebSocket Endpoints


async def _init_terminal_handler(
    websocket: WebSocket,
    session_id: str,
) -> "ConsolidatedTerminalWebSocket":
    """Helper for consolidated_terminal_websocket. Ref: #1088.

    Resolves session config, acquires Redis client, constructs and starts
    the terminal handler, and registers it with the session manager.

    Args:
        websocket: Active WebSocket connection
        session_id: Session identifier

    Returns:
        Started ConsolidatedTerminalWebSocket instance
    """
    config = session_manager.session_configs.get(session_id, {})
    security_level = SecurityLevel(config.get("security_level", SecurityLevel.STANDARD.value))
    conversation_id = config.get("conversation_id")

    # Issue #666: Use async Redis client since TerminalLogger uses await with Redis ops
    redis_client = None
    try:
        from dependencies import get_async_redis_client

        redis_client = await get_async_redis_client(database="main")
    except Exception as e:
        logger.warning("Could not get Redis client for terminal logging: %s", e)

    terminal = ConsolidatedTerminalWebSocket(websocket, session_id, security_level, conversation_id, redis_client)
    session_manager.add_connection(session_id, terminal)
    await terminal.start()
    return terminal


async def _run_terminal_message_loop(
    websocket: WebSocket,
    terminal: "ConsolidatedTerminalWebSocket",
    session_id: str,
) -> None:
    """Helper for consolidated_terminal_websocket. Ref: #1088.

    Drives the receive loop, dispatching each message to the terminal handler.
    Handles WebSocketDisconnect and generic errors with appropriate logging.

    Args:
        websocket: Active WebSocket connection
        terminal: Initialised terminal handler
        session_id: Session identifier for logging
    """
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            logger.info(
                "[WS RECV] Session %s, Type: %s, Data: %s",
                session_id,
                message.get("type"),
                str(message)[:100],
            )
            await terminal.handle_message(message)
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for session %s", session_id)
    except Exception as e:
        logger.error("Error in WebSocket handling: %s", e)
        await websocket.send_text(
            json.dumps(
                {
                    "type": "error",
                    "content": "Terminal error",
                    "timestamp": time.time(),
                }
            )
        )


@router.websocket("/ws/{session_id}")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="consolidated_terminal_websocket",
    error_code_prefix="TERMINAL",
)
async def consolidated_terminal_websocket(websocket: WebSocket, session_id: str):
    """
    Primary WebSocket endpoint for consolidated terminal access.

    Replaces both /ws/simple and /ws/secure endpoints.
    Issue #1088: Extracted _init_terminal_handler and _run_terminal_message_loop
    helpers to reduce to <=65 lines.
    """
    await websocket.accept()

    try:
        terminal = await _init_terminal_handler(websocket, session_id)
        logger.info("WebSocket connection established for session %s", session_id)
        await _run_terminal_message_loop(websocket, terminal, session_id)

    except Exception as e:
        logger.error("Error establishing WebSocket connection: %s", e)
    finally:
        session_manager.remove_connection(session_id)
        if "terminal" in locals():
            await terminal.cleanup()


# SSH Terminal WebSocket (Issue #715 - Infrastructure host connections)
# Issue #729: DEPRECATED - SSH connections to infrastructure hosts moved to slm-server
# This endpoint now returns a deprecation message and redirects to SLM


async def _init_ssh_redis_client():
    """
    Initialize Redis client for SSH terminal logging.

    Issue #620: Extracted from ssh_terminal_websocket to reduce function length.

    Returns:
        Redis client or None if unavailable
    """
    try:
        from dependencies import get_async_redis_client

        return await get_async_redis_client(database="main")
    except Exception as e:
        logger.warning("Could not get Redis client for SSH terminal logging: %s", e)
        return None


async def _setup_ssh_terminal(
    websocket: WebSocket,
    session_id: str,
    host_id: str,
    conversation_id: str,
    redis_client,
) -> "SSHTerminalWebSocket":
    """
    Create and register SSH terminal handler.

    Issue #620: Extracted from ssh_terminal_websocket to reduce function length.

    Args:
        websocket: WebSocket connection
        session_id: Unique session identifier
        host_id: Target host ID
        conversation_id: Optional conversation ID
        redis_client: Redis client for logging

    Returns:
        SSHTerminalWebSocket instance
    """
    terminal = SSHTerminalWebSocket(
        websocket=websocket,
        session_id=session_id,
        host_id=host_id,
        conversation_id=conversation_id,
        redis_client=redis_client,
    )
    await ssh_terminal_manager.add_session(session_id, terminal)
    return terminal


async def _run_ssh_message_loop(websocket: WebSocket, terminal: "SSHTerminalWebSocket", session_id: str) -> None:
    """
    Run SSH WebSocket message handling loop.

    Issue #620: Extracted from ssh_terminal_websocket to reduce function length.

    Args:
        websocket: WebSocket connection
        terminal: SSH terminal handler
        session_id: Session identifier for logging
    """
    try:
        while terminal.active:
            data = await websocket.receive_text()
            message = json.loads(data)
            await terminal.handle_message(message)
    except WebSocketDisconnect:
        logger.info("SSH WebSocket disconnected: %s", session_id)
    except Exception as e:
        logger.error("Error in SSH WebSocket handling: %s", e)
        await websocket.send_text(
            json.dumps(
                {
                    "type": "error",
                    "content": "SSH terminal error",
                    "timestamp": time.time(),
                }
            )
        )


@router.websocket("/ws/ssh/{host_id}")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="ssh_terminal_websocket",
    error_code_prefix="TERMINAL",
)
async def ssh_terminal_websocket(
    websocket: WebSocket,
    host_id: str,
    conversation_id: str = None,
):
    """
    DEPRECATED: SSH terminal connections to infrastructure hosts.

    Issue #729: This endpoint has been deprecated as part of layer separation.
    Issue #620: Refactored to use helper functions.

    SSH connections to infrastructure hosts are now handled by slm-server.

    Use slm-admin → Tools → Terminal or the SLM API directly:
        - SLM Terminal API: /api/terminal/ssh/{host_id}
        - SLM Admin UI: slm-admin → Tools → Terminal

    This endpoint remains for backward compatibility but returns a deprecation
    message directing clients to use SLM for infrastructure connections.
    """
    await websocket.accept()
    session_id = f"ssh-{host_id}-{uuid.uuid4().hex[:8]}"

    try:
        # Issue #620: Use helper for Redis client initialization
        redis_client = await _init_ssh_redis_client()

        # Issue #620: Use helper for terminal setup
        terminal = await _setup_ssh_terminal(websocket, session_id, host_id, conversation_id, redis_client)

        # Start SSH session
        if not await terminal.start():
            logger.error("Failed to start SSH terminal session for host: %s", host_id)
            return

        logger.info("SSH WebSocket connection established: %s -> host %s", session_id, host_id)

        # Issue #620: Use helper for message loop
        await _run_ssh_message_loop(websocket, terminal, session_id)

    except Exception as e:
        logger.error("Error establishing SSH WebSocket connection: %s", e)
    finally:
        await ssh_terminal_manager.close_session(session_id)


# Information endpoints


@router.get("/", response_model=TerminalInfoResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="terminal_info",
    error_code_prefix="TERMINAL",
)
async def terminal_info(
    current_user: dict = Depends(get_current_user),
):
    """Get information about the consolidated terminal API
    Issue #744: Requires authenticated user.
    """
    return {
        "name": "Consolidated Terminal API",
        "version": "1.0.0",
        "description": "Single canonical terminal API — all previous implementations consolidated here (#3383)",
        "features": [
            "REST API for session management",
            "WebSocket-based real-time terminal access",
            "Security assessment and command auditing",
            "Workflow automation control integration",
            "Multi-level security controls",
        ],
        "endpoints": {
            "sessions": "/api/terminal/sessions",
            "websocket": "/api/terminal/ws/{session_id}",
            # Issue #729: SSH to infrastructure hosts moved to slm-server
            "websocket_ssh": "/api/terminal/ws/ssh/{host_id} (deprecated - use SLM)",
        },
        "security_levels": [level.value for level in SecurityLevel],
        # Issue #729: Layer separation notice
        "notice": "SSH connections to infrastructure hosts have been moved to slm-server. "
        "Use slm-admin or the SLM API for infrastructure terminal access.",
    }


# Health and Status endpoints


@register_health_probe("terminal")
async def probe_terminal(
    request: Request | None = None,
) -> ComponentHealth:
    """Issue #3333: probe registration for terminal module."""
    try:
        active_sessions = len(simple_pty_manager.sessions)
        return ComponentHealth(
            name="terminal",
            status="ok",
            detail=f"{active_sessions} active sessions",
            data={
                "active_sessions": active_sessions,
                "manager_initialized": simple_pty_manager is not None,
            },
        )
    except Exception as exc:
        return ComponentHealth(
            name="terminal",
            status="down",
            detail=f"probe error: {type(exc).__name__}",
        )


@router.get("/status", response_model=TerminalSystemStatusResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_terminal_system_status",
    error_code_prefix="TERMINAL",
)
async def get_terminal_system_status(
    current_user: dict = Depends(get_current_user),
):
    """Get overall terminal system status and configuration
    Issue #744: Requires authenticated user.

    Returns:
        System status including:
        - Operational status
        - Supported terminal types (Tools Terminal, Chat Terminal)
        - Available features
        - Session statistics
    """
    try:
        return {
            "status": "operational",
            "terminal_types": ["tools_terminal", "chat_terminal"],
            "features": {
                "pty_support": True,
                "websocket_support": True,
                "command_validation": True,
                "security_policies": True,
                "approval_workflow": True,  # Chat Terminal feature
                "agent_integration": True,  # Chat Terminal feature
            },
            "session_info": {
                "active_sessions": len(simple_pty_manager.sessions),
                "max_concurrent_sessions": None,  # No hard limit
            },
        }
    except Exception as e:
        logger.exception("Unexpected error: %s", e)
        return {
            "status": "error",
            "error": "Internal server error",
        }


@router.get("/capabilities", response_model=TerminalCapabilitiesResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_terminal_capabilities",
    error_code_prefix="TERMINAL",
)
async def get_terminal_capabilities(
    current_user: dict = Depends(get_current_user),
):
    """Get terminal system capabilities
    Issue #744: Requires authenticated user.

    Returns:
        Detailed list of all capabilities supported by the consolidated
        terminal system, including PTY management, WebSocket streaming,
        security validation, and more.
    """
    return {
        "pty_management": True,
        "websocket_streaming": True,
        "command_execution": True,
        "security_validation": True,
        "session_management": True,
        "terminal_types": {
            "tools_terminal": {
                "description": ("Standalone system terminal for direct command execution"),
                "features": ["direct_execution", "no_approval", "system_admin"],
            },
            "chat_terminal": {
                "description": "AI-integrated terminal with approval workflow",
                "features": [
                    "approval_workflow",
                    "risk_assessment",
                    "agent_integration",
                    "chat_history_logging",
                    "user_takeover",
                ],
            },
        },
        "pty_features": {
            "echo_control": True,
            "terminal_resize": True,
            "signal_handling": True,
            "queue_based_io": True,
            "non_blocking_output": True,
        },
        "websocket_features": {
            "real_time_streaming": True,
            "bidirectional_communication": True,
            "multiple_connection_types": ["primary", "simple", "secure"],
        },
    }


@router.get("/security", response_model=TerminalSecurityPoliciesResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_security_policies",
    error_code_prefix="TERMINAL",
)
async def get_security_policies(
    current_user: dict = Depends(get_current_user),
):
    """Get terminal security policies and command validation info
    Issue #744: Requires authenticated user.

    Returns:
        Security configuration including:
        - Command validation settings
        - Risk assessment levels
        - Blocked command categories
        - Security executor information
    """
    return {
        "command_validation": "enabled",
        "risk_assessment": "multi-level",
        "risk_levels": {
            "SAFE": "Commands that are safe to execute automatically",
            "MODERATE": "Commands that require logging but are generally safe",
            "HIGH": "Potentially dangerous commands requiring approval",
            "FORBIDDEN": "Commands that are blocked completely",
        },
        "security_executor": "SecureCommandExecutor",
        "approval_workflow": {
            "enabled_for": "chat_terminal",
            "disabled_for": "tools_terminal",
            "approval_required_for": ["HIGH", "FORBIDDEN"],
        },
        "audit_logging": {
            "enabled": True,
            "logs_to": "chat_history",
            "includes": ["command", "output", "risk_level", "user_approval"],
        },
    }


@router.get("/features", response_model=TerminalFeaturesResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_terminal_features",
    error_code_prefix="TERMINAL",
)
async def get_terminal_features(
    current_user: dict = Depends(get_current_user),
):
    """Get available terminal features and implementation details
    Issue #744: Requires authenticated user.

    Returns:
        Comprehensive feature list including:
        - Terminal implementations (Tools, Chat)
        - Feature descriptions
        - Technical capabilities
        - Integration points
    """
    return {
        "manager_class": "ConsolidatedTerminalManager",
        "websocket_class": "ConsolidatedTerminalWebSocket",
        "pty_implementation": "SimplePTY",
        "implementations": [
            {
                "name": "tools_terminal",
                "description": "Standalone system terminal for direct administration",
                "frontend_component": "ToolsTerminal.vue",
                "backend_api": "terminal.py (direct)",
                "approval_workflow": False,
            },
            {
                "name": "chat_terminal",
                "description": "AI-integrated terminal with command approval workflow",
                "frontend_component": "ChatTerminal.vue",
                "backend_api": "agent_terminal.py + terminal.py",
                "approval_workflow": True,
                "service_layer": "agent_terminal_service.py",
            },
        ],
        "features": {
            "pty_shell": "Full PTY shell support with SimplePTY implementation",
            "websocket_streaming": ("Real-time bidirectional communication via WebSocket"),
            "security_validation": "Command risk assessment via SecureCommandExecutor",
            "session_cleanup": "Proper resource cleanup on disconnect",
            "approval_workflow": "User approval for high-risk commands (Chat Terminal)",
            "agent_integration": "AI agent command execution with chat logging",
            "multi_host_support": "Execute on different hosts (main, frontend, etc.)",
        },
        "shared_infrastructure": {
            "websocket_transport": "terminal.py WebSocket endpoints",
            "pty_layer": "simple_pty.py (SimplePTY class)",
            "security": "SecureCommandExecutor for risk assessment",
        },
    }


@router.get("/stats", response_model=TerminalStatsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_terminal_statistics",
    error_code_prefix="TERMINAL",
)
async def get_terminal_statistics(
    session_id: str = None,
    current_user: dict = Depends(get_current_user),
):
    """Get terminal statistics for specific session or all sessions

    Args:
        session_id: Optional query parameter. If provided, returns stats for that
                   specific session. If omitted, returns overall system statistics.

    Returns:
        Terminal statistics including:
        - Overall system metrics (if session_id not provided)
        - Per-session statistics (if session_id provided)
        - Session counts, command counts, uptime, etc.

    Examples:
        GET /api/terminal/stats - Get overall system statistics
        GET /api/terminal/stats?session_id=abc123 - Get stats for session abc123

    Issue #744: Requires authenticated user.
    """
    return session_manager.get_terminal_stats(session_id)


# SLM Admin Terminal (Issue #983) ================================================


@router.post("/execute", summary="Execute command (SLM admin terminal)", response_model=AdminExecuteResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="admin_execute_command",
    error_code_prefix="TERMINAL",
)
async def admin_execute_command(body: AdminExecuteRequest) -> AdminExecuteResponse:
    """Execute a single shell command and return stdout/stderr/exit_code.

    Runs on the local backend machine. No auth required — accessible via
    the /autobot-api/ nginx proxy (Issue #983).

    Blocks commands matching RISKY_COMMAND_PATTERNS.
    """
    command_lower = body.command.lower().strip()
    for pattern in RISKY_COMMAND_PATTERNS:
        if pattern in command_lower:
            return {
                "stdout": "",
                "stderr": f"Command blocked: contains restricted pattern '{pattern}'",
                "exit_code": 1,
            }
    try:
        cmd_parts = shlex.split(body.command)
    except ValueError as exc:
        return {
            "stdout": "",
            "stderr": safe_http_detail(exc, "Invalid command syntax"),
            "exit_code": 1,
        }
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd_parts,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=30.0)
        return {
            "stdout": stdout_b.decode("utf-8", errors="replace"),
            "stderr": stderr_b.decode("utf-8", errors="replace"),
            "exit_code": proc.returncode or 0,
        }
    except asyncio.TimeoutError:
        return {
            "stdout": "",
            "stderr": "Command timed out after 30 seconds",
            "exit_code": 124,
        }
    except Exception:
        logger.exception("Admin terminal execute failed: %s", body.command)
        return {
            "stdout": "",
            "stderr": "Internal error executing command",
            "exit_code": 1,
        }
