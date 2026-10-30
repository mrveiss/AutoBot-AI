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
from dataclasses import dataclass
from typing import Any, Dict, Optional, Union

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, SessionTransaction

from autobot_shared.logging_manager import get_logger

from ..models.enums import UNDISPATCHABLE_AGENT_STATUSES, HeartbeatInvocationSource
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

_PENDING_KEY = "llc_event_wake_pending"
_HOOKED_KEY = "llc_event_wake_hooked"


@dataclass
class _PendingDispatch:
    agent: Dict[str, Any]
    run_id: uuid.UUID
    context: Dict[str, Any]
    transaction: Optional[SessionTransaction]


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
    except Exception:  # the gate could not read its inputs: no run starts, and the write still stands
        logger.exception("Event wake skipped: agent %s (%s) could not be judged", slug, reason.value)
        return None
    wake_context = {**(context or {}), "wake_reason": reason.value}
    run.context_snapshot = dict(wake_context)
    await session.flush()
    _dispatch_after_commit(session, agent, run.id, wake_context)
    logger.info("Event wake: run %s for agent %s (%s)", run.id, slug, reason.value)
    return run.id


def _dispatch_after_commit(session: AsyncSession, agent: Dict[str, Any], run_id: uuid.UUID, context: Dict) -> None:
    """Queue the dispatch on *session*; it fires on commit and is dropped on rollback."""
    sync = session.sync_session
    if not sync.info.get(_HOOKED_KEY):
        event.listen(sync, "after_commit", _on_commit)
        event.listen(sync, "after_soft_rollback", _on_rollback)
        sync.info[_HOOKED_KEY] = True
    txn = sync.get_nested_transaction() or sync.get_transaction()
    sync.info.setdefault(_PENDING_KEY, []).append(_PendingDispatch(agent, run_id, context, txn))


def _on_commit(sync: Session) -> None:
    """Dispatch every queued wake; a dispatch that raises is logged, never raised.

    This runs inside ``commit()`` after the data is durable, so an exception here
    would make the caller's write look failed when it succeeded. ``dispatch_run``
    cannot write a FAILED status from this synchronous hook; the run stays QUEUED,
    stops counting as busy once it is stale, and the stalled-run sweep (#16817)
    closes it out.
    """
    from .heartbeat_scheduler import get_heartbeat_scheduler

    for wake in sync.info.pop(_PENDING_KEY, []):
        try:
            get_heartbeat_scheduler().dispatch_run(wake.agent, wake.run_id, wake.context)
        except Exception:
            logger.exception("Event wake: dispatch of run %s failed after commit", wake.run_id)


def _within(txn: Optional[SessionTransaction], ancestor: SessionTransaction) -> bool:
    while txn is not None:
        if txn is ancestor:
            return True
        txn = txn.parent
    return False


def _on_rollback(sync: Session, previous_transaction: SessionTransaction) -> None:
    """Drop the dispatches whose run row this rollback (outer or savepoint) undid."""
    pending = sync.info.get(_PENDING_KEY, [])
    pending[:] = [wake for wake in pending if not _within(wake.transaction, previous_transaction)]


__all__ = ["EVENT_WAKE_SOURCES", "wake_agent"]
