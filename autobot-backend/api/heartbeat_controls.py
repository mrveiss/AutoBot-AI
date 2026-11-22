# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Audited transitions for pause, resume and terminate (#21375, #21136).

The caller holds the state row's lock (``_get_or_create_state(..., for_update=True)``) and has already
answered "already in that state", so exactly one of two simultaneous requests reaches here per transition.
The order is: ``attempted`` row (a failed write stops everything), state commit, scheduler call, outcome row.
A failed state commit leaves a ``failed`` row. A failed scheduler call restores the row, so the loop and the
row agree (the state commit released the lock, so the restore re-takes it and leaves a row a newer control has
changed alone), leaves a ``failed`` row, and is surfaced to the caller as a 503. Every control writes a fresh
``control_id``, so a newer control is told apart from this one even when it wrote the same status and actor.
The restore is best-effort: a newer control (``superseded``) or a database error (``reconcile_failed``) leaves
the row as it is, and the ``failed`` row names which. The trail never claims a change that did not happen.
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import now_utc
from models.heartbeat import AgentRuntimeState, HeartbeatStatus
from services.audit.outcome import FAILED, SUCCESS, record_audit_attempt, record_audit_outcome
from services.audit.taxonomy import AuditAction, AuditCategory, AuditEvent, action_name

logger = get_logger(__name__)

SCHEDULER_FAILED_DETAIL = "Scheduler update failed; the change was rolled back"
RECONCILE_FAILED = "reconcile_failed"
SUPERSEDED = "superseded"
#: The columns that identify a transition: if all still hold, nobody has changed the row since. ``control_id``
#: is fresh per control; status and actor also catch a writer outside this module (#21376).
_IDENTITY_COLUMNS = ("control_id", "status", "paused_by")


@dataclass(frozen=True)
class Control:
    """One audited change of an agent's runtime state: who, what, and the column values to write."""

    action: AuditAction
    agent_id: str
    actor: str
    changes: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def event(self) -> AuditEvent:
        return AuditEvent(
            category=AuditCategory.SECURITY,
            action=action_name(self.action),
            actor_id=self.actor,
            resource_type="agent_heartbeat",
            resource_id=self.agent_id,
            metadata={"reason": self.reason} if self.reason else {},
        )


def halt_changes(status: HeartbeatStatus, actor: str, reason: str | None) -> dict[str, Any]:
    """The columns a pause or terminate writes: the new status and who stopped the agent, when and why."""
    halt = {"status": status.value, "paused_reason": reason, "paused_at": now_utc(), "paused_by": actor}
    return {**halt, "control_id": uuid.uuid4()}


def resume_changes() -> dict[str, Any]:
    """The columns a resume writes: ACTIVE, with the pause record cleared."""
    cleared = {"paused_reason": None, "paused_at": None, "paused_by": None, "control_id": uuid.uuid4()}
    return {"status": HeartbeatStatus.ACTIVE.value, **cleared}


async def _commit_changes(session: AsyncSession, state: AgentRuntimeState, changes: dict[str, Any]) -> None:
    for column, value in changes.items():
        setattr(state, column, value)
    await session.commit()
    await session.refresh(state)


async def _restore(
    session: AsyncSession, state: AgentRuntimeState, control: Control, prior: dict[str, Any]
) -> str | None:
    """Write the prior values back under the row lock, only if the row still holds this control's change.

    A concurrent control may have committed since: its newer state is left alone (``superseded``). ``None``
    means restored; otherwise the reason the row was not restored.
    """
    try:
        await session.refresh(state, with_for_update=True)  # re-lock, and re-read what is committed now
        if any(getattr(state, column) != control.changes[column] for column in _IDENTITY_COLUMNS):
            await session.rollback()
            return SUPERSEDED
        await _commit_changes(session, state, {**prior, "control_id": uuid.uuid4()})  # the restore is a control too
    except Exception as exc:  # noqa: BLE001 -- reported through the outcome row; the caller still gets the 503
        logger.error(
            "heartbeat: could not restore %s after a scheduler failure: %s", control.agent_id, type(exc).__name__
        )
        await session.rollback()
        return RECONCILE_FAILED
    return None


async def apply_control(
    session: AsyncSession,
    state: AgentRuntimeState,
    control: Control,
    run_scheduler: Callable[[], Awaitable[None]],
) -> None:
    """Audit, change and schedule one control; see the module docstring for the order and the failure rows."""
    event = control.event()
    prior = {column: getattr(state, column) for column in control.changes}
    await record_audit_attempt(event)
    try:
        await _commit_changes(session, state, control.changes)
    except Exception as exc:
        await session.rollback()
        await record_audit_outcome(event, FAILED, type(exc).__name__)
        raise
    try:
        await run_scheduler()
    except Exception as exc:
        not_restored = await _restore(session, state, control, prior)
        await record_audit_outcome(event, FAILED, not_restored or type(exc).__name__)
        raise HTTPException(status_code=503, detail=SCHEDULER_FAILED_DETAIL) from exc
    await record_audit_outcome(event, SUCCESS)
