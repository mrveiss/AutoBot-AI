# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The per-codebase nodes of the knowledge graph's "code" section (#20945).

Reuses the code-analysis services behind ``/analytics/call-graph`` and ``/analytics/dependencies``: the
source registry, the persisted call-graph summary the call-graph build leaves behind, and the latest
dependency task result. Nothing here extracts or copies a graph: a codebase that has not been analysed is
reported as such, and the UI fetches the full graph from the analytics endpoints by ``source_id``.

The nodes join the section ``knowledge.graph_buckets`` defines (``CODE_SECTION_KEY``); this module adds no
section of its own.
"""

from pathlib import Path
from typing import Any, Dict, List, Tuple

from fastapi import HTTPException

from api.codebase_analytics.call_graph_summary import load_call_graph_summary
from api.codebase_analytics.code_graph_queries import indexed_root_dir
from api.codebase_analytics.endpoints.dependencies import DEPENDENCIES_TASK_PREFIX
from api.codebase_analytics.endpoints.shared import caller_owner_id
from api.codebase_analytics.source_models import CodeSource, SourceStatus
from api.codebase_analytics.source_storage import RegistryUnavailable, list_sources
from api.source_scope import cached_task_result
from autobot_shared.logging_manager import get_logger
from knowledge.graph_bucket_visibility import Viewer
from knowledge.graph_buckets import CODE_SECTION_KEY

logger = get_logger(__name__)

DEPENDENCY_SUMMARY_FIELDS = ("total_modules", "total_import_relationships", "circular_dependency_count")


def _clone_is(source: CodeSource, root_dir: str | None) -> bool:
    """True when the source's clone is the tree the persistent code graph was indexed from."""
    return bool(root_dir and source.clone_path and Path(source.clone_path).resolve() == Path(root_dir).resolve())


def order_codebases(sources: List[CodeSource], index_root: str | None) -> List[CodeSource]:
    """The source cloned at the code graph's index root first; every other by (name, id), so the order is stable."""
    by_name = sorted(sources, key=lambda s: (s.name.casefold(), s.id))
    return [s for s in by_name if _clone_is(s, index_root)] + [s for s in by_name if not _clone_is(s, index_root)]


async def _index_root() -> str | None:
    try:
        return await indexed_root_dir()
    except Exception as e:  # no readable provenance: every codebase is then "other", in the stable order
        logger.warning("Code graph index root unavailable, no codebase is ordered first: %s", e)
        return None


async def indexed_codebases(user: Dict[str, Any] | None) -> List[CodeSource]:
    """Indexed sources the caller may see, the provenance-root source first (there is no default source, #20513)."""
    visible = [s for s in await list_sources(caller_owner_id(user)) if s.status == SourceStatus.READY]
    return order_codebases(visible, await _index_root()) if visible else []


async def dependencies_summary(source_id: str) -> Dict[str, Any] | None:
    """The latest ``/analytics/dependencies`` task summary for a source; None when none completed."""
    try:
        cached = await cached_task_result(DEPENDENCIES_TASK_PREFIX, source_id)
    except HTTPException as exc:  # the latest scan failed: reported as not analysed, reason is in the task status
        logger.warning("Dependency result for source %s unavailable: HTTP %s", source_id, exc.status_code)
        return None
    if cached.get("status") != "success":
        return None
    summary = cached.get("dependency_data", {}).get("summary", {})
    return {f: summary.get(f) for f in DEPENDENCY_SUMMARY_FIELDS}


async def _summary_or_none(read, source_id: str, what: str) -> Dict[str, Any] | None:
    try:
        return await read(source_id)
    except Exception as e:  # a codebase whose summary is unreadable is still listed, as not analysed
        logger.warning("%s summary for source %s failed: %s", what, source_id, e)
        return None


async def _codebase_node(source: CodeSource) -> Dict[str, Any]:
    """One codebase node; the call graph leads the metadata, dependencies are second (#20945)."""
    call_graph = await _summary_or_none(load_call_graph_summary, source.id, "Call graph")
    dependencies = await _summary_or_none(dependencies_summary, source.id, "Dependency")
    return {
        "id": f"codebase:{source.id}",
        "name": source.name,
        "type": "codebase",
        "section": CODE_SECTION_KEY,
        "metadata": {
            "source_id": source.id,
            "last_synced": source.last_synced,
            "analysed": call_graph is not None or dependencies is not None,
            "call_graph": call_graph,
            "dependencies": dependencies,
        },
    }


async def codebase_nodes_for_graph(
    user: Dict[str, Any] | None, viewer: Viewer
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """``(nodes, edges)`` of the indexed codebases, each contained by the code section; empty unless admin.

    The analytics router is admin-gated, so these nodes are too; per-source visibility follows
    ``list_sources`` exactly as the analytics endpoints do. Every codebase shown is recorded in the
    request's ``AdminReadLedger`` (#19860), as the admin bucket reads are.
    """
    if not viewer.admin_read:
        return [], []
    try:
        sources = await indexed_codebases(user)
    except RegistryUnavailable as e:
        logger.warning("Codebase nodes skipped: the source registry is unavailable: %s", e)
        return [], []
    nodes = [await _codebase_node(s) for s in sources]
    viewer.ledger.record([{"id": n["id"]} for n in nodes])
    return nodes, [
        {"from": f"section:{CODE_SECTION_KEY}", "to": n["id"], "type": "contains", "strength": 1.0} for n in nodes
    ]
