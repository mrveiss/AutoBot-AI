# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Post-approval execution registry (#17038, #17039, #17043, #17141).

An approval gate only decides yes/no; it has no idea what "yes" should DO.
An owning service that wants its own action gated -- propose it, execute
only once a human approves -- registers a handler here, keyed by
``Approval.context["action"]``, the same way ``services.orphan_storage``
lets a data-owning module register its own detector (#17038's "detection
lives with the owner of the data", extended to execution). Nothing in the
approval-gate layer needs to know what any action does; it only dispatches.

A handler failure is reported, never left to crash the approve() response and
never allowed to undo the approval decision itself -- the human's "yes"
already happened and stays recorded.

#17141: recording that outcome is THIS module's job, not each handler's.
Before this, three paths left the approval reading APPROVED with nothing
durable to show it: a handler raising, an action naming no registered
handler (indistinguishable from a deployment that never imported the module
that would have registered one -- a real defect, not a no-op), and a
handler's own early return on a malformed context. A handler that writes its
own success trail (as ``orphan_storage_cleanup_action.py`` does) still relies
on the dispatcher to catch everything that stops it getting there; a handler
is never the sole owner of its own failure recording, so a future action
registered by someone else inherits this without having to remember it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Awaitable, Callable

from autobot_shared.logging_manager import get_logger
from autobot_shared.security.safe_response import safe_error_reason
from models.approval import ApprovalComment
from services.audit_logger import audit_log

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from models.approval import Approval

logger = get_logger(__name__)

PostApprovalAction = Callable[["Approval", "AsyncSession"], Awaitable[None]]

_REGISTRY: dict[str, PostApprovalAction] = {}

#: action -> the production module that PROPOSES it (#17315). Registered in
#: the same call as the handler, so the two halves of a gate cannot drift
#: apart: an action with an executor and no proposer is unreachable, which
#: is how the orphan-storage gate shipped dead.
_PROPOSERS: dict[str, str] = {}

#: The ``audit_log`` operation every dispatcher-recorded failure shares,
#: regardless of which action failed -- the action name is in ``resource``.
_AUDIT_OPERATION = "approval.post_action_failed"


def register_post_approval_action(action: str, handler: PostApprovalAction, *, proposed_by: str) -> None:
    """Register *handler* to run when an approved gate's context names *action*.

    *proposed_by* is the dotted path of the production module that creates
    such an approval (e.g. ``"api.admin_orphan_storage"``). It is required
    and verified, not documentation: #17315 found this registry holding one
    action whose only ``context["action"]`` producer was the registering
    module itself, so an admin could never propose the one deletion the
    owner rule (#17038) requires to be proposed. Declaring the proposer
    here lets ``approval_execution_proposer_test.py`` check every registered
    action against a real entry point, so the next action cannot land
    unreachable the same way.
    """
    if not action or not action.strip():
        raise ValueError("a post-approval action needs a non-empty name")
    if not proposed_by or not proposed_by.strip():
        raise ValueError(f"action {action!r} must name the production module that proposes it (#17315)")
    _REGISTRY[action] = handler
    _PROPOSERS[action] = proposed_by.strip()


def is_registered_action(action: str) -> bool:
    """Whether *action* has a handler -- the creation-time check (#17315).

    ``POST /approval-gates`` calls this to refuse an unknown action while
    it is still only a request. Catching it at approval time instead
    leaves the only remaining option: telling a human who already said yes
    that nothing happened.
    """
    return action in _REGISTRY


def registered_action_proposers() -> dict[str, str]:
    """Every registered action mapped to the module that proposes it (#17315)."""
    return dict(_PROPOSERS)


async def run_post_approval_actions(approval: "Approval", session: "AsyncSession") -> None:
    """Dispatch on ``approval.context["action"]``.

    Called only after the transition to APPROVED already committed -- see
    ``ApprovalGateService.approve()`` -- so nothing here can prevent or roll
    back the approval decision itself. Every way execution can fail to reach
    a handler's own success recording is caught here and recorded as a
    durable anomaly instead (#17141) -- the caller of ``approve()`` never
    sees this raised.
    """
    action = (approval.context or {}).get("action")
    if not action:
        return
    handler = _REGISTRY.get(action)
    if handler is None:
        logger.error("Approved action %r has no registered handler for approval %s", action, approval.id)
        await _record_dispatch_failure(
            approval,
            session,
            action=action,
            reason=f"no handler registered for action {action!r} -- the module that registers it may not be loaded",
        )
        return
    try:
        await handler(approval, session)
    except Exception as exc:
        logger.exception("Post-approval action %r failed for approval %s", action, approval.id)
        await _record_dispatch_failure(approval, session, action=action, reason=safe_error_reason(exc))


async def _record_dispatch_failure(approval: "Approval", session: "AsyncSession", *, action: str, reason: str) -> None:
    """Write the durable trail a handler never reached: an ApprovalComment and an audit_log entry.

    Never raises: a failure recording a failure must not ALSO take down
    ``approve()``'s response, the same guarantee the dispatch itself gives.
    *reason* must already be safe to show a reviewer -- callers pass it
    through :func:`safe_error_reason`, never a bare ``str(exc)``, since an
    exception's own text can carry a host filesystem path (#17039 review).
    """
    try:
        session.add(
            ApprovalComment(
                approval_id=approval.id,
                author="system",
                author_type="system",
                body=f"Post-approval action {action!r} did not complete: {reason}",
            )
        )
        await session.commit()
        await audit_log(
            _AUDIT_OPERATION,
            result="error",
            user_id=getattr(approval, "decided_by_user", None),
            resource=action,
            details={"approval_id": str(approval.id), "reason": reason},
        )
    except Exception:
        logger.exception(
            "Failed to record the post-approval failure trail itself for approval %s, action %r",
            approval.id,
            action,
        )
