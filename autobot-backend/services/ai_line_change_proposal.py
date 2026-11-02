# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""PROPOSE a change to an AI line; never apply it (#18430, #17038).

Changing a line is itself a decision for a person, so it goes through Approvals: this files one
company-scoped approval whose context names ``ai_line.set_line``. Nothing in this module writes the
line store, and an already-pending request for the same company, action and line is reused.
"""

from __future__ import annotations

from sqlalchemy import select

from autobot_shared.ai_lines import SCOPE_COMPANY, AiLine, LineScope
from autobot_shared.logging_manager import get_logger
from llc.services.ai_lines import normalise_key
from models.approval import Approval, ApprovalStatus, ApprovalType
from services.ai_line_change_action import ACTION
from services.approval_gate_service import ApprovalGateService
from user_management.database import get_async_session_factory

logger = get_logger(__name__)

REQUESTER_PREFIX = "ai-line-change"
#: A request carrying a *plan_ref* stays the plan's own once a person has acted on it, so a retry never files it
#: again (#20115). Withdrawn and expired ones are over and do not count: a new request may follow them.
_PLAN_OWN_STATUSES = (
    ApprovalStatus.PENDING.value,
    ApprovalStatus.APPROVED.value,
    ApprovalStatus.REJECTED.value,
    ApprovalStatus.REVISION_REQUESTED.value,
)


async def _pending_match(  # noqa: ANN001
    session, *, company_id, requester, wanted: tuple, plan_ref: str | None, legacy_plan_refs: tuple = ()
):
    """The request equal to *wanted* that is still open, or None.

    With a *plan_ref* the identity is the plan's, so a retry by another admin finds the request the first
    attempt filed, and so does a retry after a person decided it (#20115); without one it stays the
    requester's own and only a pending one counts (#20168). A pending request filed under a *legacy_plan_refs*
    reference (the identity before it carried a revision) is the plan's too, so an in-flight one is not filed twice.
    """
    where = [
        (
            Approval.status == ApprovalStatus.PENDING.value
            if plan_ref is None
            else Approval.status.in_(_PLAN_OWN_STATUSES)
        ),
        Approval.approval_type == ApprovalType.WORKFLOW_GATE.value,
        Approval.company_id == company_id if company_id else Approval.company_id.is_(None),
    ]
    if plan_ref is None:
        where.append(Approval.requested_by_agent == requester)
    for existing in (await session.execute(select(Approval).where(*where))).scalars().all():
        ctx = existing.context or {}
        same = (ctx.get("action"), ctx.get("action_key"), ctx.get("line"), ctx.get("scope_id"))
        ref = ctx.get("plan_ref")
        legacy_open = ref in legacy_plan_refs and existing.status == ApprovalStatus.PENDING.value
        if same == wanted and (ref == plan_ref or legacy_open):
            return existing
    return None


async def propose_line_change(
    *,
    scope: LineScope,
    key: str,
    line: AiLine,
    requested_by: str,
    reason: str | None = None,
    plan_ref: str | None = None,
    legacy_plan_refs: tuple = (),
) -> Approval:
    """File (or reuse) the pending request to set *key* to *line* in *scope* (a company, or one user).

    A personal change is an unscoped approval whose context names the user; the handler lets only that user
    decide it. *plan_ref* is a stable identity (a workflow plan) that makes a retry reuse the request;
    *legacy_plan_refs* are older spellings of it that still match while pending.
    """
    key = normalise_key(key)
    company_id = scope.id if scope.kind == SCOPE_COMPANY else None
    scope_ctx = {"scope_kind": scope.kind, "scope_id": str(scope.id)}
    requester = f"{REQUESTER_PREFIX}:{requested_by}"
    context = {"action": ACTION, "action_key": key, "line": line.value, **scope_ctx}
    context.update({"plan_ref": plan_ref} if plan_ref else {})
    async with get_async_session_factory()() as session:
        wanted = (ACTION, key, line.value, scope_ctx["scope_id"])
        found = await _pending_match(
            session,
            company_id=company_id,
            requester=requester,
            wanted=wanted,
            plan_ref=plan_ref,
            legacy_plan_refs=legacy_plan_refs,
        )
        if found is not None:
            return found
        return await ApprovalGateService(session).create_approval(
            title=f"Set the AI line for '{key}' to {line.value}",
            approval_type=ApprovalType.WORKFLOW_GATE.value,
            requested_by_agent=requester,
            description=reason or f"Change the line for '{key}' to {line.value}. Nothing changes until approved.",
            context=context,
            company_id=company_id,
        )
