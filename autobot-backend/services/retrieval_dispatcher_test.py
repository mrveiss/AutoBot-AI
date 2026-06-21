#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for retrieval_dispatcher — Issue #9018 Phase 1.

Covers:
- select_strategy routes correctly for each mode.
- enable_cag=False never dispatches to CAG.
- get_context delegates to the right service.
- KAG and unknown modes fall back to RAG (Phase 1 policy).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("advanced_rag_optimizer")

from advanced_rag_optimizer import RAGMetrics
from services.rag_config import RAGConfig
from services.retrieval_dispatcher import get_context, select_strategy

# ---------------------------------------------------------------------------
# select_strategy unit tests
# ---------------------------------------------------------------------------


def _cfg(**kwargs) -> RAGConfig:
    defaults = dict(enable_cag=False)
    defaults.update(kwargs)
    return RAGConfig(**defaults)


def test_select_rag_returns_rag():
    assert select_strategy("rag", _cfg()) == "rag"


def test_select_kag_falls_back_to_rag():
    """Phase 1: KAG always falls back to RAG."""
    assert select_strategy("kag", _cfg(enable_cag=True)) == "rag"


def test_select_cag_disabled_returns_rag():
    """When enable_cag=False, requesting cag still returns rag."""
    assert select_strategy("cag", _cfg(enable_cag=False)) == "rag"


def test_select_cag_enabled_returns_cag():
    assert select_strategy("cag", _cfg(enable_cag=True)) == "cag"


def test_select_auto_cag_disabled_returns_rag():
    """auto + enable_cag=False → rag regardless of collection_mode."""
    assert select_strategy("auto", _cfg(enable_cag=False), collection_mode="cag") == "rag"


def test_select_auto_cag_enabled_collection_rag():
    """auto + enable_cag=True + collection_mode='rag' → rag."""
    assert select_strategy("auto", _cfg(enable_cag=True), collection_mode="rag") == "rag"


def test_select_auto_cag_enabled_collection_cag():
    """auto + enable_cag=True + collection_mode='cag' → cag."""
    assert select_strategy("auto", _cfg(enable_cag=True), collection_mode="cag") == "cag"


def test_select_auto_no_collection_mode():
    """auto + enable_cag=True + no collection_mode → rag (conservative default)."""
    assert select_strategy("auto", _cfg(enable_cag=True), collection_mode=None) == "rag"


def test_select_unknown_mode_returns_rag():
    assert select_strategy("unknown_mode", _cfg(enable_cag=True)) == "rag"


# ---------------------------------------------------------------------------
# get_context async integration tests
# ---------------------------------------------------------------------------


def _make_services(enable_cag: bool = True):
    config = RAGConfig(enable_cag=enable_cag, cag_output_headroom_tokens=512)
    rag = MagicMock()
    rag.config = config
    rag_metrics = RAGMetrics(total_time=0.1)
    rag.get_optimized_context = AsyncMock(return_value=("rag-context", rag_metrics))

    cag = MagicMock()
    cag_metrics = RAGMetrics(total_time=0.2)
    cag_metrics.strategy = "cag"  # type: ignore[attr-defined]
    cag.get_full_context = AsyncMock(return_value=("cag-context", cag_metrics))

    return rag, cag


async def test_get_context_rag_mode():
    rag, cag = _make_services()
    ctx, metrics = await get_context(query="q", rag_service=rag, cag_service=cag, mode="rag")
    assert ctx == "rag-context"
    assert getattr(metrics, "strategy", None) == "rag"
    cag.get_full_context.assert_not_called()


async def test_get_context_cag_mode_enabled():
    rag, cag = _make_services(enable_cag=True)
    ctx, metrics = await get_context(query="q", rag_service=rag, cag_service=cag, mode="cag")
    assert ctx == "cag-context"
    assert getattr(metrics, "strategy", None) == "cag"
    rag.get_optimized_context.assert_not_called()


async def test_get_context_cag_mode_disabled():
    """When enable_cag=False, even mode='cag' must route to RAG."""
    rag, cag = _make_services(enable_cag=False)
    ctx, metrics = await get_context(query="q", rag_service=rag, cag_service=cag, mode="cag")
    assert ctx == "rag-context"
    cag.get_full_context.assert_not_called()


async def test_get_context_kag_falls_back_to_rag():
    rag, cag = _make_services(enable_cag=True)
    ctx, metrics = await get_context(query="q", rag_service=rag, cag_service=cag, mode="kag")
    assert ctx == "rag-context"
    cag.get_full_context.assert_not_called()


