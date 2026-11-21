# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Audited transitions for pause, resume and terminate (#21375, #21136).

The caller holds the state row's lock (``_get_or_create_state(..., for_update=True)``) and has already
answered "already in that state", so exactly one of two simultaneous requests reaches here per transition.
The order is: ``attempted`` row (a failed write stops everything), state commit, scheduler call, outcome row.
A failed state commit leaves a ``failed`` row. A failed scheduler call restores the row, so the loop and the
row agree, leaves a ``failed`` row, and is surfaced to the caller as a 503. The trail never claims a change
that did not happen.
"""

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
    return {"status": status.value, "paused_reason": reason, "paused_at": now_utc(), "paused_by": actor}


def resume_changes() -> dict[str, Any]:
    """The columns a resume writes: ACTIVE, with the pause record cleared."""
    return {"status": HeartbeatStatus.ACTIVE.value, "paused_reason": None, "paused_at": None, "paused_by": None}


async def _commit_changes(session: AsyncSession, state: AgentRuntimeState, changes: dict[str, Any]) -> None:
    for column, value in changes.items():
        setattr(state, column, value)
    await session.commit()
    await session.refresh(state)


async def _restore(session: AsyncSession, state: AgentRuntimeState, prior: dict[str, Any]) -> bool:
    """Write the prior values back so the row matches the loop that did not change; False when that fails."""
    try:
        await _commit_changes(session, state, prior)
    except Exception as exc:  # noqa: BLE001 -- reported through the outcome row; the caller still gets the 503
        logger.error(
            "heartbeat: could not restore %s after a scheduler failure: %s", state.agent_id, type(exc).__name__
        )
        await session.rollback()
        return False
    return True


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
        restored = await _restore(session, state, prior)
        await record_audit_outcome(event, FAILED, type(exc).__name__ if restored else RECONCILE_FAILED)
        raise HTTPException(status_code=503, detail=SCHEDULER_FAILED_DETAIL) from exc
    await record_audit_outcome(event, SUCCESS)
