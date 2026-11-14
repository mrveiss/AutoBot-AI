# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Memory-graph MCP tools (#5072), split out of ``autobot_server`` to keep that file under its size ceiling.

Every graph read runs under ``current_owner()`` -- the authenticated MCP principal bound for
the request (#18825). A caller with no identity (the stdio transport) gets ``OwnerScopeRequired``,
which the dispatcher answers with a 403-class error: there is no unscoped graph read here.
``memory.verbatim_search`` is a different store (#16727) and keeps its own explicit sentinel.
"""

from typing import Any, Dict

from constants.rag_graph_constants import RAG_GRAPH_PATH_DEPTH, RAG_GRAPH_TRAVERSAL_DEPTH
from mcp_server.principal import current_owner

_PATH_DIRECTIONS = ("outgoing", "incoming", "both")


def _path_request(from_entity: str, to_entity: str, relation: str | None, max_depth: int, direction: str) -> Any:
    """The REST route's request model, with ``max_depth`` clamped (#13762) rather than rejected."""
    from api.schemas_knowledge import GraphRAGPathRequest

    return GraphRAGPathRequest(
        from_entity=from_entity,
        to_entity=to_entity,
        relation=relation,
        max_depth=max(1, min(max_depth, 10)),
        direction=direction,
    )


def _created_at(entity: Dict[str, Any]) -> str:
    return (entity.get("metadata") or {}).get("created_at", "")


def _neighbour_ids(relations: list, entity_id: str) -> list:
    """Distinct other-end ids of formatted relations (``from`` / ``to``), order-preserving."""
    ids = dict.fromkeys(r.get(end) for r in relations for end in ("from", "to"))
    return [i for i in ids if i and i != entity_id]


async def _load_neighbours(graph: Any, ids: list, owner: Any) -> list:
    """The neighbour entities ``owner`` may read; an unreadable id is simply absent."""
    found = [await graph.get_entity(entity_id=nid, owner=owner) for nid in ids]
    return [e for e in found if e]


def _within_range(entities: list, range_spec: str) -> list:
    """Keep entities whose ``created_at`` falls in ``start/end`` (string-prefix comparison)."""
    parts = range_spec.split("/", 1)
    start, end = (parts[0], parts[1]) if len(parts) == 2 else (parts[0], None)
    return [e for e in entities if _created_at(e) >= start and (end is None or _created_at(e) <= end)]


async def _expand_related(graph: Any, root_id: str, depth: int, owner: Any) -> Dict[str, Any]:
    """Breadth-first walk of ``depth`` hops from ``root_id``, every hop read as ``owner`` (#18825)."""
    visited: Dict[str, Any] = {}
    frontier = [root_id]
    for _ in range(depth):
        next_frontier: list = []
        for eid in frontier:
            if eid in visited:
                continue
            ent = await graph.get_entity(entity_id=eid, owner=owner)
            if not ent:
                continue
            visited[eid] = ent
            rels = await graph.get_relations(eid, direction="both", owner=owner)
            next_frontier.extend(c for c in _neighbour_ids(rels.get("relations", []), eid) if c not in visited)
        frontier = next_frontier
        if not frontier:
            break
    return visited


class MemoryToolsMixin:
    """The ``memory.*`` tool handlers; mixed into ``AutoBotMCPServer``."""

    async def _memory_entity_lookup(self, name: str) -> Any:
        from api.schemas_knowledge import MemoryEntityLookupRequest
        from autobot_memory_graph import AutoBotMemoryGraph

        name = MemoryEntityLookupRequest(name=name).name
        owner = current_owner()  # the authenticated principal; fails closed without one (#18825)
        graph = AutoBotMemoryGraph()
        await graph.initialize()
        entity = await graph.get_entity(entity_name=name, include_relations=True, owner=owner)
        if entity is None:
            return {"error": "Entity not found", "name": name}
        return entity

    async def _memory_timeline(self, entity: str, range: str | None = None) -> Any:
        from api.schemas_knowledge import MemoryTimelineRequest
        from autobot_memory_graph import AutoBotMemoryGraph

        args = MemoryTimelineRequest(entity=entity, range=range)
        entity, range = args.entity, args.range
        owner = current_owner()  # the authenticated principal; fails closed without one (#18825)
        graph = AutoBotMemoryGraph()
        await graph.initialize()
        base = await graph.get_entity(entity_name=entity, include_relations=True, owner=owner)
        if base is None:
            return {"error": "Entity not found", "entity": entity}

        entity_id = base.get("id", "")
        # get_relations drops every edge whose other end the principal cannot read (#18825).
        relations_data = await graph.get_relations(entity_id, direction="both", owner=owner)
        neighbour_ids = _neighbour_ids(relations_data.get("relations", []), entity_id)
        neighbours = await _load_neighbours(graph, neighbour_ids[:50], owner)

        # Sort by created_at ascending (timeline order)
        neighbours.sort(key=lambda e: _created_at(e))
        if range:
            neighbours = _within_range(neighbours, range)
        return {"entity": base, "timeline": neighbours, "count": len(neighbours)}

    async def _memory_related(self, entity: str, depth: int = RAG_GRAPH_TRAVERSAL_DEPTH) -> Any:
        from api.schemas_knowledge import MemoryRelatedRequest
        from autobot_memory_graph import AutoBotMemoryGraph

        # #13762: the entity name was unbounded. ``depth`` keeps its existing
        # clamp rather than becoming a rejection, so the model's ge/le is the
        # declared contract and the clamp is what enforces it.
        args = MemoryRelatedRequest(entity=entity, depth=max(1, min(depth, 5)))
        entity, depth = args.entity, args.depth
        owner = current_owner()  # the authenticated principal; fails closed without one (#18825)
        graph = AutoBotMemoryGraph()
        await graph.initialize()

        root = await graph.get_entity(entity_name=entity, include_relations=True, owner=owner)
        if root is None:
            return {"error": "Entity not found", "entity": entity}

        visited = await _expand_related(graph, root.get("id", ""), depth, owner)
        return {
            "root": root,
            "related": list(visited.values()),
            "count": len(visited),
        }

    async def _memory_path(
        self,
        from_entity: str,
        to_entity: str,
        relation: str | None = None,
        max_depth: int = RAG_GRAPH_PATH_DEPTH,
        direction: str = "both",
    ) -> Any:
        """Shortest relationship path between two entities (#13474).

        Delegates to AutoBotMemoryGraph.find_path so name resolution and path
        serialisation are not duplicated against the Graph-RAG ``/path``
        endpoint. #13762 extends that to the input contract: the arguments go
        through ``GraphRAGPathRequest``, the same model the REST route binds, so
        the two surfaces cannot drift on what a valid request is. ``max_depth``
        stays clamped rather than rejected — an untrusted caller must not be
        able to request an unbounded traversal, but asking for too much is not
        an error the way an unbounded entity name is.
        """
        from autobot_memory_graph import AutoBotMemoryGraph

        if direction not in _PATH_DIRECTIONS:
            return {"error": "Invalid direction", "direction": direction, "allowed": list(_PATH_DIRECTIONS)}

        args = _path_request(from_entity, to_entity, relation, max_depth, direction)
        owner = current_owner()  # the authenticated principal; fails closed without one (#18825)

        graph = AutoBotMemoryGraph()
        await graph.initialize()
        return await graph.find_path(
            from_entity=args.from_entity,
            to_entity=args.to_entity,
            relation=args.relation,
            max_depth=args.max_depth,
            direction=args.direction,
            owner=owner,
        )

    async def _memory_verbatim_search(self, query: str, session_filter: str | None = None) -> Any:
        from api.schemas_knowledge import MemoryVerbatimSearchRequest
        from memory.verbatim_store import UNSCOPED_ALL_USERS, VerbatimStore

        args = MemoryVerbatimSearchRequest(query=query, session_filter=session_filter)
        store = VerbatimStore()
        results = await store.search(args.query, user_id=UNSCOPED_ALL_USERS, session_filter=args.session_filter)
        return {"results": results, "count": len(results)}
