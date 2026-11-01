# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Approval Gates API (#1402)

CRUD and lifecycle endpoints for human-in-the-loop approval gates.
"""

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas_approvals import (
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
from api.user_management.human_decider import classify_author_type, require_interactive_human
from auth_middleware import get_current_user
from autobot_shared.auth.permissions import is_admin_role
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.models.pagination import PaginationParams
from autobot_shared.risk_tier import RiskTier
from models.approval import ApprovalSource, ApprovalStatus, ApprovalType
from services.ai_line_change_action import register_ai_line_change_action
from services.approval_execution import context_change_violation, is_registered_action, is_server_only_action
from services.approval_gate_service import ApprovalGateService
from services.knowledge.collection_space_stamp_action import register_stamp_action

logger = get_logger(__name__)
router = APIRouter()
register_stamp_action()  # registered with the router so the handler exists before any approve()
register_ai_line_change_action()  # #18430: a person's approval is what changes an AI line


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
        source=approval.source,
        risk_tier=approval.risk_tier,
        expires_at=(approval.expires_at.isoformat() if approval.expires_at else None),
        payload_hash=approval.payload_hash,
        resume_ref=approval.resume_ref,
        comments=_build_comments(approval),
        task_links=_build_task_links(approval),
    )


def _user_uuid(current_user: dict) -> uuid.UUID | None:
    """The authenticated user's id (never a username), or ``None`` if the principal carries none."""
    try:
        return uuid.UUID(str(current_user.get("id") or current_user.get("user_id")))
    except ValueError:
        return None


def _reject_unregistered_action(context: dict | None) -> None:
    """Refuse a ``context.action`` that names no registered handler (#17315).

    ``context`` is caller-supplied and reaches
    ``services.approval_execution.run_post_approval_actions`` verbatim, which
    dispatches on ``context["action"]``. An action with no handler is recorded
    there as a durable anomaly -- an ApprovalComment plus an
    ``approval.post_action_failed`` audit entry that module's own docstring
    calls "a real defect, not a no-op". Any authenticated caller could
    therefore mint those by naming a string that never existed.

    Creation is the only place the request can simply be refused. At approval
    time a human has already said yes, and the sole remaining option is to
    record that nothing happened. An approval with no ``action`` at all stays
    valid: that is the ordinary gate (``compose_tool_handler`` creates one),
    and the dispatcher returns early for it.
    """
    action = (context or {}).get("action")
    if action is None:
        return
    if is_server_only_action(action):
        # #18430: only the action's own proposer may create it, with a requester taken from the session.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="this action can be proposed only by the server"
        )
    if not isinstance(action, str) or not is_registered_action(action):
        # Deliberately does not echo the value back or list what IS
        # registered: the caller supplied it, and the set of live actions is
        # not theirs to enumerate.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="context.action names no registered post-approval handler",
        )


def _requester_matches(approval, current_user: dict) -> bool:
    """Whether the AUTHENTICATED caller is the person who made this request (#17349).

    ``requested_by_agent`` is ``<kind>:<user id>`` for server-made proposals and free text elsewhere; either the
    whole value or the part after the last colon must equal the caller's verified id or username. A request with
    no recorded requester can be resubmitted by nobody.
    """
    requester = str(approval.requested_by_agent or "").strip()
    if not requester:
        return False
    mine = {str(v) for v in (current_user.get("id"), current_user.get("user_id"), current_user.get("username")) if v}
    return requester in mine or requester.rsplit(":", 1)[-1] in mine


def _guard_resubmit(approval, new_context: dict | None, current_user: dict) -> None:
    """Refuse a resubmit by anyone but the requester, or one that rewrites what was reviewed (#17349, #18430)."""
    if approval is None:
        return  # the service reports a missing approval exactly as before
    if not _requester_matches(approval, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="only the requester can resubmit")
    if new_context is None:
        return
    if (approval.context or {}).get("action") != new_context.get("action"):
        _reject_unregistered_action(new_context)  # an unregistered or server-only action is refused first, as on create
    changed = context_change_violation(approval.context, new_context)
    if changed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=f"{changed} cannot change on resubmit; file a new request"
        )


