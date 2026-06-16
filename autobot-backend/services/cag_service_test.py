#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for CAGService — Issue #9018 Phase 1.

Covers:
- CAG assembles full docs under token budget.
- CAG falls back to RAG when docs exceed budget.
- CAG falls back to RAG when no source paths are resolved.
- CAG falls back to RAG when all source files are unreadable.
"""

from __future__ import annotations

from pathlib import Path
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("advanced_rag_optimizer")

from advanced_rag_optimizer import RAGMetrics, SearchResult
from services.cag_service import CAGService, _assemble_context, _unique_source_paths
from services.rag_config import RAGConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result(source_path: str, content: str = "chunk", rank: int = 1) -> SearchResult:
    return SearchResult(
        content=content,
        metadata={"source": source_path},
        semantic_score=0.9,
        keyword_score=0.8,
        hybrid_score=0.85,
        relevance_rank=rank,
        source_path=source_path,
    )


def _make_rag_service(results: List[SearchResult] | None = None, config: RAGConfig | None = None) -> MagicMock:
    svc = MagicMock()
    svc.config = config or RAGConfig(enable_cag=True, cag_max_documents=10, cag_output_headroom_tokens=512)
    metrics = RAGMetrics(total_time=0.05, final_results_count=len(results or []))
    svc.advanced_search = AsyncMock(return_value=(results or [], metrics))
    context_metrics = RAGMetrics(total_time=0.1, final_results_count=1)
    context_metrics.strategy = "rag"  # type: ignore[attr-defined]
    svc.get_optimized_context = AsyncMock(return_value=("fallback-context", context_metrics))
    return svc


# ---------------------------------------------------------------------------
# Unit tests for internal helpers
# ---------------------------------------------------------------------------


def test_unique_source_paths_deduplication():
    """Multiple chunks from the same source_path collapse into one CandidateDoc."""
    results = [
        _make_result("docs/a.md", "chunk1"),
        _make_result("docs/a.md", "chunk2"),
        _make_result("docs/b.md", "chunk3"),
    ]
    docs = _unique_source_paths(results)
    assert len(docs) == 2
    assert docs[0].source_path == "docs/a.md"
    assert len(docs[0].chunks) == 2


def test_unique_source_paths_filters_synthetic():
    """source_path values like 'unknown', 'topic_cache', 'semantic_cache' are skipped."""
    results = [
        _make_result("unknown"),
        _make_result("topic_cache"),
        _make_result("semantic_cache"),
        _make_result("docs/real.md"),
    ]
    docs = _unique_source_paths(results)
    assert len(docs) == 1
    assert docs[0].source_path == "docs/real.md"


def test_assemble_context_format():
    """_assemble_context produces source headers and deduped sections."""
    pairs = [("docs/a.md", "content-a"), ("docs/b.md", "content-b")]
    ctx = _assemble_context(pairs)
    assert "=== Source: docs/a.md ===" in ctx
    assert "content-a" in ctx
    assert "=== Source: docs/b.md ===" in ctx
    assert "content-b" in ctx


# ---------------------------------------------------------------------------
# CAGService async tests
# ---------------------------------------------------------------------------


async def test_cag_assembles_docs_under_budget(tmp_path: Path):
    """When docs fit in budget, CAGService returns 'cag' strategy with full content."""
    doc_file = tmp_path / "doc.md"
    doc_file.write_text("This is the full document content.", encoding="utf-8")

    rag = _make_rag_service(results=[_make_result(str(doc_file))])
    cag = CAGService(rag)

    with patch("context_window_manager.ContextWindowManager.get_adaptive_context_length", return_value=8192):
        context, metrics = await cag.get_full_context(query="test query", model="llama3")

    assert "full document content" in context
    assert getattr(metrics, "strategy", None) == "cag"
    assert getattr(metrics, "documents_loaded", 0) == 1


async def test_cag_falls_back_when_budget_zero(tmp_path: Path):
    """When budget is 0 (headroom >= adaptive), CAG falls back to RAG."""
    doc_file = tmp_path / "doc.md"
    doc_file.write_text("content" * 100, encoding="utf-8")

    # headroom equals the adaptive length → budget = 0
    config = RAGConfig(enable_cag=True, cag_output_headroom_tokens=8192, cag_max_documents=10)
    rag = _make_rag_service(results=[_make_result(str(doc_file))], config=config)
    cag = CAGService(rag)

    with patch("context_window_manager.ContextWindowManager.get_adaptive_context_length", return_value=8192):
        context, metrics = await cag.get_full_context(query="test query")

    assert context == "fallback-context"
    assert getattr(metrics, "strategy", None) == "rag"


async def test_cag_falls_back_when_no_source_paths():
    """When all results have synthetic source paths, CAG falls back to RAG."""
    results = [_make_result("unknown"), _make_result("topic_cache")]
    rag = _make_rag_service(results=results)
    cag = CAGService(rag)

    with patch("context_window_manager.ContextWindowManager.get_adaptive_context_length", return_value=8192):
        context, metrics = await cag.get_full_context(query="test query")

    assert context == "fallback-context"
    assert getattr(metrics, "strategy", None) == "rag"


async def test_cag_falls_back_when_no_results():
    """When advanced_search returns empty, CAG falls back to RAG."""
    rag = _make_rag_service(results=[])
    cag = CAGService(rag)

    with patch("context_window_manager.ContextWindowManager.get_adaptive_context_length", return_value=8192):
        context, metrics = await cag.get_full_context(query="test query")

    assert context == "fallback-context"
    assert getattr(metrics, "strategy", None) == "rag"


async def test_cag_falls_back_when_file_unreadable():
    """When the source file doesn't exist on disk, CAG falls back to RAG."""
    rag = _make_rag_service(results=[_make_result("/nonexistent/path/doc.md")])
    cag = CAGService(rag)

    with patch("context_window_manager.ContextWindowManager.get_adaptive_context_length", return_value=8192):
        context, metrics = await cag.get_full_context(query="test query")

    assert context == "fallback-context"
    assert getattr(metrics, "strategy", None) == "rag"


async def test_cag_respects_max_documents(tmp_path: Path):
    """cag_max_documents caps the number of docs loaded."""
    files = []
    for i in range(5):
        f = tmp_path / f"doc{i}.md"
        f.write_text(f"content of document {i}", encoding="utf-8")
        files.append(f)

    config = RAGConfig(enable_cag=True, cag_max_documents=2, cag_output_headroom_tokens=256)
    results = [_make_result(str(f), rank=i) for i, f in enumerate(files)]
    rag = _make_rag_service(results=results, config=config)
    cag = CAGService(rag)

    with patch("context_window_manager.ContextWindowManager.get_adaptive_context_length", return_value=131072):
        context, metrics = await cag.get_full_context(query="test")

    assert getattr(metrics, "documents_loaded", 0) <= 2
