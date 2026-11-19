# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The event side of the wake model (#19582): what each write point hands the dispatcher.

Each function here is called at a write point and turns that write into zero or more
``wake_agent`` calls. None of them decides whether an agent is woken -- status, active
runs and tenant scope are the dispatcher's (``llc.scheduler.event_wake``).

Write points (each calls exactly one function below):

* work item created or updated  -> :func:`wake_for_item_changes` (assignment, mentions)
* work item handed to an agent   -> :func:`wake_for_item_changes` (assignment)
* comment added                  -> :func:`wake_for_comment` (comment, mentions)
* approval approved or rejected  -> :func:`wake_for_decided_approval`

:func:`wake_for_item_changes` reads the ORM attribute history, so it must run BEFORE
the flush that would clear it.
"""

import uuid
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstanceState

from autobot_shared.logging_manager import get_logger

from ..models.enums import ApprovalStatus, ApprovalType, HeartbeatInvocationSource
from .mention_parser import new_mentions, parse_mentions

logger = get_logger(__name__)

_DECIDED = frozenset({ApprovalStatus.APPROVED.value, ApprovalStatus.REJECTED.value})


def _change(obj: Any, attr: str) -> tuple:
    """``(old, new)`` for *attr* if this unit of work changed it, else ``(None, None)``.

    An object with no ORM state (not a mapped instance) carries no history, so no change.
    """
    state = inspect(obj, raiseerr=False)
    history = state.attrs[attr].history if isinstance(state, InstanceState) else None
    if history is None or not history.added:
        return None, None
    old = history.deleted[0] if history.deleted else None
    new = history.added[0]
    return (old, new) if str(new) != str(old) else (None, None)  # a str and a UUID of one id are no change


def _added_mentions(item: Any) -> List[str]:
    """Slugs ``@mentioned`` in the title or description that were not there before this write."""
    added: List[str] = []
    for attr in ("title", "description"):
        old, new = _change(item, attr)
        added += new_mentions(new, old)
    return list(dict.fromkeys(added))


async def _wake(session: AsyncSession, company_id: Any, ref: Any, reason: HeartbeatInvocationSource, ctx: Dict):
    from ..scheduler.event_wake import wake_agent

    return await wake_agent(session, company_id=company_id, agent_ref=ref, reason=reason, context=ctx)


async def wake_for_mentions(
    session: AsyncSession, company_id: Any, slugs: Iterable[str], context: Dict[str, Any]
) -> List[uuid.UUID]:
    """Wake every agent named in *slugs*; the runs started."""
    runs = []
    for slug in slugs:
        run_id = await _wake(session, company_id, slug, HeartbeatInvocationSource.AGENT_MENTIONED, context)
        if run_id is not None:
            runs.append(run_id)
    return runs


async def wake_for_item_changes(session: AsyncSession, item: Any) -> List[uuid.UUID]:
    """Wake a newly assigned agent and agents newly ``@mentioned`` in the title or description."""
    _, assignee = _change(item, "assignee_agent_id")
    mentioned = _added_mentions(item)
    context = {"work_item_id": str(item.id)}
    runs = []
    if assignee is not None:
        run_id = await _wake(session, item.company_id, assignee, HeartbeatInvocationSource.WORK_ITEM_ASSIGNED, context)
        runs += [run_id] if run_id is not None else []
    runs += await wake_for_mentions(session, item.company_id, mentioned, context)
    return runs


async def wake_for_comment(session: AsyncSession, comment: Any) -> List[uuid.UUID]:
    """Wake the work item's assignee (comment wake) and every agent ``@mentioned`` in it."""
    from .comment_wake_service import CommentWakeService

    run_id = await CommentWakeService().wake_for_comment(session, comment)
    context = {"work_item_id": str(comment.work_item_id), "wake_comment_id": str(comment.id)}
    mentioned = await wake_for_mentions(session, comment.company_id, parse_mentions(comment.body), context)
    return ([run_id] if run_id is not None else []) + mentioned


def _decided_wake_ref(approval: Any) -> Any:
    """Who hears a decision: the agent a budget override names, since a person may have asked for it (#8214)."""
    if approval.approval_type == ApprovalType.BUDGET_OVERRIDE.value:
        return (approval.context or {}).get("agent_id") or approval.requested_by_agent
    return approval.requested_by_agent


async def wake_for_decided_approval(session: AsyncSession, approval: Any, status: str) -> Optional[uuid.UUID]:
    """Wake the agent *approval* concerns once it is approved or rejected."""
    if status not in _DECIDED or approval.company_id is None or not approval.requested_by_agent:
        return None
    context = {"approval_id": str(approval.id), "approval_status": status}
    reason = HeartbeatInvocationSource.APPROVAL_DECIDED
    return await _wake(session, approval.company_id, _decided_wake_ref(approval), reason, context)
