# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unlanded branches keep a scope spoken for, and stewardship transfers (#15987).

The assertions worth writing here are the ones about what this must NOT do: it
must not refuse a claim, must not let a handoff be assumed, must not grow a chain
without bound, and must not survive its branch. A happy-path test would pass on
a version that did all four.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from autobot_shared.coordination.branch_stewardship import (
    EmptyLiveSet,
    HandoffRefused,
    acquire_aware,
    declare,
    interests,
    prune,
    release,
    transfer,
)
from autobot_shared.coordination.work_claims import Claim, ClaimConflict, ClaimMode

try:
    import fakeredis.aioredis as fakeredis_async
except ImportError:  # pragma: no cover
    fakeredis_async = None


@pytest_asyncio.fixture
async def redis(monkeypatch):
    if fakeredis_async is None:
        pytest.skip("fakeredis[lua] not installed")
    from autobot_shared.coordination import branch_stewardship as bs
    from autobot_shared.coordination import work_claims as wc

    client = fakeredis_async.FakeRedis(server=fakeredis_async.FakeServer(), decode_responses=True)

    async def _client(database: str = "main"):
        return client

    monkeypatch.setattr(bs, "get_async_redis_client", _client)
    monkeypatch.setattr(wc, "get_async_redis_client", _client)
    yield client
    await client.flushall()


# ---------------------------------------------------------------------------
# An interest informs; it never refuses
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_interest_does_not_block_the_claim(redis):
    """Blocking on an open PR would serialise the fleet behind review."""
    await declare("path:a/b.py", branch="issue-1", steward="agent-1", intent="refactor")
    outcome, found = await acquire_aware("path:a/b.py", agent_id="agent-2", task_id="t2", intent="rename")
    assert isinstance(outcome, Claim), "an unlanded branch must not refuse a claim"
    assert [i.branch for i in found] == ["issue-1"]
    assert "refactor" in found[0].intent


@pytest.mark.asyncio
async def test_the_second_agent_learns_before_editing_not_at_merge(redis):
    """The whole point: the collision is visible at acquire time."""
    await declare("path:a/b.py", branch="issue-1", steward="agent-1", intent="fix the parser")
    _, found = await acquire_aware("path:a/b.py", agent_id="agent-2", task_id="t2", intent="x")
    assert "issue-1" in str(found[0]) and "fix the parser" in str(found[0])


@pytest.mark.asyncio
async def test_two_non_overlapping_edits_to_one_file_still_find_each_other(redis):
    """The silent case, and the reason this module exists at all.

    Two agents fix two unrelated defects in one file, in regions that never
    touch. Every signal downstream of this moment is blind to it: the two diffs
    do not conflict, the merge is clean, `git` reports nothing, and CI is green
    on each branch alone. The collision is real regardless -- whichever lands
    second was reasoning about a version of the file that no longer exists --
    and it surfaces as a silent logical regression rather than as a conflict
    anybody is asked to resolve.

    Acquire time is therefore the only moment either agent can still hear about
    the other, which is what makes this the case worth pinning: a merge-time
    check cannot be written, because at merge time there is nothing to see.

    Two assertions, and the first is the one a stricter implementation would
    get wrong. The claim must be GRANTED -- serialising unrelated work behind
    review would make the registry worse than not having it -- while the
    disclosure still names the other branch and what it is doing there.
    """
    scope = "path:autobot-backend/services/parser.py"
    await declare(
        scope,
        branch="issue-1",
        steward="agent-1",
        intent="fix the header parse at the top of the file",
    )

    outcome, found = await acquire_aware(
        scope,
        agent_id="agent-2",
        task_id="t2",
        intent="fix the footer checksum at the bottom of the file",
    )

    assert isinstance(outcome, Claim), "non-overlapping edits to one file must not be serialised"
    assert [i.branch for i in found] == ["issue-1"]
    assert found[0].steward == "agent-1"
    assert "header parse" in found[0].intent, "a disclosure that omits the intent cannot be acted on"


@pytest.mark.asyncio
async def test_awareness_is_mutual_once_both_branches_have_declared(redis):
    """The incumbent has to be able to learn too, not only the newcomer.

    `acquire_aware` tells the arriving agent about work already declared, which
    is a one-way disclosure: on its own it leaves the agent who got there first
    still believing it is alone in the file. An implementation that only ever
    reported *prior* interests to a newcomer would pass every other test here.
    """
    scope = "path:autobot-backend/services/parser.py"
    await declare(scope, branch="issue-1", steward="agent-1", intent="header parse")
    await declare(scope, branch="issue-2", steward="agent-2", intent="footer checksum")

    assert sorted(i.branch for i in await interests(scope)) == ["issue-1", "issue-2"]


@pytest.mark.asyncio
async def test_an_interest_in_a_parent_path_covers_a_child_scope(redis):
    """A branch holding a directory is in flight for files under it."""
    await declare("path:a", branch="issue-1", steward="agent-1", intent="tree-wide")
    found = await interests("path:a/b/c.py")
    assert [i.branch for i in found] == ["issue-1"]


@pytest.mark.asyncio
async def test_an_unrelated_scope_reports_nothing(redis):
    await declare("path:a/b.py", branch="issue-1", steward="agent-1", intent="x")
    assert await interests("path:z/other.py") == []


