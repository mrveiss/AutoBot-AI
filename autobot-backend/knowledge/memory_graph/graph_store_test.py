# Copyright (c) mrveiss. All rights reserved.
"""
Unit tests for knowledge.memory_graph.graph_store and schema.

All Redis interactions are mocked with unittest.mock so these tests run
without a real Redis instance.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers — build a minimal fake async Redis client
# ---------------------------------------------------------------------------


def _make_redis(store: dict | None = None):
    """Return a minimal async-redis-style mock backed by *store*.

    Supports:
    - redis.json().get(key)
    - redis.json().set(key, path, value)
    - redis.json().arrappend(key, path, item)
    - redis.exists(key)
    - redis.pipeline()
    - redis.execute_command(*args)
    """
    if store is None:
        store = {}

    json_mock = MagicMock()

    async def _json_get(key):
        return store.get(key)

    async def _json_set(key, path, value, *args, **kwargs):
        if path == "$":
            store[key] = value
        else:
            # Simplified path handling for $.relations only
            if path == "$.relations" and key in store:
                store[key]["relations"] = value

    async def _json_arrappend(key, path, item):
        if key in store:
            store[key].setdefault("relations", []).append(item)
        return [len(store.get(key, {}).get("relations", []))]

    json_mock.get = AsyncMock(side_effect=_json_get)
    json_mock.set = AsyncMock(side_effect=_json_set)
    json_mock.arrappend = AsyncMock(side_effect=_json_arrappend)

    # redis_client.json() must return the same mock each time
    client = MagicMock()
    client.json = MagicMock(return_value=json_mock)

    async def _exists(key):
        return key in store

    client.exists = AsyncMock(side_effect=_exists)

    # pipeline
    pipe = MagicMock()
    pipe_json = MagicMock()
    pipe_arrappend_calls = []

    def _pipe_arrappend(key, path, item):
        pipe_arrappend_calls.append((key, path, item))

    pipe_json.arrappend = MagicMock(side_effect=_pipe_arrappend)
    pipe.json = MagicMock(return_value=pipe_json)

    async def _pipe_execute():
        for key, path, item in pipe_arrappend_calls:
            if key in store:
                store[key].setdefault("relations", []).append(item)
        pipe_arrappend_calls.clear()
        return []

    pipe.execute = AsyncMock(side_effect=_pipe_execute)
    client.pipeline = MagicMock(return_value=pipe)

    async def _execute_command(*args):
        cmd = args[0].upper() if args else ""
        if cmd == "FT.INFO":
            raise Exception("Index not found")
        return None

    client.execute_command = AsyncMock(side_effect=_execute_command)

    return client, store


# ---------------------------------------------------------------------------
# schema tests
# ---------------------------------------------------------------------------


class TestSchema:
    def test_entity_key_prefix(self):
        from knowledge.memory_graph.schema import ENTITY_KEY_PREFIX
        assert ENTITY_KEY_PREFIX == "memory:entity:"

    def test_relation_prefixes(self):
        from knowledge.memory_graph.schema import RELATIONS_IN_PREFIX, RELATIONS_OUT_PREFIX
        assert RELATIONS_OUT_PREFIX == "memory:relations:out:"
        assert RELATIONS_IN_PREFIX == "memory:relations:in:"

    def test_entity_types_are_frozenset(self):
        from knowledge.memory_graph.schema import ENTITY_TYPES
        assert isinstance(ENTITY_TYPES, frozenset)
        assert "conversation" in ENTITY_TYPES
        assert "bug_fix" in ENTITY_TYPES
        assert "task" in ENTITY_TYPES

    def test_relation_types_are_frozenset(self):
        from knowledge.memory_graph.schema import RELATION_TYPES
        assert isinstance(RELATION_TYPES, frozenset)
        assert "fixes" in RELATION_TYPES
        assert "depends_on" in RELATION_TYPES

    def test_index_names(self):
        from knowledge.memory_graph.schema import FULLTEXT_INDEX_NAME, PRIMARY_INDEX_NAME
        assert PRIMARY_INDEX_NAME == "memory_entity_idx"
        assert FULLTEXT_INDEX_NAME == "memory_fulltext_idx"

    @pytest.mark.asyncio
    async def test_ensure_indexes_calls_ft_create(self):
        from knowledge.memory_graph.schema import ensure_indexes

        client, _ = _make_redis()
        created_indexes = []

        async def _execute_command(*args):
            cmd = args[0].upper()
            if cmd == "FT.INFO":
                raise Exception("Index not found")
            if cmd == "FT.CREATE":
                created_indexes.append(args[1])
            return None

        client.execute_command = AsyncMock(side_effect=_execute_command)
        await ensure_indexes(client)
        assert "memory_entity_idx" in created_indexes
        assert "memory_fulltext_idx" in created_indexes

    @pytest.mark.asyncio
    async def test_ensure_indexes_skips_existing(self):
        from knowledge.memory_graph.schema import ensure_indexes

        client, _ = _make_redis()
        created_indexes = []

        async def _execute_command(*args):
            cmd = args[0].upper()
            if cmd == "FT.INFO":
                return ["index_name", args[1]]  # pretend it exists
            if cmd == "FT.CREATE":
                created_indexes.append(args[1])
            return None

        client.execute_command = AsyncMock(side_effect=_execute_command)
        await ensure_indexes(client)
        assert created_indexes == []


# ---------------------------------------------------------------------------
# create_entity tests
# ---------------------------------------------------------------------------


class TestCreateEntity:
    @pytest.mark.asyncio
    async def test_creates_entity_in_store(self):
        from knowledge.memory_graph.graph_store import create_entity

        client, store = _make_redis()
        entity = await create_entity(client, "task", "Build feature X", ["first obs"])

        assert entity["type"] == "task"
        assert entity["name"] == "Build feature X"
        assert entity["observations"] == ["first obs"]
        assert "id" in entity
        assert entity["created_at"] > 0

    @pytest.mark.asyncio
    async def test_persists_to_redis(self):
        from knowledge.memory_graph.graph_store import create_entity

        client, store = _make_redis()
        entity = await create_entity(client, "conversation", "Chat #1", [])

        key = "memory:entity:" + entity["id"]
        assert key in store
        assert store[key]["id"] == entity["id"]

    @pytest.mark.asyncio
    async def test_invalid_type_raises(self):
        from knowledge.memory_graph.graph_store import create_entity

        client, _ = _make_redis()
        with pytest.raises(ValueError, match="Invalid entity_type"):
            await create_entity(client, "UNKNOWN_TYPE", "x", [])

    @pytest.mark.asyncio
    async def test_empty_name_raises(self):
        from knowledge.memory_graph.graph_store import create_entity

        client, _ = _make_redis()
        with pytest.raises(ValueError, match="name must not be empty"):
            await create_entity(client, "task", "  ", [])

    @pytest.mark.asyncio
    async def test_metadata_merged(self):
        from knowledge.memory_graph.graph_store import create_entity

        client, _ = _make_redis()
        entity = await create_entity(
            client, "decision", "Adopt Redis", [], metadata={"session_id": "abc"}
        )
        assert entity["metadata"]["session_id"] == "abc"
        assert entity["metadata"]["status"] == "active"

    @pytest.mark.asyncio
    async def test_redis_error_raises_runtime_error(self):
        from knowledge.memory_graph.graph_store import create_entity

        client, _ = _make_redis()
        client.json().set = AsyncMock(side_effect=Exception("connection refused"))
        with pytest.raises(RuntimeError, match="Entity creation failed"):
            await create_entity(client, "task", "Fail test", [])


# ---------------------------------------------------------------------------
# get_entity tests
# ---------------------------------------------------------------------------


class TestGetEntity:
    @pytest.mark.asyncio
    async def test_returns_entity(self):
        from knowledge.memory_graph.graph_store import create_entity, get_entity

        client, _ = _make_redis()
        created = await create_entity(client, "feature", "Dark mode", ["initial"])
        fetched = await get_entity(client, created["id"])

        assert fetched is not None
        assert fetched["id"] == created["id"]
        assert fetched["name"] == "Dark mode"

    @pytest.mark.asyncio
    async def test_returns_none_for_missing(self):
        from knowledge.memory_graph.graph_store import get_entity

        client, _ = _make_redis()
        result = await get_entity(client, "non-existent-uuid")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_redis_error(self):
        from knowledge.memory_graph.graph_store import get_entity

        client, _ = _make_redis()
        client.json().get = AsyncMock(side_effect=Exception("timeout"))
        result = await get_entity(client, "some-uuid")
        assert result is None


# ---------------------------------------------------------------------------
# create_relation tests
# ---------------------------------------------------------------------------


class TestCreateRelation:
    @pytest.mark.asyncio
    async def test_creates_outgoing_and_incoming(self):
        from knowledge.memory_graph.graph_store import (
            create_entity,
            create_relation,
            get_incoming_relations,
            get_outgoing_relations,
        )

        client, _ = _make_redis()
        a = await create_entity(client, "task", "Task A", [])
        b = await create_entity(client, "task", "Task B", [])

        ok = await create_relation(client, a["id"], b["id"], "depends_on")
        assert ok is True

        out = await get_outgoing_relations(client, a["id"])
        assert len(out) == 1
        assert out[0]["to"] == b["id"]
        assert out[0]["type"] == "depends_on"

        inc = await get_incoming_relations(client, b["id"])
        assert len(inc) == 1
        assert inc[0]["from"] == a["id"]
        assert inc[0]["type"] == "depends_on"

    @pytest.mark.asyncio
    async def test_invalid_rel_type_raises(self):
        from knowledge.memory_graph.graph_store import create_relation

        client, _ = _make_redis()
        with pytest.raises(ValueError, match="Invalid rel_type"):
            await create_relation(client, "id-a", "id-b", "INVALID_TYPE")

    @pytest.mark.asyncio
    async def test_returns_false_on_error(self):
        from knowledge.memory_graph.graph_store import create_relation

        client, _ = _make_redis()
        # Simulate pipeline failure
        client.pipeline().execute = AsyncMock(side_effect=Exception("pipe error"))
        result = await create_relation(client, "id-a", "id-b", "fixes")
        assert result is False

    @pytest.mark.asyncio
    async def test_metadata_stored_on_outgoing_edge(self):
        from knowledge.memory_graph.graph_store import (
            create_entity,
            create_relation,
            get_outgoing_relations,
        )

        client, _ = _make_redis()
        a = await create_entity(client, "bug_fix", "Fix A", [])
        b = await create_entity(client, "bug_fix", "Fix B", [])
        await create_relation(
            client, a["id"], b["id"], "relates_to", metadata={"strength": 0.9}
        )
        out = await get_outgoing_relations(client, a["id"])
        assert out[0]["metadata"]["strength"] == 0.9


# ---------------------------------------------------------------------------
# get_outgoing_relations / get_incoming_relations tests
# ---------------------------------------------------------------------------


class TestGetRelations:
    @pytest.mark.asyncio
    async def test_empty_when_no_relations(self):
        from knowledge.memory_graph.graph_store import (
            get_incoming_relations,
            get_outgoing_relations,
        )

        client, _ = _make_redis()
        assert await get_outgoing_relations(client, "no-such-id") == []
        assert await get_incoming_relations(client, "no-such-id") == []

    @pytest.mark.asyncio
    async def test_empty_on_redis_error(self):
        from knowledge.memory_graph.graph_store import get_outgoing_relations

        client, _ = _make_redis()
        client.json().get = AsyncMock(side_effect=Exception("err"))
        assert await get_outgoing_relations(client, "id") == []


# ---------------------------------------------------------------------------
# traverse_relations tests
# ---------------------------------------------------------------------------


class TestTraverseRelations:
    @pytest.mark.asyncio
    async def test_single_hop(self):
        from knowledge.memory_graph.graph_store import (
            create_entity,
            create_relation,
            traverse_relations,
        )

        client, _ = _make_redis()
        root = await create_entity(client, "task", "Root", [])
        child = await create_entity(client, "task", "Child", [])
        await create_relation(client, root["id"], child["id"], "depends_on")

        result = await traverse_relations(client, root["id"], "depends_on", max_depth=1)
        assert len(result) == 1
        assert result[0]["id"] == child["id"]

    @pytest.mark.asyncio
    async def test_multi_hop(self):
        from knowledge.memory_graph.graph_store import (
            create_entity,
            create_relation,
            traverse_relations,
        )

        client, _ = _make_redis()
        root = await create_entity(client, "task", "Root", [])
        mid = await create_entity(client, "task", "Middle", [])
        leaf = await create_entity(client, "task", "Leaf", [])
        await create_relation(client, root["id"], mid["id"], "depends_on")
        await create_relation(client, mid["id"], leaf["id"], "depends_on")

        result = await traverse_relations(client, root["id"], "depends_on", max_depth=2)
        ids = [e["id"] for e in result]
        assert mid["id"] in ids
        assert leaf["id"] in ids

    @pytest.mark.asyncio
    async def test_relation_type_filter(self):
        from knowledge.memory_graph.graph_store import (
            create_entity,
            create_relation,
            traverse_relations,
        )

        client, _ = _make_redis()
        root = await create_entity(client, "task", "Root", [])
        a = await create_entity(client, "task", "A", [])
        b = await create_entity(client, "feature", "B", [])
        await create_relation(client, root["id"], a["id"], "depends_on")
        await create_relation(client, root["id"], b["id"], "relates_to")

        result = await traverse_relations(client, root["id"], "depends_on", max_depth=1)
        ids = [e["id"] for e in result]
        assert a["id"] in ids
        assert b["id"] not in ids

    @pytest.mark.asyncio
    async def test_no_cycle(self):
        from knowledge.memory_graph.graph_store import (
            create_entity,
            create_relation,
            traverse_relations,
        )

        client, _ = _make_redis()
        x = await create_entity(client, "task", "X", [])
        y = await create_entity(client, "task", "Y", [])
        await create_relation(client, x["id"], y["id"], "depends_on")
        await create_relation(client, y["id"], x["id"], "depends_on")

        # Must not loop forever
        result = await traverse_relations(client, x["id"], "depends_on", max_depth=5)
        ids = [e["id"] for e in result]
        # Y reachable; X already in visited so not duplicated
        assert ids.count(y["id"]) == 1

    @pytest.mark.asyncio
    async def test_empty_when_no_relations(self):
        from knowledge.memory_graph.graph_store import create_entity, traverse_relations

        client, _ = _make_redis()
        root = await create_entity(client, "task", "Alone", [])
        result = await traverse_relations(client, root["id"])
        assert result == []

    @pytest.mark.asyncio
    async def test_max_depth_zero_returns_empty(self):
        from knowledge.memory_graph.graph_store import (
            create_entity,
            create_relation,
            traverse_relations,
        )

        client, _ = _make_redis()
        root = await create_entity(client, "task", "Root", [])
        child = await create_entity(client, "task", "Child", [])
        await create_relation(client, root["id"], child["id"], "depends_on")

        result = await traverse_relations(client, root["id"], max_depth=0)
        assert result == []
