# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The per-action record of AutoBot's own dev-loop participation (#17091).

#17091's second criterion asks for the spend and rate budgets to be *"enforced
before each action and recorded per action in the registry"*. Enforcement lives
in ``llm_shared.token_budget``'s dev-loop gate, which keeps a cumulative spend
counter and an hourly action counter -- two running totals. A total answers
"may the next action run"; it cannot answer "what did the loop do, to which
issue, and why did it stop", which is what the third criterion's *records why,
and surfaces it* needs and what #17092's page reads.

So this is the append-only half: one entry per attempted action, including the
attempts that never ran. A refusal that leaves no trace is indistinguishable
from an action that was never attempted -- the distinction
``MEASUREMENT_DISCIPLINE.md`` is about, applied to the loop's own history.

It lives beside ``work_claims`` and in its keyspace (``work_claims:actions:*``)
because it is the same registry from the claimant's point of view: the claim
says who holds an issue now, this says what was done to it and at what cost.
It is deliberately NOT a field on :class:`work_claims.Claim` -- a claim is a
live lock that disappears on release, so hanging the audit trail off it would
delete the record at exactly the moment it becomes history.

Recording is best-effort by design: the claim has already been acquired by the
time an entry is written, so a Redis failure here must not fail an action that
is otherwise allowed to run. Every such failure is logged and reported through
the return value -- ``False`` means *not recorded*, never *nothing happened*.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any, Optional

from autobot_shared.env_utils import env_int_clamped
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.time_utils import utc_timestamp

logger = get_logger(__name__)

#: How long one issue's action history survives. A week by default: long enough
#: to answer "why did the loop stop on this issue" after a weekend, short enough
#: that an abandoned issue's entries do not accumulate forever.
ACTION_LOG_TTL_S = env_int_clamped("AUTOBOT_DEV_LOOP_ACTION_LOG_TTL_S", 604800, min_v=3600, max_v=2592000)

#: Entries kept per issue. The list is trimmed to the most recent, so a loop
#: that retries an issue many times cannot push its own early history out of
#: Redis memory across every other issue.
ACTION_LOG_MAX = env_int_clamped("AUTOBOT_DEV_LOOP_ACTION_LOG_MAX", 200, min_v=10, max_v=5000)

#: How many entries `recent` returns when the caller does not say. A page of
#: history for a reader, not a limit on what is kept -- that is ACTION_LOG_MAX.
DEFAULT_RECENT_LIMIT = 50

_ACTIONS_KEY = "work_claims:actions:issue:{issue}"

#: Outcomes. Every attempted action ends as exactly one of these, including the
#: two that never invoke the action at all -- that is the point of recording.
OUTCOME_RAN = "ran"
OUTCOME_FAILED = "failed"
OUTCOME_SKIPPED_CLAIMED = "skipped_claimed"
OUTCOME_REFUSED_BUDGET = "refused_budget"

OUTCOMES = frozenset({OUTCOME_RAN, OUTCOME_FAILED, OUTCOME_SKIPPED_CLAIMED, OUTCOME_REFUSED_BUDGET})


@dataclass(frozen=True)
class DevLoopAction:
    """One attempted dev-loop action against one issue.

    ``estimated_tokens`` is the caller's pre-flight estimate, matching what the
    budget gate charged -- not a post-hoc actual, which a refused or failed
    action would not have.
    """

    issue: int
    intent: str
    outcome: str
    estimated_tokens: int
    #: Why this outcome, for the two that stop the loop. Empty for `ran`.
    reason: str
    at: str


