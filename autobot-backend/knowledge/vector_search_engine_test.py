# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for knowledge.vector_search_engine — Issue #3828.

Covers:
- Hardware auto-selection logic (NPU > GPU > CPU)
- Forced hardware backend routing
- Search result standardization (SearchResult dataclass)
- Reranker callable integration
- Fallback to CPU when primary backend raises
- Singleton factory returns the same instance
"""

from __future__ import annotations

import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stub heavy dependencies before importing the engine
# ---------------------------------------------------------------------------

# autobot_shared.ssot_config
_ssot = types.ModuleType("autobot_shared.ssot_config")
_feature = MagicMock()
_feature.npu_enabled = True
_autobot_cfg = MagicMock()
_autobot_cfg.feature = _feature
_ssot.config = _autobot_cfg
sys.modules.setdefault("autobot_shared", types.ModuleType("autobot_shared"))
sys.modules.setdefault("autobot_shared.ssot_config", _ssot)

# knowledge (for CPUBackend)
_knowledge_mod = types.ModuleType("knowledge")
sys.modules.setdefault("knowledge", _knowledge_mod)

# npu_semantic_search (for NPUBackend)
_npu_mod = types.ModuleType("npu_semantic_search")
sys.modules.setdefault("npu_semantic_search", _npu_mod)

# utils.gpu_vector_search (for GPUBackend and _check_faiss_flags)
_gpu_mod = types.ModuleType("utils.gpu_vector_search")
_gpu_mod.FAISS_AVAILABLE = False
_gpu_mod.FAISS_GPU_AVAILABLE = False
_gpu_mod.VectorSearchConfig = MagicMock()
_gpu_mod.get_hybrid_vector_search = AsyncMock()
sys.modules.setdefault("utils", types.ModuleType("utils"))
sys.modules.setdefault("utils.gpu_vector_search", _gpu_mod)

# knowledge.facts (legacy stub — no longer used by GPUBackend after #5105
# but retained because other test paths may import the module name)
_facts_mod = types.ModuleType("knowledge.facts")
_facts_mod._generate_embedding_with_npu_fallback = AsyncMock(return_value=[0.1, 0.2, 0.3])
sys.modules.setdefault("knowledge.facts", _facts_mod)

# services.npu_client (canonical NPU-fallback helper used by GPUBackend
# after #5105 consolidation)
_services_mod = types.ModuleType("services")
_npu_client_mod = types.ModuleType("services.npu_client")
_npu_client_mod.generate_embedding_with_fallback = AsyncMock(return_value=[0.1, 0.2, 0.3])
sys.modules.setdefault("services", _services_mod)
sys.modules.setdefault("services.npu_client", _npu_client_mod)

# ---------------------------------------------------------------------------
# Import after stubs are in place
# ---------------------------------------------------------------------------

# Reset module-level singleton and FAISS flags before import

if "knowledge.vector_search_engine" in sys.modules:
    del sys.modules["knowledge.vector_search_engine"]

import knowledge.vector_search_engine as vse  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_engine_result(text="hello", score=0.9, metadata=None, source="doc1"):
    return vse.SearchResult(text=text, score=score, metadata=metadata or {}, source=source)


def _cpu_backend_returning(results):
    """Return a _CPUBackend whose search always returns *results*."""
    backend = MagicMock()
    backend.search = AsyncMock(return_value=results)
    return backend


def _npu_backend_returning(results):
    backend = MagicMock()
    backend.search = AsyncMock(return_value=results)
    return backend


def _gpu_backend_returning(results):
    backend = MagicMock()
    backend.search = AsyncMock(return_value=results)
    return backend


# ---------------------------------------------------------------------------
# SearchResult dataclass
# ---------------------------------------------------------------------------


class TestSearchResult:
    def test_defaults(self):
        r = vse.SearchResult(text="hello", score=0.5)
        assert r.text == "hello"
        assert r.score == 0.5
        assert r.metadata == {}
        assert r.source == ""

    def test_explicit_fields(self):
        r = vse.SearchResult(text="abc", score=0.8, metadata={"k": "v"}, source="fact-42")
        assert r.metadata["k"] == "v"
        assert r.source == "fact-42"


# ---------------------------------------------------------------------------
# Hardware selection
# ---------------------------------------------------------------------------


class TestHardwareSelection:
    """VectorSearchEngine._select_backend logic."""

    def _engine(self):
        engine = vse.VectorSearchEngine()
        engine._npu = MagicMock()
        engine._gpu = MagicMock()
        engine._cpu = MagicMock()
        return engine

    def test_explicit_npu(self):
        engine = self._engine()
        assert engine._select_backend("npu") is engine._npu

    def test_explicit_gpu(self):
        engine = self._engine()
        assert engine._select_backend("gpu") is engine._gpu

    def test_explicit_cpu(self):
        engine = self._engine()
        assert engine._select_backend("cpu") is engine._cpu

    def test_auto_prefers_npu_when_enabled(self):
        engine = self._engine()
        with (
            patch.object(vse, "_npu_enabled", return_value=True),
            patch.object(vse, "_gpu_available", return_value=True),
        ):
            assert engine._select_backend("auto") is engine._npu

    def test_auto_falls_to_gpu_when_npu_disabled(self):
        engine = self._engine()
        with (
            patch.object(vse, "_npu_enabled", return_value=False),
            patch.object(vse, "_gpu_available", return_value=True),
        ):
            assert engine._select_backend("auto") is engine._gpu

    def test_auto_falls_to_cpu_when_neither_available(self):
        engine = self._engine()
        with (
            patch.object(vse, "_npu_enabled", return_value=False),
            patch.object(vse, "_gpu_available", return_value=False),
        ):
            assert engine._select_backend("auto") is engine._cpu


# ---------------------------------------------------------------------------
# search() — result standardization
# ---------------------------------------------------------------------------


class TestSearchResultStandardization:
    @pytest.mark.asyncio
    async def test_returns_sorted_descending(self):
        engine = vse.VectorSearchEngine()
        unsorted = [
            _make_engine_result(text="low", score=0.3),
            _make_engine_result(text="high", score=0.9),
            _make_engine_result(text="mid", score=0.6),
        ]
        engine._cpu = _cpu_backend_returning(unsorted)
        with (
            patch.object(vse, "_npu_enabled", return_value=False),
            patch.object(vse, "_gpu_available", return_value=False),
        ):
            results = await engine.search("query", top_k=10, hardware_backend="auto")
        assert [r.score for r in results] == [0.9, 0.6, 0.3]

    @pytest.mark.asyncio
    async def test_empty_query_returns_empty(self):
        engine = vse.VectorSearchEngine()
        results = await engine.search("   ", top_k=5)
        assert results == []

    @pytest.mark.asyncio
    async def test_correct_fields_forwarded(self):
        result = _make_engine_result(text="content", score=0.75, metadata={"cat": "test"}, source="fact-1")
        engine = vse.VectorSearchEngine()
        engine._npu = _npu_backend_returning([result])
        with patch.object(vse, "_npu_enabled", return_value=True):
            results = await engine.search("query")
        assert len(results) == 1
        assert results[0].text == "content"
        assert results[0].score == 0.75
        assert results[0].metadata == {"cat": "test"}
        assert results[0].source == "fact-1"

    @pytest.mark.asyncio
    async def test_filters_forwarded_to_backend(self):
        backend = MagicMock()
        backend.search = AsyncMock(return_value=[])
        engine = vse.VectorSearchEngine()
        engine._cpu = backend
        filters = {"category": "docs"}
        with (
            patch.object(vse, "_npu_enabled", return_value=False),
            patch.object(vse, "_gpu_available", return_value=False),
        ):
            await engine.search("q", top_k=5, filters=filters)
        backend.search.assert_awaited_once_with(query="q", top_k=5, filters=filters)


# ---------------------------------------------------------------------------
# search() — reranking
# ---------------------------------------------------------------------------


class TestReranking:
    @pytest.mark.asyncio
    async def test_reranker_called_with_query_and_results(self):
        results = [_make_engine_result(score=0.8)]
        reranked = [_make_engine_result(score=0.95)]
        reranker = AsyncMock(return_value=reranked)

        engine = vse.VectorSearchEngine()
        engine._cpu = _cpu_backend_returning(results)

        with (
            patch.object(vse, "_npu_enabled", return_value=False),
            patch.object(vse, "_gpu_available", return_value=False),
        ):
            out = await engine.search("q", reranker=reranker)

        reranker.assert_awaited_once()
        assert out[0].score == 0.95

    @pytest.mark.asyncio
    async def test_reranker_exception_does_not_propagate(self):
        """A failing reranker should be swallowed; original results returned."""
        results = [_make_engine_result(score=0.7)]
        reranker = AsyncMock(side_effect=RuntimeError("rerank failed"))

        engine = vse.VectorSearchEngine()
        engine._cpu = _cpu_backend_returning(results)

        with (
            patch.object(vse, "_npu_enabled", return_value=False),
            patch.object(vse, "_gpu_available", return_value=False),
        ):
            out = await engine.search("q", reranker=reranker)

        assert len(out) == 1
        assert out[0].score == 0.7

    @pytest.mark.asyncio
    async def test_no_reranker_when_results_empty(self):
        reranker = AsyncMock()
        engine = vse.VectorSearchEngine()
        engine._cpu = _cpu_backend_returning([])

        with (
            patch.object(vse, "_npu_enabled", return_value=False),
            patch.object(vse, "_gpu_available", return_value=False),
        ):
            out = await engine.search("q", reranker=reranker)

        reranker.assert_not_awaited()
        assert out == []


# ---------------------------------------------------------------------------
# search() — CPU fallback on primary backend failure
# ---------------------------------------------------------------------------


class TestFallback:
    @pytest.mark.asyncio
    async def test_falls_back_to_cpu_on_npu_failure(self):
        npu_backend = MagicMock()
        npu_backend.search = AsyncMock(side_effect=RuntimeError("NPU unavailable"))
        cpu_result = [_make_engine_result(text="cpu_result", score=0.5)]
        cpu_backend = _cpu_backend_returning(cpu_result)

        engine = vse.VectorSearchEngine()
        engine._npu = npu_backend
        engine._cpu = cpu_backend

        with patch.object(vse, "_npu_enabled", return_value=True):
            results = await engine.search("query")

        cpu_backend.search.assert_awaited_once()
        assert results[0].text == "cpu_result"

    @pytest.mark.asyncio
    async def test_returns_empty_on_total_failure(self):
        npu_backend = MagicMock()
        npu_backend.search = AsyncMock(side_effect=RuntimeError("NPU failed"))
        cpu_backend = MagicMock()
        cpu_backend.search = AsyncMock(side_effect=RuntimeError("CPU also failed"))

        engine = vse.VectorSearchEngine()
        engine._npu = npu_backend
        engine._cpu = cpu_backend

        with patch.object(vse, "_npu_enabled", return_value=True):
            results = await engine.search("query")

        assert results == []


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------


class TestSingleton:
    @pytest.mark.asyncio
    async def test_same_instance_returned_twice(self):
        # Reset singleton before test
        vse._instance = None
        e1 = await vse.get_vector_search_engine()
        e2 = await vse.get_vector_search_engine()
        assert e1 is e2

    @pytest.mark.asyncio
    async def test_instance_is_vector_search_engine(self):
        vse._instance = None
        e = await vse.get_vector_search_engine()
        assert isinstance(e, vse.VectorSearchEngine)
