# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for the mesh:reembed_queue consumer (#20535)."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import fakeredis.aioredis
import pytest

from initialization import lifespan, mesh_reembed_startup
from services.mesh_brain import reembed_consumer as rc
from services.mesh_brain.staleness_propagator import _REEMBED_QUEUE_KEY, enqueue_for_reembedding


@pytest.fixture
def redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.fixture
def docs(tmp_path):
    (tmp_path / "a.md").write_text("a", encoding="utf-8")
    return tmp_path


def _consumer(redis, docs, reindex):
    return rc.ReembedConsumer(redis, reindex=reindex, root=docs)


@pytest.mark.asyncio
async def test_pushed_item_is_reembedded(redis, docs):
    reindex = AsyncMock()
    await enqueue_for_reembedding(redis, ["a.md"])
    assert await _consumer(redis, docs, reindex).drain() == 1
    reindex.assert_awaited_once_with(str((docs / "a.md").resolve()))
    assert await redis.llen(rc.QUEUE_KEY) == 0
    assert await redis.llen(rc.PROCESSING_KEY) == 0


@pytest.mark.asyncio
async def test_failing_item_is_retried_then_dead_lettered(redis, docs):
    reindex = AsyncMock(side_effect=RuntimeError("down"))
    consumer = _consumer(redis, docs, reindex)
    await redis.rpush(rc.QUEUE_KEY, "a.md")
    for _ in range(rc.MAX_ATTEMPTS):
        await consumer.drain()
    assert reindex.await_count == rc.MAX_ATTEMPTS
    assert await _consumer(redis, docs, reindex).dead_letters() == ["a.md"]
    assert await redis.llen(rc.QUEUE_KEY) == 0
    assert await redis.llen(rc.PROCESSING_KEY) == 0
    assert await redis.hlen(rc.ATTEMPTS_KEY) == 0


@pytest.mark.asyncio
async def test_unresolvable_item_is_dead_lettered_without_reindex(redis, docs):
    reindex = AsyncMock()
    await redis.rpush(rc.QUEUE_KEY, "missing.md", "../escape.md")
    await _consumer(redis, docs, reindex).drain()
    reindex.assert_not_awaited()
    assert await redis.lrange(rc.DEAD_KEY, 0, -1) == ["missing.md", "../escape.md"]


@pytest.mark.asyncio
async def test_orphans_from_a_dead_leader_return_to_the_queue(redis, docs):
    await redis.rpush(rc.PROCESSING_KEY, "a.md")
    assert await _consumer(redis, docs, AsyncMock()).recover_orphans() == 1
    assert await redis.lrange(rc.QUEUE_KEY, 0, -1) == ["a.md"]


@pytest.mark.asyncio
async def test_only_one_consumer_holds_the_lease(redis, docs):
    first, second = (_consumer(redis, docs, AsyncMock()) for _ in range(2))
    with patch("autobot_shared.leader_lease.get_async_redis_client", AsyncMock(return_value=redis)):
        assert await first.lease.update_leadership() is True
        assert await second.lease.update_leadership() is False


@pytest.mark.asyncio
async def test_startup_registers_the_consumer():
    """Control: fails if the lifespan init stops starting the consumer."""
    app = SimpleNamespace(state=SimpleNamespace())
    start = AsyncMock(return_value=("consumer", "task"))
    with patch.object(rc, "start_reembed_consumer", start):
        await mesh_reembed_startup.start_mesh_reembed_consumer(app)
    start.assert_awaited_once()
    assert app.state.mesh_reembed_consumer == "consumer"


@pytest.mark.asyncio
@pytest.mark.parametrize("scheduler_enabled", [False, True])
async def test_lifespan_starts_the_consumer_whatever_the_scheduler_flag(scheduler_enabled):
    """#20535: the consumer deletes nothing, so it runs with the MeshBrainScheduler flag on or off."""
    app = SimpleNamespace(state=SimpleNamespace())
    scheduler = SimpleNamespace(start=AsyncMock())
    cfg = SimpleNamespace(misc=SimpleNamespace(mesh_brain_scheduler_enabled=scheduler_enabled))
    start = AsyncMock(return_value=("consumer", "task"))
    stub = SimpleNamespace(MeshBrainScheduler=lambda: scheduler)
    with (
        patch.object(rc, "start_reembed_consumer", start),
        patch("autobot_shared.ssot_config.config", cfg),
        patch.dict("sys.modules", {"services.mesh_brain.scheduler": stub}),
    ):
        await lifespan._init_mesh_brain_scheduler(app)
    start.assert_awaited_once()
    assert app.state.mesh_reembed_consumer == "consumer"
    assert scheduler.start.await_count == int(scheduler_enabled)


@pytest.mark.asyncio
async def test_failed_id_is_not_retried_in_the_same_drain(redis, docs):
    """A short outage must not burn every attempt inside one pass."""
    reindex = AsyncMock(side_effect=RuntimeError("down"))
    consumer = _consumer(redis, docs, reindex)
    await redis.rpush(rc.QUEUE_KEY, "a.md")
    assert await consumer.drain() == 1
    assert reindex.await_count == 1
    assert await redis.lrange(rc.QUEUE_KEY, 0, -1) == ["a.md"]
    assert await redis.hget(rc.ATTEMPTS_KEY, "a.md") == "1"


@pytest.mark.asyncio
async def test_lease_stays_held_across_a_long_drain(redis, docs):
    """The drain outlasts the lease TTL; refreshing as it goes keeps a rival worker out."""
    items, step_s = 6, 0.1

    async def slow(path):
        await asyncio.sleep(step_s)

    first = _consumer(redis, docs, slow)
    first.lease.ttl_ms = int(step_s * 4 * 1000)  # shorter than the whole drain (items * step_s)
    rival = _consumer(redis, docs, AsyncMock())
    rival.lease.ttl_ms = first.lease.ttl_ms
    await redis.rpush(rc.QUEUE_KEY, *["a.md"] * items)
    assert await first.lease.update_leadership() is True
    stolen = []

    async def poll_rival():
        while True:
            stolen.append(await rival.lease.try_acquire_or_refresh())
            await asyncio.sleep(step_s / 4)

    watcher = asyncio.create_task(poll_rival())
    try:
        assert await first.drain() == items
    finally:
        watcher.cancel()
    assert not any(stolen)


def test_lease_ttl_outlives_the_interval():
    assert rc.LEASE_TTL_MS > rc.INTERVAL_S * 1000


@pytest.mark.asyncio
async def test_stop_waits_for_the_task_before_releasing_the_lease():
    order = []

    async def loop():
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            await asyncio.sleep(0)  # still unwinding after the cancel
            order.append("task finished")
            raise

    task = asyncio.create_task(loop())
    await asyncio.sleep(0)
    lease = SimpleNamespace(release=AsyncMock(side_effect=lambda: order.append("released")))
    app = SimpleNamespace(
        state=SimpleNamespace(mesh_reembed_consumer=SimpleNamespace(lease=lease), mesh_reembed_task=task)
    )
    await mesh_reembed_startup.stop_mesh_reembed_consumer(app)
    assert order == ["task finished", "released"]


def test_consumer_reads_the_key_the_producer_writes():
    assert rc.QUEUE_KEY == _REEMBED_QUEUE_KEY
