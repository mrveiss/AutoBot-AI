# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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

When ``create_entity`` or ``create_relation`` are called the mixin also
mirrors the data into the PropertyGraph so the two stores stay in sync.
"""

from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger

from .core import AutoBotMemoryGraphCore
from .property_graph import PropertyGraph

logger = get_logger(__name__)


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
                        relation_type.upper(),
                        edge_props,
                    )
                    if bidirectional:
                        await self.graph.add_edge(
                            to_entity_data["id"],
                            from_entity_data["id"],
                            relation_type.upper(),
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
