# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Hold the scopes a run declared, for exactly as long as the run lasts (#15950).

Layer 1 (#15947) made claiming possible and #15949 made it visible. This makes it
the path agents actually take, which is what turns "two agents overwrite each
other" from discouraged into refused.

FOUR THINGS THIS GETS RIGHT AND A NAIVE VERSION GETS WRONG.

*Partial acquisition is released, not kept.* A run declaring three scopes and
winning two has not started work -- keeping the two would block other agents on
behalf of a run that never ran, and two such runs can hold each other's missing
scope forever. Anything already taken is released before the conflict is
reported.

*The renewal is tied to the run, not to a timer.* Claims carry a TTL so a crashed
holder cannot hold forever. A long run must therefore renew, and the renew must
stop when the run does -- including when it dies. Cancelling the renewal task in
``finally`` stops renewal when the run ends. It does nothing for a run that is
alive but hung: that run never reaches ``finally``, which is the fourth point.

*A failed release is logged, never raised.* Release runs in ``finally``, so an
exception there would replace the real outcome of the run -- a claim-registry
error masquerading as a task failure. The TTL is the backstop that makes this
safe to swallow.

*Renewal follows progress, and a lapsed claim refuses writes (#15950).* A run
that is alive but hung used to renew forever. Renewal now stops once the run has
reported no progress for the stall window, and the claim lapses at TTL.
Progress is reported at checkpoints every run passes through: each LLM
attempt, retries included, a tool SDK execution, and a write site's own check. So a slow run
that keeps working keeps its claim, and only silence lets one lapse. A write
site calls ``require_held`` first, and a lapsed claim refuses the write, rather
than letting a run that stalled and woke up write over a scope someone else may
now hold.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import re
import time
from dataclasses import dataclass
from typing import AsyncIterator, Sequence

from autobot_shared.coordination.run_progress import ClaimedRun, bound, current_run, record_progress
from autobot_shared.coordination.work_claims import (
    CLAIM_TTL_S,
    Claim,
    ClaimConflict,
    ClaimMode,
    ClaimUnavailable,
    Scope,
    conflict_payload,
)
from autobot_shared.env_utils import env_int_clamped
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config

logger = get_logger(__name__)

#: Renew at a third of the TTL: two consecutive renew failures still leave a
#: full third of the window to recover before the claim lapses. Renewing at the
#: TTL itself would mean the first missed renew loses the scope mid-run.
_RENEW_DIVISOR = 3

#: Long enough to stay readable in a claim table, short enough that a Redis key
#: built from several of them stays sane.
_MAX_SEGMENT = 80

#: How many renewal intervals a run may go without reporting progress before its
#: claims stop being renewed and lapse (#15950 AC4, owner ruling).
STALL_INTERVALS = env_int_clamped("AUTOBOT_WORK_CLAIM_STALL_INTERVALS", 3, min_v=2, max_v=100)


class ClaimNotHeld(RuntimeError):
    """A write was attempted under a claim that is not, or no longer, held (#15950 AC6)."""


def _longest_backoff_wait_s() -> float:
    """The longest single wait the LLM backoff imposes between attempts: its cap plus full jitter."""
    from llm_shared.rate_limit_backoff import get_backoff_handler

    backoff = get_backoff_handler().config
    return backoff.max_delay * (1 + backoff.jitter_factor)


def _stall_window_s(interval: float) -> float:
    """Seconds without progress before a run counts as stalled.

    A model call reports progress as each attempt ends, so the longest silence
    of a working call is one backoff wait plus one request: at most twice the
    larger of the backoff's cap-plus-jitter and the LLM request timeout. The
    window is never shorter than that, or it would lapse a run doing exactly
    what it should, including one waiting out a provider's rate limit (owner
    ruling, #15950). Both bounds are read from configuration, so this stays
    true when either changes.
    """
    return max(STALL_INTERVALS * interval, 2 * max(float(config.timeout.llm_request), _longest_backoff_wait_s()))


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


async def _run_is_over(stop, *, agent_id: str, task_id: str, scopes: Sequence[str]) -> bool:
    """The cancellation check: True once *stop* says the run is over."""
    if stop is None:
        return False
    try:
        if await stop():
            logger.info("run %s/%s is over; letting %s lapse at TTL", agent_id, task_id, list(scopes))
            return True
    except Exception as exc:  # noqa: BLE001 -- an unreadable state is no reason to stop renewing
        logger.warning("cancellation check failed for %s/%s: %s", agent_id, task_id, exc)
    return False


async def _renew_round(scopes: Sequence[str], *, agent_id: str, task_id: str) -> bool:
    """Renew every scope. False when one was found no longer held by this run."""
    from autobot_shared.coordination.work_claims import renew

    all_held = True
    for scope in scopes:
        try:
            if not await renew(scope, agent_id=agent_id, task_id=task_id):
                logger.warning("scope %s was no longer held by %s/%s at renew", scope, agent_id, task_id)
                all_held = False
        except Exception as exc:  # noqa: BLE001 -- a renew failure must not kill the run
            logger.warning("renewing scope %s failed: %s", scope, exc)
    return all_held


async def _renew_forever(
    scopes: Sequence[str], *, agent_id: str, task_id: str, stop=None, run: ClaimedRun | None = None
) -> None:
    """Keep *scopes* alive while the run makes progress; stop when it ends or stalls.

    *stop* exists for cancellation, which does not interrupt the executor
    (`cancel_task` flips a Redis state and returns), so releasing at once would
    free a path still being written; stopping the RENEWAL lets the claim lapse
    at TTL instead. Cooperative cancellation is the real fix (#16174).

    *run* ties renewal to progress (#15950 AC4). No progress for the stall
    window, or a renew that finds a claim gone, stops renewal and lapses the
    run, so its claims expire at TTL and a late write is refused. Losing one
    scope stops renewing all of them: a run holds every declared scope or none.
    """
    interval = max(1, CLAIM_TTL_S // _RENEW_DIVISOR)
    window = _stall_window_s(interval)
    while True:
        await asyncio.sleep(interval)
        if await _run_is_over(stop, agent_id=agent_id, task_id=task_id, scopes=scopes):
            return
        if run is not None and time.monotonic() - run.last_progress > window:
            run.lapse(f"no progress for {window:.0f}s")
            logger.warning(
                "run %s/%s reported no progress for %.0fs; %s lapse at TTL", agent_id, task_id, window, list(scopes)
            )
            return
        if not await _renew_round(scopes, agent_id=agent_id, task_id=task_id) and run is not None:
            run.lapse("a renew found the claim no longer held")
            return


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
    lossy summary of it. The metadata is the shared refusal shape (#16208).

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
        metadata=conflict_payload(conflict),
    )


async def _acquire_or_degrade(scopes: Sequence[str], *, agent_id: str, task_id: str, intent: str) -> ScopesHeld | None:
    """Take every scope or none; None when the registry is unavailable and the run goes unclaimed."""
    try:
        return await _acquire_all(scopes, agent_id=agent_id, task_id=task_id, intent=intent)
    except ClaimUnavailable:
        # Redis is down. Refusing every run would make the coordination layer a
        # single point of failure for work it only advises on, so the run
        # proceeds unclaimed and says so loudly -- and write sites see "degraded".
        logger.error(
            "work-claim registry unavailable; %s/%s runs WITHOUT claims on %s", agent_id, task_id, list(scopes)
        )
        return None


@contextlib.asynccontextmanager
async def _renewing(scopes: Sequence[str], *, agent_id: str, task_id: str, stop) -> AsyncIterator[None]:
    """Bind a held run for the body, renew its scopes throughout, and release them on any exit.

    The run is marked ended before its scopes are released, so a task spawned
    inside it that outlives the body is refused by :func:`require_held` rather
    than writing under a claim that no longer exists.
    """
    run = ClaimedRun(frozenset(scopes))
    with bound(run):
        renewer = asyncio.create_task(_renew_forever(scopes, agent_id=agent_id, task_id=task_id, stop=stop, run=run))
        try:
            yield
        finally:
            run.lapse("the run ended and released its claim")
            renewer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await renewer
            await _release_all(scopes, agent_id=agent_id, task_id=task_id)


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
    held = await _acquire_or_degrade(scopes, agent_id=agent_id, task_id=task_id, intent=intent)
    if held is None:
        with bound(ClaimedRun(frozenset(scopes), standing="degraded")):
            yield ScopesHeld(claims=())
    elif not held.granted:
        yield held
    else:
        async with _renewing(scopes, agent_id=agent_id, task_id=task_id, stop=stop):
            yield held


def _covers(held: str, wanted: str) -> bool:
    """True when claiming *held* entitles a write to *wanted*: the same scope or an ancestor."""
    h, w = Scope.parse(held), Scope.parse(wanted)
    return h.kind == w.kind and (w.path == h.path or w.path.startswith(h.path + "/"))


def require_held(scopes: Sequence[str], *, site: str) -> None:
    """Refuse a write the current run does not, or no longer, hold a claim for (#15950 AC6).

    The owner's ruling, by the run's standing:

    * held, and a held scope covers the write: allow.
    * lapsed (it stalled, or a renew found the claim gone): **refuse**.
    * degraded (the registry was unavailable): allow, and log.
    * no claimed run at all: allow, with a named warning.

    The last case is a dispatcher that ran the agent without holding its declared
    scopes (#16269). It is warned rather than refused until every dispatcher holds
    them, because refusing now would break live writes on those paths. A write
    that passes the check is itself progress.
    """
    if not scopes:
        return
    run = current_run()
    if run is None:
        logger.warning(
            "UNCLAIMED WRITE at %s: no work claim is held for %s (dispatcher bypasses hold_scopes, #16269)",
            site,
            list(scopes),
        )
        return
    if run.standing == "degraded":
        logger.warning("write at %s proceeds unclaimed: the claim registry was unavailable (%s)", site, list(scopes))
        return
    _refuse_uncovered(run, scopes, site=site)
    record_progress()


def _refuse_uncovered(run: ClaimedRun, scopes: Sequence[str], *, site: str) -> None:
    """Raise :class:`ClaimNotHeld` for any scope that no held run in *run*'s chain covers."""
    live = [s for r in run.chain() if r.standing == "held" for s in r.scopes]
    uncovered = [s for s in scopes if not any(_covers(h, s) for h in live)]
    if uncovered:
        reason = next((r.lapse_reason for r in run.chain() if r.standing == "lapsed"), "")
        raise ClaimNotHeld(
            f"write at {site} refused: {uncovered} not held" + (f" (claim lapsed: {reason})" if reason else "")
        )
