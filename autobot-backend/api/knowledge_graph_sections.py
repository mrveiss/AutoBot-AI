# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Graph-section helpers for the multi-source knowledge graph (#20945; split out of the aggregator)."""

from typing import Any, Dict, List

from api.knowledge_graph_codebase import codebase_nodes_for_graph
from api.knowledge_graph_facts import FactsPage
from api.schemas_knowledge_graph import GraphRequest
from autobot_shared.logging_manager import get_logger
from knowledge.graph_bucket_visibility import viewer_for
from knowledge.graph_buckets import CODE_SECTION_KEY, attach_section_nodes, build_bucket_sections, section_report

logger = get_logger(__name__)


def facts_section(page: FactsPage, offset: int) -> Dict[str, Any]:
    """The facts section: the VISIBLE total vs this page (never a count of facts the caller cannot read)."""
    report = section_report(
        "facts",
        "Knowledge base facts",
        page.total,
        len(page.facts),
        offset,
        page.truncated,
        budget_exhausted=page.budget_exhausted,
        failed=page.failed,
    )
    if page.by_cursor:  # no visible total in a cursor read: more remains exactly while a cursor is returned
        report["limited"] = page.cursor is not None or page.budget_exhausted
    report["cursor"] = page.cursor
    return report


async def _built_buckets(kb: Any, body: GraphRequest, viewer: Any) -> Dict[str, Any]:
    """The bucket sections of the request; empty when the KB has no ChromaDB client."""
    client = getattr(kb, "_async_chroma_client", None)
    built: Dict[str, Any] = {"nodes": [], "edges": [], "sections": [], "unmapped": []}
    if client is not None:
        built = await build_bucket_sections(
            client, viewer, getattr(kb, "ownership_manager", None), limit=body.max_facts, offset=body.offset, kb=kb
        )
    return built


async def _fold_codebases(built: Dict[str, Any], body: GraphRequest, current_user: Any, viewer: Any) -> None:
    """Put the per-codebase nodes inside the code section the registry defines; no section of their own (#20945)."""
    if body.offset:
        return
    nodes, edges = await codebase_nodes_for_graph(current_user, viewer)
    if nodes:
        attach_section_nodes(built, CODE_SECTION_KEY, nodes, edges)


async def bucket_sections_for_graph(
    kb: Any,
    body: GraphRequest,
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    current_user: Any,
    ledger: Any,
) -> List[Dict[str, Any]]:
    """Append one section per ChromaDB knowledge bucket the caller may read; return their totals (#20945)."""
    if not body.include_buckets or body.category_filter:
        return []
    try:
        viewer = viewer_for(current_user, ledger)
        built = await _built_buckets(kb, body, viewer)
        await _fold_codebases(built, body, current_user, viewer)
    except Exception as e:
        logger.warning("Failed to build bucket sections: %s", e)
        return [section_report("buckets", "Knowledge buckets", None, 0, failed=True)]  # not "no buckets"
    if built["unmapped"]:
        logger.warning("Knowledge collections missing from the graph registry: %s", built["unmapped"])
    nodes.extend(built["nodes"])
    edges.extend(built["edges"])
    return built["sections"]


async def graph_sections(
    kb: Any,
    body: GraphRequest,
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    ledger: Any,
    page: FactsPage,
    current_user: Any,
) -> List[Dict[str, Any]]:
    """The facts section, then one per bucket (the code section also carries the codebases): visible total vs page."""
    return [
        facts_section(page, body.offset),
        *await bucket_sections_for_graph(kb, body, nodes, edges, current_user, ledger),
    ]
