"""
Agent Terminal API

REST API for agent terminal access with security controls and approval workflow.

Security Features:
- Integration with SecureCommandExecutor
- Command risk assessment and approval workflow
- User interrupt/takeover mechanism
- Comprehensive audit logging
- RBAC enforcement (CVE-003 fix)
- Prompt injection protection (CVE-002 fix)
"""

import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.dependencies import get_redis_client
from backend.services.agent_terminal_service import (
    AgentRole,
    AgentSessionState,
    AgentTerminalService,
)
from src.constants.network_constants import NetworkConstants
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


class InterruptRequest(BaseModel):
    """Request to interrupt agent and take control"""

    user_id: str = Field(..., description="User requesting control")


# Dependency for AgentTerminalService
# CRITICAL: Use singleton pattern to maintain sessions across requests

_agent_terminal_service_instance: Optional[AgentTerminalService] = None


def get_agent_terminal_service(
    redis_client=Depends(get_redis_client),
) -> AgentTerminalService:
    """
    Get singleton AgentTerminalService instance.

    IMPORTANT: This MUST return the same instance for all requests,
    otherwise sessions will be lost between API calls.
    """
    global _agent_terminal_service_instance

    if _agent_terminal_service_instance is None:
        logger.info("Initializing AgentTerminalService singleton")
        _agent_terminal_service_instance = AgentTerminalService(
            redis_client=redis_client
        )

    return _agent_terminal_service_instance


# API Endpoints


@router.post("/sessions")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_agent_terminal_session",
    error_code_prefix="AGENT_TERMINAL",
)
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
        "pty_session_id": session.pty_session_id,  # CRITICAL: Frontend needs this for WebSocket connection
    }


@router.get("/sessions")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_agent_terminal_sessions",
    error_code_prefix="AGENT_TERMINAL",
)
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
                "pty_session_id": s.pty_session_id,  # CRITICAL: Frontend needs this for WebSocket connection
            }
            for s in sessions
        ],
    }


@router.get("/sessions/{session_id}")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_agent_terminal_session",
    error_code_prefix="AGENT_TERMINAL",
)
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


@router.delete("/sessions/{session_id}")
async def delete_agent_terminal_session(
    session_id: str,
    service: AgentTerminalService = Depends(get_agent_terminal_service),
):
    """
    Delete (close) an agent terminal session.
    """
    try:
        success = await service.close_session(session_id)

        if not success:
            raise HTTPException(status_code=404, detail="Session not found")

        return {
            "status": "deleted",
            "session_id": session_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting agent terminal session: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


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
    try:
        result = await service.execute_command(
            session_id=session_id,
            command=request.command,
            description=request.description,
            force_approval=request.force_approval,
        )

        return result

    except Exception as e:
        logger.error(f"Error executing agent command: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


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
    try:
        logger.info(
            f"[API] Approval request received: session_id={session_id}, approved={request.approved}, user_id={request.user_id}, comment={request.comment}"
        )

        result = await service.approve_command(
            session_id=session_id,
            approved=request.approved,
            user_id=request.user_id,
            comment=request.comment,
            auto_approve_future=request.auto_approve_future,
        )

        logger.info(
            f"[API] Approval result: {result.get('status')}, error={result.get('error')}"
        )
        return result

    except Exception as e:
        logger.error(f"Error approving agent command: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


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
    try:
        result = await service.user_interrupt(
            session_id=session_id,
            user_id=request.user_id,
        )

        return result

    except Exception as e:
        logger.error(f"Error interrupting agent session: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/resume")
async def resume_agent_session(
    session_id: str,
    service: AgentTerminalService = Depends(get_agent_terminal_service),
):
    """
    Resume agent control after user interrupt.

    Allows agent to continue executing commands after user returns control.
    """
    try:
        result = await service.agent_resume(session_id=session_id)

        return result

    except Exception as e:
        logger.error(f"Error resuming agent session: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/")
async def agent_terminal_info():
    """
    Get information about the Agent Terminal API.
    """
    return {
        "name": "Agent Terminal API",
        "version": "1.0.0",
        "description": "Secure terminal access for AI agents with approval workflow and user control",
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
            "execute_command": "POST /api/agent-terminal/execute?session_id={session_id}",
            "approve_command": "POST /api/agent-terminal/sessions/{session_id}/approve",
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
