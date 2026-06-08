# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Approval Gates API (#1402)

CRUD and lifecycle endpoints for human-in-the-loop approval gates.
"""

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas_workflows import (
    ApprovalAddCommentRequest,
    ApprovalCommentResponse,
    ApprovalGateResponse,
    ApprovalLinkTaskRequest,
    ApprovalResubmitRequest,
    ApprovalTransitionRequest,
    CreateApprovalRequest,
    TaskApprovalLinkResponse,
)
from api.user_management.dependencies import get_db_session
from auth_middleware import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.models.pagination import PaginationParams
from models.approval import ApprovalStatus, ApprovalType
from services.approval_gate_service import ApprovalGateService

logger = get_logger(__name__)
router = APIRouter()


# -- Helpers -----------------------------------------------------------


def _build_comments(approval) -> List[ApprovalCommentResponse]:
    """Build comment responses from approval ORM object (#1402)."""
    comments = []
    for c in getattr(approval, "comments", []) or []:
        comments.append(
            ApprovalCommentResponse(
                id=str(c.id),
                approval_id=str(c.approval_id),
                author=c.author,
                author_type=c.author_type,
                body=c.body,
                created_at=(c.created_at.isoformat() if c.created_at else None),
            )
        )
    return comments


def _build_task_links(approval) -> List[TaskApprovalLinkResponse]:
    """Build task link responses from approval ORM object (#1402)."""
    task_links = []
    for tl in getattr(approval, "task_links", []) or []:
        task_links.append(
            TaskApprovalLinkResponse(
                id=str(tl.id),
                approval_id=str(tl.approval_id),
                task_id=tl.task_id,
                task_type=tl.task_type,
            )
        )
    return task_links


def _to_response(approval) -> ApprovalGateResponse:
    """Convert an Approval ORM object to a response dict."""
    return ApprovalGateResponse(
        id=str(approval.id),
        title=approval.title,
        description=approval.description,
        approval_type=approval.approval_type,
        status=approval.status,
        requested_by_agent=approval.requested_by_agent,
        decided_by_user=approval.decided_by_user,
        workflow_id=approval.workflow_id,
        workflow_step=approval.workflow_step,
        context=approval.context,
        decided_at=(approval.decided_at.isoformat() if approval.decided_at else None),
        created_at=(approval.created_at.isoformat() if approval.created_at else None),
        updated_at=(approval.updated_at.isoformat() if approval.updated_at else None),
        comments=_build_comments(approval),
        task_links=_build_task_links(approval),
    )


# -- Endpoints ---------------------------------------------------------


@router.post(
    "/approval-gates",
    response_model=ApprovalGateResponse,
    status_code=status.HTTP_201_CREATED,
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_approval",
    error_code_prefix="APPROVAL_GATES",
)
async def create_approval(
    body: CreateApprovalRequest,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Create a new approval gate request (#1402)."""
    svc = ApprovalGateService(session)
    approval = await svc.create_approval(
        title=body.title,
        approval_type=body.approval_type.value,
        description=body.description,
        requested_by_agent=body.requested_by_agent,
        workflow_id=body.workflow_id,
        workflow_step=body.workflow_step,
        context=body.context,
        task_ids=body.task_ids,
    )
    return _to_response(approval)


@router.get(
    "/approval-gates",
    response_model=List[ApprovalGateResponse],
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_approvals",
    error_code_prefix="APPROVAL_GATES",
)
async def list_approvals(
    status_filter: ApprovalStatus | None = None,
    approval_type: ApprovalType | None = None,
    workflow_id: str | None = None,
    agent_id: str | None = None,
    pagination: PaginationParams = Depends(),
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """List approval gates with optional filters (#1402)."""
    svc = ApprovalGateService(session)
    approvals = await svc.list_approvals(
        status=status_filter.value if status_filter else None,
        approval_type=approval_type.value if approval_type else None,
        workflow_id=workflow_id,
        agent_id=agent_id,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return [_to_response(a) for a in approvals]


@router.get(
    "/approval-gates/{approval_id}",
    response_model=ApprovalGateResponse,
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_approval",
    error_code_prefix="APPROVAL_GATES",
)
async def get_approval(
    approval_id: uuid.UUID,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Get a single approval gate by ID (#1402)."""
    svc = ApprovalGateService(session)
    approval = await svc.get(approval_id)
    if approval is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Approval {approval_id} not found",
        )
    return _to_response(approval)


@router.post(
    "/approval-gates/{approval_id}/approve",
    response_model=ApprovalGateResponse,
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="approve",
    error_code_prefix="APPROVAL_GATES",
)
async def approve(
    approval_id: uuid.UUID,
    body: ApprovalTransitionRequest,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Approve a pending approval gate (#1402)."""
    svc = ApprovalGateService(session)
    username = current_user.get("username", "unknown")
    try:
        approval = await svc.approve(
            approval_id,
            username,
            body.comment,
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Internal server error",
        )
    return _to_response(approval)


@router.post(
    "/approval-gates/{approval_id}/reject",
    response_model=ApprovalGateResponse,
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="reject",
    error_code_prefix="APPROVAL_GATES",
)
async def reject(
    approval_id: uuid.UUID,
    body: ApprovalTransitionRequest,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Reject a pending approval gate (#1402)."""
    svc = ApprovalGateService(session)
    username = current_user.get("username", "unknown")
    try:
        approval = await svc.reject(
            approval_id,
            username,
            body.comment,
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Internal server error",
        )
    return _to_response(approval)


@router.post(
    "/approval-gates/{approval_id}/request-revision",
    response_model=ApprovalGateResponse,
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="request_revision",
    error_code_prefix="APPROVAL_GATES",
)
async def request_revision(
    approval_id: uuid.UUID,
    body: ApprovalTransitionRequest,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Request revision on a pending approval gate (#1402)."""
    svc = ApprovalGateService(session)
    username = current_user.get("username", "unknown")
    try:
        approval = await svc.request_revision(
            approval_id,
            username,
            body.comment,
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Internal server error",
        )
    return _to_response(approval)


@router.post(
    "/approval-gates/{approval_id}/resubmit",
    response_model=ApprovalGateResponse,
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="resubmit",
    error_code_prefix="APPROVAL_GATES",
)
async def resubmit(
    approval_id: uuid.UUID,
    body: ApprovalResubmitRequest,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Resubmit an approval after revision request (#1402)."""
    svc = ApprovalGateService(session)
    try:
        approval = await svc.resubmit(
            approval_id,
            body.description,
            body.context,
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Internal server error",
        )
    return _to_response(approval)


@router.post(
    "/approval-gates/{approval_id}/comments",
    response_model=ApprovalCommentResponse,
    status_code=status.HTTP_201_CREATED,
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="add_comment",
    error_code_prefix="APPROVAL_GATES",
)
async def add_comment(
    approval_id: uuid.UUID,
    body: ApprovalAddCommentRequest,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Add a comment to an approval gate (#1402)."""
    svc = ApprovalGateService(session)
    username = current_user.get("username", "unknown")
    try:
        comment = await svc.add_comment(
            approval_id,
            username,
            body.body,
            body.author_type.value,
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Internal server error",
        )
    return ApprovalCommentResponse(
        id=str(comment.id),
        approval_id=str(comment.approval_id),
        author=comment.author,
        author_type=comment.author_type,
        body=comment.body,
        created_at=(comment.created_at.isoformat() if comment.created_at else None),
    )


@router.post(
    "/approval-gates/{approval_id}/tasks",
    response_model=TaskApprovalLinkResponse,
    status_code=status.HTTP_201_CREATED,
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="link_task",
    error_code_prefix="APPROVAL_GATES",
)
async def link_task(
    approval_id: uuid.UUID,
    body: ApprovalLinkTaskRequest,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Link a task/issue to an approval gate (#1402)."""
    svc = ApprovalGateService(session)
    try:
        link = await svc.link_task(
            approval_id,
            body.task_id,
            body.task_type,
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Internal server error",
        )
    return TaskApprovalLinkResponse(
        id=str(link.id),
        approval_id=str(link.approval_id),
        task_id=link.task_id,
        task_type=link.task_type,
    )


@router.delete(
    "/approval-gates/{approval_id}/tasks/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="unlink_task",
    error_code_prefix="APPROVAL_GATES",
)
async def unlink_task(
    approval_id: uuid.UUID,
    task_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Unlink a task from an approval gate (#1402)."""
    svc = ApprovalGateService(session)
    removed = await svc.unlink_task(approval_id, task_id)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task link not found",
        )
