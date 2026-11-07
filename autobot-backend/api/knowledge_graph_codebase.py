# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The codebase section of the multi-source knowledge graph (#20945).

Reuses the code-analysis services behind ``/analytics/call-graph`` and
``/analytics/dependencies``: the registry the analytics endpoints resolve a
source from, the call-graph cache they fill, and the latest dependency task
result. Nothing here extracts a graph: a codebase that has not been analysed
is reported as such, and the UI fetches the full graph from the analytics
endpoints (``FunctionCallGraph.vue``) by ``source_id``.
"""

from typing import Any, Dict, List

from fastapi import HTTPException

from api.codebase_analytics.endpoints.call_graph import _get_cached_call_graph
from api.codebase_analytics.endpoints.dependencies import _REDIS_PREFIX as DEPENDENCIES_PREFIX
from api.codebase_analytics.endpoints.shared import _caller_owner_id, resolve_scan_root
from api.codebase_analytics.source_models import CodeSource, SourceStatus
from api.codebase_analytics.source_scope import cached_task_result
from api.codebase_analytics.source_storage import RegistryUnavailable, get_default_source_id, list_sources
from autobot_shared.logging_manager import get_logger
from knowledge.graph_buckets import section_report

logger = get_logger(__name__)

CODEBASE_SECTION_KEY = "codebase"
CODEBASE_SECTION_LABEL = "Codebases"
CALL_GRAPH_SUMMARY_FIELDS = ("total_functions", "total_call_relationships", "resolution_rate", "files_scanned")
DEPENDENCY_SUMMARY_FIELDS = ("total_modules", "total_import_relationships", "circular_dependency_count")


async def indexed_codebases(user: Dict[str, Any] | None) -> List[CodeSource]:
    """Indexed sources the caller may see, the default (AutoBot's own code) first."""
    default_id = await get_default_source_id()
    visible = [s for s in await list_sources(_caller_owner_id(user)) if s.status == SourceStatus.READY]
    return sorted(visible, key=lambda s: (s.id != default_id, -_stamp(s)))


def _stamp(source: CodeSource) -> float:
    """Newest-synced first among the non-default sources (ISO strings compare lexically)."""
    return float("".join(c for c in (source.last_synced or "") if c.isdigit()) or 0)


def _pick(summary: Dict[str, Any], fields: tuple) -> Dict[str, Any]:
    return {f: summary.get(f) for f in fields}


async def call_graph_summary(source_id: str) -> Dict[str, Any] | None:
    """The cached ``/analytics/call-graph`` summary for a source; None when not analysed yet."""
    cached = await _get_cached_call_graph(str(await resolve_scan_root(source_id)))
    if not cached:
        return None
    return {
        **_pick(cached.get("summary", {}), CALL_GRAPH_SUMMARY_FIELDS),
        "truncated": bool(cached.get("summary", {}).get("truncated")),
    }


async def dependencies_summary(source_id: str) -> Dict[str, Any] | None:
    """The latest ``/analytics/dependencies`` task summary for a source; None when none completed."""
    try:
        cached = await cached_task_result(DEPENDENCIES_PREFIX, source_id)
    except HTTPException as exc:  # the latest scan failed: reported as not analysed, reason is in the task status
        logger.warning("Dependency result for source %s unavailable: HTTP %s", source_id, exc.status_code)
        return None
    if cached.get("status") != "success":
        return None
    return _pick(cached.get("dependency_data", {}).get("summary", {}), DEPENDENCY_SUMMARY_FIELDS)


async def _codebase_node(source: CodeSource, is_default: bool) -> Dict[str, Any]:
    """One codebase node; the call graph leads the metadata, dependencies are second (#20945)."""
    try:
        call_graph = await call_graph_summary(source.id)
    except Exception as e:  # a codebase whose cache is unreadable is still listed
        logger.warning("Call graph summary for source %s failed: %s", source.id, e)
        call_graph = None
    try:
        dependencies = await dependencies_summary(source.id)
    except Exception as e:
        logger.warning("Dependency summary for source %s failed: %s", source.id, e)
        dependencies = None
    return {
        "id": f"codebase:{source.id}",
        "name": source.name,
        "type": "codebase",
        "section": CODEBASE_SECTION_KEY,
        "metadata": {
            "source_id": source.id,
            "is_autobot": is_default,
            "last_synced": source.last_synced,
            "call_graph": call_graph,
            "dependencies": dependencies,
        },
    }


async def codebase_section_for_graph(
    nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]], user: Dict[str, Any] | None, is_admin: bool
) -> List[Dict[str, Any]]:
    """Put the codebase section FIRST in nodes; return its report (one per section, [] when none).

    The analytics router is admin-gated, so the section is too; per-source visibility
    follows ``list_sources`` exactly as the analytics endpoints do.
    """
    if not is_admin:
        return []
    try:
        sources = await indexed_codebases(user)
    except RegistryUnavailable as e:
        logger.warning("Codebase section skipped: the source registry is unavailable: %s", e)
        return []
    if not sources:
        return []
    default_id = await get_default_source_id()
    children = [await _codebase_node(s, s.id == default_id) for s in sources]
    section = {
        "id": f"section:{CODEBASE_SECTION_KEY}",
        "name": CODEBASE_SECTION_LABEL,
        "type": "section",
        "section": CODEBASE_SECTION_KEY,
        "metadata": {"total": len(children)},
    }
    nodes[0:0] = [section, *children]
    edges[0:0] = [{"from": section["id"], "to": c["id"], "type": "contains", "strength": 1.0} for c in children]
    return [section_report(CODEBASE_SECTION_KEY, CODEBASE_SECTION_LABEL, len(children), len(children))]
