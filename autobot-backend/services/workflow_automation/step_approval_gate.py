# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A workflow step waiting for approval is filed in the one approvals inbox (#20917).

The step notice used to go only to the per-session workflow socket, so a workflow started
outside the Workflow Builder asked nobody. The executor now also files an approval of source
``workflow_step`` owned by the workflow's owner; the approvals inbox and its live ``global``
event show it from any page. Deciding it resumes the step through the same controller the
``control_workflow`` route uses (:func:`resume_workflow_step`); answering the step on that
route instead withdraws the approval (:meth:`StepApprovalGate.withdraw`).

Filing and withdrawing are best-effort: the step is already parked and answerable on the
socket, so a failure here is logged and never raised into the executor.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select

from autobot_shared.logging_manager import get_logger
from autobot_shared.risk_tier import RiskTier, presented_risk_tier_value
from models.approval import Approval, ApprovalSource, ApprovalStatus, ApprovalType
from services.approval_execution import register_resume_handler
from services.approval_gate_service import ApprovalGateService
from user_management.database import get_async_session_factory
from user_management.models.user import User

from .models import WorkflowControlRequest, WorkflowStepStatus

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from .models import ActiveWorkflow, WorkflowStep

logger = get_logger(__name__)

SOURCE = ApprovalSource.WORKFLOW_STEP.value
#: Generic on purpose: the title travels on the ``global`` event, which reaches every client.
TITLE = "Workflow step waiting for approval"


async def owner_username(owner_id: str | None) -> str | None:
    """The username an approval is owned by, for a workflow owner id; ``None`` when unknown (fail closed).

    A workflow records ``user_id``, ``sub`` or ``username`` (``workflow_ownership.caller_id``) while an
    approval is scoped by username. A value that is not a user id is already a username.
    """
    if not owner_id:
        logger.warning("Workflow has no owner; its waiting step is not filed in the approvals inbox")
        return None
    try:
        user_id = uuid.UUID(owner_id)
    except ValueError:
        return owner_id
    async with get_async_session_factory()() as db:
        found = await db.execute(select(User.username).where(User.id == user_id))
        username = found.scalar_one_or_none()
    if not username:
        logger.warning("Workflow owner %s has no user; its waiting step is not filed in the approvals inbox", owner_id)
    return username


def resume_ref_for(workflow_id: str, step_id: str) -> str:
    """The ``resume_ref`` that names a step."""
    return f"{workflow_id}:{step_id}"


def _step_context(workflow: "ActiveWorkflow", step: "WorkflowStep") -> dict:
    return {
        "command": step.command,
        "explanation": step.explanation,
        "step_number": workflow.current_step_index + 1,
        "total_steps": len(workflow.steps),
        "session_id": workflow.session_id,
    }


async def _create(workflow: "ActiveWorkflow", step: "WorkflowStep", owner: str) -> Approval:
    context = _step_context(workflow, step)
    async with get_async_session_factory()() as db:
        return await ApprovalGateService(db).create_approval(
            title=TITLE,
            approval_type=ApprovalType.WORKFLOW_GATE.value,
            requested_by_agent=f"workflow:{workflow.workflow_id}",
            description=f"{context['step_number']}/{context['total_steps']}: {step.description}",
            workflow_id=workflow.workflow_id,
            workflow_step=step.step_id,
            context=context,
            source=SOURCE,
            risk_tier=presented_risk_tier_value(step.risk_level) or RiskTier.HIGH.value,
            resume_ref=resume_ref_for(workflow.workflow_id, step.step_id),
            owner_user=owner,
        )


async def _withdraw_pending(workflow_id: str, step_id: str | None) -> None:
    async with get_async_session_factory()() as db:
        conditions = [
            Approval.source == SOURCE,
            Approval.workflow_id == workflow_id,
            Approval.status == ApprovalStatus.PENDING.value,
        ]
        if step_id is not None:
            conditions.append(Approval.workflow_step == step_id)
        ids = (await db.execute(select(Approval.id).where(*conditions))).scalars().all()
        for approval_id in ids:
            await ApprovalGateService(db).withdraw(approval_id)


class StepApprovalGate:
    """Files and withdraws the approval behind a parked step; injectable into the executor."""

    async def file(self, workflow: "ActiveWorkflow", step: "WorkflowStep") -> None:
        """File *step* for its owner; log and return on any failure."""
        try:
            owner = await owner_username(workflow.owner_id)
            if owner is not None:
                await _create(workflow, step, owner)
        except Exception:
            logger.exception("Could not file step %s of workflow %s for approval", step.step_id, workflow.workflow_id)

    async def withdraw(self, workflow_id: str, step_id: str | None = None) -> None:
        """Withdraw the pending approval of one step, or of the whole workflow; log and return on failure."""
        try:
            await _withdraw_pending(workflow_id, step_id)
        except Exception:
            logger.exception("Could not withdraw the approval of workflow %s", workflow_id)


async def resume_workflow_step(approval: Approval, session: "AsyncSession") -> None:
    """Run what a decision on a filed step means: approved runs it, rejected skips it, anything else waits."""
    from .routes import get_workflow_manager  # lazy: routes imports the api layer that imports this module

    workflow_id, _, step_id = (approval.resume_ref or "").rpartition(":")
    action = {ApprovalStatus.APPROVED.value: "approve_step", ApprovalStatus.REJECTED.value: "skip_step"}.get(
        approval.status
    )
    manager = get_workflow_manager()
    workflow = manager.active_workflows.get(workflow_id)
    if action is None or workflow is None or workflow.is_cancelled:
        return
    step = workflow.steps[workflow.current_step_index] if workflow.current_step_index < len(workflow.steps) else None
    if step is None or step.step_id != step_id or step.status != WorkflowStepStatus.WAITING_APPROVAL:
        logger.info("Approval %s no longer matches a waiting step; nothing to resume", approval.id)
        return
    await manager.handle_workflow_control(
        WorkflowControlRequest(workflow_id=workflow_id, action=action, step_id=step_id)
    )


def register_workflow_step_resume() -> None:
    """Register :func:`resume_workflow_step` for the ``workflow_step`` source."""
    register_resume_handler(SOURCE, resume_workflow_step)
