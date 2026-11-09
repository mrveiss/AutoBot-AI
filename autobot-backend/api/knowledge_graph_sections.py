# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Graph-section helpers for the multi-source knowledge graph (#20945; split out of the aggregator)."""

from typing import Any, Dict, List

from api.knowledge_graph_facts import FactsPage
from api.schemas_knowledge_graph import GraphRequest
from autobot_shared.logging_manager import get_logger
from knowledge.graph_bucket_visibility import viewer_for
from knowledge.graph_buckets import build_bucket_sections, section_report

logger = get_logger(__name__)


def facts_section(page: FactsPage, offset: int) -> Dict[str, Any]:
    """The facts section: the VISIBLE total vs this page (never a count of facts the caller cannot read)."""
    return section_report("facts", "Knowledge base facts", page.total, len(page.facts), offset, page.truncated)


async def bucket_sections_for_graph(
    kb: Any,
    body: GraphRequest,
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    current_user: Any,
    ledger: Any,
) -> List[Dict[str, Any]]:
    """Append one section per ChromaDB knowledge bucket the caller may read; return their totals (#20945)."""
    client = getattr(kb, "_async_chroma_client", None)
    if not body.include_buckets or client is None or body.category_filter:
        return []
    try:
        viewer = viewer_for(current_user, ledger)
        built = await build_bucket_sections(
            client, viewer, getattr(kb, "ownership_manager", None), limit=body.max_facts, offset=body.offset, kb=kb
        )
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
    ledger: Any,
    page: FactsPage,
    current_user: Any,
) -> List[Dict[str, Any]]:
    """The facts section first, then one per bucket: visible total vs this page for the whole graph."""
    return [
        facts_section(page, body.offset),
        *await bucket_sections_for_graph(kb, body, nodes, edges, current_user, ledger),
    ]
