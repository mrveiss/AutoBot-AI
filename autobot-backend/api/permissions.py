# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
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

from fastapi import APIRouter, Depends, HTTPException, Query

from api.schemas_system import (
    ApprovalRecordResponse,
    CheckCommandRequest,
    CheckCommandResponse,
    PermissionAddRuleRequest,
    PermissionClearApprovalsResponse,
    PermissionMemoryStatsResponse,
    PermissionModeRequest,
    PermissionModeResponse,
    PermissionRemoveRuleRequest,
    PermissionRuleMutateResponse,
    PermissionRuleResponse,
    PermissionRulesResponse,
    PermissionStatusResponse,
    PermissionStoreApprovalResponse,
    ProjectApprovalsResponse,
)
from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import PermissionAction, PermissionMode, config
from services.approval_memory import get_approval_memory
from services.permission_matcher import get_permission_matcher

logger = get_logger(__name__)

router = APIRouter(prefix="/permissions", tags=["permissions"])


# =============================================================================
# API Endpoints
# =============================================================================


@router.get("/status", response_model=PermissionStatusResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_permission_status",
    error_code_prefix="PERMISSIONS",
)
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
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/mode", response_model=PermissionModeResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_permission_mode",
    error_code_prefix="PERMISSIONS",
)
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
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/mode", response_model=PermissionModeResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="set_permission_mode",
    error_code_prefix="PERMISSIONS",
)
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
                detail=f"Invalid mode: {request.mode}. " f"Valid modes: {[m.value for m in PermissionMode]}",
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
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/rules", response_model=PermissionRulesResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_permission_rules",
    error_code_prefix="PERMISSIONS",
)
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
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/rules", response_model=PermissionRuleMutateResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="add_permission_rule",
    error_code_prefix="PERMISSIONS",
)
async def add_permission_rule(
    request: PermissionAddRuleRequest,
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
                detail=f"Invalid action: {request.action}. " f"Valid actions: {[a.value for a in PermissionAction]}",
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
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/rules", response_model=PermissionRuleMutateResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="remove_permission_rule",
    error_code_prefix="PERMISSIONS",
)
async def remove_permission_rule(
    request: PermissionRemoveRuleRequest, admin_check: bool = Depends(check_admin_permission)
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
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/check", response_model=CheckCommandResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="check_command",
    error_code_prefix="PERMISSIONS",
)
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
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/memory/{project_path:path}", response_model=ProjectApprovalsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_project_approvals",
    error_code_prefix="PERMISSIONS",
)
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
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/memory/{project_path:path}", response_model=PermissionClearApprovalsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="clear_project_approvals",
    error_code_prefix="PERMISSIONS",
)
async def clear_project_approvals(
    project_path: str,
    admin_check: bool = Depends(check_admin_permission),
    user_id: str | None = Query(default=None, description="User ID (optional)"),
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
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/memory", response_model=PermissionStoreApprovalResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="store_approval",
    error_code_prefix="PERMISSIONS",
)
async def store_approval(
    admin_check: bool = Depends(check_admin_permission),
    project_path: str = Query(..., description="Project path"),
    user_id: str = Query(..., description="User ID"),
    command: str = Query(..., description="Approved command"),
    risk_level: str = Query(..., description="Risk level"),
    tool: str = Query(default="Bash", description="Tool name"),
    comment: str | None = Query(default=None, description="Approval comment"),
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
    except Exception:
        logger.error("Failed to store approval")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/memory/stats", response_model=PermissionMemoryStatsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_memory_stats",
    error_code_prefix="PERMISSIONS",
)
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
        raise HTTPException(status_code=500, detail="Internal server error")
