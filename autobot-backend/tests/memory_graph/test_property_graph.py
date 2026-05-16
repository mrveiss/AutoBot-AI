# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for PropertyGraph — queryable property graph backed by Redis.

Issue #3230: Replace Redis adjacency list with queryable property graph.

All tests run without a live Redis — the async Redis client is replaced with
an in-memory AsyncMock that delegates to a simple dict/set store.
"""

import sys
import types
from typing import Dict, List
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Stub out autobot_shared so PropertyGraph imports without real Redis
# ---------------------------------------------------------------------------

_autobot_shared = types.ModuleType("autobot_shared")
_autobot_shared.__path__ = []

_redis_client_mod = types.ModuleType("autobot_shared.redis_client")
_redis_client_mod.get_redis_client = MagicMock(return_value=AsyncMock())
_redis_client_mod.get_async_redis_client = MagicMock(return_value=AsyncMock())

_redis_mgmt_pkg = types.ModuleType("autobot_shared.redis_management")
_redis_mgmt_pkg.__path__ = []

_redis_mgmt_types = types.ModuleType("autobot_shared.redis_management.types")
_redis_mgmt_types.DATABASE_MAPPING = {
    "main": 0,
    "knowledge": 1,
    "prompts": 2,
    "agents": 3,
}

_ssot_config_mod = types.ModuleType("autobot_shared.ssot_config")
_vm_config = MagicMock()
_vm_config.redis = "127.0.0.1"
_ssot_config_obj = MagicMock()
_ssot_config_obj.vm = _vm_config
_ssot_config_mod.config = _ssot_config_obj

for name, mod in [
    ("autobot_shared", _autobot_shared),
    ("autobot_shared.redis_client", _redis_client_mod),
    ("autobot_shared.redis_management", _redis_mgmt_pkg),
    ("autobot_shared.redis_management.types", _redis_mgmt_types),
    ("autobot_shared.ssot_config", _ssot_config_mod),
]:
    sys.modules.setdefault(name, mod)

from autobot_memory_graph.property_graph import (  # noqa: E402
    PropertyGraph,
    _adj_in_all_key,
    _adj_in_key,
    _adj_out_all_key,
    _adj_out_key,
    _edge_key,
    _node_key,
    _prop_index_key,
)

# ---------------------------------------------------------------------------
# Fake Redis store
# ---------------------------------------------------------------------------


class FakeRedis:
    """Minimal in-memory async Redis mock with the operations used by PropertyGraph."""

    def __init__(self) -> None:
        self._hashes: Dict[str, Dict[bytes, bytes]] = {}
        self._sets: Dict[str, set] = {}
        self._zsets: Dict[str, Dict[str, float]] = {}

    # ---- hash ----

    async def hset(self, key: str, mapping: Dict | None = None, **kwargs) -> int:
        if key not in self._hashes:
            self._hashes[key] = {}
        if mapping:
            for k, v in mapping.items():
                bk = k.encode("utf-8") if isinstance(k, str) else k
                bv = v.encode("utf-8") if isinstance(v, str) else str(v).encode("utf-8")
                self._hashes[key][bk] = bv
        return 1

    async def hgetall(self, key: str) -> Dict[bytes, bytes]:
        return dict(self._hashes.get(key, {}))

    async def hdel(self, key: str, *fields) -> int:
        h = self._hashes.get(key, {})
        removed = 0
        for f in fields:
            bk = f.encode("utf-8") if isinstance(f, str) else f
            if bk in h:
                del h[bk]
                removed += 1
        return removed

    # ---- set ----

    async def sadd(self, key: str, *members) -> int:
        if key not in self._sets:
            self._sets[key] = set()
        count = 0
        for m in members:
            s = m.encode("utf-8") if isinstance(m, str) else m
            if s not in self._sets[key]:
                self._sets[key].add(s)
                count += 1
        return count

    async def srem(self, key: str, *members) -> int:
        s = self._sets.get(key, set())
        removed = 0
        for m in members:
            bm = m.encode("utf-8") if isinstance(m, str) else m
            if bm in s:
                s.discard(bm)
                removed += 1
        return removed

    async def smembers(self, key: str) -> set:
        return set(self._sets.get(key, set()))

    # ---- sorted set ----

    async def zadd(self, key: str, mapping: Dict[str, float]) -> int:
        if key not in self._zsets:
            self._zsets[key] = {}
        for member, score in mapping.items():
            self._zsets[key][member] = score
        return len(mapping)

    async def zrem(self, key: str, *members) -> int:
        z = self._zsets.get(key, {})
        removed = 0
        for m in members:
            if m in z:
                del z[m]
                removed += 1
        return removed

    async def zrange(self, key: str, start: int, stop: int) -> List[bytes]:
        z = self._zsets.get(key, {})
        sorted_members = sorted(z.keys(), key=lambda k: z[k])
        if stop == -1:
            stop = len(sorted_members)
        else:
            stop += 1
        return [m.encode("utf-8") if isinstance(m, str) else m for m in sorted_members[start:stop]]

    # ---- generic ----

    async def exists(self, key: str) -> int:
        return 1 if (key in self._hashes or key in self._sets or key in self._zsets) else 0

    async def delete(self, *keys) -> int:
        removed = 0
        for key in keys:
            for store in (self._hashes, self._sets, self._zsets):
                if key in store:
                    del store[key]
                    removed += 1
        return removed


def make_graph() -> PropertyGraph:
    """Return a PropertyGraph wired to FakeRedis."""
    g = PropertyGraph(database="knowledge")
    g._redis = FakeRedis()
    return g


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAddNode:
    @pytest.mark.asyncio
    async def test_add_node_stores_properties(self):
        g = make_graph()
        await g.add_node("n1", {"type": "file", "lang": "python"})
        node = await g.get_node("n1")
        assert node is not None
        assert node["type"] == "file"
        assert node["lang"] == "python"
        assert node["id"] == "n1"

    @pytest.mark.asyncio
    async def test_add_node_upsert_merges(self):
        g = make_graph()
        await g.add_node("n1", {"type": "file"})
        await g.add_node("n1", {"lang": "python"})
        node = await g.get_node("n1")
        assert node["type"] == "file"
        assert node["lang"] == "python"

    @pytest.mark.asyncio
    async def test_get_node_missing_returns_none(self):
        g = make_graph()
        assert await g.get_node("missing") is None


class TestAddEdge:
    @pytest.mark.asyncio
    async def test_add_edge_returns_edge_id(self):
        g = make_graph()
        await g.add_node("a", {"type": "service"})
        await g.add_node("b", {"type": "service"})
        edge_id = await g.add_edge("a", "b", "DEPENDS_ON")
        assert isinstance(edge_id, str)
        assert len(edge_id) > 0

    @pytest.mark.asyncio
    async def test_add_edge_stores_from_to_relation(self):
        g = make_graph()
        await g.add_node("a", {"type": "task"})
        await g.add_node("b", {"type": "task"})
        edge_id = await g.add_edge("a", "b", "BLOCKS", {"priority": "high"})
        edge = await g.get_edge(edge_id)
        assert edge is not None
        assert edge["from"] == "a"
        assert edge["to"] == "b"
        assert edge["relation"] == "BLOCKS"
        assert edge["priority"] == "high"

    @pytest.mark.asyncio
    async def test_add_edge_autocreates_missing_nodes(self):
        g = make_graph()
        await g.add_edge("x", "y", "RELATES_TO")
        assert await g.get_node("x") is not None
        assert await g.get_node("y") is not None


class TestGetNeighbors:
    @pytest.mark.asyncio
    async def test_get_neighbors_outgoing(self):
        g = make_graph()
        await g.add_node("root", {"type": "module"})
        await g.add_node("dep1", {"type": "module"})
        await g.add_node("dep2", {"type": "module"})
        await g.add_edge("root", "dep1", "DEPENDS_ON")
        await g.add_edge("root", "dep2", "DEPENDS_ON")

        neighbours = await g.get_neighbors("root", relation="DEPENDS_ON")
        neighbour_ids = {e["node"]["id"] for e in neighbours}
        assert neighbour_ids == {"dep1", "dep2"}

    @pytest.mark.asyncio
    async def test_get_neighbors_filtered_by_relation(self):
        g = make_graph()
        await g.add_node("a", {})
        await g.add_node("b", {})
        await g.add_node("c", {})
        await g.add_edge("a", "b", "DEPENDS_ON")
        await g.add_edge("a", "c", "CONTAINS")

        depends = await g.get_neighbors("a", relation="DEPENDS_ON")
        assert len(depends) == 1
        assert depends[0]["node"]["id"] == "b"

    @pytest.mark.asyncio
    async def test_get_neighbors_incoming(self):
        g = make_graph()
        await g.add_node("child", {})
        await g.add_node("parent", {})
        await g.add_edge("parent", "child", "CONTAINS")

        incoming = await g.get_neighbors("child", direction="incoming")
        assert len(incoming) == 1
        assert incoming[0]["node"]["id"] == "parent"

    @pytest.mark.asyncio
    async def test_get_neighbors_both_directions(self):
        g = make_graph()
        await g.add_node("mid", {})
        await g.add_node("up", {})
        await g.add_node("down", {})
        await g.add_edge("up", "mid", "LEADS_TO")
        await g.add_edge("mid", "down", "LEADS_TO")

        both = await g.get_neighbors("mid", direction="both")
        ids = {e["node"]["id"] for e in both}
        assert ids == {"up", "down"}

    @pytest.mark.asyncio
    async def test_get_neighbors_no_relation_filter(self):
        g = make_graph()
        await g.add_node("a", {})
        await g.add_node("b", {})
        await g.add_node("c", {})
        await g.add_edge("a", "b", "DEPENDS_ON")
        await g.add_edge("a", "c", "CONTAINS")

        all_neighbours = await g.get_neighbors("a")
        ids = {e["node"]["id"] for e in all_neighbours}
        assert ids == {"b", "c"}


class TestQueryNodes:
    @pytest.mark.asyncio
    async def test_query_nodes_single_filter(self):
        g = make_graph()
        await g.add_node("bug1", {"type": "bug", "severity": "high"})
        await g.add_node("bug2", {"type": "bug", "severity": "low"})
        await g.add_node("feat1", {"type": "feature", "severity": "high"})

        results = await g.query_nodes({"type": "bug"})
        ids = {n["id"] for n in results}
        assert "bug1" in ids
        assert "bug2" in ids
        assert "feat1" not in ids

    @pytest.mark.asyncio
    async def test_query_nodes_multi_filter(self):
        g = make_graph()
        await g.add_node("bug1", {"type": "bug", "severity": "high"})
        await g.add_node("bug2", {"type": "bug", "severity": "low"})

        results = await g.query_nodes({"type": "bug", "severity": "high"})
        assert len(results) == 1
        assert results[0]["id"] == "bug1"

    @pytest.mark.asyncio
    async def test_query_nodes_no_match(self):
        g = make_graph()
        await g.add_node("n1", {"type": "task"})

        results = await g.query_nodes({"type": "nonexistent"})
        assert results == []

    @pytest.mark.asyncio
    async def test_query_nodes_empty_filter_returns_empty(self):
        g = make_graph()
        await g.add_node("n1", {"type": "task"})
        results = await g.query_nodes({})
        assert results == []


class TestDeleteNode:
    @pytest.mark.asyncio
    async def test_delete_node_removes_node(self):
        g = make_graph()
        await g.add_node("n1", {"type": "task"})
        deleted = await g.delete_node("n1")
        assert deleted is True
        assert await g.get_node("n1") is None

    @pytest.mark.asyncio
    async def test_delete_node_returns_false_if_missing(self):
        g = make_graph()
        assert await g.delete_node("ghost") is False

    @pytest.mark.asyncio
    async def test_delete_node_removes_outgoing_edges(self):
        g = make_graph()
        await g.add_node("a", {"type": "x"})
        await g.add_node("b", {"type": "x"})
        edge_id = await g.add_edge("a", "b", "DEPENDS_ON")
        await g.delete_node("a")
        assert await g.get_edge(edge_id) is None


class TestDeleteEdge:
    @pytest.mark.asyncio
    async def test_delete_edge_removes_edge(self):
        g = make_graph()
        await g.add_node("a", {})
        await g.add_node("b", {})
        edge_id = await g.add_edge("a", "b", "RELATES_TO")
        deleted = await g.delete_edge(edge_id)
        assert deleted is True
        assert await g.get_edge(edge_id) is None

    @pytest.mark.asyncio
    async def test_delete_edge_missing_returns_false(self):
        g = make_graph()
        assert await g.delete_edge("nonexistent-edge") is False

    @pytest.mark.asyncio
    async def test_delete_edge_removes_from_adjacency(self):
        g = make_graph()
        await g.add_node("a", {})
        await g.add_node("b", {})
        edge_id = await g.add_edge("a", "b", "DEPENDS_ON")
        await g.delete_edge(edge_id)
        neighbours = await g.get_neighbors("a", relation="DEPENDS_ON")
        assert len(neighbours) == 0


class TestMultiHop:
    @pytest.mark.asyncio
    async def test_multi_hop_depth_1(self):
        g = make_graph()
        for n in ("a", "b", "c"):
            await g.add_node(n, {"id": n})
        await g.add_edge("a", "b", "LEADS_TO")
        await g.add_edge("b", "c", "LEADS_TO")

        results = await g.multi_hop("a", max_depth=1)
        ids = {r["node"]["id"] for r in results}
        assert ids == {"b"}

    @pytest.mark.asyncio
    async def test_multi_hop_depth_2(self):
        g = make_graph()
        for n in ("a", "b", "c"):
            await g.add_node(n, {"id": n})
        await g.add_edge("a", "b", "LEADS_TO")
        await g.add_edge("b", "c", "LEADS_TO")

        results = await g.multi_hop("a", max_depth=2)
        ids = {r["node"]["id"] for r in results}
        assert ids == {"b", "c"}

    @pytest.mark.asyncio
    async def test_multi_hop_no_cycles(self):
        """Graph with a cycle — multi_hop should not revisit nodes."""
        g = make_graph()
        for n in ("a", "b", "c"):
            await g.add_node(n, {"id": n})
        await g.add_edge("a", "b", "LEADS_TO")
        await g.add_edge("b", "c", "LEADS_TO")
        await g.add_edge("c", "a", "LEADS_TO")  # cycle back

        results = await g.multi_hop("a", max_depth=5)
        ids = [r["node"]["id"] for r in results]
        # Each node visited at most once
        assert len(ids) == len(set(ids))

    @pytest.mark.asyncio
    async def test_multi_hop_relation_filter(self):
        g = make_graph()
        for n in ("a", "b", "c"):
            await g.add_node(n, {"id": n})
        await g.add_edge("a", "b", "DEPENDS_ON")
        await g.add_edge("a", "c", "CONTAINS")

        results = await g.multi_hop("a", relation="DEPENDS_ON", max_depth=1)
        ids = {r["node"]["id"] for r in results}
        assert ids == {"b"}
        assert "c" not in ids


class TestSubgraph:
    @pytest.mark.asyncio
    async def test_subgraph_includes_center_node(self):
        g = make_graph()
        await g.add_node("center", {"type": "module"})
        result = await g.subgraph("center", max_depth=1)
        node_ids = {n["id"] for n in result["nodes"]}
        assert "center" in node_ids

    @pytest.mark.asyncio
    async def test_subgraph_includes_adjacent_nodes(self):
        g = make_graph()
        await g.add_node("center", {})
        await g.add_node("left", {})
        await g.add_node("right", {})
        await g.add_edge("left", "center", "LEADS_TO")
        await g.add_edge("center", "right", "LEADS_TO")

        result = await g.subgraph("center", max_depth=1)
        node_ids = {n["id"] for n in result["nodes"]}
        assert {"center", "left", "right"} == node_ids

    @pytest.mark.asyncio
    async def test_subgraph_edges_captured(self):
        g = make_graph()
        await g.add_node("a", {})
        await g.add_node("b", {})
        await g.add_edge("a", "b", "DEPENDS_ON")

        result = await g.subgraph("a", max_depth=1)
        assert len(result["edges"]) >= 1
        edge = result["edges"][0]
        assert edge["from"] == "a"
        assert edge["to"] == "b"


class TestShortestPath:
    @pytest.mark.asyncio
    async def test_shortest_path_direct(self):
        g = make_graph()
        await g.add_node("src", {})
        await g.add_node("dst", {})
        await g.add_edge("src", "dst", "LEADS_TO")

        path = await g.shortest_path("src", "dst")
        assert path is not None
        assert len(path) == 1
        assert path[0]["node"]["id"] == "dst"

    @pytest.mark.asyncio
    async def test_shortest_path_two_hops(self):
        g = make_graph()
        for n in ("a", "b", "c"):
            await g.add_node(n, {"id": n})
        await g.add_edge("a", "b", "LEADS_TO")
        await g.add_edge("b", "c", "LEADS_TO")

        path = await g.shortest_path("a", "c")
        assert path is not None
        node_ids = [step["node"]["id"] for step in path]
        assert node_ids == ["b", "c"]

    @pytest.mark.asyncio
    async def test_shortest_path_same_node(self):
        g = make_graph()
        await g.add_node("a", {})
        path = await g.shortest_path("a", "a")
        assert path == []

    @pytest.mark.asyncio
    async def test_shortest_path_unreachable(self):
        g = make_graph()
        await g.add_node("a", {})
        await g.add_node("b", {})  # no edge

        path = await g.shortest_path("a", "b")
        assert path is None

    @pytest.mark.asyncio
    async def test_shortest_path_prefers_shorter(self):
        """When two paths exist, BFS returns the shorter one."""
        g = make_graph()
        for n in ("a", "b", "c", "d"):
            await g.add_node(n, {"id": n})
        # Short: a -> d (direct)
        await g.add_edge("a", "d", "LEADS_TO")
        # Long: a -> b -> c -> d
        await g.add_edge("a", "b", "LEADS_TO")
        await g.add_edge("b", "c", "LEADS_TO")
        await g.add_edge("c", "d", "LEADS_TO")

        path = await g.shortest_path("a", "d")
        assert path is not None
        assert len(path) == 1  # direct hop wins