def build_action(
    issue: int,
    *,
    intent: str,
    outcome: str,
    estimated_tokens: int,
    reason: str = "",
) -> DevLoopAction:
    """A :class:`DevLoopAction` stamped now, with the outcome validated.

    An unknown outcome raises rather than being recorded: a history containing
    a typo'd outcome silently drops out of every count that filters on one.
    """
    if outcome not in OUTCOMES:
        raise ValueError(f"unknown dev-loop outcome {outcome!r}; outcomes are {sorted(OUTCOMES)}")
    return DevLoopAction(
        issue=issue,
        intent=intent,
        outcome=outcome,
        estimated_tokens=estimated_tokens,
        reason=reason,
        at=utc_timestamp(),
    )


async def record(action: DevLoopAction) -> bool:
    """Append *action* to its issue's history. ``False`` means not recorded.

    Never raises: the caller has already claimed the issue and may already have
    run the action, so a failure to write the audit trail must not turn into a
    failure of the work. It is logged at warning level, because an unrecorded
    action is a hole in the very history #17091 asks for.
    """
    key = _ACTIONS_KEY.format(issue=action.issue)
    try:
        client = await get_async_redis_client(database="main")
        if client is None:
            logger.warning("dev-loop actions: Redis unavailable, action on #%s NOT recorded", action.issue)
            return False
        await client.lpush(key, json.dumps(asdict(action)))
        await client.ltrim(key, 0, ACTION_LOG_MAX - 1)
        await client.expire(key, ACTION_LOG_TTL_S)
        return True
    except Exception:  # noqa: BLE001 -- an audit write must not break the action it describes
        logger.warning("dev-loop actions: failed to record action on #%s", action.issue, exc_info=True)
        return False


async def recent(issue: int, *, limit: int = DEFAULT_RECENT_LIMIT) -> list[DevLoopAction]:
    """This issue's most recent actions, newest first.

    An empty list from a healthy Redis means *no action was ever attempted on
    this issue*. An unreachable Redis raises, so a caller can tell that apart
    from *nothing happened* -- the two must never look the same.
    """
    client = await get_async_redis_client(database="main")
    if client is None:
        raise RuntimeError("dev-loop actions: Redis client unavailable; this issue's history cannot be read")
    try:
        raw = await client.lrange(_ACTIONS_KEY.format(issue=issue), 0, max(limit, 1) - 1)
    except Exception as exc:  # noqa: BLE001 -- re-raised, never swallowed; see below
        # A connection that drops mid-call is the same fact as a client that was
        # never there, and callers key on this contract (`RuntimeError`, "cannot
        # be read") to tell it apart from an empty history. Without this, one of
        # the two ways Redis can be unavailable raises the redis library's own
        # type and slips past that check (review).
        raise RuntimeError("dev-loop actions: this issue's history cannot be read") from exc
    return [_decode(entry) for entry in raw]


def _decode(raw: Any) -> DevLoopAction:
    if isinstance(raw, bytes):
        raw = raw.decode()
    return DevLoopAction(**json.loads(raw))


def action_payload(action: DevLoopAction) -> dict[str, Any]:
    """A JSON-safe dict for an API or a page (#17092), mirroring `claim_payload`."""
    return asdict(action)


def last_refusal(actions: list[DevLoopAction]) -> Optional[DevLoopAction]:
    """The most recent entry that STOPPED the loop, if any.

    `recent` returns newest first, so this is the first refusal in the list --
    what "surfaces it" (#17091 AC 3) has to show to answer *why has the loop
    stopped touching this issue*.
    """
    for action in actions:
        if action.outcome in (OUTCOME_REFUSED_BUDGET, OUTCOME_SKIPPED_CLAIMED):
            return action
    return None


__all__ = [
    "ACTION_LOG_MAX",
    "ACTION_LOG_TTL_S",
    "DEFAULT_RECENT_LIMIT",
    "DevLoopAction",
    "OUTCOMES",
    "OUTCOME_FAILED",
    "OUTCOME_RAN",
    "OUTCOME_REFUSED_BUDGET",
    "OUTCOME_SKIPPED_CLAIMED",
    "action_payload",
    "build_action",
    "last_refusal",
    "recent",
    "record",
]
