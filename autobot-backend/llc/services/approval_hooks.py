# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Post-decision hooks for LLC board approvals (GH#8214).

``ApprovalService.decide`` calls :func:`run_post_decision_hook` inside the decision's own
transaction, so a hook that raises leaves the approval undecided. A hook that must touch
Redis or the scheduler cannot be undone by a rollback, so it is split: the database half runs
here, and :func:`run_post_commit_hook` runs the rest after the route has committed.

A hook is selected by the approval's type and decision and acts on the approval's own
``company_id``; nothing in the payload can name another company.
"""

import uuid
from decimal import Decimal
from typing import Any, Awaitable, Callable, Dict, Optional

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger
from models.approval import Approval

from ..models.activity import ActorType
from ..models.budget import LLCAgentBudget
from ..models.enums import ActivityEventType, ApprovalStatus, ApprovalType
from .activity_log import LLCActivityLogService
from .agent_hire_service import HirePayload, insert_hired_agent, schedule_hired_agent

logger = get_logger(__name__)

_activity_log = LLCActivityLogService()


class ApprovalHookError(Exception):
    """The action behind an approval cannot be applied; the decision must not be recorded."""


class BudgetOverridePayload(BaseModel):
    """What a BUDGET_OVERRIDE approval asks for: a higher dollar limit for one agent."""

    agent_id: str = Field(min_length=1, max_length=255)
    budget_limit: Decimal = Field(gt=0, lt=Decimal("1000000000"))
    reason: Optional[str] = None


class SprintClosePayload(BaseModel):
    """What a SPRINT_CLOSE approval names: the sprint to close."""

    sprint_id: uuid.UUID


#: Types whose payload is executed on approval, mapped to the model that payload must satisfy.
_PAYLOAD_MODELS: Dict[str, type] = {
    ApprovalType.HIRE.value: HirePayload,
    ApprovalType.BUDGET_OVERRIDE.value: BudgetOverridePayload,
    ApprovalType.SPRINT_CLOSE.value: SprintClosePayload,
}


def validate_payload(gate_type: ApprovalType, payload: Dict[str, Any]) -> None:
    """Raise :class:`ApprovalHookError` unless *payload* is what *gate_type* executes on approval."""
    model = _PAYLOAD_MODELS.get(gate_type.value)
    if model is None:
        return
    try:
        model.model_validate(payload or {})
    except ValidationError as exc:
        raise ApprovalHookError(f"{gate_type.value} payload is invalid: {exc.error_count()} error(s)") from exc


async def _hire_approved(session: AsyncSession, approval: Approval, decided_by: uuid.UUID) -> Dict[str, Any]:
    hire = HirePayload.model_validate(approval.context or {})
    node_id = await insert_hired_agent(session, approval.company_id, hire)
    await _activity_log.record(
        session,
        str(approval.company_id),
        ActorType.USER,
        str(decided_by),
        ActivityEventType.AGENT_HIRED,
        "agent",
        str(node_id),
        after={"agent_id": hire.agent_id, "name": hire.agent_name, "approval_id": str(approval.id)},
    )
    return {"agent_id": hire.agent_id}


async def _budget_override_approved(session: AsyncSession, approval: Approval, decided_by: uuid.UUID) -> Dict[str, Any]:
    ask = BudgetOverridePayload.model_validate(approval.context or {})
    row = (
        await session.execute(
            select(LLCAgentBudget)
            .where(LLCAgentBudget.agent_id == ask.agent_id, LLCAgentBudget.company_id == str(approval.company_id))
            .with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        raise ApprovalHookError(f"agent {ask.agent_id!r} has no budget in this company")
    if row.budget_mode == "tokens" and row.token_limit is not None:
        # Token enforcement reads token_limit and ignores budget_limit, so raising it would record an approval
        # that changes nothing.
        raise ApprovalHookError("this agent's budget is token-limited; a dollar override would not change it")
    if ask.budget_limit <= Decimal(str(row.budget_limit)):
        raise ApprovalHookError("a budget override must raise the limit")
    before = Decimal(str(row.budget_limit))
    row.budget_limit = ask.budget_limit
    await session.flush()
    return {"agent_id": ask.agent_id, "budget_limit_before": str(before), "budget_limit_after": str(ask.budget_limit)}


async def _sprint_close_approved(session: AsyncSession, approval: Approval, decided_by: uuid.UUID) -> Dict[str, Any]:
    from .sprint_autoclose import SprintAutoCloseService  # noqa: PLC0415 -- it imports ApprovalService

    ask = SprintClosePayload.model_validate(approval.context or {})
    try:
        await SprintAutoCloseService().execute_close(
            session, sprint_id=ask.sprint_id, approval_id=approval.id, decided_by=decided_by
        )
    except ValueError as exc:
        raise ApprovalHookError(str(exc)) from exc
    return {"sprint_id": str(ask.sprint_id)}


_ApprovedHook = Callable[[AsyncSession, Approval, uuid.UUID], Awaitable[Dict[str, Any]]]

#: Applied when the decision is APPROVED. A REJECTED hire is never created, a rejected budget
#: override leaves the agent as it was, and a rejected sprint close leaves the sprint open, so
#: rejection has nothing to apply.
_ON_APPROVED: Dict[str, _ApprovedHook] = {
    ApprovalType.HIRE.value: _hire_approved,
    ApprovalType.BUDGET_OVERRIDE.value: _budget_override_approved,
    ApprovalType.SPRINT_CLOSE.value: _sprint_close_approved,
}


async def run_post_decision_hook(
    session: AsyncSession, approval: Approval, decision: ApprovalStatus, decided_by: uuid.UUID
) -> Dict[str, Any]:
    """Apply what *approval* authorises, in the caller's transaction; return what changed."""
    hook = _ON_APPROVED.get(approval.approval_type)
    if decision != ApprovalStatus.APPROVED or hook is None:
        return {}
    try:
        return await hook(session, approval, decided_by)
    except ApprovalHookError:
        raise
    except ValidationError as exc:
        raise ApprovalHookError(f"{approval.approval_type} payload is invalid: {exc.error_count()} error(s)") from exc
    except Exception as exc:
        # One path for every other failure (a database error, a unique-key clash): the decision is not recorded.
        logger.exception("Approval %s (%s): applying the approved action failed", approval.id, approval.approval_type)
        raise ApprovalHookError(f"the approved {approval.approval_type} action failed: {type(exc).__name__}") from exc


