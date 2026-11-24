# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Workflow Permissions & Audit Log API (#2152)

Endpoints for per-workflow RBAC management and audit trail retrieval.

Routes:
  GET    /api/workflows/{workflow_id}/permissions         — list permissions
  PUT    /api/workflows/{workflow_id}/permissions         — grant / update role
  DELETE /api/workflows/{workflow_id}/permissions/{user_id} — revoke access
  GET    /api/workflows/{workflow_id}/audit               — view audit log
  POST   /api/workflow-permissions/subject-remap-requests — PROPOSE rewriting username-keyed grants (admin)

The grant subject is the canonical principal id (#22180). The remap route only PROPOSES; nothing is rewritten
until a human approves it in the approval queue (#17038).
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas_workflow_grant_remap import GrantRemapProposalResponse, UnmappedGrant
from api.schemas_workflows import (
    GrantPermissionRequest,
    WorkflowAuditLogEntry,
    WorkflowPermissionResponse,
)
from api.user_management.dependencies import get_db_session
from auth_middleware import check_admin_permission, get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.principal import require_principal_id
from models.approval import Approval
from services.approval_gate_service import ApprovalGateService
from services.audit.taxonomy import AuditAction
from services.kb_cleanup_proposals import cleanup_proposal, create_proposal_once, record_cleanup_proposed
from services.workflow_grant_subjects import ACTION as GRANT_REMAP_ACTION
from services.workflow_grant_subjects import SCOPE as GRANT_REMAP_SCOPE
from services.workflow_grant_subjects import (
    plan_remap,
    register_grant_remap_action,
    resolve_user_ref,
)
from services.workflow_permission_service import (
    ROLE_HIERARCHY,
    WorkflowPermissionService,
)
from services.workflow_rbac import require_workflow_permission

logger = get_logger(__name__)

router = APIRouter(tags=["workflow-permissions"])

# Registered at this router's import time so the executor exists before any approve() can reach it.
register_grant_remap_action()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _current_user_id(current_user: dict) -> str:
    """The caller's canonical principal id; an identity-less caller is a 401, never a shared subject (#22180)."""
    return require_principal_id(current_user)


async def _target_id(session: AsyncSession, ref: str) -> str:
    """Resolve a grant target (user id, or a username resolved once, here) to a user id; unknown is refused."""
    target = await resolve_user_ref(session, ref)
    if target is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown user")
    return target


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
    target = await _target_id(session, body.user_id)
    svc = WorkflowPermissionService(session)
    perm = await svc.grant_permission(
        workflow_id=workflow_id,
        user_id=target,
        role=body.role,
        granted_by=actor,
    )
    await svc.log_action(
        user_id=actor,
        workflow_id=workflow_id,
        action="grant",
        details={"target_user": target, "role": body.role},
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
    # A legacy row may still be keyed by the literal value (#22180); removing it only ever reduces access.
    subjects = list(dict.fromkeys([await resolve_user_ref(session, user_id) or user_id, user_id]))
    deleted = False
    for subject in subjects:
        deleted = await svc.revoke_permission(workflow_id=workflow_id, user_id=subject, revoked_by=actor) or deleted
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


# ---------------------------------------------------------------------------
# Subject remap proposal (#22180)
# ---------------------------------------------------------------------------


async def _create_remap_proposal(
    service: ApprovalGateService, current_user: dict, mappings: list, unmapped: list, approval_id
) -> Approval:
    """Audit-log, then create, the pending proposal (the audit row names the approval it precedes)."""
    await record_cleanup_proposed(
        approval_id,
        current_user,
        operation=AuditAction.WORKFLOW_GRANT_REMAP_PROPOSED.value,
        resource=GRANT_REMAP_SCOPE,
    )
    left = ", ".join(sorted({f"{u['old']} ({u['workflow_id']})" for u in unmapped})) or "none"
    return await service.create_approval(
        **cleanup_proposal(
            current_user,
            title=f"Rewrite {len(mappings)} workflow grant subject(s) from username to user id",
            description=(
                "Each listed grant row is keyed by a username. Approving rewrites its user_id to the account's id; "
                f"every row is re-checked first. Rows that cannot be mapped stay untouched: {left}."
            ),
            context={"action": GRANT_REMAP_ACTION, "scope": GRANT_REMAP_SCOPE, "mappings": mappings},
            approval_id=approval_id,
        )
    )


@router.post(
    "/workflow-permissions/subject-remap-requests",
    response_model=GrantRemapProposalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Propose rewriting username-keyed workflow grants to user ids",
    dependencies=[Depends(check_admin_permission)],
)
async def propose_grant_subject_remap(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> GrantRemapProposalResponse:
    """PROPOSE the rewrite -- a request, not a rewrite. Rows that cannot be mapped are reported and left alone."""
    _current_user_id(current_user)
    mappings, unmapped = await plan_remap(session)
    if not mappings:
        raise HTTPException(status.HTTP_409_CONFLICT, f"No grant row can be mapped ({len(unmapped)} unmapped)")
    service = ApprovalGateService(session)
    approval = await create_proposal_once(
        service,
        GRANT_REMAP_ACTION,
        "scope",
        GRANT_REMAP_SCOPE,
        lambda approval_id: _create_remap_proposal(service, current_user, mappings, unmapped, approval_id),
        current_user=current_user,
        resource=GRANT_REMAP_SCOPE,
    )
    return GrantRemapProposalResponse(
        approval_id=str(approval.id),
        status=approval.status,
        action=GRANT_REMAP_ACTION,
        mapped=len(mappings),
        unmapped=[UnmappedGrant(workflow_id=u["workflow_id"], subject=u["old"]) for u in unmapped],
    )
