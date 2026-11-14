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


class _VirtualClockLease:
    """The slice of Redis a ``LeaderLease`` uses (``set NX PX``, compare-and-extend ``eval``) on a clock the
    test advances by hand, so no real time passes and the expiry is exact (#21102)."""

    def __init__(self):
        self.now_ms = 0
        self._owner = None
        self._expires_ms = 0

    def _holder(self):
        return self._owner if self.now_ms < self._expires_ms else None

    async def set(self, key, worker_id, nx, px):
        if self._holder() is not None:
            return None
        self._owner, self._expires_ms = worker_id, self.now_ms + px
        return True

    async def eval(self, script, numkeys, key, worker_id, ttl_ms):
        if self._holder() != worker_id:
            return 0
        self._expires_ms = self.now_ms + int(ttl_ms)
        return 1


async def _long_drain(redis, docs, *, refresh_per_item):
    """Drain 6 items of 100 ms each under a 400 ms lease; return what a rival polling every 25 ms won."""
    items, step_ms, poll_ms = 6, 100, 25
    clock = _VirtualClockLease()
    stolen = []

    async def lease_client(database="main"):
        return clock

    async def slow(path):
        for _ in range(step_ms // poll_ms):
            clock.now_ms += poll_ms
            stolen.append(await rival.lease.try_acquire_or_refresh())

    first = _consumer(redis, docs, slow)
    rival = _consumer(redis, docs, AsyncMock())
    for consumer in (first, rival):
        consumer.lease.ttl_ms = step_ms * 4  # shorter than the whole drain (items * step_ms)
        consumer.lease._client_factory = lease_client
    if not refresh_per_item:
        first.lease.hold_or_refresh = AsyncMock(return_value=True)  # the drain never extends the lease
    await redis.rpush(rc.QUEUE_KEY, *["a.md"] * items)
    assert await first.lease.update_leadership() is True
    assert await first.drain() == items
    return stolen


@pytest.mark.asyncio
async def test_lease_stays_held_across_a_long_drain(redis, docs):
    """The drain outlasts the lease TTL; refreshing as it goes keeps a rival worker out."""
    stolen = await _long_drain(redis, docs, refresh_per_item=True)
    assert len(stolen) >= 1, "the rival never polled, so nothing was tested"
    assert not any(stolen)


@pytest.mark.asyncio
async def test_rival_takes_the_lease_when_the_drain_does_not_refresh_it(redis, docs):
    """Control: without the per-item refresh the same drain loses the lease, so the test above can fail."""
    stolen = await _long_drain(redis, docs, refresh_per_item=False)
    assert any(stolen)


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
