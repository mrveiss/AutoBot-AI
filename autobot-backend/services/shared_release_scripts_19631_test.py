# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The owner-checked releases and renewals behave through the shared scripts, on a real Lua engine (#19631)."""

from __future__ import annotations

from types import SimpleNamespace

import fakeredis.aioredis
import pytest

import autobot_shared.leader_lease as leader_lease
import services.task_claim as task_claim
from autobot_memory_graph.entity_upsert import name_index_key, release_name
from autobot_shared.idempotency import _marker, release_key
from llc.sync import outbound_sync

pytestmark = pytest.mark.asyncio

KEY_TTL = 1000
SHORT_LEASE_MS = 5000


@pytest.fixture
def redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


def _serve(monkeypatch, module, redis) -> None:
    async def _client(*_args, **_kwargs):
        return redis

    monkeypatch.setattr(module, "get_async_redis_client", _client)


async def test_task_claim_release_and_renew_need_the_owner(monkeypatch, redis):
    _serve(monkeypatch, task_claim, redis)
    monkeypatch.setattr(task_claim, "emit", lambda _event: None)
    assert await task_claim.claim_task("t", "a", ttl=10)

    assert await task_claim.renew_claim("t", "b", ttl=KEY_TTL) is False
    assert await redis.ttl("task:claim:t") <= 10
    assert await task_claim.renew_claim("t", "a", ttl=KEY_TTL) is True
    assert 10 < await redis.ttl("task:claim:t") <= KEY_TTL

    assert await task_claim.release_claim("t", "b") is False
    assert await task_claim.release_claim("t", "a") is True
    assert await redis.get("task:claim:t") is None


async def test_idempotency_release_keeps_a_successors_claim(redis):
    await redis.set("k", _marker("live"))
    assert await release_key(redis, "k", "lapsed") is False
    assert await redis.get("k") == _marker("live")
    assert await release_key(redis, "k", "live") is True
    assert await redis.get("k") is None


async def test_entity_name_release_keeps_a_new_owners_entry(redis):
    graph = SimpleNamespace(redis_client=redis)
    key = name_index_key("name")
    await redis.set(key, "new-owner")
    await release_name(graph, "name", "old-owner")
    assert await redis.get(key) == "new-owner"
    await release_name(graph, "name", "new-owner")
    assert await redis.get(key) is None


async def test_leader_lease_refresh_extends_only_its_own_key(monkeypatch, redis):
    _serve(monkeypatch, leader_lease, redis)
    lease = leader_lease.LeaderLease("lease", ttl_ms=KEY_TTL * 1000, worker_id="w1")
    lease._is_leader = True

    await redis.set("lease", "w2", px=SHORT_LEASE_MS)
    assert await lease.try_acquire_or_refresh() is False
    assert await redis.pttl("lease") <= SHORT_LEASE_MS

    await redis.set("lease", "w1", px=SHORT_LEASE_MS)
    assert await lease.try_acquire_or_refresh() is True
    assert await redis.pttl("lease") > SHORT_LEASE_MS


async def test_outbound_sync_refresh_extends_only_its_own_key(monkeypatch, redis):
    _serve(monkeypatch, outbound_sync, redis)
    service = outbound_sync.LLCOutboundSyncService()
    service._is_leader = True
    key = outbound_sync._LEADER_KEY

    await redis.set(key, "someone-else", px=SHORT_LEASE_MS)
    assert await service._try_acquire_or_refresh() is False

    await redis.set(key, service._worker_id, px=SHORT_LEASE_MS)
    assert await service._try_acquire_or_refresh() is True
    assert await redis.pttl(key) > SHORT_LEASE_MS