async def _require_visible(svc: ApprovalGateService, approval_id: uuid.UUID, current_user: dict) -> None:
    """404 an approval the caller may not see, exactly as a missing one, before any write (#18413, #17161).

    Same rule as the reads: an admin, the row's ``owner_user``, or a legacy unsourced unowned row. Nothing
    is read into the response and nothing is written when it refuses.
    """
    visible = await svc.get_visible(
        approval_id, viewer=current_user.get("username"), is_admin=is_admin_role(current_user.get("role"))
    )
    if visible is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Approval {approval_id} not found")


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
    _reject_unregistered_action(body.context)
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
    source: ApprovalSource | None = None,
    risk_tier: RiskTier | None = None,
    pagination: PaginationParams = Depends(),
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """List approval gates with optional filters (#1402, #13421)."""
    svc = ApprovalGateService(session)
    approvals = await svc.list_approvals(
        status=status_filter.value if status_filter else None,
        approval_type=approval_type.value if approval_type else None,
        workflow_id=workflow_id,
        agent_id=agent_id,
        limit=pagination.limit,
        offset=pagination.offset,
        source=source.value if source else None,
        risk_tier=risk_tier.value if risk_tier else None,
        extra_where=svc.visibility(current_user.get("username"), is_admin_role(current_user.get("role"))),
    )
    return [_to_response(a) for a in approvals]


# Declared before ``/approval-gates/{approval_id}`` so "pending" is never parsed as a UUID.
@router.get(
    "/approval-gates/pending",
    response_model=List[ApprovalGateResponse],
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_pending_approvals",
    error_code_prefix="APPROVAL_GATES",
)
async def list_pending_approvals(
    source: ApprovalSource | None = None,
    risk_tier: RiskTier | None = None,
    pagination: PaginationParams = Depends(),
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Every pending approval across all sources -- the one approval inbox (#13421)."""
    svc = ApprovalGateService(session)
    approvals = await svc.list_pending(
        viewer=current_user.get("username"),
        is_admin=is_admin_role(current_user.get("role")),
        source=source.value if source else None,
        risk_tier=risk_tier.value if risk_tier else None,
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
    """Get a single approval gate by ID; another user's approval is a 404 (#1402, #18413)."""
    svc = ApprovalGateService(session)
    approval = await svc.get_visible(
        approval_id, viewer=current_user.get("username"), is_admin=is_admin_role(current_user.get("role"))
    )
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
    """Approve a pending approval gate (#1402); only a person may (#17042)."""
    require_interactive_human(current_user, "approval gate approve")
    svc = ApprovalGateService(session)
    await _require_visible(svc, approval_id, current_user)
    username = current_user.get("username", "unknown")
    try:
        approval = await svc.approve(
            approval_id,
            username,
            body.comment,
            author_type=classify_author_type(current_user),
            decider_id=_user_uuid(current_user),
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
    """Reject a pending approval gate (#1402); only a person may (#17042)."""
    require_interactive_human(current_user, "approval gate reject")
    svc = ApprovalGateService(session)
    await _require_visible(svc, approval_id, current_user)
    username = current_user.get("username", "unknown")
    try:
        approval = await svc.reject(
            approval_id,
            username,
            body.comment,
            author_type=classify_author_type(current_user),
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
    """Request revision on a pending approval gate (#1402); only a person may (#17042)."""
    require_interactive_human(current_user, "approval gate request_revision")
    svc = ApprovalGateService(session)
    await _require_visible(svc, approval_id, current_user)
    username = current_user.get("username", "unknown")
    try:
        approval = await svc.request_revision(
            approval_id,
            username,
            body.comment,
            author_type=classify_author_type(current_user),
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
    await _require_visible(svc, approval_id, current_user)
    _guard_resubmit(await svc.get(approval_id), body.context, current_user)
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
    await _require_visible(svc, approval_id, current_user)
    username = current_user.get("username", "unknown")
    if body.author_type is not None:
        logger.warning(
            "Ignoring client-supplied author_type=%s for approval %s; recording the verified caller's (#17056)",
            body.author_type.value,
            approval_id,
        )
    try:
        comment = await svc.add_comment(
            approval_id,
            username,
            body.body,
            author_type=classify_author_type(current_user),
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
    await _require_visible(svc, approval_id, current_user)
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
    await _require_visible(svc, approval_id, current_user)
    try:
        removed = await svc.unlink_task(approval_id, task_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Internal server error",
        )
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task link not found",
        )
