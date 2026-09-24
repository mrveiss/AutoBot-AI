# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Claim and budget gate around AutoBot's own dev-loop actions (#17091).

Part of #16698: AutoBot itself, not only the Claude Code agent sessions, will
act on GitHub issues (#17090 is the first such action -- verifying acceptance
criteria and posting evidence). Two things must be true before it does:

* it must not collide with an agent session already working the same issue,
  which means claiming it through the same registry the agents use
  (``autobot_shared.coordination.work_claims``, ``issue:<number>`` scope,
  #17091 AC 1) -- not a second, parallel claim mechanism;
* it must not run unbounded, which means a spend and a rate ceiling, both
  sourced from env/SSOT (``llm_shared.token_budget``'s dev-loop extension),
  checked before every action, never after (AC 2/3).

``run_dev_loop_action`` is the one entry point that does both, so #17090 (and
whatever else in #16698's family acts on an issue) never has to get the
ordering right itself: claim first (a concurrent claimant is cheaper to find
out about than a spent budget), then the budget, then the action, releasing
the claim on every exit -- success, a budget refusal, or *action* raising.

NEVER PARTIALLY POSTS: a budget refusal returns before *action* is ever
invoked, so either the whole action runs or none of it does. What happens
inside *action* itself (a partial GitHub write mid-call, say) is *action*'s
own contract to keep -- this gate cannot make an arbitrary callable atomic,
only guarantee it is never even started against an exhausted budget.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from dataclasses import dataclass
from typing import Awaitable, Callable, TypeVar, Union

from autobot_shared.coordination.dev_loop_actions import (
    OUTCOME_FAILED,
    OUTCOME_RAN,
    OUTCOME_REFUSED_BUDGET,
    OUTCOME_SKIPPED_CLAIMED,
    build_action,
    record,
)
from autobot_shared.coordination.work_claims import (
    CLAIM_TTL_S,
    ClaimConflict,
    ClaimMode,
    release,
    renew,
    try_acquire,
)
from autobot_shared.logging_manager import get_logger
from llm_shared.token_budget import DevLoopBudgetRefusal, get_token_budget_gate

logger = get_logger(__name__)

T = TypeVar("T")

#: The agent identity AutoBot's own dev-loop participation claims under --
#: distinct from any Claude Code session's agent id, so a conflict report
#: names it unambiguously as the dev loop, not another session.
DEV_LOOP_AGENT_ID = "autobot-dev-loop"

#: Renew at a third of the TTL (matches agents/scope_enforcement.py's own
#: convention): two consecutive missed renews still leave a third of the
#: window to recover before the claim lapses mid-action.
_RENEW_INTERVAL_S = CLAIM_TTL_S / 3


@dataclass(frozen=True)
class IssueClaimSkipped:
    """The issue is already claimed by someone else (#17091 AC 1). *action* did not run."""

    issue_number: int
    holder: ClaimConflict


@dataclass(frozen=True)
class IssueBudgetExhausted:
    """The dev loop's spend or rate budget refused this action (AC 2/3). *action* did not run."""

    issue_number: int
    refusal: DevLoopBudgetRefusal


async def run_dev_loop_action(
    issue_number: int,
    *,
    intent: str,
    estimated_tokens: int,
    action: Callable[[], Awaitable[T]],
) -> Union[T, IssueClaimSkipped, IssueBudgetExhausted]:
    """Claim *issue_number*, check the budget, run *action*, always release.

    Args:
        issue_number: the GitHub issue AutoBot is about to act on.
        intent: human-readable, carried on the claim -- what a conflicting
            holder's refusal names as why this issue was claimed.
        estimated_tokens: *action*'s expected token cost, checked against the
            dev-loop budget before *action* runs and recorded once it exits --
            success or raise -- since it is an estimate of what was attempted,
            not a post-hoc actual only a successful call would report.
        action: the work itself. Only invoked when both the claim and the
            budget allow it.

    Returns:
        *action*'s own return value on success. An :class:`IssueClaimSkipped`
        when the issue is already claimed elsewhere. An
        :class:`IssueBudgetExhausted` when the dev loop's budget refuses.
        Neither is raised: both are ordinary outcomes the caller decides how
        to report, exactly like :func:`work_claims.try_acquire`'s own
        never-raises-on-contention contract.

    Raises:
        Whatever *action* itself raises, once its own budget and claim checks
        have passed -- the claim is still released (AC 1's "on both success
        and failure"), but the exception propagates rather than being
        swallowed, so the caller sees what actually went wrong.
    """
    scope = f"issue:{issue_number}"
    task_id = f"dev-loop-{uuid.uuid4()}"

    claimed = await try_acquire(
        scope,
        agent_id=DEV_LOOP_AGENT_ID,
        task_id=task_id,
        mode=ClaimMode.EXCLUSIVE,
        intent=intent,
    )
    if isinstance(claimed, ClaimConflict):
        logger.info("dev loop: issue #%s already claimed, skipping (%s)", issue_number, claimed)
        await _record(issue_number, intent, OUTCOME_SKIPPED_CLAIMED, 0, str(claimed))
        return IssueClaimSkipped(issue_number=issue_number, holder=claimed)

    claim_lost: list[str] = []
    renewal_task = asyncio.create_task(_renew_forever(scope, task_id=task_id, lost=claim_lost))
    try:
        gate = get_token_budget_gate()
        refusal = await gate.evaluate_dev_loop_action(estimated_tokens)
        if refusal is not None:
            logger.warning("dev loop: budget refused action on issue #%s (%s)", issue_number, refusal.reason)
            await _record(issue_number, intent, OUTCOME_REFUSED_BUDGET, estimated_tokens, refusal.reason)
            return IssueBudgetExhausted(issue_number=issue_number, refusal=refusal)

        outcome, reason = OUTCOME_FAILED, "action raised before returning"
        try:
            result = await action()
            outcome, reason = OUTCOME_RAN, ""
        finally:
            # Recorded regardless of outcome (review): estimated_tokens is
            # the caller's own pre-flight estimate, not actual usage, so
            # "action raised after real spend" and "action succeeded" cost
            # the dev loop the same either way -- a repeatedly-failing
            # action must still count against the budget, or it burns real
            # spend unbounded on the failure path (AC3).
            await gate.record_dev_loop_action(estimated_tokens)
            if claim_lost:
                reason = f"{reason + '; ' if reason else ''}{claim_lost[0]}"
            await _record(issue_number, intent, outcome, estimated_tokens, reason)
        return result
    finally:
        renewal_task.cancel()
        # Suppress anything the renewal raises, not only CancelledError (review):
        # `await renewal_task` re-raises whatever it ended with, and an exception
        # here would skip the release below entirely -- a real claim leak, not a
        # masked log line.
        with contextlib.suppress(BaseException):
            await renewal_task
        try:
            await release(scope, agent_id=DEV_LOOP_AGENT_ID, task_id=task_id)
        except Exception:  # noqa: BLE001 -- see below; this must not mask the action's own error
            # `release` reaches Redis and can raise (ClaimUnavailable on an
            # outage). Raised from inside this `finally` it would REPLACE the
            # exception already propagating from `action()`, which contradicts
            # this function's own contract two docstrings up -- the caller would
            # see a release failure instead of what actually went wrong. The
            # claim then lapses on its own TTL, which is what the TTL is for.
            logger.warning(
                "dev loop: releasing the claim on %s failed; it lapses in <= %ss",
                scope,
                CLAIM_TTL_S,
                exc_info=True,
            )


async def _record(issue_number: int, intent: str, outcome: str, estimated_tokens: int, reason: str) -> None:
    """Append this attempt to the issue's history (#17091 AC 2/3).

    Every exit of `run_dev_loop_action` passes through here, including the two
    that never invoke the action -- a refusal that leaves no trace cannot be
    told apart from an action nobody attempted.
    """
    written = await record(
        build_action(
            issue_number,
            intent=intent,
            outcome=outcome,
            estimated_tokens=estimated_tokens,
            reason=reason,
        )
    )
    if not written:
        # `record` already logged the cause; this names what was lost, because a
        # discarded False is the difference between a healthy audit trail and a
        # silently degraded one (review).
        logger.warning("dev loop: issue #%s's %s outcome is NOT in the action history", issue_number, outcome)


async def _renew_forever(scope: str, *, task_id: str, lost: list[str]) -> None:
    """Keep *scope* alive for as long as *action* runs (review finding).

    The claim's TTL (`work_claims.CLAIM_TTL_S`, 300s by default) is not a
    limit on how long an action may take -- see that module's own docstring
    -- but only if something renews. Without this, an action running longer
    than the TTL lets the claim lapse mid-action, and a concurrent session
    can claim and start acting on the SAME issue: exactly the collision AC1
    exists to prevent. Cancelled in the caller's `finally`, so renewal
    always stops when the action does, including when it raises.
    """
    while True:
        await asyncio.sleep(_RENEW_INTERVAL_S)
        try:
            if not await renew(scope, agent_id=DEV_LOOP_AGENT_ID, task_id=task_id):
                # Recorded, not only logged (review): the action keeps running --
                # cancelling it mid-write is how AC3's "never partially posts"
                # gets broken -- but a run whose claim lapsed is a run another
                # agent could have collided with, and the history has to say so
                # or the collision is invisible afterwards.
                logger.warning("dev loop: claim on %s was no longer held at renew", scope)
                lost.append("the claim lapsed mid-action: another agent could have acquired this issue")
                return
        except Exception:  # noqa: BLE001 -- a renew failure must not kill the run
            logger.warning("dev loop: renewing claim on %s failed", scope, exc_info=True)


__all__ = [
    "DEV_LOOP_AGENT_ID",
    "IssueClaimSkipped",
    "IssueBudgetExhausted",
    "run_dev_loop_action",
]
