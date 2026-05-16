# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Workflow Permissions & Audit Log API (#2152)

Endpoints for per-workflow RBAC management and audit trail retrieval.

Routes:
  GET    /api/workflows/{workflow_id}/permissions         — list permissions
  PUT    /api/workflows/{workflow_id}/permissions         — grant / update role
  DELETE /api/workflows/{workflow_id}/permissions/{user_id} — revoke access
  GET    /api/workflows/{workflow_id}/audit               — view audit log
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas_workflows import (
    GrantPermissionRequest,
    WorkflowAuditLogEntry,
    WorkflowPermissionResponse,
)
from api.user_management.dependencies import get_db_session
from auth_middleware import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from services.workflow_permission_service import (
    ROLE_HIERARCHY,
    WorkflowPermissionService,
)
from services.workflow_rbac import require_workflow_permission

logger = get_logger(__name__)

router = APIRouter(tags=["workflow-permissions"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _current_user_id(current_user: dict) -> str:
    """Extract a stable user identifier from the current user dict."""
    return current_user.get("username") or current_user.get("user_id", "unknown")


def _permission_to_response(perm) -> WorkflowPermissionResponse:
    """Convert a WorkflowPermission ORM row to its response schema."""
    return WorkflowPermissionResponse(
        workflow_id=perm.workflow_id,
        user_id=perm.user_id,
        role=perm.role,
        granted_by=perm.granted_by,
        created_at=perm.created_at.isoformat() if perm.created_at else "",
        updated_at=perm.updated_at.isoformat() if perm.updated_at else "",
    )


def _audit_to_response(entry) -> WorkflowAuditLogEntry:
    """Convert a WorkflowAuditLog ORM row to its response schema."""
    return WorkflowAuditLogEntry(
        id=str(entry.id),
        timestamp=entry.timestamp.isoformat() if entry.timestamp else "",
        user_id=entry.user_id,
        workflow_id=entry.workflow_id,
        action=entry.action,
        details=entry.details,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/workflows/{workflow_id}/permissions",
    response_model=List[WorkflowPermissionResponse],
    summary="List workflow permissions",
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_workflow_permissions",
    error_code_prefix="WORKFLOW_PERMISSIONS",
)
async def list_workflow_permissions(
    workflow_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    _: bool = Depends(require_workflow_permission("view")),
) -> List[WorkflowPermissionResponse]:
    """Return all permission entries for the specified workflow (#2152)."""
    svc = WorkflowPermissionService(session)
    rows = await svc.get_permissions(workflow_id)
    await svc.log_action(
        user_id=_current_user_id(current_user),
        workflow_id=workflow_id,
        action="view",
        details={"endpoint": "list_permissions"},
    )
    return [_permission_to_response(r) for r in rows]


@router.put(
    "/workflows/{workflow_id}/permissions",
    response_model=WorkflowPermissionResponse,
    summary="Grant or update a workflow permission",
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="grant_workflow_permission",
    error_code_prefix="WORKFLOW_PERMISSIONS",
)
async def grant_workflow_permission(
    workflow_id: str,
    body: GrantPermissionRequest,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    _: bool = Depends(require_workflow_permission("grant")),
) -> WorkflowPermissionResponse:
    """
    Grant (or update) a role for *body.user_id* on the workflow (#2152).

    Only owners and admins may call this endpoint.
    """
    if body.role not in ROLE_HIERARCHY:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid role '{body.role}'. Valid roles: {ROLE_HIERARCHY}",
        )

    actor = _current_user_id(current_user)
    svc = WorkflowPermissionService(session)
    perm = await svc.grant_permission(
        workflow_id=workflow_id,
        user_id=body.user_id,
        role=body.role,
        granted_by=actor,
    )
    await svc.log_action(
        user_id=actor,
        workflow_id=workflow_id,
        action="grant",
        details={"target_user": body.user_id, "role": body.role},
    )
    return _permission_to_response(perm)


@router.delete(
    "/workflows/{workflow_id}/permissions/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a workflow permission",
    response_model=None,
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="revoke_workflow_permission",
    error_code_prefix="WORKFLOW_PERMISSIONS",
)
async def revoke_workflow_permission(
    workflow_id: str,
    user_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    _: bool = Depends(require_workflow_permission("revoke")),
) -> None:
    """
    Remove *user_id*'s permission entry for the workflow (#2152).

    Only owners and admins may call this endpoint.
    """
    actor = _current_user_id(current_user)
    svc = WorkflowPermissionService(session)
    deleted = await svc.revoke_permission(
        workflow_id=workflow_id,
        user_id=user_id,
        revoked_by=actor,
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No permission entry for user '{user_id}' on workflow '{workflow_id}'",
        )
    await svc.log_action(
        user_id=actor,
        workflow_id=workflow_id,
        action="revoke",
        details={"target_user": user_id},
    )


@router.get(
    "/workflows/{workflow_id}/audit",
    response_model=List[WorkflowAuditLogEntry],
    summary="Get workflow audit log",
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_workflow_audit_log",
    error_code_prefix="WORKFLOW_PERMISSIONS",
)
async def get_workflow_audit_log(
    workflow_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    _: bool = Depends(require_workflow_permission("view")),
) -> List[WorkflowAuditLogEntry]:
    """Return the audit trail for the specified workflow, newest first (#2152)."""
    svc = WorkflowPermissionService(session)
    entries = await svc.get_audit_log(workflow_id, limit=limit, offset=offset)
    return [_audit_to_response(e) for e in entries]