@pytest.mark.asyncio
async def test_a_claim_conflict_still_reports_interests(redis):
    """A refused claim and an in-flight branch are different facts, both useful."""
    await declare("path:a/b.py", branch="issue-1", steward="agent-1", intent="unlanded")
    from autobot_shared.coordination.work_claims import try_acquire

    await try_acquire("path:a/b.py", agent_id="agent-3", task_id="t3", intent="holding")
    outcome, found = await acquire_aware(
        "path:a/b.py", agent_id="agent-2", task_id="t2", mode=ClaimMode.EXCLUSIVE, intent="x"
    )
    assert isinstance(outcome, ClaimConflict)
    assert [i.branch for i in found] == ["issue-1"]


# ---------------------------------------------------------------------------
# Handoff is refusable, and bounded
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stewardship_transfers_and_records_the_chain(redis):
    await declare("path:a/b.py", branch="issue-1", steward="agent-1", intent="x")
    moved = await transfer("path:a/b.py", branch="issue-1", to_steward="agent-2", accepted=True)
    assert moved.steward == "agent-2"
    assert moved.handoffs == ("agent-1", "agent-2")
    assert moved.hops == 1
    assert (await interests("path:a/b.py"))[0].steward == "agent-2"


@pytest.mark.asyncio
async def test_a_declined_handoff_changes_nothing(redis):
    """Acceptance is required rather than assumed.

    A handoff that could not be declined would turn a batching *default* into a
    batching *requirement*, and overrule the rule that independent or
    different-risk changes get separate PRs.
    """
    await declare("path:a/b.py", branch="issue-1", steward="agent-1", intent="x")
    with pytest.raises(HandoffRefused):
        await transfer("path:a/b.py", branch="issue-1", to_steward="agent-2", accepted=False)
    assert (await interests("path:a/b.py"))[0].steward == "agent-1"


@pytest.mark.asyncio
async def test_the_chain_is_bounded(redis, monkeypatch):
    """An unbounded chain recreates the worktree pile inside one branch."""
    from autobot_shared.coordination import branch_stewardship as bs

    monkeypatch.setattr(bs, "MAX_HANDOFFS", 2)
    await declare("path:a/b.py", branch="issue-1", steward="s0", intent="x")
    await transfer("path:a/b.py", branch="issue-1", to_steward="s1", accepted=True)
    await transfer("path:a/b.py", branch="issue-1", to_steward="s2", accepted=True)
    with pytest.raises(HandoffRefused, match="land it before"):
        await transfer("path:a/b.py", branch="issue-1", to_steward="s3", accepted=True)


@pytest.mark.asyncio
async def test_transferring_an_unknown_branch_raises(redis):
    with pytest.raises(KeyError):
        await transfer("path:a/b.py", branch="never-declared", to_steward="a", accepted=True)


# ---------------------------------------------------------------------------
# The interest ends with the branch, not with a timer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_release_ends_the_interest_and_is_idempotent(redis):
    """A merge and a close can both fire; neither should raise on the other."""
    await declare("path:a/b.py", branch="issue-1", steward="agent-1", intent="x")
    assert await release("path:a/b.py", branch="issue-1") is True
    assert await interests("path:a/b.py") == []
    assert await release("path:a/b.py", branch="issue-1") is False


@pytest.mark.asyncio
async def test_prune_drops_interests_whose_branch_is_gone(redis):
    await declare("path:a/b.py", branch="open-one", steward="s", intent="live")
    await declare("path:c/d.py", branch="closed-one", steward="s", intent="landed")
    dropped = await prune({"open-one"})
    assert [i.branch for i in dropped] == ["closed-one"]
    assert [i.branch for i in await interests("path:a/b.py")] == ["open-one"]
    assert await interests("path:c/d.py") == []


@pytest.mark.asyncio
async def test_prune_refuses_an_empty_live_set_unless_told_to_expect_it(redis):
    """The registry cannot tell 'no branches' from 'no answer', so it must be told.

    An earlier revision documented this hazard and let the call through — a rule
    with nothing enforcing it, which is the failure this whole module exists to
    remove. `except: return []` is the most common shape a failed GitHub call
    takes, and accepting it would delete every interest while logging "pruned N
    whose branch is no longer open": false in precisely the case that produced it.
    """
    await declare("path:a/b.py", branch="open-one", steward="s", intent="live")
    with pytest.raises(EmptyLiveSet, match="allow_empty"):
        await prune(set())
    # Nothing was dropped by the refusal.
    assert [i.branch for i in await interests("path:a/b.py")] == ["open-one"]


@pytest.mark.asyncio
async def test_an_explicit_empty_live_set_still_drops_everything(redis):
    """'Nothing is open' is a legitimate state, and stays expressible.

    A floor would have been the other option and is worse here: it cannot tell a
    genuine zero from a failed fetch, which is the distinction that matters.
    """
    await declare("path:a/b.py", branch="gone", steward="s", intent="landed")
    assert [i.branch for i in await prune(set(), allow_empty=True)] == ["gone"]
    assert await interests("path:a/b.py") == []


@pytest.mark.asyncio
async def test_declare_refuses_an_empty_branch_or_steward(redis):
    for branch, steward in (("", "s"), ("b", ""), ("  ", "s")):
        with pytest.raises(ValueError, match="must be non-empty"):
            await declare("path:a/b.py", branch=branch, steward=steward, intent="x")
