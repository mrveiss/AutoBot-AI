# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Graph-section helpers for the multi-source knowledge graph (#20945; split out of the aggregator)."""

from typing import Any, Dict, List

from api.knowledge_graph_codebase import codebase_section_for_graph
from api.schemas_knowledge_graph import GraphRequest
from autobot_shared.logging_manager import get_logger
from knowledge.graph_buckets import build_bucket_sections, section_report

logger = get_logger(__name__)


async def facts_section(kb: Any, returned: int, offset: int) -> Dict[str, Any]:
    """The facts section's total vs returned; total is None (reported as limited) when stats are unreadable."""
    total = None
    try:
        total = (await kb.get_stats()).get("total_facts")
    except Exception as e:
        logger.warning("Failed to read fact total for graph: %s", e)
    return section_report("facts", "Knowledge base facts", total, offset + returned)


async def bucket_sections_for_graph(
    kb: Any, body: GraphRequest, nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]], is_admin: bool
) -> List[Dict[str, Any]]:
    """Append one section per ChromaDB knowledge bucket; return their total vs returned (#20945)."""
    client = getattr(kb, "_async_chroma_client", None)
    if not body.include_buckets or client is None or body.offset > 0 or body.category_filter:
        return []
    try:
        built = await build_bucket_sections(client, is_admin)
    except Exception as e:
        logger.warning("Failed to build bucket sections: %s", e)
        return []
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
    is_admin: bool,
    fact_count: int,
    user: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    """The codebase section first (AutoBot's own code), then facts, then one per bucket: total vs returned."""
    codebases: List[Dict[str, Any]] = []
    if body.include_buckets and body.offset == 0 and not body.category_filter:
        codebases = await codebase_section_for_graph(nodes, edges, user, is_admin)
    return [
        *codebases,
        await facts_section(kb, fact_count, body.offset),
        *await bucket_sections_for_graph(kb, body, nodes, edges, is_admin),
    ]
