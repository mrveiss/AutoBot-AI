# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Hold the scopes a run declared, for exactly as long as the run lasts (#15950).

Layer 1 (#15947) made claiming possible and #15949 made it visible. This makes it
the path agents actually take, which is what turns "two agents overwrite each
other" from discouraged into refused.

THREE THINGS THIS GETS RIGHT AND A NAIVE VERSION GETS WRONG.

*Partial acquisition is released, not kept.* A run declaring three scopes and
winning two has not started work -- keeping the two would block other agents on
behalf of a run that never ran, and two such runs can hold each other's missing
scope forever. Anything already taken is released before the conflict is
reported.

*The renewal is tied to the run, not to a timer.* Claims carry a TTL so a crashed
holder cannot hold forever. A long run must therefore renew, and the renew must
stop when the run does -- including when it dies. Cancelling the renewal task in
``finally`` is what makes a hung executor's scope free itself rather than being
renewed forever by a loop nobody is watching.

*A failed release is logged, never raised.* Release runs in ``finally``, so an
exception there would replace the real outcome of the run -- a claim-registry
error masquerading as a task failure. The TTL is the backstop that makes this
safe to swallow.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from typing import AsyncIterator, Sequence

from autobot_shared.coordination.work_claims import (
    CLAIM_TTL_S,
    Claim,
    ClaimConflict,
    ClaimMode,
    ClaimUnavailable,
)
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

#: Renew at a third of the TTL: two consecutive renew failures still leave a
#: full third of the window to recover before the claim lapses. Renewing at the
#: TTL itself would mean the first missed renew loses the scope mid-run.
_RENEW_DIVISOR = 3


@dataclass(frozen=True)
class ScopesHeld:
    """The outcome of trying to hold a run's declared scopes.

    ``conflict`` is None when every scope was won. When it is set, nothing is
    held -- see the partial-acquisition rule in the module docstring.
    """

    claims: tuple[Claim, ...]
    conflict: ClaimConflict | None = None

    @property
    def granted(self) -> bool:
        return self.conflict is None


async def _renew_forever(scopes: Sequence[str], *, agent_id: str, task_id: str) -> None:
    """Keep *scopes* alive until cancelled. Cancellation is the normal exit."""
    from autobot_shared.coordination.work_claims import renew

    interval = max(1, CLAIM_TTL_S // _RENEW_DIVISOR)
    while True:
        await asyncio.sleep(interval)
        for scope in scopes:
            try:
                if not await renew(scope, agent_id=agent_id, task_id=task_id):
                    logger.warning("scope %s was no longer held by %s/%s at renew", scope, agent_id, task_id)
            except Exception as exc:  # noqa: BLE001 -- a renew failure must not kill the run
                logger.warning("renewing scope %s failed: %s", scope, exc)


async def _release_all(scopes: Sequence[str], *, agent_id: str, task_id: str) -> None:
    """Release every scope, surviving individual failures. Never raises."""
    from autobot_shared.coordination.work_claims import release

    for scope in scopes:
        try:
            await release(scope, agent_id=agent_id, task_id=task_id)
        except Exception as exc:  # noqa: BLE001 -- see the module docstring
            logger.warning("releasing scope %s failed; its TTL will expire it: %s", scope, exc)


async def _acquire_all(scopes: Sequence[str], *, agent_id: str, task_id: str, intent: str) -> ScopesHeld:
    """Take every scope or none, reporting the first refusal with its holder."""
    from autobot_shared.coordination.work_claims import try_acquire

    taken: list[Claim] = []
    for scope in scopes:
        outcome = await try_acquire(scope, agent_id=agent_id, task_id=task_id, mode=ClaimMode.EXCLUSIVE, intent=intent)
        if isinstance(outcome, ClaimConflict):
            await _release_all([c.scope for c in taken], agent_id=agent_id, task_id=task_id)
            return ScopesHeld(claims=(), conflict=outcome)
        taken.append(outcome)
    return ScopesHeld(claims=tuple(taken))


def refused_response(request, conflict: ClaimConflict, *, agent_type: str):
    """A refusal that names who holds the scope and what they are doing there.

    Not a bare error: the operator's next question is always "blocked by what?",
    and a run that fails without answering it has turned a coordination event
    into a mystery. `ClaimConflict.__str__` already renders holder, task, mode,
    expiry and intent, so the message is the conflict itself rather than a
    lossy summary of it.

    Imported lazily to keep this module importable from `base_agent`, which is
    where `AgentResponse` lives.
    """
    from agents.base_agent_types import AgentResponse

    logger.info("Agent %s refused: %s", agent_type, conflict)
    return AgentResponse(
        request_id=request.request_id,
        agent_type=agent_type,
        status="refused",
        result=None,
        error=str(conflict),
        metadata={
            "refused_scope": conflict.requested,
            "held_by_agent": conflict.holder.agent_id,
            "held_by_task": conflict.holder.task_id,
            "holder_intent": conflict.holder.intent,
            "holder_expires_at": conflict.holder.expires_at,
        },
    )


@contextlib.asynccontextmanager
async def hold_scopes(
    scopes: Sequence[str], *, agent_id: str, task_id: str, intent: str, stop=None
) -> AsyncIterator[ScopesHeld]:
    """Hold *scopes* for the body, renewing throughout and releasing on any exit.

    Yields a :class:`ScopesHeld` whose ``granted`` is False when the scopes could
    not all be taken; the body decides what to do about that. Refusal is yielded
    rather than raised because "someone else is working here" is an ordinary
    answer, and the caller owes the operator a result that says so.

    An empty *scopes* is a no-op that still yields a granted result: an agent
    declaring nothing is the default, and it must not pay for the registry.
    """
    if not scopes:
        yield ScopesHeld(claims=())
        return

    try:
        held = await _acquire_all(scopes, agent_id=agent_id, task_id=task_id, intent=intent)
    except ClaimUnavailable:
        # Redis is down. Refusing every run would make the coordination layer a
        # single point of failure for work it only advises on, so the run
        # proceeds unclaimed and says so loudly.
        logger.error(
            "work-claim registry unavailable; %s/%s runs WITHOUT claims on %s", agent_id, task_id, list(scopes)
        )
        yield ScopesHeld(claims=())
        return

    if not held.granted:
        yield held
        return

    renewer = asyncio.create_task(_renew_forever(scopes, agent_id=agent_id, task_id=task_id, stop=stop))
    try:
        yield held
    finally:
        renewer.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await renewer
        await _release_all(scopes, agent_id=agent_id, task_id=task_id)
