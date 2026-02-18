# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Permissions API - Claude Code-Style Permission System Management

Provides REST API endpoints for managing the permission system:
- Get/Set permission mode
- List/Add/Remove permission rules
- View/Clear project approval memory
- Get permission system status

This API enables frontend components to configure and manage
the Claude Code-style permission system.

Usage:
    GET  /api/permissions/mode          - Get current mode
    PUT  /api/permissions/mode          - Set mode
    GET  /api/permissions/rules         - List all rules
    POST /api/permissions/rules         - Add a new rule
    DELETE /api/permissions/rules       - Remove a rule
    GET  /api/permissions/memory/{path} - Get project approvals
    DELETE /api/permissions/memory/{path} - Clear project approvals
    GET  /api/permissions/status        - Get system status
"""

import logging
from typing import List, Optional

from auth_middleware import check_admin_permission
from backend.services.approval_memory import get_approval_memory
from backend.services.permission_matcher import get_permission_matcher
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from autobot_shared.ssot_config import PermissionAction, PermissionMode, config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/permissions", tags=["permissions"])


# =============================================================================
# Request/Response Models
# =============================================================================


class PermissionModeResponse(BaseModel):
    """Response model for permission mode."""

    mode: str
    enabled: bool
    is_admin_only: bool
    allowed_modes: List[str]


class PermissionModeRequest(BaseModel):
    """Request model for setting permission mode."""

    mode: str = Field(..., description="Permission mode to set")


class PermissionRuleResponse(BaseModel):
    """Response model for a single rule."""

    tool: str
    pattern: str
    action: str
    description: str


class PermissionRulesResponse(BaseModel):
    """Response model for all rules."""

    allow: List[PermissionRuleResponse]
    ask: List[PermissionRuleResponse]
    deny: List[PermissionRuleResponse]


class AddRuleRequest(BaseModel):
    """Request model for adding a rule."""

    tool: str = Field(default="Bash", description="Tool name")
    pattern: str = Field(..., description="Glob pattern")
    action: str = Field(..., description="allow, ask, or deny")
    description: str = Field(default="", description="Rule description")


class RemoveRuleRequest(BaseModel):
    """Request model for removing a rule."""

    tool: str = Field(default="Bash", description="Tool name")
    pattern: str = Field(..., description="Pattern to remove")


class ApprovalRecordResponse(BaseModel):
    """Response model for an approval record."""

    pattern: str
    tool: str
    risk_level: str
    user_id: str
    created_at: float
    original_command: str
    comment: Optional[str] = None


class ProjectApprovalsResponse(BaseModel):
    """Response model for project approvals."""

    project_path: str
    approvals: List[ApprovalRecordResponse]


class PermissionStatusResponse(BaseModel):
    """Response model for permission system status."""

    enabled: bool
    mode: str
    approval_memory_enabled: bool
    approval_memory_ttl_days: int
    rules_file: str
    rules_count: dict


class CheckCommandRequest(BaseModel):
    """Request model for checking a command."""

    command: str = Field(..., description="Command to check")
    tool: str = Field(default="Bash", description="Tool name")


class CheckCommandResponse(BaseModel):
    """Response model for command check."""

    result: str  # allow, ask, deny, default
    pattern: Optional[str] = None
    description: Optional[str] = None


# =============================================================================
# API Endpoints
# =============================================================================


@router.get("/status", response_model=PermissionStatusResponse)
async def get_permission_status(admin_check: bool = Depends(check_admin_permission)):
    """
    Get permission system status.

    Returns current configuration and statistics.

    Issue #744: Requires admin authentication.
    """
    try:
        matcher = get_permission_matcher()
        rules = matcher.get_all_rules()

        return PermissionStatusResponse(
            enabled=config.permission.enabled,
            mode=config.permission.mode.value,
            approval_memory_enabled=config.permission.approval_memory_enabled,
            approval_memory_ttl_days=config.permission.approval_memory_ttl // 86400,
            rules_file=config.permission.rules_file,
            rules_count={
                "allow": len(rules["allow"]),
                "ask": len(rules["ask"]),
                "deny": len(rules["deny"]),
                "total": len(rules["allow"]) + len(rules["ask"]) + len(rules["deny"]),
            },
        )
    except Exception as e:
        logger.error(f"Failed to get permission status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/mode", response_model=PermissionModeResponse)
async def get_permission_mode(
    admin_check: bool = Depends(check_admin_permission),
    is_admin: bool = Query(default=False),
):
    """
    Get current permission mode.

    Args:
        is_admin: Whether user has admin privileges (affects allowed modes)

    Issue #744: Requires admin authentication.
    """
    try:
        matcher = get_permission_matcher(is_admin=is_admin)
        allowed_modes = [m.value for m in matcher.get_allowed_modes()]

        return PermissionModeResponse(
            mode=matcher.get_mode().value,
            enabled=config.permission.enabled,
            is_admin_only=config.permission.is_admin_only_mode(matcher.get_mode()),
            allowed_modes=allowed_modes,
        )
    except Exception as e:
        logger.error(f"Failed to get permission mode: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/mode", response_model=PermissionModeResponse)
async def set_permission_mode(
    request: PermissionModeRequest,
    admin_check: bool = Depends(check_admin_permission),
    is_admin: bool = Query(default=False),
):
    """
    Set permission mode.

    Args:
        request: New mode to set
        is_admin: Whether user has admin privileges

    Issue #744: Requires admin authentication.
    """
    try:
        # Validate mode
        try:
            new_mode = PermissionMode(request.mode)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid mode: {request.mode}. "
                f"Valid modes: {[m.value for m in PermissionMode]}",
            )

        # Check admin requirement
        if config.permission.is_admin_only_mode(new_mode) and not is_admin:
            raise HTTPException(
                status_code=403,
                detail=f"Mode '{new_mode.value}' requires admin privileges",
            )

        matcher = get_permission_matcher(is_admin=is_admin)
        if not matcher.set_mode(new_mode):
            raise HTTPException(
                status_code=403,
                detail="Failed to set mode - permission denied",
            )

        allowed_modes = [m.value for m in matcher.get_allowed_modes()]

        return PermissionModeResponse(
            mode=matcher.get_mode().value,
            enabled=config.permission.enabled,
            is_admin_only=config.permission.is_admin_only_mode(matcher.get_mode()),
            allowed_modes=allowed_modes,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to set permission mode: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rules", response_model=PermissionRulesResponse)
async def get_permission_rules(admin_check: bool = Depends(check_admin_permission)):
    """
    Get all permission rules.

    Issue #744: Requires admin authentication.
    """
    try:
        matcher = get_permission_matcher()
        rules = matcher.get_all_rules()

        return PermissionRulesResponse(
            allow=[
                PermissionRuleResponse(
                    tool=r["tool"],
                    pattern=r["pattern"],
                    action="allow",
                    description=r["description"],
                )
                for r in rules["allow"]
            ],
            ask=[
                PermissionRuleResponse(
                    tool=r["tool"],
                    pattern=r["pattern"],
                    action="ask",
                    description=r["description"],
                )
                for r in rules["ask"]
            ],
            deny=[
                PermissionRuleResponse(
                    tool=r["tool"],
                    pattern=r["pattern"],
                    action="deny",
                    description=r["description"],
                )
                for r in rules["deny"]
            ],
        )
    except Exception as e:
        logger.error(f"Failed to get permission rules: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rules")
async def add_permission_rule(
    request: AddRuleRequest,
    admin_check: bool = Depends(check_admin_permission),
    is_admin: bool = Query(default=False),
):
    """
    Add a new permission rule.

    Note: Adding ALLOW rules requires admin privileges.

    Issue #744: Requires admin authentication.
    """
    try:
        # Validate action
        try:
            action = PermissionAction(request.action)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid action: {request.action}. "
                f"Valid actions: {[a.value for a in PermissionAction]}",
            )

        matcher = get_permission_matcher(is_admin=is_admin)

        if not matcher.add_rule(
            tool=request.tool,
            pattern=request.pattern,
            action=action,
            description=request.description,
        ):
            raise HTTPException(
                status_code=403,
                detail="Failed to add rule - permission denied (ALLOW rules require admin)",
            )

        return {
            "status": "success",
            "message": f"Added {action.value} rule: {request.tool}({request.pattern})",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to add permission rule: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/rules")
async def remove_permission_rule(
    request: RemoveRuleRequest, admin_check: bool = Depends(check_admin_permission)
):
    """
    Remove a permission rule.

    Issue #744: Requires admin authentication.
    """
    try:
        matcher = get_permission_matcher()

        if not matcher.remove_rule(request.tool, request.pattern):
            raise HTTPException(
                status_code=404,
                detail=f"Rule not found: {request.tool}({request.pattern})",
            )

        return {
            "status": "success",
            "message": f"Removed rule: {request.tool}({request.pattern})",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to remove permission rule: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/check", response_model=CheckCommandResponse)
async def check_command(
    request: CheckCommandRequest,
    admin_check: bool = Depends(check_admin_permission),
    is_admin: bool = Query(default=False),
):
    """
    Check what action would be taken for a command.

    Useful for previewing permission decisions without executing.

    Issue #744: Requires admin authentication.
    """
    try:
        matcher = get_permission_matcher(is_admin=is_admin)
        result, rule = matcher.match(request.tool, request.command)

        return CheckCommandResponse(
            result=result.value,
            pattern=rule.pattern if rule else None,
            description=rule.description if rule else None,
        )
    except Exception as e:
        logger.error(f"Failed to check command: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/memory/{project_path:path}", response_model=ProjectApprovalsResponse)
async def get_project_approvals(
    project_path: str,
    admin_check: bool = Depends(check_admin_permission),
    user_id: str = Query(..., description="User ID"),
):
    """
    Get stored approvals for a project.

    Issue #744: Requires admin authentication.
    """
    try:
        memory = get_approval_memory()
        records = await memory.get_project_approvals(project_path, user_id)

        return ProjectApprovalsResponse(
            project_path=project_path,
            approvals=[
                ApprovalRecordResponse(
                    pattern=r.pattern,
                    tool=r.tool,
                    risk_level=r.risk_level,
                    user_id=r.user_id,
                    created_at=r.created_at,
                    original_command=r.original_command,
                    comment=r.comment,
                )
                for r in records
            ],
        )
    except Exception as e:
        logger.error(f"Failed to get project approvals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/memory/{project_path:path}")
async def clear_project_approvals(
    project_path: str,
    admin_check: bool = Depends(check_admin_permission),
    user_id: Optional[str] = Query(default=None, description="User ID (optional)"),
):
    """
    Clear stored approvals for a project.

    If user_id is provided, only clears that user's approvals.
    Otherwise, clears all approvals for the project.

    Issue #744: Requires admin authentication.
    """
    try:
        memory = get_approval_memory()
        success = await memory.clear_project_approvals(project_path, user_id)

        if not success:
            raise HTTPException(
                status_code=500,
                detail="Failed to clear approvals",
            )

        return {
            "status": "success",
            "message": f"Cleared approvals for project: {project_path}"
            + (f" (user: {user_id})" if user_id else " (all users)"),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to clear project approvals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/memory")
async def store_approval(
    admin_check: bool = Depends(check_admin_permission),
    project_path: str = Query(..., description="Project path"),
    user_id: str = Query(..., description="User ID"),
    command: str = Query(..., description="Approved command"),
    risk_level: str = Query(..., description="Risk level"),
    tool: str = Query(default="Bash", description="Tool name"),
    comment: Optional[str] = Query(default=None, description="Approval comment"),
):
    """
    Store a command approval in memory.

    Issue #744: Requires admin authentication.
    """
    try:
        memory = get_approval_memory()
        success = await memory.remember_approval(
            project_path=project_path,
            command=command,
            user_id=user_id,
            risk_level=risk_level,
            tool=tool,
            comment=comment,
        )

        if not success:
            raise HTTPException(
                status_code=500,
                detail="Failed to store approval",
            )

        return {
            "status": "success",
            "message": "Approval stored",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to store approval: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/memory/stats")
async def get_memory_stats(admin_check: bool = Depends(check_admin_permission)):
    """
    Get approval memory statistics.

    Issue #744: Requires admin authentication.
    """
    try:
        memory = get_approval_memory()
        stats = await memory.get_memory_stats()
        return stats
    except Exception as e:
        logger.error(f"Failed to get memory stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
