# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for the mesh:reembed_queue consumer (#20535)."""

import inspect
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
        await mesh_reembed_startup._init_mesh_reembed_consumer(app)
    start.assert_awaited_once()
    assert app.state.mesh_reembed_consumer == "consumer"


def test_lifespan_startup_calls_the_init():
    assert "_init_mesh_reembed_consumer(app)" in inspect.getsource(lifespan._init_mesh_brain_scheduler)


def test_consumer_reads_the_key_the_producer_writes():
    assert rc.QUEUE_KEY == _REEMBED_QUEUE_KEY
