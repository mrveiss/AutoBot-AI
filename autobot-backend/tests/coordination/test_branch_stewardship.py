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
async def test_prune_with_an_empty_live_set_drops_everything(redis):
    """Documented, and the reason the docstring warns about it.

    A caller whose branch-list fetch failed must not pass the empty result: this
    is indistinguishable from 'every branch closed', and the registry cannot tell
    the difference between no branches and no answer.
    """
    await declare("path:a/b.py", branch="open-one", steward="s", intent="live")
    assert [i.branch for i in await prune(set())] == ["open-one"]


@pytest.mark.asyncio
async def test_declare_refuses_an_empty_branch_or_steward(redis):
    for branch, steward in (("", "s"), ("b", ""), ("  ", "s")):
        with pytest.raises(ValueError, match="must be non-empty"):
            await declare("path:a/b.py", branch=branch, steward=steward, intent="x")
