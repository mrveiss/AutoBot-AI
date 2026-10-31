# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""get_or_create_entity is atomic and never reads a Redis error as 'absent' (#18417)."""

import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from autobot_memory_graph import AutoBotMemoryGraph
from autobot_memory_graph.owner_scope import UNSCOPED_ALL_USERS, OwnerScope


class FakeRedis:
    """Just enough Redis: strings with NX, JSON documents, and an injectable outage."""

    def __init__(self):
        self.strings, self.docs, self.down = {}, {}, False
        self.search_down = False
        self.eval_gate = None  # an Event the FIRST eval caller waits on, to stall it mid-flight
        self._first_eval = True

    async def _release(self, _numkeys, index_key, owner_id):
        """Python mirror of RELEASE_IF_OWNER_LUA: compare and delete in one step."""
        self._check()
        if self.strings.get(index_key) == owner_id:
            del self.strings[index_key]
            return 1
        return 0

    async def eval(self, script, numkeys, index_key, doc_key=None, new_id=None, doc_json=None, prefix=None):
        """Python mirror of CLAIM_AND_WRITE_LUA. No await between read and write = atomic, like the script."""
        from autobot_memory_graph import entity_upsert

        if script == entity_upsert.RELEASE_IF_OWNER_LUA:
            return await self._release(numkeys, index_key, doc_key)
        assert script == entity_upsert.CLAIM_AND_WRITE_LUA
        if self._first_eval and self.eval_gate is not None:
            self._first_eval = False
            await self.eval_gate.wait()
        self._check()
        existing = self.strings.get(index_key)
        if existing and f"{prefix}{existing}" in self.docs:
            return existing
        self.strings[index_key] = new_id
        self.docs[doc_key] = json.loads(doc_json)
        return new_id

    async def execute_command(self, *args):
        self._check()
        if self.search_down:
            raise RuntimeError("RediSearch index missing")
        return [0]

    async def scan_iter(self, match=None):
        self._check()
        for key in list(self.docs):
            yield key

    async def set(self, key, value, nx=False):
        await asyncio.sleep(0)  # yield, so concurrent callers genuinely interleave
        self._check()
        if nx and key in self.strings:
            return None
        self.strings[key] = value
        return True

    async def get(self, key):
        await asyncio.sleep(0)
        self._check()
        return self.strings.get(key)

    async def delete(self, key):
        self.strings.pop(key, None)

    def json(self):
        outer = self

        class _Json:
            async def get(self, key):
                await asyncio.sleep(0)
                outer._check()
                return outer.docs.get(key)

            async def set(self, key, path, doc):
                await asyncio.sleep(0)
                outer._check()
                outer.docs[key] = doc

        return _Json()

    def _check(self):
        if self.down:
            raise ConnectionError("redis down")


def _graph(redis, existing_by_name=None):
    graph = AutoBotMemoryGraph()
    graph._initialized = True
    graph.redis_client = redis
    graph.knowledge_base = None
    if existing_by_name is not None:
        graph.get_entity = AsyncMock(return_value=existing_by_name)
    return graph


@pytest.mark.asyncio
async def test_concurrent_double_upsert_yields_one_entity():
    redis = FakeRedis()
    graph = _graph(redis)

    results = await asyncio.gather(
        graph.get_or_create_entity("TASK", "Redis", ["a"], owner=OwnerScope.for_user("user-a")),
        graph.get_or_create_entity("TASK", "Redis", ["a"], owner=OwnerScope.for_user("user-a")),
    )

    assert len(redis.docs) == 1
    assert sorted(created for _, created in results) == [False, True]
    assert results[0][0]["id"] == results[1][0]["id"]


@pytest.mark.asyncio
async def test_name_case_is_not_identity():
    redis = FakeRedis()
    graph = _graph(redis)
    await graph.get_or_create_entity("TASK", "Redis", [], owner=OwnerScope.for_user("user-a"))
    _, created = await graph.get_or_create_entity("TASK", " redis ", [], owner=OwnerScope.for_user("user-a"))
    assert created is False and len(redis.docs) == 1


@pytest.mark.asyncio
async def test_redis_error_raises_and_creates_nothing():
    redis = FakeRedis()
    redis.down = True
    graph = _graph(redis)

    with pytest.raises(ConnectionError):
        await graph.get_or_create_entity("TASK", "Redis", [], owner=OwnerScope.for_user("user-a"))

    assert redis.docs == {} and redis.strings == {}


@pytest.mark.asyncio
async def test_legacy_entity_without_index_is_adopted_not_duplicated():
    redis = FakeRedis()
    legacy = {"id": "old-1", "name": "Redis", "_resolution": "exact", "owner_user_id": "user-a"}
    redis.docs["memory:entity:old-1"] = legacy
    graph = _graph(redis, existing_by_name=legacy)
    redis.strings.clear()

    entity, created = await graph.get_or_create_entity("TASK", "Redis", [], owner=OwnerScope.for_user("user-a"))

    assert created is False and entity["id"] == "old-1"
    assert list(redis.docs) == ["memory:entity:old-1"]


