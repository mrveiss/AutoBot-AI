# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
PropertyGraphMixin — integrates PropertyGraph into AutoBotMemoryGraph.

Issue #3230: Replaces plain adjacency list with a queryable property graph.

The mixin lazily initialises a ``PropertyGraph`` instance on first access
via the ``property_graph`` attribute and exposes convenience wrappers so
callers can use graph-style queries directly on AutoBotMemoryGraph:

    memory.graph.get_neighbors("entity-id", relation="depends_on")
    memory.graph.query_nodes({"type": "BUG", "severity": "high"})
    memory.graph.multi_hop("entity-id", max_depth=3)
    memory.graph.subgraph("entity-id")
    memory.graph.shortest_path("entity-id-a", "entity-id-b")

Path queries by entity *name* go through the mixin itself rather than the
PropertyGraph, since only AutoBotMemoryGraph can resolve a name to an id:

    memory.find_path("Redis Config", "Incident 7")   # #13474

When ``create_entity`` or ``create_relation`` are called the mixin also
mirrors the data into the PropertyGraph so the two stores stay in sync.
"""

import asyncio
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger

from .core import AutoBotMemoryGraphCore
from .property_graph import PropertyGraph

logger = get_logger(__name__)


def _endpoint_summary(entity: Dict[str, Any]) -> Dict[str, Any]:
    """Reduce an entity to the fields a path response needs. #13474."""
    return {"id": entity.get("id"), "name": entity.get("name"), "type": entity.get("type")}


