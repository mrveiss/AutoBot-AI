# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Security API endpoints for command approval and audit
"""

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from src.constants.network_constants import NetworkConstants
from src.enhanced_security_layer import EnhancedSecurityLayer
from src.utils.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)
router = APIRouter()


class CommandApprovalRequest(BaseModel):
    command_id: str
    approved: bool


class CommandApprovalResponse(BaseModel):
    success: bool
    message: str


class SecurityStatusResponse(BaseModel):
    security_enabled: bool
    command_security_enabled: bool
    docker_sandbox_enabled: bool
    pending_approvals: List[Dict[str, Any]]


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_security_status",
    error_code_prefix="SECURITY",
)
@router.get("/status", response_model=SecurityStatusResponse)
async def get_security_status(request: Request):
    """Get current security configuration and status"""
    try:
        # Try to get enhanced security layer, fall back to basic security layer
        enhanced_security = getattr(request.app.state, "enhanced_security_layer", None)
        basic_security = getattr(request.app.state, "security_layer", None)

        if enhanced_security:
            pending_approvals = enhanced_security.get_pending_approvals()
            return SecurityStatusResponse(
                security_enabled=enhanced_security.enable_auth,
                command_security_enabled=enhanced_security.enable_command_security,
                docker_sandbox_enabled=enhanced_security.use_docker_sandbox,
                pending_approvals=pending_approvals,
            )
        elif basic_security:
            # Fallback to basic security layer
            return SecurityStatusResponse(
                security_enabled=basic_security.enable_auth,
                command_security_enabled=False,  # Not available in basic layer
                docker_sandbox_enabled=False,  # Not available in basic layer
                pending_approvals=[],  # Not available in basic layer
            )
        else:
            # No security layer found - initialize enhanced security layer on demand
            enhanced_security = EnhancedSecurityLayer()
            request.app.state.enhanced_security_layer = enhanced_security

            pending_approvals = enhanced_security.get_pending_approvals()
            return SecurityStatusResponse(
                security_enabled=enhanced_security.enable_auth,
                command_security_enabled=enhanced_security.enable_command_security,
                docker_sandbox_enabled=enhanced_security.use_docker_sandbox,
                pending_approvals=pending_approvals,
            )
    except Exception as e:
        logger.error(f"Error getting security status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="approve_command",
    error_code_prefix="SECURITY",
)
@router.post("/approve-command", response_model=CommandApprovalResponse)
async def approve_command(request: Request, approval: CommandApprovalRequest):
    """Approve or deny a pending command execution"""
    try:
        # Get or initialize enhanced security layer
        security_layer = getattr(request.app.state, "enhanced_security_layer", None)
        if not security_layer:
            security_layer = EnhancedSecurityLayer()
            request.app.state.enhanced_security_layer = security_layer

        # Approve or deny the command
        security_layer.approve_command(approval.command_id, approval.approved)

        action = "approved" if approval.approved else "denied"
        message = f"Command {approval.command_id} {action}"

        logger.info(message)

        return CommandApprovalResponse(success=True, message=message)
    except Exception as e:
        logger.error(f"Error approving command: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_pending_approvals",
    error_code_prefix="SECURITY",
)
@router.get("/pending-approvals")
async def get_pending_approvals(request: Request):
    """Get list of commands waiting for approval"""
    try:
        # Get or initialize enhanced security layer
        security_layer = getattr(request.app.state, "enhanced_security_layer", None)
        if not security_layer:
            security_layer = EnhancedSecurityLayer()
            request.app.state.enhanced_security_layer = security_layer
        pending = security_layer.get_pending_approvals()

        return {"success": True, "pending_approvals": pending, "count": len(pending)}
    except Exception as e:
        logger.error(f"Error getting pending approvals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_command_history",
    error_code_prefix="SECURITY",
)
@router.get("/command-history")
async def get_command_history(request: Request, user: str = None, limit: int = 50):
    """Get command execution history from audit log"""
    try:
        # Get or initialize enhanced security layer
        security_layer = getattr(request.app.state, "enhanced_security_layer", None)
        if not security_layer:
            security_layer = EnhancedSecurityLayer()
            request.app.state.enhanced_security_layer = security_layer
        history = security_layer.get_command_history(user=user, limit=limit)

        return {"success": True, "command_history": history, "count": len(history)}
    except Exception as e:
        logger.error(f"Error getting command history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_audit_log",
    error_code_prefix="SECURITY",
)
@router.get("/audit-log")
async def get_audit_log(request: Request, limit: int = 100):
    """Get recent audit log entries"""
    try:
        # Get or initialize enhanced security layer
        security_layer = getattr(request.app.state, "enhanced_security_layer", None)
        if not security_layer:
            security_layer = EnhancedSecurityLayer()
            request.app.state.enhanced_security_layer = security_layer

        # Read audit log file
        audit_entries = []
        try:
            with open(security_layer.audit_log_file, "r") as f:
                lines = f.readlines()

            # Parse JSON entries
            import json

            for line in lines[-limit:]:
                try:
                    entry = json.loads(line.strip())
                    audit_entries.append(entry)
                except json.JSONDecodeError:
                    continue

        except FileNotFoundError:
            audit_entries = []

        return {
            "success": True,
            "audit_entries": audit_entries,
            "count": len(audit_entries),
        }
    except Exception as e:
        logger.error(f"Error getting audit log: {e}")
        raise HTTPException(status_code=500, detail=str(e))
