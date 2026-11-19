# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one executor skeleton behind every approved knowledge delete (#21383, #17038).

``services.kb_wipe_action``, ``services.claude_md_reindex_action`` and ``services.kb_collection_delete_action`` each
delete knowledge-base data only after a human approved a proposal. They share what is the same in all three and
keep only what differs (the scope check, the delete itself, the detail fields):

* :func:`require_approved` -- the approval is an approved proposal of this action;
* :func:`pending_approval` -- the pending proposal of an action, optionally narrowed to one scope;
* :func:`write_audit` -- one durable entry, resource ``knowledge_base``;
* :func:`refuse_more_than_approved` -- delete nothing when more is in scope now than the approver saw;
* :func:`run_audited_delete` -- the paper trail around a delete: the durable *intent* entry first (no committed entry
  means nothing is deleted), then the delete, then the *completion* entry, or a *failure* entry that never replaces
  the delete's own error.

The callers pass an ``audit`` callable ``(result, details) -> bool`` of their own, which looks ``audit_log`` up in
their own module, so each action stays patchable and keeps its own action name and detail shape.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from autobot_shared.logging_manager import get_logger
from models.approval import Approval, ApprovalStatus
from services.audit.taxonomy import AuditAction
from services.audit_logger import AuditResult

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

#: ``(result, details) -> committed`` -- one durable entry for one approval.
Audit = Callable[[AuditResult, dict], Awaitable[bool]]


def require_approved(approval: "Approval", action: str, what: str) -> None:
    """Refuse an approval that is not an approved proposal of *action*."""
    if (approval.context or {}).get("action") != action or approval.status != ApprovalStatus.APPROVED.value:
        raise ValueError(f"approval {approval.id} is not an approved {action} proposal; {what} is refused")


async def pending_approval(
    session: "AsyncSession", action: str, same_scope: Callable[[dict], bool] | None = None
) -> "Approval | None":
    """The pending proposal of *action* (row-locked), the first one *same_scope* accepts when it is given."""
    query = (
        select(Approval)
        .where(Approval.status == ApprovalStatus.PENDING.value, Approval.context["action"].astext == action)
        .with_for_update()
    )
    pending = (await session.execute(query)).scalars().all()
    return next((a for a in pending if same_scope is None or same_scope(a.context or {})), None)


async def write_audit(
    audit_fn: Callable[..., Awaitable[bool]],
    action: AuditAction,
    approval: "Approval",
    result: AuditResult,
    details: dict,
) -> bool:
    """Whether the durable entry was committed. *audit_fn* is the caller module's own ``audit_log``."""
    return await audit_fn(
        action.value,
        result=result,
        user_id=approval.decided_by_user,
        resource="knowledge_base",
        durable=True,
        details=details,
    )


async def audit_failure(audit: Audit, approval: "Approval", details: dict, label: str) -> None:
    """Record the failed outcome. Never raises, so the delete's own error stays the one that propagates."""
    outcome = "returned False"
    try:
        if await audit("failed", details):
            return
    except Exception as audit_exc:  # noqa: BLE001 -- logged below; it must not replace the original error
        outcome = type(audit_exc).__name__
    logger.error("%s: the failure audit entry for approval %s was not written (%s)", label, approval.id, outcome)


async def refuse_more_than_approved(
    audit: Audit,
    approval: "Approval",
    found: int,
    *,
    count_key: str,
    unit: str,
    refused_details: Callable[[Any, int], dict],
) -> None:
    """Delete nothing when more is in scope now than the approver saw; fewer is fine (some may be gone already)."""
    approved = ((approval.context or {}).get("plan") or {}).get(count_key)
    if isinstance(approved, int) and not isinstance(approved, bool) and found <= approved:
        return
    await audit("failed", {**refused_details(approved, found), "phase": "refused"})
    raise ValueError(
        f"approval {approval.id} approved {approved} {unit} but {found} are in scope now; nothing was deleted. "
        "Re-propose."
    )


async def run_audited_delete(
    approval: "Approval",
    audit: Audit,
    *,
    what: str,
    intent: dict,
    delete: Callable[[], Awaitable[Any]],
    failure: Callable[[BaseException], dict],
    completion: Callable[[Any], dict],
) -> Any:
    """Intent entry, then the delete, then the outcome entry; returns what *delete* returned."""
    if not await audit("attempted", {**intent, "phase": "intent"}):
        raise RuntimeError(f"the audit entry for approval {approval.id} could not be written; nothing was deleted")
    try:
        done = await delete()
    except Exception as exc:
        await audit_failure(audit, approval, {**failure(exc), "phase": "failure"}, what)
        raise
    if not await audit("success", {**completion(done), "phase": "completion"}):
        raise RuntimeError(f"{what} for approval {approval.id} ran but its audit record could not be written")
    return done
