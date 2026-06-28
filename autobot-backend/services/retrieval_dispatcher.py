#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Retrieval Strategy Dispatcher — Issue #9018.

Composes RAGService, CAGService and GraphRAGService under a single entry-point.
- Phase 1: rag | cag (+ auto → cag when collection requests it).
- Phase 2: kag → GraphRAGService.graph_aware_search, adapted to the shared
  (context: str, RAGMetrics) contract. Inert (falls back to rag) when
  enable_kag=False.

Auto-selection currently honours collection_mode for cag/kag; richer
heuristic auto-selection is Phase 3.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Tuple

from autobot_shared.logging_manager import get_llm_logger

if TYPE_CHECKING:
    from advanced_rag_optimizer import RAGMetrics, SearchResult
    from services.cag_service import CAGService
    from services.graph_rag_service import GraphRAGService
    from services.rag_config import RAGConfig
    from services.rag_service import RAGService

logger = get_llm_logger("retrieval_dispatcher")

# Supported mode literals.
_MODES = frozenset({"rag", "cag", "kag", "auto"})


def select_strategy(mode: str, config: "RAGConfig", collection_mode: str | None = None) -> str:
    """Return the concrete strategy to use ('rag', 'cag' or 'kag').

    Decision table:
    - mode == 'rag'  → 'rag'
    - mode == 'kag'  → 'kag' only when enable_kag=True, else 'rag' (inert)
    - mode == 'cag'  → 'cag' only when enable_cag=True, else 'rag'
    - mode == 'auto' → 'cag' when enable_cag and collection_mode=='cag';
                       'kag' when enable_kag and collection_mode=='kag';
                       else 'rag'
    - unknown        → 'rag'
    """
    enable_cag = getattr(config, "enable_cag", False)
    enable_kag = getattr(config, "enable_kag", False)

    if mode not in _MODES:
        logger.warning("Unknown retrieval mode %r — defaulting to rag", mode)
        return "rag"

    if mode == "rag":
        return "rag"

    if mode == "kag":
        if not enable_kag:
            logger.debug("KAG requested but enable_kag=False — using rag")
            return "rag"
        return "kag"

    if mode == "cag":
        if not enable_cag:
            logger.debug("CAG requested but enable_cag=False — using rag")
            return "rag"
        return "cag"

    # mode == 'auto'
    if enable_cag and collection_mode == "cag":
        return "cag"
    if enable_kag and collection_mode == "kag":
        return "kag"
    return "rag"


def _build_kag_context(results: List["SearchResult"]) -> str:
    """Assemble a context string from graph-aware SearchResult list.

    Mirrors RAG context assembly: ordered, provenance-headed blocks.
    """
    blocks = []
    for r in results:
        source = r.source_path or "unknown"
        blocks.append(f"[source: {source}]\n{r.content}")
    return "\n\n".join(blocks)


async def _run_kag(
    query: str,
    graph_rag_service: "GraphRAGService",
    model: str | None,
) -> "Tuple[str, RAGMetrics]":
    """Run the KAG strategy and adapt to the (context, RAGMetrics) contract.

    Returns the graph-augmented context plus a RAGMetrics carrying
    strategy='kag' and graph_results_added from GraphRAGMetrics.
    """
    results, graph_metrics = await graph_rag_service.graph_aware_search(query=query)
    context = _build_kag_context(results)
    graph_metrics.strategy = "kag"  # type: ignore[attr-defined]
    # graph_results_added already populated by GraphRAGMetrics; mirror defensively.
    graph_metrics.graph_results_added = getattr(graph_metrics, "graph_results_added", 0)
    logger.info(
        "KAG: %d results, graph_results_added=%d",
        len(results),
        graph_metrics.graph_results_added,
    )
    return context, graph_metrics


async def get_context(
    query: str,
    rag_service: "RAGService",
    cag_service: "CAGService",
    graph_rag_service: "GraphRAGService | None" = None,
    mode: str = "auto",
    collection: str | None = None,
    model: str | None = None,
    collection_mode: str | None = None,
) -> "Tuple[str, RAGMetrics]":
    """Route the query to the selected strategy and return (context, metrics).

    Args:
        query: Search / generation query.
        rag_service: Initialized RAGService instance.
        cag_service: CAGService wrapping rag_service.
        graph_rag_service: Optional GraphRAGService for the kag strategy.
            When None, a kag request falls back to rag.
        mode: Caller-requested mode ('auto'|'rag'|'cag'|'kag').
        collection: Optional collection identifier (for logging).
        model: Active model name (used by CAGService for budget calc).
        collection_mode: Per-collection setting from DB/metadata.

    Returns:
        (context, metrics) with metrics.strategy reflecting the strategy used.
    """
    config = rag_service.config
    strategy = select_strategy(mode, config, collection_mode)

    logger.info(
        "Dispatcher: mode=%r strategy=%r collection=%r model=%r",
        mode,
        strategy,
        collection,
        model,
    )

    if strategy == "cag":
        return await cag_service.get_full_context(query=query, collection=collection, model=model)

    if strategy == "kag":
        if graph_rag_service is None:
            logger.warning("KAG selected but no GraphRAGService provided — using rag")
        else:
            return await _run_kag(query=query, graph_rag_service=graph_rag_service, model=model)

    # RAG path (default, kag/cag-disabled fallback, unknown mode fallback)
    context, metrics = await rag_service.get_optimized_context(query=query)
    metrics.strategy = "rag"
    return context, metrics
