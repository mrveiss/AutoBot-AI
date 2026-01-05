# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Agent Terminal API - Chat Terminal with Command Approval Workflow

This module provides the REST API layer for the Chat Terminal, which enables
AI agents to execute commands with user oversight. It implements a sophisticated
approval workflow to prevent unauthorized or dangerous command execution.

Purpose:
-------
The Chat Terminal is DIFFERENT from the Tools Terminal:
- Tools Terminal: Direct command execution, no chat link, no approval
- Chat Terminal: AI agent execution, chat-linked, approval workflow

This is the backend for Chat Terminal, managing agent sessions and command approval.

Architecture:
------------
┌────────────────────────────────────────────────────────────────┐
│  ChatTerminal.vue (Frontend)                                   │
│  • Links to chat session ID                                    │
│  • Shows approval dialogs                                      │
│  • Displays command output                                     │
└───────────────────────┬────────────────────────────────────────┘
                        │
                        │ POST /api/agent-terminal/sessions
                        ▼
┌────────────────────────────────────────────────────────────────┐
│  backend/api/agent_terminal.py (THIS MODULE)                   │
│  • REST API for session management                             │
│  • Command execution requests                                  │
│  • Approval/denial endpoints                                   │
│  • User takeover mechanism                                     │
└───────────────────────┬────────────────────────────────────────┘
                        │
                        │ Delegates to
                        ▼
┌────────────────────────────────────────────────────────────────┐
│  backend/services/agent_terminal_service.py                    │
│  • Business logic for approval workflow                        │
│  • Risk assessment (via SecureCommandExecutor)                 │
│  • State machine (AGENT_CONTROL ↔ USER_CONTROL)                │
│  • Chat integration (ChatHistoryManager)                       │
│  • Audit logging (TerminalLogger)                              │
└───────────────────────┬────────────────────────────────────────┘
                        │
                        │ Uses PTY from
                        ▼
┌────────────────────────────────────────────────────────────────┐
│  backend/api/terminal.py                                       │
│  • WebSocket: /api/terminal/ws/{pty_session_id}                │
│  • Shared PTY infrastructure                                   │
└────────────────────────────────────────────────────────────────┘

Approval Workflow:
-----------------
1. Agent Requests Command
   POST /api/agent-terminal/sessions/{id}/execute
   {
     "command": "sudo apt install nginx",
     "description": "Install nginx web server"
   }

2. Risk Assessment (SecureCommandExecutor)
   • SAFE → Execute immediately
   • MODERATE/HIGH → Require user approval
   • FORBIDDEN → Block completely

3. User Approval (if required)
   Frontend shows approval dialog
   User clicks [Approve] or [Deny]

4. Approval Response
   POST /api/agent-terminal/sessions/{id}/approve
   {
     "approved": true,
     "user_id": "user123",
     "comment": "Approved for nginx installation"
   }

5. Command Execution
   • Sent to PTY via terminal.py
   • Output captured and sent to chat
   • Logged to command history

State Machine:
-------------
AGENT_CONTROL → (user interrupt) → USER_INTERRUPT → USER_CONTROL
                                                           │
                                                           │
AGENT_CONTROL ← (agent resume) ← AGENT_RESUME ← (user release)

REST API Endpoints:
------------------
# Session Management
POST   /api/agent-terminal/sessions           - Create agent session
GET    /api/agent-terminal/sessions           - List sessions
GET    /api/agent-terminal/sessions/{id}      - Get session details
DELETE /api/agent-terminal/sessions/{id}      - Close session

# Command Execution
POST   /api/agent-terminal/sessions/{id}/execute  - Execute command
POST   /api/agent-terminal/sessions/{id}/approve  - Approve/deny command

# User Control
POST   /api/agent-terminal/sessions/{id}/interrupt - User takes control
POST   /api/agent-terminal/sessions/{id}/release   - User releases control

# Information
GET    /api/agent-terminal/sessions/{id}/history   - Command history
GET    /api/agent-terminal/sessions/{id}/state     - Current state

