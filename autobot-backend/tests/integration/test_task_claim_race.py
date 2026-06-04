# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Integration tests for atomic task-claim race elimination (GH#6468).

Verifies that concurrent agent pickup attempts result in exactly one winner.
Requires a real Redis instance (set REDIS_URL / REDIS_HOST or use the
test fixture that spins up fakeredis).
"""

import asyncio

import pytest
import pytest_asyncio

# ---------------------------------------------------------------------------
# Redis fixture: prefer fakeredis for isolation; fall back to real Redis.
# ---------------------------------------------------------------------------

try:
    import fakeredis.aioredis as fakeredis_async

    _FAKEREDIS_AVAILABLE = True
except ImportError:
    _FAKEREDIS_AVAILABLE = False


@pytest_asyncio.fixture
async def fake_redis(monkeypatch):
    """Patch get_async_redis_client to return a shared fakeredis instance."""
    if not _FAKEREDIS_AVAILABLE:
        pytest.skip("fakeredis not installed — skipping Redis-backed tests")

    server = fakeredis_async.FakeServer()
    client = fakeredis_async.FakeRedis(server=server, decode_responses=True)

    # Patch module-level helper in task_claim so all calls hit the fake client.
    import services.task_claim as tc_mod

    async def _fake_get_client(*_args, **_kwargs):
        return client

    monkeypatch.setattr(tc_mod, "get_async_redis_client", _fake_get_client)
    yield client
    await client.aclose()


# ---------------------------------------------------------------------------
# claim_task / renew_claim / release_claim unit-level integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_claim_granted_to_first_caller(fake_redis):
    """Only the first claimant for a task_id wins."""
    from services.task_claim import claim_task

    result_a = await claim_task("task-1", "agent-A")
    result_b = await claim_task("task-1", "agent-B")

    assert result_a is True, "First caller should be granted the claim"
    assert result_b is False, "Second caller should be denied"


@pytest.mark.asyncio
async def test_claim_different_tasks_both_win(fake_redis):
    """Two agents claiming different tasks should both succeed."""
    from services.task_claim import claim_task

    result_a = await claim_task("task-2", "agent-A")
    result_b = await claim_task("task-3", "agent-B")

    assert result_a is True
    assert result_b is True


@pytest.mark.asyncio
async def test_release_frees_task_for_reclaim(fake_redis):
    """After release, a different agent can claim the same task."""
    from services.task_claim import claim_task, release_claim

    assert await claim_task("task-4", "agent-A") is True
    await release_claim("task-4", "agent-A")
    assert await claim_task("task-4", "agent-B") is True, "After release, task should be re-claimable"


@pytest.mark.asyncio
async def test_release_by_non_owner_has_no_effect(fake_redis):
    """An agent that does not own the claim cannot release it."""
    from services.task_claim import claim_task, is_claim_alive, release_claim

    assert await claim_task("task-5", "agent-A") is True
    released = await release_claim("task-5", "agent-B")
    assert released is False, "Non-owner release should return False"
    assert await is_claim_alive("task-5"), "Claim should still be alive after non-owner release attempt"


@pytest.mark.asyncio
async def test_renew_extends_ttl(fake_redis):
    """Renew call by the owner should succeed."""
    from services.task_claim import claim_task, renew_claim

    assert await claim_task("task-6", "agent-A", ttl=30) is True
    renewed = await renew_claim("task-6", "agent-A", ttl=300)
    assert renewed is True


@pytest.mark.asyncio
async def test_renew_by_non_owner_fails(fake_redis):
    """Renew call by a different agent should return False."""
    from services.task_claim import claim_task, renew_claim

    assert await claim_task("task-7", "agent-A") is True
    assert await renew_claim("task-7", "agent-B") is False


# ---------------------------------------------------------------------------
# Concurrent pickup simulation — the core race test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_pickup_only_one_wins(fake_redis):
    """Spawn N concurrent claim attempts; exactly one should win."""
    from services.task_claim import claim_task

    task_id = "task-race-1"
    n_agents = 10

    results = await asyncio.gather(*[claim_task(task_id, f"agent-{i}") for i in range(n_agents)])

    winners = [i for i, r in enumerate(results) if r is True]
    assert len(winners) == 1, f"Expected exactly 1 winner, got {len(winners)}: {winners}"


# ---------------------------------------------------------------------------
# DistributedAgentManager integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_active_task_blocked_on_second_agent(fake_redis, monkeypatch):
    """add_active_task returns False for the second agent on the same task."""
    from agents.agent_orchestration.distributed_management import DistributedAgentManager
    from agents.agent_orchestration.types import DistributedAgentInfo

    mgr = DistributedAgentManager(builtin_agents={})

    # Minimal stub agent info
    class _FakeHealth:
        class status:
            value = "healthy"

    class _FakeAgent:
        agent_id = "agent-A"

    info_a = DistributedAgentInfo(agent=_FakeAgent(), health=_FakeHealth(), active_tasks=set())
    info_b_agent = type("B", (), {"agent_id": "agent-B"})()
    info_b = DistributedAgentInfo(agent=info_b_agent, health=_FakeHealth(), active_tasks=set())

    mgr.distributed_agents["agent-A"] = info_a
    mgr.distributed_agents["agent-B"] = info_b

    # Also stub out Redis persistence helpers to avoid real DB calls
    import agents.agent_orchestration.distributed_management as dm_mod

    async def _noop(*_args, **_kwargs):
        return None

    monkeypatch.setattr(dm_mod, "persist_task_assigned", _noop)

    result_a = await mgr.add_active_task("agent-A", "shared-task")
    result_b = await mgr.add_active_task("agent-B", "shared-task")

    assert result_a is True, "First agent should win the claim"
    assert result_b is False, "Second agent should be refused"
    assert "shared-task" in mgr.distributed_agents["agent-A"].active_tasks
    assert "shared-task" not in mgr.distributed_agents["agent-B"].active_tasks
