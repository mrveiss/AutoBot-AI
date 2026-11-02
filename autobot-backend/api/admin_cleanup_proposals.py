# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Admin API: PROPOSE removing old ``.env.*~`` copies on this node (#20567).

Endpoints:
    GET  /api/admin/env-copies-cleanup                   how many ``.env.*~`` copies would go
    POST /api/admin/env-copies-cleanup/requests          PROPOSE it -- creates a PENDING approval

No route removes anything. Nothing runs until a human approves it in the Approvals inbox, and it is
never auto-approved (#17038). Only this node's files are handled. The executors live in
``services.install_cleanup_actions``; the request carries no path.
"""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas_cleanup_proposals import CleanupRequestResponse, CleanupStatus
from api.user_management.dependencies import get_db_session
from auth_middleware import get_current_user
from auth_rbac import require_role
from models.approval import Approval, ApprovalStatus, ApprovalType
from services.approval_gate_service import ApprovalGateService
from services.install_cleanup_actions import (
    ENV_COPIES_ACTION,
    CleanupPlan,
    plan_env_copies,
    register_install_cleanup_actions,
)

router = APIRouter(prefix="/admin", dependencies=[Depends(require_role("admin", "superadmin"))])

# Registered at this router's import time so the executors exist before any approve().
register_install_cleanup_actions()


def _status(plan: CleanupPlan, found: str, none: str) -> CleanupStatus:
    if plan.refused:
        return CleanupStatus(count=0, detail=plan.refused, refused=plan.refused)
    return CleanupStatus(count=plan.count, detail=found if plan.count else none)


def _env_status(plan: CleanupPlan) -> CleanupStatus:
    return _status(plan, f"{plan.count} older .env.*~ copies; the newest is kept", "No older .env.*~ copies")


@router.get("/env-copies-cleanup", response_model=CleanupStatus)
async def env_copies_status() -> CleanupStatus:
    """Read only: counts, never a file's contents."""
    return _env_status(await asyncio.to_thread(plan_env_copies))


async def _propose(
    plan: CleanupPlan, *, action: str, title: str, description: str, current_user: dict, session: AsyncSession
) -> CleanupRequestResponse:
    requester = current_user.get("id") or current_user.get("user_id")  # as the approve route reads the decider
    if not requester:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "The proposal cannot be attributed to a verified user")
    if plan.refused:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Not proposable: {plan.refused}")
    if not plan.targets:
        raise HTTPException(status.HTTP_409_CONFLICT, "There is nothing to remove")
    service = ApprovalGateService(session)
    pending = await service.list_approvals(
        status=ApprovalStatus.PENDING.value,
        approval_type=ApprovalType.DESTRUCTIVE_ACTION.value,
        extra_where=(Approval.context["action"].astext == action,),
        limit=1,
    )
    if pending:
        raise HTTPException(status.HTTP_409_CONFLICT, "This cleanup is already waiting for review")
    approval = await service.create_approval(
        title=title,
        approval_type=ApprovalType.DESTRUCTIVE_ACTION.value,
        description=description,
        requested_by_agent=f"cleanup-proposal:{requester}",
        context={"action": action},
    )
    return CleanupRequestResponse(approval_id=str(approval.id), status=approval.status, action=action)


@router.post("/env-copies-cleanup/requests", response_model=CleanupRequestResponse, status_code=status.HTTP_201_CREATED)
async def propose_env_copies_cleanup(
    current_user: dict = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)
) -> CleanupRequestResponse:
    """Propose keeping only the newest ``.env.*~`` copy -- a request, not an execution."""
    plan = await asyncio.to_thread(plan_env_copies)
    return await _propose(
        plan,
        action=ENV_COPIES_ACTION,
        title="Remove old .env.*~ copies, keeping the newest",
        description=(
            f"{plan.count} older copies of the backend's secrets file sit beside it. Approving deletes them for "
            "good and keeps the newest. The paths are chosen by the server when it runs, not by this request."
        ),
        current_user=current_user,
        session=session,
    )