Security Features:
-----------------
1. **CVE-003 Fix: No God Mode**
   - All agents subject to RBAC
   - Agent role determines permission level
   - No agent can bypass security checks

2. **CVE-002 Fix: Prompt Injection Protection**
   - Command text validated before execution
   - Risk assessment on every command
   - User approval required for suspicious patterns

3. **Command Risk Assessment**
   - FORBIDDEN: rm -rf /, dd, mkfs, fork bombs
   - HIGH: sudo commands, package installs, system modifications
   - MODERATE: chmod, chown, kill commands
   - SAFE: ls, pwd, cat, grep, etc.

4. **Audit Trail**
   - All commands logged with TerminalLogger
   - Linked to conversation_id for full context
   - Timestamp, risk level, approval status recorded

5. **User Override**
   - User can interrupt agent at any time
   - User can deny dangerous commands
   - User can take direct control of terminal

Request/Response Examples:
-------------------------
# Create Session
POST /api/agent-terminal/sessions
{
  "agent_id": "chat_agent_abc123",
  "agent_role": "chat_agent",
  "conversation_id": "chat_xyz",
  "host": "main"
}
→ {
  "session_id": "agent-session-456",
  "pty_session_id": "pty-789",  # Use this for WebSocket
  "state": "agent_control",
  "created_at": 1704801234.56
}

# Execute Command (Approval Required)
POST /api/agent-terminal/sessions/agent-session-456/execute
{
  "command": "sudo apt install nginx",
  "description": "Install nginx"
}
→ {
  "status": "approval_required",
  "command": "sudo apt install nginx",
  "risk": "high",
  "reasons": ["Requires sudo", "Package installation"],
  "session_id": "agent-session-456"
}

# Approve Command
POST /api/agent-terminal/sessions/agent-session-456/approve
{
  "approved": true,
  "user_id": "user123"
}
→ {
  "status": "approved",
  "command": "sudo apt install nginx",
  "executed": true
}

# User Takeover
POST /api/agent-terminal/sessions/agent-session-456/interrupt
{
  "user_id": "user123"
}
→ {
  "status": "success",
  "previous_state": "agent_control",
  "new_state": "user_control",
  "session_id": "agent-session-456"
}

Integration Points:
------------------
1. **ChatHistoryManager**
   - All terminal output saved to chat history
   - Commands shown as [TERMINAL] messages
   - Complete transcript available

2. **TerminalLogger**
   - Commands logged with metadata
   - Risk level, timestamp, approval status
   - Linked to conversation_id

3. **SecureCommandExecutor**
   - Risk assessment engine
   - Pattern matching for dangerous commands
   - Returns risk level + reasons

4. **CommandApprovalManager**
   - Tracks pending approvals
   - Auto-approval rules (future)
   - Approval history

