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
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from models.approval import Approval

logger = get_logger(__name__)

PostApprovalAction = Callable[["Approval", "AsyncSession"], Awaitable[None]]

_REGISTRY: dict[str, PostApprovalAction] = {}

#: source -> handler that continues the work a decided approval was blocking (#13421).
#: Distinct from ``_REGISTRY``: that dispatches on ``context["action"]`` and runs only on
#: APPROVE; this dispatches on ``Approval.source`` and runs on EVERY decision, because a
#: rejected tool call must also unblock the agent loop waiting on it. The handler reads
#: ``approval.status`` to tell which.
_RESUME_HANDLERS: dict[str, PostApprovalAction] = {}

#: action -> the production module that PROPOSES it (#17315). Registered in
#: the same call as the handler, so the two halves of a gate cannot drift
#: apart: an action with an executor and no proposer is unreachable, which
#: is how the orphan-storage gate shipped dead.
_PROPOSERS: dict[str, str] = {}

#: The ``audit_log`` operation every dispatcher-recorded failure shares,
#: regardless of which action failed -- the action name is in ``resource``.
_AUDIT_OPERATION = "approval.post_action_failed"


#: Actions only a server-side proposer may create (#18430). A public create route would let a caller write the
#: approval's payload AND its requester, which defeats any rule about who may decide it.
_SERVER_ONLY: set[str] = set()

#: Attribute carrying the VERIFIED decider's user id from the decision route to the handler. Never persisted and
#: never parsed from ``decided_by_user``, which is a display name on one route and a different shape on the other.
_DECIDER_ATTR = "_verified_decider_id"


def is_server_only_action(action: object) -> bool:
    """Whether *action* may be created only by its own server-side proposer, never through a create route."""
    return isinstance(action, str) and action in _SERVER_ONLY


def set_verified_decider(approval: "Approval", user_id: "uuid.UUID | None") -> None:
    """Record, for this decision only, the id of the authenticated person who decided *approval*."""
    setattr(approval, _DECIDER_ATTR, user_id)


def verified_decider(approval: "Approval") -> "uuid.UUID | None":
    """The authenticated decider's user id, or ``None`` when the route did not supply one (the handler refuses)."""
    return getattr(approval, _DECIDER_ATTR, None)


#: action -> the ``context`` keys that are free text the action IGNORES. Every other key of an approval that names
#: a registered action is what a human reviewed and is frozen: resubmitting after a revision request may not change
#: it, or the human would approve something other than what they looked at (#17349).
_FREE_TEXT_KEYS: dict[str, frozenset[str]] = {}


def context_change_violation(old: "dict | None", new: "dict | None") -> str | None:
    """What a resubmit may NOT change, or ``None``: the action, and every reviewed field of a registered action.

    An approval that names no action carries no executable meaning, so its context may change freely.
    """
    old, new = old or {}, new or {}
    if old.get("action") != new.get("action"):
        return "context.action"
    if old.get("action") not in _REGISTRY:
        return None
    free = _FREE_TEXT_KEYS.get(old["action"], frozenset())
    for key in sorted((set(old) | set(new)) - free):
        if old.get(key) != new.get(key):
            return f"context.{key}"
    return None


def register_post_approval_action(
    action: str,
    handler: PostApprovalAction,
    *,
    proposed_by: str,
    server_only: bool = False,
    free_text_keys: "frozenset[str]" = frozenset(),
) -> None:
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
    if server_only:
        _SERVER_ONLY.add(action)
    _FREE_TEXT_KEYS[action] = frozenset(free_text_keys)


def register_resume_handler(source: str, handler: PostApprovalAction) -> None:
    """Register *handler* to resume the work behind a decided approval of *source* (#13421).

    Runs after the decision commits, for approved, rejected and revision-requested alike, and
    only for an approval that carries a ``resume_ref``. Failures are recorded, never raised.
    """
    if not source or not source.strip():
        raise ValueError("a resume handler needs a non-empty source")
    _RESUME_HANDLERS[source] = handler


def is_registered_resume_source(source: str) -> bool:
    """Whether *source* has a resume handler -- the creation-time check for ``resume_ref``."""
    return source in _RESUME_HANDLERS


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


async def run_post_approval_actions(
    approval: "Approval", session: "AsyncSession", *, only: "frozenset[str] | None" = None
) -> None:
    """Dispatch on ``approval.context["action"]``.

    ``only`` restricts a CALLER to a named set of actions (#18430): an action outside it is not run and leaves a
    durable comment saying so. The LLC decide route passes it, because that route's approvals are self-created
    with arbitrary payloads (#17161).

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
    if only is not None and action not in only:
        await _record_dispatch_failure(
            approval, session, action=action, reason="this decision route runs only its allowed actions (#17161)"
        )
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


async def resume_decided_approval(approval: "Approval", session: "AsyncSession") -> None:
    """Continue the work behind a decided approval via its source's resume handler (#13421).

    A no-op for an approval with no ``resume_ref``. A ``resume_ref`` whose source has no handler
    is recorded as an anomaly exactly like an unregistered action (#17141) -- never raised, and
    never undoing the decision already committed.
    """
    source, ref = getattr(approval, "source", None), getattr(approval, "resume_ref", None)
    if not source or not ref:
        return
    handler = _RESUME_HANDLERS.get(source)
    if handler is None:
        logger.error("Approval %s has resume_ref but source %r has no resume handler", approval.id, source)
        await _record_dispatch_failure(
            approval, session, action=f"resume:{source}", reason=f"no resume handler registered for source {source!r}"
        )
        return
    try:
        await handler(approval, session)
    except Exception as exc:
        logger.exception("Resume of approval %s (source %r) failed", approval.id, source)
        await _record_dispatch_failure(approval, session, action=f"resume:{source}", reason=safe_error_reason(exc))


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
