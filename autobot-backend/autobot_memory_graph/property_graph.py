# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Property Graph — queryable graph store backed by Redis hashes and sorted sets.

Issue #3230: Replace Redis adjacency list with a queryable property graph for
knowledge relationships.

Design:
- Nodes: Redis hash  ``pg:node:{id}``  — arbitrary property key/value pairs
- Edges: Redis hash  ``pg:edge:{id}``  — arbitrary property key/value pairs
                                         plus mandatory ``from``, ``to``, ``relation``
- Adjacency (typed, outgoing):  sorted set  ``pg:adj:out:{node_id}:{relation}``
  members = edge_id, score = created_at_ms
- Adjacency (typed, incoming):  sorted set  ``pg:adj:in:{node_id}:{relation}``
- All-relations index (outgoing): set  ``pg:adj:out:{node_id}``  — member = "rel\x00edge_id"
- Property-value index:  set  ``pg:idx:prop:{key}:{value}`` — member = node_id
  (populated on add_node and add_edge — enables query_nodes without full scan)

All Redis operations are async (redis.asyncio).
"""

import json
import time
import uuid
from collections import deque
from typing import Any, Dict, List, Set, Tuple

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client

logger = get_logger(__name__)

# Key prefixes
_PFX_NODE = "pg:node:"
_PFX_EDGE = "pg:edge:"
_PFX_ADJ_OUT = "pg:adj:out:"
_PFX_ADJ_IN = "pg:adj:in:"
_PFX_IDX_PROP = "pg:idx:prop:"


def _node_key(node_id: str) -> str:
    return f"{_PFX_NODE}{node_id}"


def _edge_key(edge_id: str) -> str:
    return f"{_PFX_EDGE}{edge_id}"


def _adj_out_key(node_id: str, relation: str) -> str:
    return f"{_PFX_ADJ_OUT}{node_id}:{relation}"


def _adj_in_key(node_id: str, relation: str) -> str:
    return f"{_PFX_ADJ_IN}{node_id}:{relation}"


def _adj_out_all_key(node_id: str) -> str:
    """Set of all 'relation\x00edge_id' strings leaving node_id."""
    return f"{_PFX_ADJ_OUT}{node_id}"


def _adj_in_all_key(node_id: str) -> str:
    """Set of all 'relation\x00edge_id' strings arriving at node_id."""
    return f"{_PFX_ADJ_IN}{node_id}"


def _prop_index_key(prop_key: str, prop_value: str) -> str:
    return f"{_PFX_IDX_PROP}{prop_key}:{prop_value}"


def _ms_now() -> float:
    return time.time() * 1000


def _serialize_props(props: Dict[str, Any]) -> Dict[str, str]:
    """Flatten property dict to Redis hash-compatible str->str mapping."""
    result: Dict[str, str] = {}
    for k, v in props.items():
        if isinstance(v, (dict, list)):
            result[k] = json.dumps(v, ensure_ascii=False)
        else:
            result[k] = str(v)
    return result


def _deserialize_props(raw: Dict[bytes, bytes]) -> Dict[str, Any]:
    """Convert Redis hgetall bytes result back to Python dict."""
    out: Dict[str, Any] = {}
    for bk, bv in raw.items():
        key = bk.decode("utf-8") if isinstance(bk, bytes) else bk
        val = bv.decode("utf-8") if isinstance(bv, bytes) else bv
        # Try to restore JSON-encoded values
        if val.startswith(("{", "[")):
            try:
                val = json.loads(val)
            except (ValueError, TypeError):
                pass
        out[key] = val
    return out


class PropertyGraph:
    """
    Queryable property graph backed by Redis.

    Usage::

        graph = PropertyGraph(database="knowledge")
        await graph.initialize()

        await graph.add_node("file:main.py", {"type": "file", "lang": "python"})
        await graph.add_node("bug:123",      {"type": "bug",  "severity": "high"})
        await graph.add_edge("file:main.py", "bug:123", "CONTAINS",
                              {"confidence": "0.9"})

        neighbours = await graph.get_neighbors("file:main.py", relation="CONTAINS")
        bugs = await graph.query_nodes({"type": "bug", "severity": "high"})
        subgraph = await graph.subgraph("file:main.py", max_depth=2)
        path = await graph.shortest_path("file:main.py", "bug:123")

    **Property serialisation:** All property values are stored as strings in
    Redis.  Numeric and boolean values are coerced via ``str()``.  When
    querying with ``query_nodes()``, pass string representations of the values
    you stored — e.g. ``query_nodes({"confidence": "0.9"})`` not
    ``{"confidence": 0.9}``.  dict/list values are JSON-encoded and excluded
    from the property index (not queryable via ``query_nodes``).
    """

    def __init__(self, database: str = "knowledge") -> None:
        self._database = database
        self._redis: Any = None

    async def initialize(self) -> None:
        """Acquire async Redis connection."""
        if self._redis is None:
            self._redis = await get_async_redis_client(database=self._database)
        logger.info("PropertyGraph initialized (db=%s)", self._database)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _index_properties(self, entity_id: str, props: Dict[str, Any]) -> None:
        """Maintain ``pg:idx:prop:{key}:{value}`` sets for fast property lookup."""
        for k, v in props.items():
            if isinstance(v, (dict, list)):
                continue  # skip complex values
            idx_key = _prop_index_key(k, str(v))
            await self._redis.sadd(idx_key, entity_id)

    async def _deindex_properties(self, entity_id: str, props: Dict[str, Any]) -> None:
        """Remove entity from property-value index entries."""
        for k, v in props.items():
            if isinstance(v, (dict, list)):
                continue
            idx_key = _prop_index_key(k, str(v))
            await self._redis.srem(idx_key, entity_id)

    # ------------------------------------------------------------------
    # Node operations
    # ------------------------------------------------------------------

    async def add_node(self, node_id: str, properties: Dict[str, Any]) -> None:
        """
        Upsert a node with given properties.

        If the node already exists its properties are merged (new keys added,
        existing keys overwritten). Old property-index entries are cleaned up
        before the new ones are written.

        Args:
            node_id: Unique node identifier.
            properties: Arbitrary property dict (values serialised to str).
        """
        existing_raw = await self._redis.hgetall(_node_key(node_id))
        if existing_raw:
            existing = _deserialize_props(existing_raw)
            await self._deindex_properties(node_id, existing)

        merged: Dict[str, Any] = {}
        if existing_raw:
            merged.update(_deserialize_props(existing_raw))
        merged.update(properties)
        if "id" not in merged:
            merged["id"] = node_id

        await self._redis.hset(_node_key(node_id), mapping=_serialize_props(merged))
        await self._index_properties(node_id, merged)
        logger.debug("add_node: %s props=%s", node_id, list(properties.keys()))

    async def get_node(self, node_id: str) -> Dict[str, Any] | None:
        """
        Return node properties or None if not found.

        Args:
            node_id: Node identifier.

        Returns:
            Property dict or None.
        """
        raw = await self._redis.hgetall(_node_key(node_id))
        if not raw:
            return None
        return _deserialize_props(raw)

    async def delete_node(self, node_id: str) -> bool:
        """
        Delete a node and all its edges (both directions).

        Args:
            node_id: Node identifier.

        Returns:
            True if the node existed and was deleted, False otherwise.
        """
        raw = await self._redis.hgetall(_node_key(node_id))
        if not raw:
            return False

        existing = _deserialize_props(raw)
        await self._deindex_properties(node_id, existing)
        await self._redis.delete(_node_key(node_id))

        # Remove all outgoing edges
        all_out_key = _adj_out_all_key(node_id)
        out_members = await self._redis.smembers(all_out_key)
        for member in out_members:
            rel_edge = member.decode("utf-8") if isinstance(member, bytes) else member
            relation, edge_id = rel_edge.split("\x00", 1)
            await self._delete_edge_by_id(edge_id, node_id, relation)

        await self._redis.delete(all_out_key)

        # Remove all incoming edges
        all_in_key = _adj_in_all_key(node_id)
        in_members = await self._redis.smembers(all_in_key)
        for member in in_members:
            rel_edge = member.decode("utf-8") if isinstance(member, bytes) else member
            relation, edge_id = rel_edge.split("\x00", 1)
            edge_raw = await self._redis.hgetall(_edge_key(edge_id))
            if edge_raw:
                edge = _deserialize_props(edge_raw)
                from_id = edge.get("from", "")
                if from_id:
                    await self._redis.zrem(_adj_out_key(from_id, relation), edge_id)
                    await self._redis.srem(_adj_out_all_key(from_id), f"{relation}\x00{edge_id}")
            await self._redis.delete(_edge_key(edge_id))

        await self._redis.delete(all_in_key)
        logger.debug("delete_node: %s (and its edges)", node_id)
        return True

    # ------------------------------------------------------------------
    # Edge operations
    # ------------------------------------------------------------------

    async def add_edge(
        self,
        from_id: str,
        to_id: str,
        relation: str,
        properties: Dict[str, Any] | None = None,
    ) -> str:
        """
        Add a directed edge from ``from_id`` to ``to_id`` with given relation type.

        Auto-creates nodes if they do not yet exist (with just ``id`` property).

        Args:
            from_id: Source node identifier.
            to_id: Target node identifier.
            relation: Relationship type string (e.g. ``"DEPENDS_ON"``).
            properties: Optional additional edge properties.

        Returns:
            The generated edge_id.
        """
        # Ensure nodes exist
        if not await self._redis.exists(_node_key(from_id)):
            await self.add_node(from_id, {"id": from_id})
        if not await self._redis.exists(_node_key(to_id)):
            await self.add_node(to_id, {"id": to_id})

        edge_id = str(uuid.uuid4())
        score = _ms_now()

        edge_props: Dict[str, Any] = {
            "id": edge_id,
            "from": from_id,
            "to": to_id,
            "relation": relation,
            "created_at_ms": str(int(score)),
        }
        if properties:
            edge_props.update(properties)

        await self._redis.hset(_edge_key(edge_id), mapping=_serialize_props(edge_props))

        # Typed adjacency sorted sets (score = created_at_ms for chronological ordering)
        await self._redis.zadd(_adj_out_key(from_id, relation), {edge_id: score})
        await self._redis.zadd(_adj_in_key(to_id, relation), {edge_id: score})

        # All-relations index (for delete_node + relation-agnostic iteration)
        await self._redis.sadd(_adj_out_all_key(from_id), f"{relation}\x00{edge_id}")
        await self._redis.sadd(_adj_in_all_key(to_id), f"{relation}\x00{edge_id}")

        logger.debug("add_edge: %s -[%s]-> %s (edge_id=%s)", from_id, relation, to_id, edge_id)
        return edge_id

    async def get_edge(self, edge_id: str) -> Dict[str, Any] | None:
        """Return edge properties or None if not found."""
        raw = await self._redis.hgetall(_edge_key(edge_id))
        if not raw:
            return None
        return _deserialize_props(raw)

    async def delete_edge(self, edge_id: str) -> bool:
        """
        Delete an edge by its edge_id.

        Args:
            edge_id: Edge identifier returned by ``add_edge``.

        Returns:
            True if the edge existed, False otherwise.
        """
        raw = await self._redis.hgetall(_edge_key(edge_id))
        if not raw:
            return False

        edge = _deserialize_props(raw)
        from_id = edge.get("from", "")
        to_id = edge.get("to", "")
        relation = edge.get("relation", "")

        await self._delete_edge_by_id(edge_id, from_id, relation)
        if to_id:
            await self._redis.zrem(_adj_in_key(to_id, relation), edge_id)
            await self._redis.srem(_adj_in_all_key(to_id), f"{relation}\x00{edge_id}")

        logger.debug("delete_edge: %s", edge_id)
        return True

    async def _delete_edge_by_id(self, edge_id: str, from_id: str, relation: str) -> None:
        """Remove edge hash + outgoing adjacency entries (internal helper)."""
        await self._redis.delete(_edge_key(edge_id))
        if from_id and relation:
            await self._redis.zrem(_adj_out_key(from_id, relation), edge_id)
            await self._redis.srem(_adj_out_all_key(from_id), f"{relation}\x00{edge_id}")

    # ------------------------------------------------------------------
    # Query operations
    # ------------------------------------------------------------------

    async def get_neighbors(
        self,
        node_id: str,
        relation: str | None = None,
        direction: str = "outgoing",
    ) -> List[Dict[str, Any]]:
        """
        Return neighbouring nodes with edge metadata.

        Args:
            node_id: Starting node identifier.
            relation: Filter to this relation type; None means all types.
            direction: ``"outgoing"``, ``"incoming"``, or ``"both"``.

        Returns:
            List of dicts with keys ``node``, ``edge``.
        """
        results: List[Dict[str, Any]] = []

        if direction in ("outgoing", "both"):
            results.extend(await self._neighbors_one_direction(node_id, relation, "outgoing"))
        if direction in ("incoming", "both"):
            results.extend(await self._neighbors_one_direction(node_id, relation, "incoming"))

        return results

    async def _neighbors_one_direction(
        self, node_id: str, relation: str | None, direction: str
    ) -> List[Dict[str, Any]]:
        """Fetch neighbours in a single direction."""
        results: List[Dict[str, Any]] = []

        if relation:
            relations_to_query = [relation]
        else:
            # Discover relation types from all-relations index
            all_key = _adj_out_all_key(node_id) if direction == "outgoing" else _adj_in_all_key(node_id)
            members = await self._redis.smembers(all_key)
            seen_rels: Set[str] = set()
            for m in members:
                rel_part = (m.decode("utf-8") if isinstance(m, bytes) else m).split("\x00")[0]
                seen_rels.add(rel_part)
            relations_to_query = list(seen_rels)

        for rel in relations_to_query:
            adj_key = _adj_out_key(node_id, rel) if direction == "outgoing" else _adj_in_key(node_id, rel)
            edge_ids = await self._redis.zrange(adj_key, 0, -1)
            for eid_bytes in edge_ids:
                eid = eid_bytes.decode("utf-8") if isinstance(eid_bytes, bytes) else eid_bytes
                edge_raw = await self._redis.hgetall(_edge_key(eid))
                if not edge_raw:
                    continue
                edge = _deserialize_props(edge_raw)
                neighbour_id = edge.get("to") if direction == "outgoing" else edge.get("from")
                if not neighbour_id:
                    continue
                node_raw = await self._redis.hgetall(_node_key(neighbour_id))
                node = _deserialize_props(node_raw) if node_raw else {"id": neighbour_id}
                results.append({"node": node, "edge": edge})

        return results

    async def query_nodes(self, property_filter: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Return nodes matching ALL property key/value pairs in ``property_filter``.

        Uses property-value index sets for efficient lookup — no full key scan.
        Performs intersection of candidate sets, then verifies each candidate
        possesses every required property (in case of partial index coverage).

        Args:
            property_filter: Dict of ``{property_key: property_value}`` pairs.
                             All conditions must match (AND semantics).

        Returns:
            List of matching node property dicts.
        """
        if not property_filter:
            return []

        candidate_sets: List[Set[str]] = []
        for k, v in property_filter.items():
            idx_key = _prop_index_key(k, str(v))
            raw_members = await self._redis.smembers(idx_key)
            candidate_sets.append({m.decode("utf-8") if isinstance(m, bytes) else m for m in raw_members})

        if not candidate_sets:
            return []

        # Intersection: nodes that appear in ALL property index sets
        candidates: Set[str] = candidate_sets[0]
        for s in candidate_sets[1:]:
            candidates = candidates.intersection(s)

        results: List[Dict[str, Any]] = []
        for node_id in candidates:
            raw = await self._redis.hgetall(_node_key(node_id))
            if not raw:
                continue
            node = _deserialize_props(raw)
            # Double-check all filter conditions (index may lag on complex values)
            if all(str(node.get(k)) == str(v) for k, v in property_filter.items()):
                results.append(node)

        return results

    # ------------------------------------------------------------------
    # Graph traversal
    # ------------------------------------------------------------------

    async def multi_hop(
        self,
        start_node_id: str,
        relation: str | None = None,
        max_depth: int = 2,
        direction: str = "outgoing",
    ) -> List[Dict[str, Any]]:
        """
        BFS multi-hop traversal from ``start_node_id``.

        Args:
            start_node_id: Starting node.
            relation: Restrict traversal to this relation type; None = all.
            max_depth: Maximum number of hops.
            direction: ``"outgoing"``, ``"incoming"``, or ``"both"``.

        Returns:
            List of dicts ``{node, edge, depth}`` for every visited node
            (excluding the start node itself).
        """
        visited: Set[str] = {start_node_id}
        queue: deque[Tuple[str, int]] = deque([(start_node_id, 0)])
        results: List[Dict[str, Any]] = []

        while queue:
            current_id, depth = queue.popleft()
            if depth >= max_depth:
                continue

            neighbours = await self.get_neighbors(current_id, relation=relation, direction=direction)
            for entry in neighbours:
                neighbour_id = entry["node"].get("id")
                if not neighbour_id or neighbour_id in visited:
                    continue
                visited.add(neighbour_id)
                results.append({**entry, "depth": depth + 1})
                queue.append((neighbour_id, depth + 1))

        return results

    async def subgraph(
        self,
        center_node_id: str,
        max_depth: int = 2,
        relation: str | None = None,
    ) -> Dict[str, Any]:
        """
        Extract a connected subgraph around ``center_node_id``.

        Traverses in both directions to include context from all connected
        nodes within ``max_depth`` hops.

        Args:
            center_node_id: Root node.
            max_depth: Maximum hop distance.
            relation: Restrict to this relation type; None = all.

        Returns:
            Dict with ``nodes`` (list of node dicts) and ``edges``
            (list of edge dicts).
        """
        visited_nodes: Set[str] = {center_node_id}
        visited_edges: Set[str] = set()
        queue: deque[Tuple[str, int]] = deque([(center_node_id, 0)])
        nodes: List[Dict[str, Any]] = []
        edges: List[Dict[str, Any]] = []

        center_raw = await self._redis.hgetall(_node_key(center_node_id))
        if center_raw:
            nodes.append(_deserialize_props(center_raw))

        while queue:
            current_id, depth = queue.popleft()
            if depth >= max_depth:
                continue

            neighbours = await self.get_neighbors(current_id, relation=relation, direction="both")
            for entry in neighbours:
                neighbour_id = entry["node"].get("id")
                edge_id = entry["edge"].get("id")

                if edge_id and edge_id not in visited_edges:
                    visited_edges.add(edge_id)
                    edges.append(entry["edge"])

                if neighbour_id and neighbour_id not in visited_nodes:
                    visited_nodes.add(neighbour_id)
                    nodes.append(entry["node"])
                    queue.append((neighbour_id, depth + 1))

        return {"nodes": nodes, "edges": edges}

    async def shortest_path(
        self,
        from_id: str,
        to_id: str,
        relation: str | None = None,
        max_depth: int = 6,
    ) -> List[Dict[str, Any]] | None:
        """
        BFS shortest path between two nodes.

        Args:
            from_id: Source node identifier.
            to_id: Target node identifier.
            relation: Restrict traversal to this relation type; None = all.
            max_depth: Maximum path length to search.

        Returns:
            Ordered list of ``{node, edge}`` dicts representing the path
            (excluding the start node), or None if no path found.
        """
        if from_id == to_id:
            return []

        # BFS with path tracking
        visited: Set[str] = {from_id}
        # queue items: (current_id, path_so_far)
        queue: deque[Tuple[str, List[Dict[str, Any]]]] = deque([(from_id, [])])

        while queue:
            current_id, path = queue.popleft()
            if len(path) >= max_depth:
                continue

            neighbours = await self.get_neighbors(current_id, relation=relation, direction="outgoing")
            for entry in neighbours:
                neighbour_id = entry["node"].get("id")
                if not neighbour_id:
                    continue
                new_path = path + [entry]
                if neighbour_id == to_id:
                    return new_path
                if neighbour_id not in visited:
                    visited.add(neighbour_id)
                    queue.append((neighbour_id, new_path))

        return None  # No path found
