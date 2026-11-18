# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Run status transitions for a heartbeat run (#16818, #620).

Sits beside `run_context` and `run_workspace`: one small module per per-run concern,
rather than another few dozen lines inside the scheduler.
"""

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import exists, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from autobot_shared.logging_manager import get_logger
from models.agent_org import AgentOrgNode

from ..models.enums import LLCRunStatus
from ..models.heartbeat_run import LLCHeartbeatRun
from .stalled_run_sweep import run_age_anchor, stall_cutoff

logger = get_logger(__name__)

#: A run in one of these states is "this agent is already being worked" (#19582): an
#: event wake is not started beside it, the same rule replay and the comment wake had.
ACTIVE_RUN_STATUSES = (LLCRunStatus.QUEUED.value, LLCRunStatus.RUNNING.value)

#: Written to a run that lost the claim to another RUNNING run of the same agent.
SUPERSEDED_REASON = "superseded: the agent already has a RUNNING run (#19582)"


class RunSuperseded(Exception):
    """The run was not started: another run of the same agent is RUNNING (#19582)."""


async def latest_run_in(
    session: AsyncSession, agent_id: str, statuses: tuple, *extra: Any
) -> Optional[LLCHeartbeatRun]:
    """The newest run of *agent_id* whose status is in *statuses* (and *extra*), or ``None``.

    One finder for the scheduler's rate-limited resume and the event wake's
    active-run check (:func:`active_run`), instead of one query per caller.
    """
    result = await session.execute(
        select(LLCHeartbeatRun)
        .where(LLCHeartbeatRun.agent_id == agent_id, LLCHeartbeatRun.status.in_(statuses), *extra)
        .order_by(LLCHeartbeatRun.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def is_live(entity: Any = LLCHeartbeatRun) -> Any:
    """SQL: the run is younger than the stalled-run sweep's deadline (#19582 review).

    A QUEUED or RUNNING row left behind by a crash or restart is not the agent being
    busy -- counting it would SKIP every later run and every wake for ever. The age
    and the deadline are the sweep's own (#16817), which owns closing such rows out;
    this check only stops them blocking, it never reaps.
    """
    return run_age_anchor(entity) > stall_cutoff()


async def active_run(session: AsyncSession, agent_id: str) -> Optional[LLCHeartbeatRun]:
    """The newest live QUEUED or RUNNING run of *agent_id*: the agent is busy."""
    return await latest_run_in(session, agent_id, ACTIVE_RUN_STATUSES, is_live())


def _claim_running(run_id: UUID) -> Any:
    """UPDATE that marks *run_id* RUNNING only while no OTHER live run of its agent is RUNNING.

    This is the per-agent claim (#19582): a tick and an event can each create a run,
    but only one of them can hold RUNNING, so the two never run the agent at once.
    It is race-free only under :func:`_lock_agent`, which :func:`claim_running` takes.
    """
    other = aliased(LLCHeartbeatRun)
    busy = exists().where(
        other.agent_id == LLCHeartbeatRun.agent_id,
        other.status == LLCRunStatus.RUNNING.value,
        other.id != run_id,
        is_live(other),
    )
    return (
        update(LLCHeartbeatRun)
        .where(LLCHeartbeatRun.id == run_id, ~busy)
        .values(status=LLCRunStatus.RUNNING.value, started_at=datetime.now(tz=timezone.utc))
        .execution_options(synchronize_session=False)
    )


async def _lock_agent(session: AsyncSession, agent_id: str) -> None:
    """Row-lock the agent's ``agent_org_nodes`` row until this transaction ends.

    Serializes claims per agent (#19582 review). Without it, two claims for
    different runs of one agent each evaluate ``NOT EXISTS`` against a snapshot that
    predates the other's uncommitted RUNNING, and under READ COMMITTED both win. With
    it, the second claim waits for the first to commit, and its UPDATE -- a new
    statement, so a new snapshot -- sees that RUNNING row. SQLite renders no
    ``FOR UPDATE``; it serializes writers on the database lock instead.
    """
    await session.execute(
        select(AgentOrgNode.id).where(AgentOrgNode.agent_id == agent_id).order_by(AgentOrgNode.id).with_for_update()
    )


async def claim_running(session: AsyncSession, run_id: UUID, agent_id: str) -> bool:
    """Take the per-agent RUNNING claim for *run_id* in *session*; the caller commits."""
    await _lock_agent(session, agent_id)
    claimed = await session.execute(_claim_running(run_id))
    return claimed.rowcount != 0


async def _mark_superseded(session: AsyncSession, run_id: UUID) -> None:
    """Close out a run that lost the claim as SKIPPED, with the reason on the row."""
    await session.execute(
        update(LLCHeartbeatRun)
        .where(LLCHeartbeatRun.id == run_id)
        .values(status=LLCRunStatus.SKIPPED.value, finished_at=datetime.now(tz=timezone.utc), error=SUPERSEDED_REASON)
    )
    await session.commit()
    logger.info("Run %s not started: %s", run_id, SUPERSEDED_REASON)


async def mark_running(factory: Any, run_id: UUID) -> Optional[int]:
    """Read `retry_count`, then mark the run RUNNING. ``None`` if that failed.

        The read comes first so backoff is computed from the count before this attempt.
        On failure the run is marked FAILED here -- the status write belongs with the
        attempt that failed -- but the workspace release does NOT: the caller owns that,
        so that every exit from `_run_adapter` has its release where a reader of
        `_run_adapter` can see it. Extracted from that function to keep it inside the
        65-line limit (#620), and placed beside `run_context` and `run_workspace`, which hold the
    other per-run concerns.

    Raises :class:`RunSuperseded` (after marking the run SKIPPED) when another run of
    the same agent is already RUNNING -- see :func:`_claim_running` (#19582).
    """
    try:
        async with factory() as session:
            retry_count = await _claim_or_supersede(session, run_id)
            await session.commit()
        return retry_count
    except RunSuperseded:
        raise
    except Exception as exc:
        logger.exception("Failed to mark run %s as RUNNING — marking FAILED", run_id)
        await _mark_failed(factory, run_id, exc)
        return None


async def _claim_or_supersede(session: AsyncSession, run_id: UUID) -> int:
    """The run's `retry_count` once it holds RUNNING; :class:`RunSuperseded` if it lost."""
    result = await session.execute(
        select(LLCHeartbeatRun.retry_count, LLCHeartbeatRun.agent_id).where(LLCHeartbeatRun.id == run_id)
    )
    row = result.first()
    if not await claim_running(session, run_id, row.agent_id if row else ""):
        await _mark_superseded(session, run_id)
        raise RunSuperseded(SUPERSEDED_REASON)
    return (row.retry_count if row else 0) or 0


async def _mark_failed(factory: Any, run_id: UUID, exc: Exception) -> None:
    """Write FAILED for a run whose RUNNING claim raised; a second failure is only logged."""
    try:
        async with factory() as session:
            await session.execute(
                update(LLCHeartbeatRun)
                .where(LLCHeartbeatRun.id == run_id)
                .values(status=LLCRunStatus.FAILED.value, finished_at=datetime.now(tz=timezone.utc), error=str(exc))
            )
            await session.commit()
    except Exception:
        logger.exception("Could not write FAILED status for run %s", run_id)
