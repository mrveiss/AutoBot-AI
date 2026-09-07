# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Work claims: overlap, mode conflicts, reentrancy, expiry, and atomicity (#15947).

Two halves, deliberately separated.

**Scope logic needs no Redis** and is tested directly — it is where the
false-positive lives (``path:a/b`` must not cover ``path:a/bc.py``), and a test
that needs a server to prove a string-prefix rule would not be run as often.

**Everything else needs a real ``EVAL``.** Acquire is a Lua script because
read-then-write in Python cannot promise "no two overlapping exclusive claims"
across workers, so a fake that stubs ``eval`` would assert the mock rather than
the guarantee. These use ``fakeredis[lua]``, which is in ``requirements-ci-test``
for exactly this (#11604), and skip rather than pass when it is absent — a
skipped test says nothing; a passing stub says something false.
"""

from __future__ import annotations

import asyncio
import itertools

import pytest
import pytest_asyncio

from autobot_shared.coordination.work_claims import (
    Claim,
    ClaimConflict,
    ClaimConflictError,
    ClaimMode,
    HolderError,
    Scope,
    ScopeError,
    list_claims,
    release,
    renew,
    try_acquire,
    work_claim,
)

try:
    import fakeredis.aioredis as fakeredis_async
except ImportError:  # pragma: no cover - environment without the extra
    fakeredis_async = None


@pytest_asyncio.fixture
async def redis(monkeypatch):
    """Point work_claims at one fakeredis server shared by every call."""
    if fakeredis_async is None:
        pytest.skip("fakeredis[lua] not installed — Redis-backed claim tests need real EVAL")
    from autobot_shared.coordination import work_claims as mod

    client = fakeredis_async.FakeRedis(server=fakeredis_async.FakeServer(), decode_responses=True)

    async def _client(database: str = "main"):
        return client

    monkeypatch.setattr(mod, "get_async_redis_client", _client)
    yield client
    await client.flushall()


# ---------------------------------------------------------------------------
# Scope grammar — no Redis
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    ["nokind", "bogus:a/b", "path:", "path:a//b", "path:a/../b", "path:a/./b", "path:a/b c"],
)
def test_parse_rejects_unusable_scopes(raw):
    with pytest.raises(ScopeError):
        Scope.parse(raw)


def test_parse_accepts_every_valid_kind():
    for kind in ("path", "kb", "device", "project", "config"):
        assert Scope.parse(f"{kind}:a/b").kind == kind


def test_overlap_is_segment_aligned_not_string_prefix():
    """The false positive that makes a naive prefix check wrong."""
    parent = Scope.parse("path:a/b")
    assert parent.overlaps(Scope.parse("path:a/b/c.py"))
    assert Scope.parse("path:a/b/c.py").overlaps(parent)
    assert parent.overlaps(parent)
    # 'a/bc.py' starts with 'a/b' as a string and is a different tree.
    assert not parent.overlaps(Scope.parse("path:a/bc.py"))
    assert not Scope.parse("path:a/bc.py").overlaps(parent)


def test_overlap_never_crosses_kinds():
    assert not Scope.parse("path:a/b").overlaps(Scope.parse("kb:a/b"))


# ---------------------------------------------------------------------------
# Mode matrix — all four pairs
# ---------------------------------------------------------------------------


async def _acquire(scope, agent, task="t", mode=ClaimMode.EXCLUSIVE, **kw):
    return await try_acquire(scope, agent_id=agent, task_id=task, mode=mode, intent="test", **kw)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("first", "second", "compatible"),
    [
        (ClaimMode.SHARED, ClaimMode.SHARED, True),
        (ClaimMode.SHARED, ClaimMode.EXCLUSIVE, False),
        (ClaimMode.EXCLUSIVE, ClaimMode.SHARED, False),
        (ClaimMode.EXCLUSIVE, ClaimMode.EXCLUSIVE, False),
    ],
)
async def test_mode_conflict_matrix(redis, first, second, compatible):
    assert isinstance(await _acquire("path:a/b", "agent-1", "t1", first), Claim)
    outcome = await _acquire("path:a/b", "agent-2", "t2", second)
    assert isinstance(outcome, Claim) is compatible


@pytest.mark.asyncio
async def test_conflict_names_the_holder_and_its_intent(redis):
    await try_acquire("path:a/b", agent_id="agent-1", task_id="t1", intent="refactor the loop")
    outcome = await try_acquire("path:a/b", agent_id="agent-2", task_id="t2", intent="rename")
    assert isinstance(outcome, ClaimConflict)
    assert outcome.holder.agent_id == "agent-1"
    assert outcome.holder.task_id == "t1"
    assert "refactor the loop" in outcome.holder.intent
    # A refusal the loser can act on, not a bare boolean (#15948).
    assert "agent-1" in str(outcome)


@pytest.mark.asyncio
async def test_a_child_scope_conflicts_with_a_held_parent(redis):
    await _acquire("path:autobot-backend/llc", "agent-1", "t1")
    outcome = await _acquire("path:autobot-backend/llc/budget.py", "agent-2", "t2")
    assert isinstance(outcome, ClaimConflict)


@pytest.mark.asyncio
async def test_a_parent_scope_conflicts_with_a_held_child(redis):
    await _acquire("path:autobot-backend/llc/budget.py", "agent-1", "t1")
    outcome = await _acquire("path:autobot-backend/llc", "agent-2", "t2")
    assert isinstance(outcome, ClaimConflict)


@pytest.mark.asyncio
async def test_a_sibling_scope_does_not_conflict(redis):
    await _acquire("path:a/b", "agent-1", "t1")
    assert isinstance(await _acquire("path:a/c", "agent-2", "t2"), Claim)


# ---------------------------------------------------------------------------
# Reentrancy — an agent must never deadlock against itself
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_same_holder_reacquiring_renews_rather_than_conflicting(redis):
    first = await _acquire("path:a/b", "agent-1", "t1")
    second = await _acquire("path:a/b", "agent-1", "t1")
    assert isinstance(second, Claim)
    assert second.expires_at >= first.expires_at


@pytest.mark.asyncio
async def test_same_holder_may_claim_a_child_of_its_own_scope(redis):
    await _acquire("path:a/b", "agent-1", "t1")
    assert isinstance(await _acquire("path:a/b/c.py", "agent-1", "t1"), Claim)


@pytest.mark.asyncio
async def test_a_second_task_of_the_same_agent_is_not_the_same_holder(redis):
    """Reentrancy is keyed on (agent, task) — two tasks of one agent still collide."""
    await _acquire("path:a/b", "agent-1", "t1")
    assert isinstance(await _acquire("path:a/b", "agent-1", "t2"), ClaimConflict)


# ---------------------------------------------------------------------------
# Atomicity, expiry, ownership
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_overlapping_acquires_yield_exactly_one_winner(redis):
    scopes = ["path:a", "path:a/b", "path:a/b/c", "path:a/b/c/d"]
    results = await asyncio.gather(*(_acquire(s, f"agent-{i}", f"t{i}") for i, s in enumerate(scopes)))
    assert sum(isinstance(r, Claim) for r in results) == 1


@pytest.mark.asyncio
async def test_an_expired_claim_neither_lists_nor_blocks(redis):
    await _acquire("path:a/b", "agent-1", "t1", ttl_s=10)
    assert len(await list_claims("path")) == 1
    await redis.delete("work_claims:c:path:a/b")  # what Redis TTL expiry leaves behind
    assert await list_claims("path") == []
    assert isinstance(await _acquire("path:a/b", "agent-2", "t2"), Claim)


@pytest.mark.asyncio
async def test_release_is_owner_checked(redis):
    await _acquire("path:a/b", "agent-1", "t1")
    assert await release("path:a/b", agent_id="agent-2", task_id="t2") is False
    assert isinstance(await _acquire("path:a/b", "agent-3", "t3"), ClaimConflict)
    assert await release("path:a/b", agent_id="agent-1", task_id="t1") is True
    assert isinstance(await _acquire("path:a/b", "agent-3", "t3"), Claim)


@pytest.mark.asyncio
async def test_renew_is_owner_checked_and_false_once_gone(redis):
    await _acquire("path:a/b", "agent-1", "t1")
    assert await renew("path:a/b", agent_id="agent-2", task_id="t2") is False
    assert await renew("path:a/b", agent_id="agent-1", task_id="t1") is True
    await release("path:a/b", agent_id="agent-1", task_id="t1")
    assert await renew("path:a/b", agent_id="agent-1", task_id="t1") is False


@pytest.mark.asyncio
async def test_list_claims_prunes_the_index_it_reads(redis):
    await _acquire("path:a/b", "agent-1", "t1")
    await redis.delete("work_claims:c:path:a/b")
    await list_claims("path")
    assert await redis.smembers("work_claims:idx:path") == set()


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_work_claim_releases_on_a_raising_block(redis):
    with pytest.raises(ValueError):
        async with work_claim("path:a/b", agent_id="agent-1", task_id="t1", intent="x"):
            raise ValueError("boom")
    assert isinstance(await _acquire("path:a/b", "agent-2", "t2"), Claim)


@pytest.mark.asyncio
async def test_work_claim_raises_a_conflict_carrying_the_holder(redis):
    await _acquire("path:a/b", "agent-1", "t1")
    with pytest.raises(ClaimConflictError) as excinfo:
        async with work_claim("path:a/b", agent_id="agent-2", task_id="t2", intent="x"):
            pass
    assert excinfo.value.conflict.holder.agent_id == "agent-1"


@pytest.mark.asyncio
async def test_adhoc_callers_do_not_share_one_task_identity(redis):
    """Two omitted task_ids must not accidentally satisfy each other's reentrancy."""
    async with work_claim("path:a/b", agent_id="agent-1", intent="first"):
        with pytest.raises(ClaimConflictError):
            async with work_claim("path:a/b", agent_id="agent-1", intent="second"):
                pass


# ---------------------------------------------------------------------------
# The two rules must agree with each other, not each with its own constants
# ---------------------------------------------------------------------------

_ALPHABET = ("a", "b", "ab")  # 'ab' is what makes a string-prefix check wrong
_KINDS = ("path", "kb")


def _bounded_scopes() -> list[str]:
    """Every scope over a deliberately tiny space: 2 kinds x 39 paths."""
    paths = [
        "/".join(combo)
        for depth in (1, 2, 3)
        for combo in itertools.product(_ALPHABET, repeat=depth)
    ]
    return [f"{kind}:{path}" for kind in _KINDS for path in paths]


@pytest.mark.asyncio
async def test_python_and_lua_overlap_rules_agree_over_a_bounded_space(redis):
    """`Scope.overlaps` and the Lua state one rule twice — pin them to each other.

    Both are currently tested against their own hand-written cases, which is
    exactly what hides a divergence while each stays internally consistent
    (#15906). Testing them against a shared case *list* would only move that
    shared constant, so this is **exhaustive** over a bounded space instead:
    every ordered pair of 78 scopes, 6084 comparisons, no case list to agree
    with.

    The Python rule short-circuits on ``self.kind != other.kind``; the Lua never
    compares kinds at all, relying on each kind owning a separate index set and
    key prefix. Two kinds are in the space so that structural claim is tested
    rather than asserted.
    """
    scopes = _bounded_scopes()
    disagreements = []
    for left in scopes:
        for right in scopes:
            python_says = Scope.parse(left).overlaps(Scope.parse(right))
            held = await _acquire(left, "agent-1", "t1")
            assert isinstance(held, Claim)
            outcome = await _acquire(right, "agent-2", "t2")
            lua_says = isinstance(outcome, ClaimConflict)
            if isinstance(outcome, Claim):
                await release(right, agent_id="agent-2", task_id="t2")
            await release(left, agent_id="agent-1", task_id="t1")
            if python_says != lua_says:
                disagreements.append((left, right, python_says, lua_says))
    assert not disagreements, f"overlap rules disagree on {len(disagreements)} pairs: {disagreements[:5]}"


# ---------------------------------------------------------------------------
# Holder identity — validated because nothing else validates it
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(("agent", "task"), [("", "t"), ("a", ""), ("   ", "t"), ("a", "  ")])
async def test_empty_holder_identity_is_refused(redis, agent, task):
    with pytest.raises(HolderError):
        await try_acquire("path:a/b", agent_id=agent, task_id=task, intent="x")


@pytest.mark.asyncio
async def test_release_and_renew_also_refuse_an_empty_holder(redis):
    """Otherwise the ownership check could be satisfied by a blank identity."""
    for call in (release, renew):
        with pytest.raises(HolderError):
            await call("path:a/b", agent_id="", task_id="")