async def run_post_commit_hook(approval: Approval) -> None:
    """The half of an approved action that cannot be rolled back; call after the commit."""
    if approval.status != ApprovalStatus.APPROVED.value:
        return
    if approval.approval_type == ApprovalType.HIRE.value:
        await schedule_hired_agent(HirePayload.model_validate(approval.context or {}))
    elif approval.approval_type == ApprovalType.BUDGET_OVERRIDE.value:
        from .budget import BudgetService  # noqa: PLC0415 -- keeps the Redis tracker out of import time

        ask = BudgetOverridePayload.model_validate(approval.context or {})
        await BudgetService.invalidate_cache(ask.agent_id, str(approval.company_id))
    elif approval.approval_type == ApprovalType.SPRINT_CLOSE.value:
        from .sprint_autoclose import SprintAutoCloseService  # noqa: PLC0415 -- it imports ApprovalService

        ask = SprintClosePayload.model_validate(approval.context or {})
        SprintAutoCloseService().schedule_closed_sprint_summary(ask.sprint_id)


async def record_approval_event(
    session: AsyncSession,
    approval: Approval,
    event: ActivityEventType,
    *,
    actor_user_id: Optional[uuid.UUID],
    before: Optional[Dict[str, Any]] = None,
    after: Optional[Dict[str, Any]] = None,
) -> None:
    """Write one activity row for an approval mutation, in the caller's transaction.

    The actor is the verified caller's user id; with none (a sweep or the scheduler asking)
    the act is the system's and the requester is kept in ``metadata`` rather than named as actor.
    """
    actor = ActorType.USER if actor_user_id else ActorType.SYSTEM
    await _activity_log.record(
        session,
        str(approval.company_id),
        actor,
        str(actor_user_id) if actor_user_id else None,
        event,
        "approval",
        str(approval.id),
        before=before,
        after={"type": approval.approval_type, **(after or {})},
        metadata={"requested_by": approval.requested_by_agent},
    )
