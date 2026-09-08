# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unlanded changes keep a scope spoken for, and stewardship transfers (#15987).

`work_claims` (#15947) answers "is another agent touching this right now" and
frees the scope when the task ends. That is correct and it is half the problem.

The other half: the task ends, the claim frees, **the change is still unmerged**.
Base is untouched, so a second agent claims the same scope, branches from base,
and edits the same file for a different reason. Whichever PR merges second either
conflicts -- loud, fixable -- or merges cleanly and produces a file neither
author reviewed. The clean merge is the dangerous one, because each PR earned a
green run against a base that did not contain the other.

THE LOCK IS THE BRANCH, NOT THE SESSION, and this is the decision everything
else follows from. A session is not a durable holder: on 2026-09-07 a census of
this repository's worktrees found 13 of 17 belonged to sessions that were offline
or ended. A lock keyed to a session would have held those scopes with nobody
alive to release it, which is exactly the failure the TTL rule in
:mod:`~autobot_shared.coordination.work_claims` exists to prevent. A branch's end
condition -- merged, or closed -- is externally observable rather than a timer.

So the branch holds the interest, a session is only its **steward**, and
stewardship transfers.

AN INTEREST NEVER REFUSES A CLAIM. Blocking work because someone has an open PR
would serialise the whole fleet behind review. :func:`acquire_aware` grants the
claim and hands back what else is in flight, so the second agent decides: take
the handoff, or proceed knowing what it is about to collide with.

WHY THERE IS NO TTL HERE. A claim expires because its holder may die; an
interest ends because its branch merges or closes, and that is a fact someone
can look up. But this package cannot look it up -- `autobot_shared` has no
GitHub client and must not grow one -- so :func:`prune` takes the set of live
branches from a caller that does have one. The backstop TTL exists only so an
abandoned record cannot outlive the repository; it is deliberately long enough
that it never fires in a healthy fleet, and a record reaching it means nobody
called :func:`prune`, not that the branch was abandoned.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any, Iterable

from autobot_shared.coordination.work_claims import (
    Claim,
    ClaimConflict,
    ClaimMode,
    ClaimUnavailable,
    Scope,
    try_acquire,
)
from autobot_shared.env_utils import env_int_clamped
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.time_utils import now_utc

logger = get_logger(__name__)

#: Backstop only. An interest ends when its branch merges or closes; this exists
#: so a record whose branch nobody ever pruned cannot outlive the repository.
#: Reaching it means `prune` was never called, not that the work was abandoned.
INTEREST_TTL_S = env_int_clamped("AUTOBOT_BRANCH_INTEREST_TTL_S", 1209600, min_v=3600, max_v=7776000)

#: How many times one branch may be handed on before it must land. An unbounded
#: chain recreates, inside a single branch, the pile the worktree ceiling exists
#: to prevent -- work accreting on something that never merges, and less visible
#: there than as separate branches.
MAX_HANDOFFS = env_int_clamped("AUTOBOT_STEWARDSHIP_MAX_HANDOFFS", 3, min_v=1, max_v=20)

_INTEREST_KEY = "branch_interest:{kind}:{path}:{branch}"
_INDEX_KEY = "branch_interest:idx:{kind}"


class HandoffRefused(RuntimeError):
    """A handoff the receiving side declined, or that the chain limit stopped."""


class EmptyLiveSet(RuntimeError):
    """:func:`prune` was handed no live branches without being told to expect that.

    A subclass of ``RuntimeError`` so an existing broad ``except`` keeps working,
    and named after the condition rather than the caller's mistake, because both
    a genuine "nothing is open" and a failed fetch arrive here identically -- that
    is the whole reason it must be said out loud rather than inferred.

    Mirrors ``tools/lint/_scan_helpers.EmptyEnumeration`` (#15962), which refuses
    to report an empty enumeration as a clean tree for the same reason.
    """


@dataclass(frozen=True)
class Interest:
    """An unlanded branch's stake in a scope, and who is currently carrying it."""

    scope: str
    branch: str
    steward: str
    intent: str
    declared_at: str
    #: Every steward so far, oldest first. The chain is the audit trail and the
    #: bound: ``len(handoffs) - 1`` is how many times this has changed hands.
    handoffs: tuple[str, ...]

    @property
    def hops(self) -> int:
        return max(0, len(self.handoffs) - 1)

    def __str__(self) -> str:
        return f"{self.scope} held unlanded on branch {self.branch} by {self.steward}: {self.intent}"


async def _redis() -> Any:
    client = await get_async_redis_client(database="main")
    if client is None:
        raise ClaimUnavailable("branch_stewardship: Redis unavailable; in-flight interest cannot be trusted")
    return client


def _decode(raw: bytes | str) -> Interest:
    if isinstance(raw, bytes):
        raw = raw.decode()
    data = json.loads(raw)
    data["handoffs"] = tuple(data.get("handoffs", ()))
    return Interest(**data)


def _member(scope: Scope, branch: str) -> str:
    return f"{scope.path}|{branch}"


async def declare(
    scope: str | Scope,
    *,
    branch: str,
    steward: str,
    intent: str,
) -> Interest:
    """Record that *branch* has unlanded changes to *scope*.

    Called when a branch first touches a scope, not when its PR opens: the
    window this closes starts at the first edit, and a change that is committed
    but not yet pushed is exactly as invisible to another agent as one that is.
    """
    parsed = Scope.parse(scope)
    if not branch.strip() or not steward.strip():
        raise ValueError(f"branch and steward must be non-empty; got {branch!r}, {steward!r}")
    interest = Interest(
        scope=str(parsed),
        branch=branch,
        steward=steward,
        intent=intent,
        declared_at=now_utc().isoformat(),
        handoffs=(steward,),
    )
    client = await _redis()
    key = _INTEREST_KEY.format(kind=parsed.kind, path=parsed.path, branch=branch)
    await client.set(key, json.dumps(asdict(interest)), ex=INTEREST_TTL_S)
    await client.sadd(_INDEX_KEY.format(kind=parsed.kind), _member(parsed, branch))
    return interest


async def interests(scope: str | Scope) -> list[Interest]:
    """Every unlanded branch with a stake in *scope* or a scope overlapping it.

    Overlap is `Scope.overlaps`, so a branch holding a parent path is returned
    for a child scope. Records whose key has gone are pruned from the index on
    read, as claims are.
    """
    parsed = Scope.parse(scope)
    client = await _redis()
    index = _INDEX_KEY.format(kind=parsed.kind)
    found: list[Interest] = []
    for member in await client.smembers(index):
        member = member.decode() if isinstance(member, bytes) else member
        path, _, branch = member.partition("|")
        raw = await client.get(_INTEREST_KEY.format(kind=parsed.kind, path=path, branch=branch))
        if raw is None:
            await client.srem(index, member)
            continue
        if Scope(kind=parsed.kind, path=path).overlaps(parsed):
            found.append(_decode(raw))
    return found


async def acquire_aware(
    scope: str | Scope,
    *,
    agent_id: str,
    task_id: str,
    mode: ClaimMode = ClaimMode.EXCLUSIVE,
    intent: str,
) -> tuple[Claim | ClaimConflict, list[Interest]]:
    """Acquire *scope*, and report what unlanded work already touches it.

    **The interest never refuses the claim.** Blocking on an open PR would
    serialise the fleet behind review; the point is that the second agent finds
    out *before* editing rather than at merge time, and can then take a handoff
    or proceed deliberately.
    """
    outcome = await try_acquire(scope, agent_id=agent_id, task_id=task_id, mode=mode, intent=intent)
    return outcome, await interests(scope)


async def transfer(
    scope: str | Scope,
    *,
    branch: str,
    to_steward: str,
    accepted: bool,
) -> Interest:
    """Hand stewardship of *branch* to *to_steward*, if they accept.

    *accepted* is the receiving side's answer and is required rather than
    assumed. A handoff that could not be declined would turn this repository's
    batching **default** into a batching **requirement**, and quietly overrule
    the rule that independent or different-risk changes get separate PRs.

    Raises:
        HandoffRefused: the receiver declined, or the chain has reached
            :data:`MAX_HANDOFFS` and the branch must land before growing further.
        KeyError: no interest is recorded for that branch and scope.
    """
    parsed = Scope.parse(scope)
    if not accepted:
        raise HandoffRefused(f"{to_steward} declined stewardship of {branch} for {parsed}")
    client = await _redis()
    key = _INTEREST_KEY.format(kind=parsed.kind, path=parsed.path, branch=branch)
    raw = await client.get(key)
    if raw is None:
        raise KeyError(f"no in-flight interest recorded for {branch} on {parsed}")
    current = _decode(raw)
    if current.hops >= MAX_HANDOFFS:
        raise HandoffRefused(
            f"{branch} has changed hands {current.hops} times (limit {MAX_HANDOFFS}); "
            "land it before accepting more work onto it"
        )
    moved = Interest(**{**asdict(current), "steward": to_steward, "handoffs": current.handoffs + (to_steward,)})
    await client.set(key, json.dumps(asdict(moved)), ex=INTEREST_TTL_S)
    return moved


async def release(scope: str | Scope, *, branch: str) -> bool:
    """Drop *branch*'s interest in *scope*. Called when its PR merges or closes.

    True when a record went. Releasing something already gone is not an error --
    a merge and a close can both fire, and neither should raise on the other.
    """
    parsed = Scope.parse(scope)
    client = await _redis()
    key = _INTEREST_KEY.format(kind=parsed.kind, path=parsed.path, branch=branch)
    removed = await client.delete(key)
    await client.srem(_INDEX_KEY.format(kind=parsed.kind), _member(parsed, branch))
    return bool(removed)


async def prune(
    live_branches: Iterable[str],
    *,
    kind: str | None = None,
    allow_empty: bool = False,
) -> list[Interest]:
    """Drop interests whose branch is no longer open. Returns what was dropped.

    *live_branches* comes from the caller because this package has no GitHub
    client and must not grow one -- the branch's state is the authority, and only
    something outside `autobot_shared` can read it.

    An empty *live_branches* would drop every interest, and an empty set is also
    what a failed fetch returns, so it must be **stated** rather than inferred:
    without ``allow_empty=True`` this raises :class:`EmptyLiveSet` instead. That
    is not defensiveness about a rare case -- ``except: return []`` is the most
    common shape a failed GitHub call takes, and the log line would have read
    "pruned N interest(s) whose branch is no longer open", which is false in
    precisely the situation that produced it.

    Raises:
        EmptyLiveSet: *live_branches* is empty and *allow_empty* is not set.
    """
    live = set(live_branches)
    if not live and not allow_empty:
        # An empty live set and a failed fetch are the same value. The most
        # common shape of a failed GitHub call is `except: return []`, and
        # accepting it here would delete every interest in the registry while
        # logging "pruned N whose branch is no longer open" -- a false statement
        # in exactly the case that matters. A caller that genuinely means "no
        # branches are open" can say so; a caller handing over the wreckage of a
        # failed query cannot say it by accident.
        raise EmptyLiveSet(
            "prune() received no live branches. If nothing is genuinely open, pass "
            "allow_empty=True; if the branch listing failed, do not prune on its result."
        )
    from autobot_shared.coordination.work_claims import VALID_KINDS

    kinds = sorted(VALID_KINDS) if kind is None else [kind]
    client = await _redis()
    dropped: list[Interest] = []
    for k in kinds:
        index = _INDEX_KEY.format(kind=k)
        for member in await client.smembers(index):
            member = member.decode() if isinstance(member, bytes) else member
            path, _, branch = member.partition("|")
            if branch in live:
                continue
            key = _INTEREST_KEY.format(kind=k, path=path, branch=branch)
            raw = await client.get(key)
            if raw is not None:
                dropped.append(_decode(raw))
                await client.delete(key)
            await client.srem(index, member)
    if dropped:
        logger.info("branch_stewardship: pruned %d interest(s) whose branch is no longer open", len(dropped))
    return dropped
