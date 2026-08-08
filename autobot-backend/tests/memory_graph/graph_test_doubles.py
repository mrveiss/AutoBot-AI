# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Shared test doubles for the memory property graph.

Extracted from ``test_property_graph.py`` in #13474 so the shortest-path wiring
test can drive the *same* in-memory graph the unit tests use, rather than a
second copy of it.

Nothing here talks to a real Redis: ``FakeRedis`` implements only the handful of
hash/set/sorted-set operations PropertyGraph actually issues.
"""

from typing import Dict, List

from autobot_memory_graph.property_graph import PropertyGraph
from autobot_memory_graph.property_graph_mixin import PropertyGraphMixin


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


class MixinHarness(PropertyGraphMixin):
    """Minimal host for ``PropertyGraphMixin.find_path`` (#13474).

    AutoBotMemoryGraph needs Redis and a search index to construct, but
    ``find_path`` depends on exactly two things: ``get_entity`` (name -> entity)
    and ``graph`` (the PropertyGraph). Supplying just those keeps tests on the
    wiring under test instead of the memory graph's initialisation path — the
    mixin's own code runs unmodified.
    """

    def __init__(self, graph: PropertyGraph, entities: Dict[str, dict]) -> None:
        self._graph_obj = graph
        self._entities = entities

    @property
    def graph(self) -> PropertyGraph:
        return self._graph_obj

    async def get_entity(self, entity_id=None, entity_name=None, include_relations=False):
        return self._entities.get(entity_name)


async def make_harness() -> MixinHarness:
    """Graph with 'Redis Config' -CAUSED-> 'Incident 7', plus an unlinked 'Orphan'."""
    graph = make_graph()
    entities = {
        "Redis Config": {"id": "e1", "name": "Redis Config", "type": "decision"},
        "Incident 7": {"id": "e2", "name": "Incident 7", "type": "incident"},
        "Orphan": {"id": "e3", "name": "Orphan", "type": "note"},
    }
    for ent in entities.values():
        await graph.add_node(ent["id"], {"name": ent["name"], "type": ent["type"]})
    await graph.add_edge("e1", "e2", "CAUSED")
    return MixinHarness(graph, entities)
