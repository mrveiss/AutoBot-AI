#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Retrieval Strategy Dispatcher — Phase 1 (Issue #9018).

Composes RAGService and CAGService under a single entry-point.
KAG and unknown modes fall back to RAG in Phase 1.
Auto-selection: defaults to RAG unless enable_cag=True AND the collection
explicitly requests cag (future Phase 3 adds heuristic auto-selection).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Tuple

from autobot_shared.logging_manager import get_llm_logger

if TYPE_CHECKING:
    from advanced_rag_optimizer import RAGMetrics
    from services.cag_service import CAGService
    from services.rag_config import RAGConfig
    from services.rag_service import RAGService

logger = get_llm_logger("retrieval_dispatcher")

# Supported mode literals.
_MODES = frozenset({"rag", "cag", "kag", "auto"})


def select_strategy(mode: str, config: "RAGConfig", collection_mode: str | None = None) -> str:
    """Return the concrete strategy to use ('rag' or 'cag').

    Decision table (Phase 1):
    - mode == 'rag'  → 'rag'
    - mode == 'kag'  → 'rag'  (Phase 2)
    - mode == 'cag'  → 'cag' only when enable_cag=True, else 'rag'
    - mode == 'auto' → 'cag' when enable_cag=True AND collection_mode=='cag', else 'rag'
    - unknown        → 'rag'
    """
    enable_cag = getattr(config, "enable_cag", False)

    if mode not in _MODES:
        logger.warning("Unknown retrieval mode %r — defaulting to rag", mode)
        return "rag"

    if mode == "rag":
        return "rag"

    if mode == "kag":
        logger.debug("KAG not yet implemented (Phase 2) — using rag")
        return "rag"

    if mode == "cag":
        if not enable_cag:
            logger.debug("CAG requested but enable_cag=False — using rag")
            return "rag"
        return "cag"

    # mode == 'auto'
    if enable_cag and collection_mode == "cag":
        return "cag"
    return "rag"


async def get_context(
    query: str,
    rag_service: "RAGService",
    cag_service: "CAGService",
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

    # RAG path (default, kag fallback, unknown mode fallback)
    context, metrics = await rag_service.get_optimized_context(query=query)
    metrics.strategy = "rag"
    return context, metrics