async def test_get_context_auto_defaults_to_rag():
    """auto mode without collection_mode='cag' defaults to rag."""
    rag, cag = _make_services(enable_cag=True)
    ctx, metrics = await get_context(query="q", rag_service=rag, cag_service=cag, mode="auto", collection_mode=None)
    assert ctx == "rag-context"
    cag.get_full_context.assert_not_called()


async def test_get_context_auto_collection_cag():
    """auto + collection_mode='cag' + enable_cag=True → CAG."""
    rag, cag = _make_services(enable_cag=True)
    ctx, metrics = await get_context(query="q", rag_service=rag, cag_service=cag, mode="auto", collection_mode="cag")
    assert ctx == "cag-context"
    rag.get_optimized_context.assert_not_called()


# ---------------------------------------------------------------------------
# Phase 2 (KAG) — Issue #9018
# ---------------------------------------------------------------------------

from advanced_rag_optimizer import SearchResult  # noqa: E402


def test_select_kag_enabled_returns_kag():
    """enable_kag=True + mode='kag' → 'kag'."""
    assert select_strategy("kag", _cfg(enable_kag=True)) == "kag"


def test_select_kag_disabled_returns_rag():
    """enable_kag=False + mode='kag' → 'rag' (inert)."""
    assert select_strategy("kag", _cfg(enable_kag=False)) == "rag"


def test_select_auto_kag_enabled_collection_kag():
    """auto + enable_kag=True + collection_mode='kag' → 'kag'."""
    assert select_strategy("auto", _cfg(enable_kag=True), collection_mode="kag") == "kag"


def test_select_auto_kag_disabled_collection_kag():
    """auto + enable_kag=False + collection_mode='kag' → 'rag'."""
    assert select_strategy("auto", _cfg(enable_kag=False), collection_mode="kag") == "rag"


def _make_kag_services(enable_kag: bool = True, graph_results_added: int = 2):
    """Build rag/cag/graph_rag mocks for KAG dispatch tests."""
    from services.graph_rag_service import GraphRAGMetrics

    config = RAGConfig(enable_kag=enable_kag)
    rag = MagicMock()
    rag.config = config
    rag.get_optimized_context = AsyncMock(return_value=("rag-context", RAGMetrics(total_time=0.1)))

    cag = MagicMock()

    results = [
        SearchResult(
            content="entity observation A",
            metadata={"source": "graph_expansion"},
            semantic_score=0.0,
            keyword_score=0.0,
            hybrid_score=0.9,
            relevance_rank=1,
            source_path="graph:EntityA",
            chunk_index=0,
        ),
        SearchResult(
            content="entity observation B",
            metadata={"source": "graph_expansion"},
            semantic_score=0.0,
            keyword_score=0.0,
            hybrid_score=0.8,
            relevance_rank=2,
            source_path="graph:EntityB",
            chunk_index=0,
        ),
    ]
    gmetrics = GraphRAGMetrics()
    gmetrics.graph_results_added = graph_results_added
    graph_rag = MagicMock()
    graph_rag.graph_aware_search = AsyncMock(return_value=(results, gmetrics))
    return rag, cag, graph_rag


async def test_get_context_kag_routes_to_graph_aware_search():
    """KAG enabled → graph_aware_search invoked; (str, RAGMetrics) with strategy=kag."""
    rag, cag, graph_rag = _make_kag_services(enable_kag=True, graph_results_added=2)
    ctx, metrics = await get_context(
        query="relational q",
        rag_service=rag,
        cag_service=cag,
        graph_rag_service=graph_rag,
        mode="kag",
    )
    graph_rag.graph_aware_search.assert_awaited_once()
    assert isinstance(ctx, str)
    assert "entity observation A" in ctx and "graph:EntityA" in ctx
    assert getattr(metrics, "strategy", None) == "kag"
    assert metrics.graph_results_added == 2
    rag.get_optimized_context.assert_not_called()


async def test_get_context_kag_disabled_falls_back_to_rag():
    """enable_kag=False → kag inert, routes to RAG, graph never called."""
    rag, cag, graph_rag = _make_kag_services(enable_kag=False)
    ctx, metrics = await get_context(
        query="q",
        rag_service=rag,
        cag_service=cag,
        graph_rag_service=graph_rag,
        mode="kag",
    )
    assert ctx == "rag-context"
    assert getattr(metrics, "strategy", None) == "rag"
    graph_rag.graph_aware_search.assert_not_called()


async def test_get_context_kag_no_service_falls_back_to_rag():
    """KAG enabled but no GraphRAGService supplied → safe RAG fallback."""
    rag, cag, _ = _make_kag_services(enable_kag=True)
    ctx, metrics = await get_context(
        query="q",
        rag_service=rag,
        cag_service=cag,
        graph_rag_service=None,
        mode="kag",
    )
    assert ctx == "rag-context"
    assert getattr(metrics, "strategy", None) == "rag"
