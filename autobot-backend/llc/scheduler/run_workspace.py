# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The scheduler's half of the workspace lease (#16818).

Four subprocess adapters each resolve ``workspace_dir`` for themselves. Leasing in
each of them would mean four acquire sites, four release sites, and four chances to
forget one -- which is the shape that produced this defect in the first place: a
directory used everywhere and owned nowhere. So the lease is taken once, in the
scheduler, where the run is created and a session is already open.

The three reasons a workspace comes back are kept distinct on purpose. A run that
ended normally, a run the stalled sweep closed out, and a lease that simply expired
are three different stories, and an audit trail that cannot tell them apart cannot
answer the only question anyone asks of it: why was this workspace taken from me?
"""

import logging
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from llc.services.workspace_lease import (
    WorkspaceCapacityExhausted,
    WorkspaceLeaseHeld,
    acquire_lease,
    release_for_run,
)

logger = logging.getLogger(__name__)

#: Written to a lease released because its run finished. Distinct from the stalled
#: sweep's reason and from an expiry reclaim.
RUN_ENDED_RELEASE_REASON = "run ended ({status}): workspace released by the scheduler (#16818)"


def workspace_dir(agent: Dict[str, Any], context: Optional[Dict[str, Any]]) -> Optional[str]:
    """The workspace this run will use, from adapter config or run context.

    One reader for all four adapters, resolving the same two places they each check.
    """
    config = agent.get("adapter_config")
    if isinstance(config, dict) and config.get("workspace_dir"):
        return str(config["workspace_dir"])
    if context and context.get("workspace_dir"):
        return str(context["workspace_dir"])
    return None


async def acquire_run_workspace(
    session: AsyncSession,
    agent: Dict[str, Any],
    agent_id: str,
    run_id: UUID,
    context: Optional[Dict[str, Any]],
) -> bool:
    """Lease this run's workspace. False means do not dispatch.

    Returning False on a collision is deliberate. Two agents in one worktree corrupt
    each other's work, and that is precisely what the lease exists to prevent --
    dispatching anyway would make the lease a record of the conflict rather than a
    guard against it. The wake is re-queued by the caller, and the lease's own expiry
    is what guarantees a held workspace cannot wedge the agent for ever.

    An agent with no configured workspace leases nothing and dispatches as before.
    """
    path = workspace_dir(agent, context)
    if not path:
        return True
    try:
        await acquire_lease(
            session,
            company_id=agent["company_id"],
            path=path,
            owner=agent_id,
            purpose=f"heartbeat run for agent {agent_id}",
            heartbeat_run_id=run_id,
        )
        return True
    except (WorkspaceLeaseHeld, WorkspaceCapacityExhausted) as exc:
        await session.rollback()
        logger.warning("#16818: heartbeat for agent %s deferred -- %s", agent_id, exc)
        return False


async def release_run_workspace(session: AsyncSession, run_id: UUID, final_status: str) -> None:
    """Hand back whatever the run held, on the normal end of a run.

    The stalled sweep releases what never reaches here; this is the path that returns
    a slot in seconds rather than at the next deadline.
    """
    await release_for_run(session, run_id, RUN_ENDED_RELEASE_REASON.format(status=final_status))


__all__ = ["RUN_ENDED_RELEASE_REASON", "acquire_run_workspace", "release_run_workspace", "workspace_dir"]


async def release_workspace_best_effort(factory: Any, run_id: UUID, final_status: str) -> None:
    """Hand a run's workspace back on an ending that does not reach ``_finish_run``.

    Owns its own session, because the callers are endings that have already written the
    run's status and closed their transaction.

    WHY THIS EXISTS SEPARATELY FROM ``_finish_run`` (#17725 review)
    --------------------------------------------------------------
    ``_finish_run`` is where completed, skipped and adapter-failed runs release. Three
    endings never reach it: the early FAILED path when marking a run RUNNING fails, the
    rate-limited return, and the quota-exhausted return. ``_finish_run``'s docstring
    used to claim releasing there "cannot miss the failure paths", which was false for
    all three. The run is over in every case -- a rate-limited retry is re-dispatched as
    a NEW run that acquires its own lease -- so holding this one keeps the directory
    unusable until the deadline and makes the retry's acquire fail against a lease
    nobody is using. That is the slow version of the bug #16818 exists to fix.

    **There is no ``finally`` covering those paths**, and a blanket one would be wrong:
    each ending releases with a different ``final_status``. So a fourth early exit needs
    this call added explicitly, which
    ``test_every_return_in_run_adapter_is_preceded_by_a_release`` enforces structurally
    rather than by a count.

    NEVER RAISES. The run has already ended and its status is already recorded, so
    failing to release must not turn a recorded outcome into an unhandled exception. A
    missed release is recovered by the expiry sweep -- slow, which is the bug this
    avoids rather than causes.
    """
    try:
        async with factory() as session:
            await release_run_workspace(session, run_id, final_status)
            await session.commit()
    except Exception:
        logger.exception("#16818: could not release workspace for run %s", run_id)
