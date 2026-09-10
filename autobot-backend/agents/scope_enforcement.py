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
import hashlib
import re
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

#: Long enough to stay readable in a claim table, short enough that a Redis key
#: built from several of them stays sane.
_MAX_SEGMENT = 80


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


async def _renew_forever(scopes: Sequence[str], *, agent_id: str, task_id: str, stop=None) -> None:
    """Keep *scopes* alive until cancelled, or until *stop* says the run is over.

    *stop* exists for cancellation. A cancelled task here does not interrupt its
    executor -- `cancel_task` flips a state in Redis and returns -- so the work
    keeps running, and releasing its scope immediately would free a path that is
    still being written. Stopping the RENEWAL instead lets the claim lapse at its
    TTL, which bounds a cancelled task's hold without ever unlocking a scope
    while work continues.

    That is a bound, not a release, and #15950's cancellation criterion is left
    unticked because of it. Cooperative cancellation in the executor is the real
    fix (#16174); this path stays afterwards as the backstop for an executor
    wedged before it reaches any checkpoint.
    """
    from autobot_shared.coordination.work_claims import renew

    interval = max(1, CLAIM_TTL_S // _RENEW_DIVISOR)
    while True:
        await asyncio.sleep(interval)
        if stop is not None:
            try:
                if await stop():
                    logger.info("run %s/%s is over; letting %s lapse at TTL", agent_id, task_id, list(scopes))
                    return
            except Exception as exc:  # noqa: BLE001 -- an unreadable state is no reason to stop renewing
                logger.warning("cancellation check failed for %s/%s: %s", agent_id, task_id, exc)
        for scope in scopes:
            try:
                if not await renew(scope, agent_id=agent_id, task_id=task_id):
                    logger.warning("scope %s was no longer held by %s/%s at renew", scope, agent_id, task_id)
            except Exception as exc:  # noqa: BLE001 -- a renew failure must not kill the run
                logger.warning("renewing scope %s failed: %s", scope, exc)


async def _release_all(scopes: Sequence[str], *, agent_id: str, task_id: str) -> None:
    """Release every scope, surviving individual failures.

    An ordinary exception from one release is logged and never raised; the TTL
    expires that claim. Cancellation still propagates.
    """
    from autobot_shared.coordination.work_claims import release

    for scope in scopes:
        try:
            await release(scope, agent_id=agent_id, task_id=task_id)
        except Exception as exc:  # noqa: BLE001 -- see the module docstring
            logger.warning("releasing scope %s failed; its TTL will expire it: %s", scope, exc)


async def _acquire_all(scopes: Sequence[str], *, agent_id: str, task_id: str, intent: str) -> ScopesHeld:
    """Take every scope or none, reporting the first refusal with its holder.

    A raise part-way through releases the scopes already taken before it
    propagates, so a malformed later declaration strands nothing (#16213).
    """
    from autobot_shared.coordination.work_claims import try_acquire

    taken: list[Claim] = []
    try:
        for scope in scopes:
            outcome = await try_acquire(
                scope, agent_id=agent_id, task_id=task_id, mode=ClaimMode.EXCLUSIVE, intent=intent
            )
            if isinstance(outcome, ClaimConflict):
                await _release_all([c.scope for c in taken], agent_id=agent_id, task_id=task_id)
                return ScopesHeld(claims=(), conflict=outcome)
            taken.append(outcome)
    except BaseException:
        # A raise mid-loop -- a malformed later scope (ScopeError from Scope.parse)
        # or a store error -- must not strand the scopes already taken until their
        # TTL: "every scope or none" holds on the raising path too (#16213 review).
        await _release_all([c.scope for c in taken], agent_id=agent_id, task_id=task_id)
        raise
    return ScopesHeld(claims=tuple(taken))


def scope_segment(text: str) -> str:
    """Turn arbitrary text into one scope segment the grammar will accept.

    Scopes are `<kind>:<segment>/<segment>` with segments matching
    `[A-Za-z0-9._@+-]+`, but the things agents write are named by humans -- a
    knowledge-base title, a topic, a filename with spaces. Declaring a scope
    therefore needs a normalisation step, and it needs one that CANNOT fail:
    an agent whose declaration raises would be an agent that stops working
    because someone used an apostrophe.

    So the fallback is a hash rather than an exception or an empty string.
    Empty would mean "declared nothing", which is silently no protection at
    exactly the inputs that are strangest -- the failure mode this module
    exists to remove. A hash is opaque to a human reading the claim table, but
    it is stable, unique, and it still collides for two agents writing the same
    title, which is the collision that matters.
    """
    cleaned = re.sub(r"[^A-Za-z0-9._@+-]+", "-", text).strip("-")
    if cleaned:
        return cleaned[:_MAX_SEGMENT]
    return "x-" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


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