@pytest.mark.asyncio
async def test_a_racer_stalled_between_lookup_and_write_cannot_duplicate():
    """The claim and the write are one step: there is no 'claimed, not yet written' state to repair."""
    redis = FakeRedis()
    redis.eval_gate = asyncio.Event()
    graph = _graph(redis)

    stalled = asyncio.ensure_future(
        graph.get_or_create_entity("TASK", "Redis", ["a"], owner=OwnerScope.for_user("user-a"))
    )
    await asyncio.sleep(0.01)  # the first racer is now parked inside eval
    fast_entity, fast_created = await graph.get_or_create_entity(
        "TASK", "Redis", ["b"], owner=OwnerScope.for_user("user-a")
    )
    redis.eval_gate.set()
    slow_entity, slow_created = await stalled

    assert len(redis.docs) == 1
    assert fast_created is True and slow_created is False
    assert slow_entity["id"] == fast_entity["id"]


@pytest.mark.asyncio
async def test_a_racer_that_loses_the_claim_to_another_owner_is_refused_not_handed_their_entity():
    """The lost-race path re-checks the owner: the winner belongs to someone else (#18825)."""
    from autobot_memory_graph.entity_upsert import EntityNameInUse

    redis = FakeRedis()
    redis.eval_gate = asyncio.Event()
    graph = _graph(redis)

    stalled = asyncio.ensure_future(
        graph.get_or_create_entity("TASK", "Redis", ["a"], owner=OwnerScope.for_user("user-a"))
    )
    await asyncio.sleep(0.01)  # user-a is parked inside eval
    await graph.get_or_create_entity("TASK", "Redis", ["b"], owner=OwnerScope.for_user("user-b"))
    redis.eval_gate.set()

    with pytest.raises(EntityNameInUse) as refused:
        await stalled
    assert "Redis" not in str(refused.value)
    assert len(redis.docs) == 1


@pytest.mark.asyncio
async def test_a_dangling_claim_is_repaired_atomically_not_duplicated():
    redis = FakeRedis()
    graph = _graph(redis)
    from autobot_memory_graph import entity_upsert

    redis.strings[entity_upsert.name_index_key("Redis")] = "gone-id"  # index points at a deleted document
    entity, created = await graph.get_or_create_entity("TASK", "Redis", [], owner=OwnerScope.for_user("user-a"))

    assert created is True and list(redis.docs) == [f"memory:entity:{entity['id']}"]


@pytest.mark.asyncio
async def test_legacy_lookup_error_raises_and_creates_nothing():
    """The index read succeeds (nothing there), then the legacy lookup cannot read: no create (#18417 H1)."""
    redis = FakeRedis()
    redis.search_down = True
    graph = _graph(redis)

    async def scan_fails(match=None):
        raise ConnectionError("redis down mid-lookup")
        yield  # pragma: no cover

    redis.scan_iter = scan_fails

    with pytest.raises(ConnectionError):
        await graph.get_or_create_entity("TASK", "Redis", [], owner=OwnerScope.for_user("user-a"))

    assert redis.docs == {}


@pytest.mark.asyncio
async def test_get_entity_strict_raises_where_default_returns_none():
    """Contrast: the default swallows a read error; strict surfaces it."""
    redis = FakeRedis()
    redis.down = True
    graph = AutoBotMemoryGraph()
    graph._initialized = True
    graph.redis_client = redis

    assert await graph.get_entity(entity_id="x", owner=UNSCOPED_ALL_USERS) is None
    with pytest.raises(ConnectionError):
        await graph.get_entity(entity_id="x", strict=True, owner=UNSCOPED_ALL_USERS)
    with pytest.raises(ConnectionError):
        await graph.get_entity(entity_name="x", strict=True, owner=UNSCOPED_ALL_USERS)


@pytest.mark.asyncio
async def test_delete_entity_drops_the_name_index():
    from autobot_memory_graph import entity_upsert

    redis = FakeRedis()
    graph = _graph(redis)
    entity, _ = await graph.get_or_create_entity("TASK", "Redis", [], owner=OwnerScope.for_user("user-a"))
    graph.get_entity = AsyncMock(return_value={**entity, "_resolution": "exact"})

    async def delete_all(*keys):
        for key in keys:
            redis.strings.pop(key, None)
            redis.docs.pop(key, None)
        return 1

    redis.delete = delete_all
    assert await graph.delete_entity("Redis") is True

    assert entity_upsert.name_index_key("Redis") not in redis.strings
    graph.get_entity = AsyncMock(return_value=None)  # the entity is gone
    _, created = await graph.get_or_create_entity("TASK", "Redis", [], owner=OwnerScope.for_user("user-a"))
    assert created is True


@pytest.mark.asyncio
async def test_delete_does_not_drop_an_index_that_points_elsewhere():
    from autobot_memory_graph import entity_upsert

    redis = FakeRedis()
    graph = _graph(redis)
    redis.strings[entity_upsert.name_index_key("Redis")] = "someone-else"
    await entity_upsert.release_name(graph, "Redis", "mine")
    assert redis.strings[entity_upsert.name_index_key("Redis")] == "someone-else"


@pytest.mark.asyncio
async def test_a_reclaim_between_read_and_delete_survives():
    """The old GET -> compare -> DEL lost a claim landing in the gap; compare-and-delete cannot."""
    from autobot_memory_graph import entity_upsert

    redis = FakeRedis()
    graph = _graph(redis)
    key = entity_upsert.name_index_key("Redis")
    redis.strings[key] = "old"
    stale_read = redis.strings[key]  # what a GET-then-DEL releaser would have compared against
    redis.strings[key] = "new"  # a re-claim lands in the gap

    await entity_upsert.release_name(graph, "Redis", stale_read)

    assert redis.strings[key] == "new"
