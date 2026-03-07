# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Approval Gates API (#1402)

CRUD and lifecycle endpoints for human-in-the-loop approval gates.
"""

import logging
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional

from api.user_management.dependencies import get_db_session
from auth_middleware import get_current_user
from fastapi import APIRouter, Depends, HTTPException, Query, status
from models.approval import ApprovalStatus, ApprovalType
from pydantic import BaseModel, Field
from services.approval_gate_service import ApprovalGateService
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)
router = APIRouter()


# -- Request / Response schemas ----------------------------------------


class AuthorTypeEnum(str, Enum):
    """Valid author types for comments."""

    HUMAN = "human"
    AGENT = "agent"
    SYSTEM = "system"


class CreateApprovalRequest(BaseModel):
    """Request body for creating an approval gate."""

    title: str
    approval_type: ApprovalType
    description: Optional[str] = None
    requested_by_agent: Optional[str] = None
    workflow_id: Optional[str] = None
    workflow_step: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    task_ids: Optional[List[str]] = None


class TransitionRequest(BaseModel):
    """Request body for approve / reject / request-revision."""

    comment: Optional[str] = None


class ResubmitRequest(BaseModel):
    """Request body for resubmitting after revision."""

    description: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


class AddCommentRequest(BaseModel):
    """Request body for adding a comment."""

    body: str
    author_type: AuthorTypeEnum = AuthorTypeEnum.HUMAN


class LinkTaskRequest(BaseModel):
    """Request body for linking a task."""

    task_id: str
    task_type: str = "github_issue"


class TaskApprovalLinkResponse(BaseModel):
    """Response for a task-approval link."""

    id: str
    approval_id: str
    task_id: str
    task_type: str


class CommentResponse(BaseModel):
    """Response for a comment."""

    id: str
    approval_id: str
    author: str
    author_type: str
    body: str
    created_at: Optional[str] = None


class ApprovalResponse(BaseModel):
    """Response for an approval."""

    id: str
    title: str
    description: Optional[str] = None
    approval_type: str
    status: str
    requested_by_agent: Optional[str] = None
    decided_by_user: Optional[str] = None
    workflow_id: Optional[str] = None
    workflow_step: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    decided_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    comments: List[CommentResponse] = Field(default_factory=list)
    task_links: List[TaskApprovalLinkResponse] = Field(default_factory=list)


# -- Helpers -----------------------------------------------------------


def _build_comments(approval) -> List[CommentResponse]:
    """Build comment responses from approval ORM object (#1402)."""
    comments = []
    for c in getattr(approval, "comments", []) or []:
        comments.append(
            CommentResponse(
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


def _to_response(approval) -> ApprovalResponse:
    """Convert an Approval ORM object to a response dict."""
    return ApprovalResponse(
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
    response_model=ApprovalResponse,
    status_code=status.HTTP_201_CREATED,
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
    response_model=List[ApprovalResponse],
)
async def list_approvals(
    status_filter: Optional[ApprovalStatus] = None,
    approval_type: Optional[ApprovalType] = None,
    workflow_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
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
        limit=limit,
        offset=offset,
    )
    return [_to_response(a) for a in approvals]


@router.get(
    "/approval-gates/{approval_id}",
    response_model=ApprovalResponse,
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
    response_model=ApprovalResponse,
)
async def approve(
    approval_id: uuid.UUID,
    body: TransitionRequest,
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
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    return _to_response(approval)


@router.post(
    "/approval-gates/{approval_id}/reject",
    response_model=ApprovalResponse,
)
async def reject(
    approval_id: uuid.UUID,
    body: TransitionRequest,
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
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    return _to_response(approval)


@router.post(
    "/approval-gates/{approval_id}/request-revision",
    response_model=ApprovalResponse,
)
async def request_revision(
    approval_id: uuid.UUID,
    body: TransitionRequest,
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
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    return _to_response(approval)


@router.post(
    "/approval-gates/{approval_id}/resubmit",
    response_model=ApprovalResponse,
)
async def resubmit(
    approval_id: uuid.UUID,
    body: ResubmitRequest,
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
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    return _to_response(approval)


@router.post(
    "/approval-gates/{approval_id}/comments",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_comment(
    approval_id: uuid.UUID,
    body: AddCommentRequest,
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
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    return CommentResponse(
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
async def link_task(
    approval_id: uuid.UUID,
    body: LinkTaskRequest,
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
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
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
