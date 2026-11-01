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
from typing import Any, Awaitable, Callable, Dict, Literal, Optional

from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.approval_four_eyes import FourEyesError
from autobot_shared.logging_manager import get_logger
from models.approval import Approval
from services.agent_org_service import AgentOrgService

from ..models.activity import ActorType
from ..models.budget import LLCAgentBudget
from ..models.enums import ActivityEventType, ApprovalStatus, ApprovalType
from .activity_log import LLCActivityLogService
from .agent_hire_service import HirePayload, insert_hired_agent, schedule_hired_agent
from .authz import require_four_eyes

logger = get_logger(__name__)

_activity_log = LLCActivityLogService()


class ApprovalHookError(Exception):
    """The action behind an approval cannot be applied; the decision must not be recorded."""


class BudgetOverridePayload(BaseModel):
    """What a BUDGET_OVERRIDE approval asks for: a higher limit for one agent, in dollars or in tokens.

    ``budget_mode`` switches which limit is enforced (a switch is judged as a raise, #8214);
    at least one of the three limit fields must be present.
    """

    agent_id: str = Field(min_length=1, max_length=255)
    budget_limit: Optional[Decimal] = Field(None, gt=0, lt=Decimal("1000000000"))
    token_limit: Optional[int] = Field(None, gt=0)
    budget_mode: Optional[Literal["dollars", "tokens"]] = None
    alert_threshold: Optional[float] = None
    reason: Optional[str] = None

    @model_validator(mode="after")
    def _names_a_limit(self) -> "BudgetOverridePayload":
        if self.budget_limit is None and self.token_limit is None and self.budget_mode is None:
            raise ValueError("a budget override names a limit or a mode")
        return self


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


async def _require_manager_still_here(session: AsyncSession, approval: Approval, hire: HirePayload) -> None:
    """Refuse the approval when the hire's manager has left the company since the hire was requested (#20422).

    Refuse rather than clear: the board approved this reporting line, so dropping it silently would seat the
    agent somewhere nobody approved. The approval stays pending (409); reject it and request the hire again.
    """
    try:
        await AgentOrgService(session).assert_manager_in_company(hire.reports_to, approval.company_id)
    except ValueError as exc:
        raise ApprovalHookError(
            f"the hire's manager {hire.reports_to!r} is no longer an agent of this company"
        ) from exc


async def _hire_approved(session: AsyncSession, approval: Approval, decided_by: uuid.UUID) -> Dict[str, Any]:
    hire = HirePayload.model_validate(approval.context or {})
    await _require_manager_still_here(session, approval, hire)
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


def _check_override_applies(row: LLCAgentBudget, ask: BudgetOverridePayload) -> None:
    """Refuse an override that would change nothing or lower a limit; the approval then stays pending."""
    mode = ask.budget_mode or str(row.budget_mode)
    if ask.token_limit is not None and mode != "tokens":
        raise ApprovalHookError("a token limit is not enforced on a dollar budget; switch the mode with it")
    same_mode = mode == str(row.budget_mode)
    if ask.token_limit is not None and row.token_limit is not None and same_mode:
        if ask.token_limit <= int(row.token_limit):
            raise ApprovalHookError("a budget override must raise the limit")
    if ask.budget_limit is None:
        if ask.token_limit is None and same_mode:
            raise ApprovalHookError("a budget override must change the limit or the mode")
        return
    if ask.token_limit is None and mode == "tokens" and row.token_limit is not None:
        # Token enforcement reads token_limit and ignores budget_limit, so raising it would record an approval
        # that changes nothing.
        raise ApprovalHookError("this agent's budget is token-limited; a dollar override would not change it")
    if ask.token_limit is None and same_mode and ask.budget_limit <= Decimal(str(row.budget_limit)):
        raise ApprovalHookError("a budget override must raise the limit")


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
    _check_override_applies(row, ask)
    before = {
        "budget_mode": str(row.budget_mode),
        "budget_limit": str(row.budget_limit),
        "token_limit": row.token_limit,
    }
    for field in ("budget_mode", "budget_limit", "token_limit", "alert_threshold"):
        if getattr(ask, field) is not None:
            setattr(row, field, getattr(ask, field))
    await session.flush()
    after = {"budget_mode": str(row.budget_mode), "budget_limit": str(row.budget_limit), "token_limit": row.token_limit}
    return {
        "agent_id": ask.agent_id,
        "budget_limit_before": before["budget_limit"],
        "budget_limit_after": after["budget_limit"],
        "before": before,
        "after": after,
    }


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


#: Types whose approval moves money or headcount: the one who asked cannot also approve while another admin exists.
_FOUR_EYES_TYPES = frozenset({ApprovalType.HIRE.value, ApprovalType.BUDGET_OVERRIDE.value})


async def review_decider(
    session: AsyncSession, approval: Approval, decision: ApprovalStatus, decided_by: uuid.UUID
) -> bool:
    """Apply the four-eyes rule (#8214, #18430) to an APPROVED hire or budget override; True when it is a self-approval.

    A requester may always reject their own request. A refusal raises :class:`ApprovalHookError`, which rolls
    the decision back and leaves the approval pending for another admin. A requester that names no person
    (an agent, or a row from before requesters were pinned to the verified caller) is not the decider, so it
    passes unflagged rather than stranding the request; nothing stored is rewritten (#17038).
    """
    if decision != ApprovalStatus.APPROVED or approval.approval_type not in _FOUR_EYES_TYPES:
        return False
    try:
        return await require_four_eyes(
            approval, session, decided_by, what=f"a {approval.approval_type}", unidentified_requester_ok=True
        )
    except FourEyesError as exc:
        raise ApprovalHookError(str(exc)) from exc


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
