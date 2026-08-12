# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Reverse-BFS impact analysis over the resolved code graph (#13471).

"What breaks if I change this" — a depth-limited reverse walk of the ``calls``
edges persisted by ``code_indexer.py`` (#13469): starting from a node id, find
every node that transitively calls it. ``find_callers()`` (``code_indexer.py``)
is one hop; this module is the transitive closure on top of it.

Binding decisions this module implements (closed gate #13482):
  - Q1: code and memory graphs stay separate. This module never touches
    ``autobot_memory_graph`` — it only reads the ChromaDB collection
    ``code_indexer`` already writes edge/node documents into.
  - Q2: coverage is reported as a resolved/unresolved **count**, never an
    invented confidence score. See ``ImpactResult.resolved_edge_count`` /
    ``unresolved_edge_count``.

Honesty requirements this module exists to satisfy (#13471):
  - Ambiguous edges (2+ suffix-match candidates, #13470's
    ``resolve_callee_by_suffix``) are never silently followed (that would be
    guessing which candidate the call actually reaches) nor silently dropped
    (that would under-report impact and look confident doing it) — they are
    surfaced in ``ImpactResult.skipped_edges`` with the reason.
  - Cycles are real in call graphs (mutual recursion, etc.) and are handled by
    never re-expanding an already-visited node — the walk still records the
    edge that closes the cycle, it just does not loop on it forever.
  - Depth is bounded (``AUTOBOT_IMPACT_ANALYSIS_MAX_DEPTH``, default below) and
    the bound is always reported: a capped walk sets ``depth_capped=True`` and
    lists the un-expanded frontier, so it never reports as if it were
    complete (the #13468 defect this issue explicitly calls out avoiding).
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any

from autobot_shared.env_utils import blank_to_none
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
from services.knowledge.code_indexer import find_callers

logger = get_logger(__name__)

# Reverse-BFS hop limit. Not hard-coded per-call — env-overridable via
# AUTOBOT_IMPACT_ANALYSIS_MAX_DEPTH (see chat_history/cache.py for the same
# pattern). 6 hops covers realistic caller chains without the walk degrading
# into a near-repo-wide scan on a densely connected symbol.
_DEFAULT_MAX_DEPTH = 6


def _resolve_max_depth() -> int:
    """Return the configured reverse-BFS hop limit, falling back safely."""
    raw = blank_to_none(config.misc.impact_analysis_max_depth)
    if raw is None:
        return _DEFAULT_MAX_DEPTH
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "AUTOBOT_IMPACT_ANALYSIS_MAX_DEPTH=%r is not an integer; falling back to %d",
            raw,
            _DEFAULT_MAX_DEPTH,
        )
        return _DEFAULT_MAX_DEPTH
    if value <= 0:
        logger.warning(
            "AUTOBOT_IMPACT_ANALYSIS_MAX_DEPTH=%d must be positive; falling back to %d",
            value,
            _DEFAULT_MAX_DEPTH,
        )
        return _DEFAULT_MAX_DEPTH
    return value


_MAX_DEPTH = _resolve_max_depth()


@dataclass
class ImpactResult:
    """Outcome of one reverse-BFS impact walk, honest about its own coverage (#13471).

    ``resolved_edge_count``/``unresolved_edge_count`` are the coverage pair
    #13482 Q2 requires in place of a confidence score: how many incoming
    edges were actually traversed versus how many existed but could not be
    (ambiguous or otherwise unresolved), for every node this walk reached.
    """

    root_id: str
    seed_ids: list[str] = field(default_factory=list)
    reached: list[str] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)
    skipped_edges: list[dict[str, Any]] = field(default_factory=list)
    max_depth: int = 0
    depth_reached: int = 0
    depth_capped: bool = False
    depth_capped_frontier: list[str] = field(default_factory=list)

    @property
    def resolved_edge_count(self) -> int:
        return len(self.edges)

    @property
    def unresolved_edge_count(self) -> int:
        return len(self.skipped_edges)


async def _find_member_ids(collection: Any, root_id: str) -> list[str]:
    """Return *root_id*'s own member function/method node ids (#13471).

    Seeding the walk with these as well as *root_id* itself means a caller
    that binds to ``Class.method`` rather than ``Class`` is still reachable.
    A member's id is always ``f"{parent_id}.{node_name}"`` by construction
    (``compute_node_id``), so this needs only the ``node_name`` out of each
    matching node's metadata — no dependency on the ``ids`` array a
    ``collection.get(where=...)`` call also returns.
    """
    result = await asyncio.to_thread(
        collection.get,
        where={"$and": [{"record_type": {"$eq": "node"}}, {"parent": {"$eq": root_id}}]},
        include=["metadatas"],
    )
    metas = result.get("metadatas") or []
    return [f"{root_id}.{m['node_name']}" for m in metas if m.get("node_name")]


async def _find_skipped_edges(collection: Any, node_id: str) -> list[dict[str, Any]]:
    """Ambiguous/unresolved edges whose raw call name matches *node_id*'s bare name.

    Never followed — resolving one would mean guessing which of several
    candidates (or, for a zero-candidate edge, which nonexistent one) the
    call actually reaches — but never dropped either: each is a real call
    site that might be calling *node_id*, and the graph says so honestly
    instead of pretending the incoming-edge count is complete (#13471).
    """
    bare_name = node_id.rsplit(".", 1)[-1]
    result = await asyncio.to_thread(
        collection.get,
        where={
            "$and": [
                {"record_type": {"$eq": "edge"}},
                {"target_name": {"$eq": bare_name}},
                {"resolved": {"$eq": False}},
            ]
        },
        include=["metadatas"],
    )
    return list(result.get("metadatas") or [])


async def _expand_frontier(collection: Any, frontier: list[str], visited: set[str], result: ImpactResult) -> list[str]:
    """One BFS hop: pull callers of every node in *frontier*.

    Records every traversed edge and every skipped (ambiguous/unresolved)
    near-miss regardless of whether the caller turns out to be new, so a
    cycle edge (caller already visited) is still visible in the result even
    though it does not re-expand the walk.
    """
    next_frontier: list[str] = []
    for node_id in frontier:
        for edge in await find_callers(collection, node_id):
            result.edges.append(edge)
            source_id = edge.get("source_id")
            if source_id and source_id not in visited:
                visited.add(source_id)
                result.reached.append(source_id)
                next_frontier.append(source_id)
        result.skipped_edges.extend(await _find_skipped_edges(collection, node_id))
    return next_frontier


async def find_impact(collection: Any, root_id: str, max_depth: int | None = None) -> ImpactResult:
    """Reverse-BFS from *root_id*: what transitively calls it (#13471).

    Seeds with *root_id* plus its own members, then walks incoming ``calls``
    edges hop by hop. An already-visited node is never re-expanded, so a
    cycle (A calls B, B calls A) terminates instead of looping — the edge
    that closes the cycle is still recorded in ``edges``. Stops when the
    frontier empties naturally or *max_depth* hops are exhausted; the latter
    sets ``depth_capped=True`` with the un-expanded frontier so a truncated
    walk is never mistaken for a complete one.
    """
    depth_limit = max_depth if max_depth is not None else _MAX_DEPTH
    seeds = [root_id] + [m for m in await _find_member_ids(collection, root_id) if m != root_id]
    result = ImpactResult(root_id=root_id, seed_ids=seeds, max_depth=depth_limit)

    visited = set(seeds)
    frontier = seeds
    depth = 0
    while frontier:
        if depth >= depth_limit:
            result.depth_capped = True
            result.depth_capped_frontier = frontier
            break
        frontier = await _expand_frontier(collection, frontier, visited, result)
        depth += 1
    result.depth_reached = depth
    return result