def _serialize_hop(hop: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten one ``{node, edge, direction}`` traversal step. #13474."""
    node = hop.get("node") or {}
    edge = hop.get("edge") or {}
    return {
        "relation": edge.get("relation"),
        "direction": hop.get("direction"),
        "edge_id": edge.get("id"),
        "from": edge.get("from"),
        "to": edge.get("to"),
        "node": _endpoint_summary(node),
    }


def _path_result(
    from_node: Dict[str, Any] | None,
    to_node: Dict[str, Any] | None,
    raw_path: List[Dict[str, Any]] | None,
    missing: List[str],
    query: Dict[str, Any],
    reason: str | None = None,
) -> Dict[str, Any]:
    """Build the ``find_path`` response dict. #13474.

    ``raw_path`` distinguishes three outcomes that a truthiness check would
    collapse: ``None`` means no path exists, ``[]`` means the two names resolved
    to the same entity (a zero-hop path, which IS found), and a non-empty list is
    a real path.

    An explicit *reason* overrides that inference, for outcomes the path alone
    cannot express (``not_in_graph``).
    """
    if reason is None:
        reason = "entity_not_found" if missing else ("no_path" if raw_path is None else None)
    return {
        "found": reason is None,
        "reason": reason,
        "missing_entities": missing,
        "from_entity": _endpoint_summary(from_node) if from_node else None,
        "to_entity": _endpoint_summary(to_node) if to_node else None,
        "hops": len(raw_path) if raw_path is not None else 0,
        "path": [_serialize_hop(hop) for hop in raw_path] if raw_path is not None else [],
        "query": query,
    }


class PropertyGraphMixin:
    """
    Mixin that wires a PropertyGraph into AutoBotMemoryGraph.

    Designed for use alongside the other AutoBotMemoryGraph mixins.
    Relies on ``self.redis_client`` and ``self._initialized`` from
    ``AutoBotMemoryGraphCore``.
    """

    # Lazily created on first access
    _property_graph: PropertyGraph | None = None

    @property
    def graph(self) -> PropertyGraph:
        """Return the lazily-initialised PropertyGraph instance.

        Raises RuntimeError if AutoBotMemoryGraph is not yet initialised.
        """
        self.ensure_initialized()  # type: ignore[attr-defined]
        if self._property_graph is None:
            self._property_graph = PropertyGraph(database="knowledge")
            self._property_graph._redis = self.redis_client  # reuse connection
        return self._property_graph

    # ------------------------------------------------------------------
    # Entity sync: mirror create_entity into PropertyGraph
    # ------------------------------------------------------------------

    async def create_entity(  # type: ignore[override]
        self: AutoBotMemoryGraphCore,
        entity_type: str,
        name: str,
        observations: List[str] | None = None,
        metadata: Dict[str, Any] | None = None,
        tags: List[str] | None = None,
    ) -> Dict[str, Any]:
        """Create entity in the standard store AND mirror into PropertyGraph."""
        entity = await super().create_entity(  # type: ignore[misc]
            entity_type=entity_type,
            name=name,
            observations=observations,
            metadata=metadata,
            tags=tags,
        )
        if entity:
            node_props: Dict[str, Any] = {
                "type": entity_type,
                "name": name,
            }
            if metadata:
                # Flatten scalar metadata values into node properties
                for k, v in metadata.items():
                    if isinstance(v, (str, int, float, bool)):
                        node_props[k] = v
            try:
                await self.graph.add_node(entity["id"], node_props)
            except Exception as exc:
                logger.warning("PropertyGraph sync skipped for entity %s: %s", entity.get("id"), type(exc).__name__)
        return entity

    # ------------------------------------------------------------------
    # Relation sync: mirror create_relation into PropertyGraph
    # ------------------------------------------------------------------

    async def create_relation(  # type: ignore[override]
        self: AutoBotMemoryGraphCore,
        from_entity: str,
        to_entity: str,
        relation_type: str,
        bidirectional: bool = False,
        strength: float = 1.0,
        metadata: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Create relation in the standard store AND mirror into PropertyGraph."""
        relation = await super().create_relation(  # type: ignore[misc]
            from_entity=from_entity,
            to_entity=to_entity,
            relation_type=relation_type,
            bidirectional=bidirectional,
            strength=strength,
            metadata=metadata,
        )
        if relation:
            # #13452: label the property-graph edge with the type that was
            # actually stored, not the caller's raw spelling. super() folds
            # aliases onto the canonical name, so using relation_type here wrote
            # "related_to" into Redis JSON but "pg:adj:out:<id>:RELATES_TO" into
            # the adjacency index — two stores silently disagreeing, and nothing
            # canonicalises the index later.
            edge_label = relation.get("type", relation_type).upper()
            edge_props: Dict[str, Any] = {"strength": str(strength)}
            if metadata:
                for k, v in metadata.items():
                    if isinstance(v, (str, int, float, bool)):
                        edge_props[k] = v
            try:
                # Resolve IDs via existing entity lookup
                from_entity_data = await self.get_entity(entity_name=from_entity)  # type: ignore[attr-defined]
                to_entity_data = await self.get_entity(entity_name=to_entity)  # type: ignore[attr-defined]
                if from_entity_data and to_entity_data:
                    await self.graph.add_edge(
                        from_entity_data["id"],
                        to_entity_data["id"],
                        edge_label,
                        edge_props,
                    )
                    if bidirectional:
                        await self.graph.add_edge(
                            to_entity_data["id"],
                            from_entity_data["id"],
                            edge_label,
                            edge_props,
                        )
            except Exception as exc:
                logger.warning(
                    "PropertyGraph sync skipped for relation %s->%s: %s",
                    from_entity,
                    to_entity,
                    type(exc).__name__,
                )
        return relation

    # ------------------------------------------------------------------
    # Path queries: name-addressed shortest path (#13474)
    # ------------------------------------------------------------------

    async def find_path(
        self: AutoBotMemoryGraphCore,
        from_entity: str,
        to_entity: str,
        relation: str | None = None,
        max_depth: int = 6,
        direction: str = "both",
    ) -> Dict[str, Any]:
        """Return the shortest relationship path between two named entities.

        This is the name-addressed entry point to ``PropertyGraph.shortest_path``
        — callers hold entity *names*, the property graph is keyed by entity
        *ids*, and #13474 wired the two together so the traversal has a
        production caller (the Graph-RAG ``/path`` endpoint and the
        ``memory.path`` MCP tool both land here, so the resolution and
        serialisation live in exactly one place).

        Args:
            from_entity: Source entity name.
            to_entity: Target entity name.
            relation: Restrict traversal to this relation type; None = all.
            max_depth: Maximum path length to search.
            direction: ``"outgoing"``, ``"incoming"``, or ``"both"`` (default —
                connection questions are usually undirected).

        Returns:
            Dict with ``found``, ``reason``, ``missing_entities``,
            ``from_entity``, ``to_entity``, ``hops``, ``path`` and ``query``.
            Redis failures propagate: a traversal that could not run must not be
            reported as "no path".
        """
        from_node, to_node = await asyncio.gather(
            self.get_entity(entity_name=from_entity),  # type: ignore[attr-defined]
            self.get_entity(entity_name=to_entity),  # type: ignore[attr-defined]
        )
        query = {
            "from_entity": from_entity,
            "to_entity": to_entity,
            "relation": relation,
            "max_depth": max_depth,
            "direction": direction,
        }
        missing = [name for name, node in ((from_entity, from_node), (to_entity, to_node)) if node is None]
        if missing:
            # get_entity swallows infrastructure errors and returns None, so a
            # bare None cannot be trusted to mean "no such entity" — during a
            # Redis outage it means "we could not look". Telling the user their
            # name is wrong when the store was unreachable is a false negative
            # dressed as an answer, so confirm the store is up before saying it.
            await self._assert_store_reachable()
            logger.info("find_path: unresolved entity names %s", missing)
            return _path_result(from_node, to_node, None, missing, query)

        # An entity can exist in the main store yet have no property-graph node:
        # create_entity mirrors into the graph best-effort, and anything created
        # before the mirror existed was never mirrored at all. Reporting that as
        # "not connected" is a confident wrong answer, so it gets its own reason.
        ungraphed = await self._unmirrored_endpoints(from_node, to_node)
        if ungraphed:
            logger.info("find_path: endpoints absent from the property graph: %s", ungraphed)
            return _path_result(from_node, to_node, None, [], query, reason="not_in_graph")

        raw_path = await self.graph.shortest_path(
            from_node["id"],
            to_node["id"],
            relation=relation,
            max_depth=max_depth,
            direction=direction,
        )
        return _path_result(from_node, to_node, raw_path, [], query)

    async def _assert_store_reachable(self: AutoBotMemoryGraphCore) -> None:
        """Raise if the entity store is unreachable. #13474.

        Guards the one inference ``find_path`` makes from a negative result:
        that a ``None`` from ``get_entity`` means the entity does not exist.
        """
        try:
            await self.redis_client.ping()
        except Exception as exc:
            raise RuntimeError("Entity lookup could not be completed — store unreachable") from exc

    async def _unmirrored_endpoints(
        self: AutoBotMemoryGraphCore,
        from_node: Dict[str, Any],
        to_node: Dict[str, Any],
    ) -> List[str]:
        """Return the endpoint names that have no property-graph node. #13474."""
        nodes = await asyncio.gather(
            self.graph.get_node(from_node["id"]),
            self.graph.get_node(to_node["id"]),
        )
        return [
            entity.get("name") or entity.get("id")
            for entity, node in zip((from_node, to_node), nodes)
            if node is None
        ]
