# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The ONE dispatcher for event wakes (#19582).

Owner model (2026-10-25): a heartbeat is an optional periodic schedule; EVENTS always
wake an agent. The four events -- a comment on its work item, the work item assigned to
it, an ``@mention`` of it, and an approval it requested being decided -- all call
:func:`wake_agent`, and nothing else creates an event-driven run.

The rules, each kept in exactly one place:

* **Gate is agent status**, not ``heartbeat_enabled`` (that gates only the periodic
  tick) and not the adapter. A paused ("dormant"), inactive or terminated agent is not
  woken.
* **Same runner as the heartbeat.** The run is created by the scheduler's
  ``trigger_manual`` (one run-creation path) and executed by its ``dispatch_run``, which
  falls back to the in-process AutoBot agent for a NULL adapter.
* **No double-run.** No wake beside a QUEUED or RUNNING run of the agent, and the
  scheduler's RUNNING claim (``run_status.mark_running``) settles an event racing a tick.
* **Tenant scope.** The agent is looked up inside the event's company only.
* **Dispatch after commit.** The adapter task starts only once the caller's transaction
  commits, so its RUNNING update can see the run row; a rollback (including of the
  savepoint the wake was made in) drops the dispatch with the row.
* **A wake never fails the write.** The comment, assignment or approval is the user's
  work; a wake that cannot be created or dispatched is logged, never raised into it.
"""

import uuid
from typing import Any, Dict, Optional, Union

from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger

from ..models.enums import UNDISPATCHABLE_AGENT_STATUSES, HeartbeatInvocationSource
from ..services.after_commit import defer_until_commit
from .dispatch_gate import as_uuid, resolve_agent
from .run_status import active_run

logger = get_logger(__name__)

#: The events that wake an agent; ``wake_agent`` refuses any other source.
EVENT_WAKE_SOURCES = frozenset(
    {
        HeartbeatInvocationSource.WORK_ITEM_COMMENTED,
        HeartbeatInvocationSource.WORK_ITEM_ASSIGNED,
        HeartbeatInvocationSource.AGENT_MENTIONED,
        HeartbeatInvocationSource.APPROVAL_DECIDED,
    }
)


async def _wakeable_slug(session: AsyncSession, company_id: Any, agent_ref: Any) -> Optional[str]:
    """The slug to wake, or ``None`` when the agent is absent, not wakeable, or busy."""
    cid = as_uuid(company_id)
    row = await resolve_agent(session, cid, agent_ref) if cid is not None and agent_ref else None
    if row is None:
        logger.debug("Event wake: no agent %r in company %s", agent_ref, company_id)
        return None
    if (row.status or "") in UNDISPATCHABLE_AGENT_STATUSES:
        logger.info("Event wake skipped: agent %s is %s", row.agent_id, row.status)
        return None
    active = await active_run(session, row.agent_id)  # a stale (crashed) run does not count
    if active is not None:
        logger.info("Event wake skipped: agent %s already has run %s (%s)", row.agent_id, active.id, active.status)
        return None
    return row.agent_id


async def wake_agent(
    session: AsyncSession,
    *,
    company_id: Union[str, uuid.UUID],
    agent_ref: Union[str, uuid.UUID],
    reason: HeartbeatInvocationSource,
    context: Optional[Dict[str, Any]] = None,
) -> Optional[uuid.UUID]:
    """Wake *agent_ref* (slug or node PK) for *reason*; the new run's id, or ``None``.

    The run is flushed in the caller's transaction and dispatched after it commits.
    ``context`` reaches the adapter and is recorded on the run with ``wake_reason``.
    """
    if reason not in EVENT_WAKE_SOURCES:
        raise ValueError(f"{reason!r} is not an event wake source")
    slug = await _wakeable_slug(session, company_id, agent_ref)
    if slug is None:
        return None
    from .heartbeat_scheduler import get_heartbeat_scheduler

    try:
        run, agent = await get_heartbeat_scheduler().trigger_manual(session, slug, source=reason)
    except ValueError as exc:  # unconfigured or refused by the gate: the user's write still stands
        logger.warning("Event wake skipped: agent %s (%s) could not be woken: %s", slug, reason.value, exc)
        return None
    wake_context = {**(context or {}), "wake_reason": reason.value}
    run.context_snapshot = dict(wake_context)
    await session.flush()
    _dispatch_after_commit(session, agent, run.id, wake_context)
    logger.info("Event wake: run %s for agent %s (%s)", run.id, slug, reason.value)
    return run.id


def _dispatch_after_commit(session: AsyncSession, agent: Dict[str, Any], run_id: uuid.UUID, context: Dict) -> None:
    """Queue the dispatch on *session*; it fires on commit and is dropped on rollback.

    ``dispatch_run`` runs synchronously inside the ``after_commit`` hook. A failure is logged, never raised: it
    would make the caller's write look failed after the data is durable. ``dispatch_run`` cannot write a FAILED
    status from this synchronous hook; the run stays QUEUED, stops counting as busy once it is stale, and the
    stalled-run sweep (#16817) closes it out.
    """
    from .heartbeat_scheduler import get_heartbeat_scheduler

    defer_until_commit(
        session,
        lambda: get_heartbeat_scheduler().dispatch_run(agent, run_id, context),
        f"event wake dispatch of run {run_id}",
    )


__all__ = ["EVENT_WAKE_SOURCES", "wake_agent"]