See Also:
--------
- backend/api/terminal.py - Shared PTY infrastructure
- backend/services/agent_terminal_service.py - Business logic
- docs/architecture/TERMINAL_APPROVAL_WORKFLOW.md - Detailed workflow
- docs/architecture/TERMINAL_ARCHITECTURE_DIAGRAM.md - System architecture
"""

import logging
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.dependencies import get_redis_client
from backend.services.agent_terminal import (
    AgentSessionState,
    AgentTerminalService,
)
from backend.services.command_approval_manager import AgentRole
from backend.services.command_execution_queue import get_command_queue
from src.utils.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/agent-terminal", tags=["agent-terminal"])


# Request/Response Models


class CreateSessionRequest(BaseModel):
    """Request to create agent terminal session"""

    agent_id: str = Field(..., description="Unique identifier for the agent")
    agent_role: str = Field(
        ...,
        description="Role of the agent (chat_agent, automation_agent, system_agent, admin_agent)",
    )
    conversation_id: Optional[str] = Field(
        None, description="Chat conversation ID to link"
    )
    host: str = Field(
        "main",
        description="Target host (main, frontend, npu-worker, redis, ai-stack, browser)",
    )
    metadata: Optional[Dict] = Field(None, description="Additional session metadata")


class ExecuteCommandRequest(BaseModel):
    """Request to execute command in agent session"""

    command: str = Field(..., description="Command to execute")
    description: Optional[str] = Field(
        None, description="Description of what command does"
    )
    force_approval: bool = Field(
        False, description="Force user approval even for safe commands"
    )


class ApproveCommandRequest(BaseModel):
    """Request to approve/deny pending command"""

    approved: bool = Field(..., description="Whether command is approved")
    user_id: Optional[str] = Field(None, description="User who made the decision")
    comment: Optional[str] = Field(
        None, description="Optional comment or reason for the decision"
    )
    auto_approve_future: bool = Field(
        False, description="Auto-approve similar commands in the future"
    )
    # Permission v2: Project memory fields
    remember_for_project: bool = Field(
        False, description="Remember approval for this project"
    )
    project_path: Optional[str] = Field(
        None, description="Project path for approval memory"
    )


class InterruptRequest(BaseModel):
    """Request to interrupt agent and take control"""

    user_id: str = Field(..., description="User requesting control")


# Dependency for AgentTerminalService
# CRITICAL: Use singleton pattern to maintain sessions across requests

_agent_terminal_service_instance: Optional[AgentTerminalService] = None


# Thread-safe lock for singleton
import threading

_agent_terminal_service_lock = threading.Lock()


def get_agent_terminal_service(
    redis_client=Depends(get_redis_client),
) -> AgentTerminalService:
    """
    Get singleton AgentTerminalService instance (thread-safe).

    IMPORTANT: This MUST return the same instance for all requests,
    otherwise sessions will be lost between API calls.
    """
    global _agent_terminal_service_instance

    if _agent_terminal_service_instance is None:
        with _agent_terminal_service_lock:
            # Double-check after acquiring lock
            if _agent_terminal_service_instance is None:
                logger.info("Initializing AgentTerminalService singleton")
                _agent_terminal_service_instance = AgentTerminalService(
                    redis_client=redis_client
                )

    return _agent_terminal_service_instance


# API Endpoints


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_agent_terminal_session",
    error_code_prefix="AGENT_TERMINAL",
)
@router.post("/sessions")
async def create_agent_terminal_session(
    request: CreateSessionRequest,
    service: AgentTerminalService = Depends(get_agent_terminal_service),
):
    """
    Create a new agent terminal session.

    Security:
    - Agent role determines permission level
    - All agents subject to RBAC (no god mode)
    - Session linked to conversation for audit trail
    """
    # Parse agent role
    try:
        agent_role = AgentRole[request.agent_role.upper()]
    except KeyError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid agent_role: {request.agent_role}. "
            f"Must be one of: {[role.name.lower() for role in AgentRole]}",
        )

    # Create session
    session = await service.create_session(
        agent_id=request.agent_id,
        agent_role=agent_role,
        conversation_id=request.conversation_id,
        host=request.host,
        metadata=request.metadata,
    )

    return {
        "status": "created",
        "session_id": session.session_id,
        "agent_id": session.agent_id,
        "agent_role": session.agent_role.value,
        "conversation_id": session.conversation_id,
        "host": session.host,
        "state": session.state.value,
        "created_at": session.created_at,
        "pty_session_id": (
            session.pty_session_id
        ),  # CRITICAL: Frontend needs this for WebSocket connection
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_agent_terminal_sessions",
    error_code_prefix="AGENT_TERMINAL",
)
@router.get("/sessions")
async def list_agent_terminal_sessions(
    agent_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    service: AgentTerminalService = Depends(get_agent_terminal_service),
):
    """
    List agent terminal sessions.

    Query parameters:
    - agent_id: Filter by agent ID
    - conversation_id: Filter by conversation ID
    """
    sessions = await service.list_sessions(
        agent_id=agent_id,
        conversation_id=conversation_id,
    )

    return {
        "status": "success",
        "total": len(sessions),
        "sessions": [
            {
                "session_id": s.session_id,
                "agent_id": s.agent_id,
                "agent_role": s.agent_role.value,
                "conversation_id": s.conversation_id,
                "host": s.host,
                "state": s.state.value,
                "created_at": s.created_at,
                "last_activity": s.last_activity,
                "command_count": len(s.command_history),
                "pty_session_id": (
                    s.pty_session_id
                ),  # CRITICAL: Frontend needs this for WebSocket connection
            }
            for s in sessions
        ],
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_agent_terminal_session",
    error_code_prefix="AGENT_TERMINAL",
)
@router.get("/sessions/{session_id}")
async def get_agent_terminal_session(
    session_id: str,
    service: AgentTerminalService = Depends(get_agent_terminal_service),
):
    """
    Get detailed information about an agent terminal session.
    """
    session_info = await service.get_session_info(session_id)

    if not session_info:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "status": "success",
        **session_info,
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delete_agent_terminal_session",
    error_code_prefix="AGENT_TERMINAL",
)
@router.delete("/sessions/{session_id}")
async def delete_agent_terminal_session(
    session_id: str,
    service: AgentTerminalService = Depends(get_agent_terminal_service),
):
    """
    Delete (close) an agent terminal session.
    """
    success = await service.close_session(session_id)

    if not success:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "status": "deleted",
        "session_id": session_id,
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="execute_agent_command",
    error_code_prefix="AGENT_TERMINAL",
)
@router.post("/execute")
async def execute_agent_command(
    session_id: str,
    request: ExecuteCommandRequest,
    service: AgentTerminalService = Depends(get_agent_terminal_service),
):
    """
    Execute a command in an agent terminal session.

    Security workflow:
    1. Validate session and agent permissions
    2. Assess command risk (SecureCommandExecutor)
    3. Check if approval is needed based on agent role and risk level
    4. Return pending approval or execute immediately (for safe auto-approved commands)

    Returns:
    - status: "success" (executed), "pending_approval" (needs approval), or "error"
    - If pending_approval: includes approval details
    - If success: includes command execution result
    """
    result = await service.execute_command(
        session_id=session_id,
        command=request.command,
        description=request.description,
        force_approval=request.force_approval,
    )

    return result


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="approve_agent_command",
    error_code_prefix="AGENT_TERMINAL",
)
@router.post("/sessions/{session_id}/approve")
async def approve_agent_command(
    session_id: str,
    request: ApproveCommandRequest,
    service: AgentTerminalService = Depends(get_agent_terminal_service),
):
    """
    Approve or deny a pending agent command.

    User approves HIGH/DANGEROUS commands that agents want to execute.
    """
    logger.info(
        f"[API] Approval request received: session_id={session_id}, approved={request.approved}, "
        f"user_id={request.user_id}, comment={request.comment}, "
        f"remember_for_project={request.remember_for_project}"
    )

    result = await service.approve_command(
        session_id=session_id,
        approved=request.approved,
        user_id=request.user_id,
        comment=request.comment,
        auto_approve_future=request.auto_approve_future,
        remember_for_project=request.remember_for_project,
        project_path=request.project_path,
    )

    logger.info(
        f"[API] Approval result: {result.get('status')}, error={result.get('error')}"
    )
    return result


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="interrupt_agent_session",
    error_code_prefix="AGENT_TERMINAL",
)
@router.post("/sessions/{session_id}/interrupt")
async def interrupt_agent_session(
    session_id: str,
    request: InterruptRequest,
    service: AgentTerminalService = Depends(get_agent_terminal_service),
):
    """
    User interrupt - Take control from agent.

    Allows user to:
    - Stop agent command execution
    - Review pending commands
    - Execute own commands
    - Deny pending agent commands
    """
    result = await service.user_interrupt(
        session_id=session_id,
        user_id=request.user_id,
    )

    return result


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="resume_agent_session",
    error_code_prefix="AGENT_TERMINAL",
)
@router.post("/sessions/{session_id}/resume")
async def resume_agent_session(
    session_id: str,
    service: AgentTerminalService = Depends(get_agent_terminal_service),
):
    """
    Resume agent control after user interrupt.

    Allows agent to continue executing commands after user returns control.
    """
    result = await service.agent_resume(session_id=session_id)
    return result


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_command_state",
    error_code_prefix="AGENT_TERMINAL",
)
@router.get("/commands/{command_id}")
async def get_command_state(command_id: str):
    """
    Get command state and output from the command execution queue.

    This endpoint enables event-driven polling for command state changes.
    Frontend polls this endpoint to check if a command has completed and
    to retrieve its output.

    Args:
        command_id: Unique identifier for the command

    Returns:
        Command state, output, and metadata

    Raises:
        HTTPException 404: Command not found in queue

    Example Response:
        {
            "command_id": "abc-123-def",
            "command": "whoami",
            "state": "completed",
            "output": "kali",
            "stderr": "",
            "return_code": 0,
            "requested_at": 1699564800.123,
            "execution_completed_at": 1699564802.456
        }
    """
    # Get command queue singleton
    queue = get_command_queue()

    # Retrieve command from queue
    command = await queue.get_command(command_id)

    if not command:
        raise HTTPException(
            status_code=404, detail=f"Command {command_id} not found in queue"
        )

    # Return command state and output
    return {
        "command_id": command.command_id,
        "terminal_session_id": command.terminal_session_id,
        "chat_id": command.chat_id,
        "command": command.command,
        "purpose": command.purpose,
        "state": command.state.value,
        "output": command.output,
        "stderr": command.stderr,
        "return_code": command.return_code,
        "risk_level": command.risk_level.value,
        "risk_reasons": command.risk_reasons,
        "requested_at": command.requested_at,
        "approved_at": command.approved_at,
        "execution_started_at": command.execution_started_at,
        "execution_completed_at": command.execution_completed_at,
        "approved_by_user_id": command.approved_by_user_id,
        "approval_comment": command.approval_comment,
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="agent_terminal_info",
    error_code_prefix="AGENT_TERMINAL",
)
@router.get("/")
async def agent_terminal_info():
    """
    Get information about the Agent Terminal API.
    """
    return {
        "name": "Agent Terminal API",
        "version": "1.0.0",
        "description": (
            "Secure terminal access for AI agents with approval workflow and user control"
        ),
        "features": [
            "Agent session management",
            "Command execution with risk assessment",
            "User approval workflow for HIGH/DANGEROUS commands",
            "User interrupt/takeover mechanism",
            "RBAC enforcement (CVE-003 fix)",
            "Prompt injection protection (CVE-002 fix)",
            "Comprehensive audit logging",
        ],
        "agent_roles": [role.value for role in AgentRole],
        "session_states": [state.value for state in AgentSessionState],
        "endpoints": {
            "create_session": "POST /api/agent-terminal/sessions",
            "list_sessions": "GET /api/agent-terminal/sessions",
            "get_session": "GET /api/agent-terminal/sessions/{session_id}",
            "delete_session": "DELETE /api/agent-terminal/sessions/{session_id}",
            "execute_command": (
                "POST /api/agent-terminal/execute?session_id={session_id}"
            ),
            "approve_command": "POST /api/agent-terminal/sessions/{session_id}/approve",
            "get_command_state": "GET /api/agent-terminal/commands/{command_id}",
            "interrupt": "POST /api/agent-terminal/sessions/{session_id}/interrupt",
            "resume": "POST /api/agent-terminal/sessions/{session_id}/resume",
        },
        "security_features": {
            "cve_002_fix": "Prompt injection detection and prevention",
            "cve_003_fix": "No god mode - all agents subject to RBAC",
            "risk_assessment": "Commands classified as SAFE/MODERATE/HIGH/DANGEROUS",
            "approval_workflow": "HIGH/DANGEROUS commands require user approval",
            "user_control": "Users can interrupt and take control at any time",
        },
    }
