# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Read-only code-graph queries: the ONE implementation behind the HTTP routes and the MCP tools (#21327).

``/impact`` (by node id or symbol) and ``/patterns/similar`` delegate here, and so do the
``code.*`` MCP tools in ``mcp_server/code_graph_tools.py``. Nothing in this module writes: it
reads the graph collection, the stored provenance record and the pattern store.

Every answer says which commit the graph was built at and, when the caller states the commit
it expects, whether the two agree. The comparison has four outcomes and only one of them is
"current": a graph with no provenance record is ``unknown`` and no expectation is ``unchecked``,
neither of which may read as fresh (#13508).
"""

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any

from autobot_shared.code_graph.commit_freshness import freshness_of
from autobot_shared.logging_manager import get_logger
from constants.threshold_constants import QueryDefaults
from services.knowledge.impact_analysis import find_impact

from .storage import get_existing_code_graph_collection

if TYPE_CHECKING:
    from services.knowledge.code_indexer import GraphProvenance

logger = get_logger(__name__)

#: The stated scope of every graph answer (#20513): all indexed code, not one source.
SOURCE_SCOPE = "cross-source"

#: Candidates returned for one symbol before the list is cut and flagged ``truncated``.
RESOLVE_MAX_CANDIDATES = 50

_NOT_BUILT = "The code graph collection is not available — run an index first."  # missing; reading never creates it
#: The route that builds the graph. Kept as its own quoted path so the unconnected-code gate (#20512)
#: sees this module as the caller it is -- the hint below is the only thing that sends a user to it.
_INDEX_CODE_PATH = "/api/knowledge_base/index/code"
_EMPTY = f"The code graph collection exists but is empty — run POST {_INDEX_CODE_PATH} and retry."


def provenance_fields(provenance: "GraphProvenance | None", expected_commit: str | None) -> dict[str, Any]:
    """Where the answer came from: the commit, the build time, the tree, and the staleness verdict."""
    commit = (provenance.indexed_at_commit or None) if provenance else None
    return {
        "source_scope": SOURCE_SCOPE,
        "indexed_at_commit": commit,
        "indexed_at": (provenance.indexed_at or None) if provenance else None,
        "index_root": Path(provenance.root_dir).name if provenance and provenance.root_dir else None,
        **freshness_of(commit, expected_commit),
    }


async def load_provenance(collection: Any) -> "GraphProvenance | None":
    """The stored build record of the graph, or None when it has none (reads as unknown, never fresh)."""
    from services.knowledge.code_indexer import load_graph_provenance  # heavy import, kept off the route import path

    return await load_graph_provenance(collection)


async def open_graph(extra: dict[str, Any]) -> tuple[Any, dict[str, Any] | None]:
    """The graph collection, or ``(None, not-indexed answer)`` when it is missing or empty.

    Opens the collection read-only: a missing one is reported as not indexed, never created.

    "The graph has not been built" is a different answer from "that node does not exist"
    (#17254), so it is returned as its own ``indexed: false`` answer rather than an empty hit.
    """
    collection = await asyncio.to_thread(get_existing_code_graph_collection)
    if collection is None:
        return None, {"indexed": False, "source_scope": SOURCE_SCOPE, **extra, "message": _NOT_BUILT}
    if not await asyncio.to_thread(collection.count):
        return None, {"indexed": False, "source_scope": SOURCE_SCOPE, **extra, "message": _EMPTY}
    return collection, None


def _select_candidates(symbol: str, nodes: list[tuple[str, dict]]) -> tuple[str, list[tuple[str, dict]]]:
    """Narrow same-named nodes by the most specific form *symbol* matches: id, qualified name, bare name."""
    exact = [n for n in nodes if n[0] == symbol]
    if exact:
        return "node_id", exact
    if "." in symbol:
        return "qualified_name", [n for n in nodes if n[0].endswith("." + symbol)]
    return "name", nodes


def _candidate_record(node_id: str, meta: dict) -> dict[str, Any]:
    return {
        "node_id": node_id,
        "name": meta.get("node_name"),
        "kind": meta.get("node_kind"),
        "path": meta.get("source_path"),
        "line": meta.get("line"),
        "parent": meta.get("parent") or None,
    }


async def _named_nodes(collection: Any, bare_name: str) -> list[tuple[str, dict]]:
    found = await asyncio.to_thread(
        collection.get,
        where={"$and": [{"record_type": {"$eq": "node"}}, {"node_name": {"$eq": bare_name}}]},
        include=["metadatas"],
    )
    return list(zip(found.get("ids") or [], found.get("metadatas") or []))


async def resolve_symbol(symbol: str, expected_commit: str | None = None) -> dict[str, Any]:
    """Resolve a symbol name to graph node ids. Never picks one of several silently.

    ``status`` is ``resolved`` (exactly one node, ``node_id`` set), ``ambiguous`` (several,
    ``node_id`` is None and ``candidates`` lists them) or ``not_found``. Accepts a bare name
    (``helper``), a qualified name (``Class.method``, ``module.helper``) or an exact node id.
    """
    collection, unindexed = await open_graph({"symbol": symbol})
    if unindexed is not None:
        return unindexed
    nodes = await _named_nodes(collection, symbol.rsplit(".", 1)[-1])
    matched_by, chosen = _select_candidates(symbol, nodes)
    candidates = [_candidate_record(nid, meta) for nid, meta in sorted(chosen, key=lambda n: n[0])]
    provenance = await load_provenance(collection)
    return {
        "indexed": True,
        "symbol": symbol,
        "status": "not_found" if not candidates else "resolved" if len(candidates) == 1 else "ambiguous",
        "matched_by": matched_by if candidates else None,
        "node_id": candidates[0]["node_id"] if len(candidates) == 1 else None,
        "candidates": candidates[:RESOLVE_MAX_CANDIDATES],
        "candidate_count": len(candidates),
        "truncated": len(candidates) > RESOLVE_MAX_CANDIDATES,
        **provenance_fields(provenance, expected_commit),
    }


def _impact_fields(result: Any) -> dict[str, Any]:
    """The walk's coverage in full: a capped or partly unresolved walk must not read as complete."""
    return {
        "root_id": result.root_id,
        "seed_ids": result.seed_ids,
        "reached": result.reached,
        "edges": result.edges,
        "depth_capped": result.depth_capped,
        "depth_capped_frontier": result.depth_capped_frontier,
        "skipped_edges": result.skipped_edges,
        "resolved_edge_count": result.resolved_edge_count,
        "unresolved_edge_count": result.unresolved_edge_count,
        "max_depth": result.max_depth,
        "depth_reached": result.depth_reached,
    }


async def query_impact(
    node_id: str,
    max_depth: int | None = None,
    expected_commit: str | None = None,
) -> dict[str, Any]:
    """What transitively calls *node_id*, with the commit the graph was built at."""
    collection, unindexed = await open_graph({"node_id": node_id})
    if unindexed is not None:
        return unindexed
    result = await find_impact(collection, node_id, max_depth=max_depth)
    logger.info(
        "Impact walk for %s: %d reached, depth %d/%d%s",
        node_id,
        len(result.reached),
        result.depth_reached,
        result.max_depth,
        " (capped)" if result.depth_capped else "",
    )
    provenance = await load_provenance(collection)
    return {"indexed": True, **_impact_fields(result), **provenance_fields(provenance, expected_commit)}


async def query_impact_by_symbol(
    symbol: str,
    max_depth: int | None = None,
    expected_commit: str | None = None,
) -> dict[str, Any]:
    """Impact for a symbol name. An unresolved or ambiguous symbol returns the resolution, not a walk."""
    resolution = await resolve_symbol(symbol, expected_commit)
    if resolution.get("node_id") is None:
        return {**resolution, "impact": None}
    impact = await query_impact(resolution["node_id"], max_depth, expected_commit)
    return {**impact, "symbol": symbol, "matched_by": resolution["matched_by"]}


async def query_affected(
    node_id: str | None = None,
    symbol: str | None = None,
    max_depth: int | None = None,
    expected_commit: str | None = None,
) -> dict[str, Any]:
    """Impact by node id or by symbol name -- the one entry point the route and the tool both call."""
    if (node_id is None) == (symbol is None):
        raise ValueError("give exactly one of node_id or symbol")
    if node_id is not None:
        return await query_impact(node_id, max_depth, expected_commit)
    return await query_impact_by_symbol(symbol, max_depth, expected_commit)


async def find_similar_code(
    code: str,
    source_id: str,
    pattern_type: str | None = None,
    limit: int = QueryDefaults.DEFAULT_SEARCH_LIMIT,
) -> list[dict[str, Any]]:
    """Stored patterns of *source_id* most similar to the snippet *code*."""
    from code_intelligence.pattern_analysis import CodePatternAnalyzer
    from code_intelligence.pattern_analysis.storage import search_similar_patterns

    query_embedding = await CodePatternAnalyzer()._generate_embedding(code)
    return await search_similar_patterns(
        query_embedding=query_embedding,
        pattern_type=pattern_type,
        n_results=limit,
        source_id=source_id,
    )


def similar_code_answer(
    results: list[dict[str, Any]], source_id: str, expected_commit: str | None = None
) -> dict[str, Any]:
    """Wrap similar-code hits with their source. The pattern store records no build commit, so
    ``indexed_at_commit`` is None and a stated expectation yields ``unknown``, never ``current``."""
    return {
        "source_id": source_id,
        "results": results,
        "count": len(results),
        "indexed_at_commit": None,
        **freshness_of(None, expected_commit),
    }
