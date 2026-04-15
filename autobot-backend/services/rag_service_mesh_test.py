#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for Neural Mesh RAG feature flags and RAGService mesh path (#2059, #4724)."""

import pytest
from unittest.mock import AsyncMock, MagicMock


# =============================================================================
# Helpers
# =============================================================================


def _make_service(mesh_retriever_enabled: bool = False):
    """Build a RAGService stub; no Redis or ChromaDB connections."""
    from advanced_rag_optimizer import RAGMetrics
    from services.rag_config import RAGConfig
    from services.rag_service import RAGService

    svc = RAGService.__new__(RAGService)
    svc._initialized = True
    svc._cache = {}
    svc._cache_lock = MagicMock()
    cfg = RAGConfig()
    cfg.enable_advanced_rag = True
    cfg.mesh_retriever_enabled = mesh_retriever_enabled
    svc.config = cfg
    svc._mesh_retriever = None
    opt = MagicMock()
    opt.advanced_search = AsyncMock(return_value=([], RAGMetrics()))
    opt.advanced_search_with_refinement = AsyncMock(return_value=([], RAGMetrics(), []))
    svc.optimizer = opt
    return svc


def _make_mesh_result(chunk_ids):
    """Return a mock MeshRetrievalResult."""
    from advanced_rag_optimizer import SearchResult

    chunks = [
        SearchResult(
            content=f"content-{cid}",
            metadata={"chunk_id": cid},
            semantic_score=0.5,
            keyword_score=0.0,
            hybrid_score=0.5,
            relevance_rank=i + 1,
            source_path=cid,
        )
        for i, cid in enumerate(chunk_ids)
    ]
    result = MagicMock()
    result.chunks = chunks
    return result


# =============================================================================
# Test: mesh_retriever_enabled default and to_dict
# =============================================================================


class TestMeshFeatureFlagsDefaultValues:
    def test_defaults(self):
        from services.rag_config import RAGConfig
        cfg = RAGConfig()
        assert cfg.mesh_retriever_enabled is False
        assert cfg.mesh_seed_edges is True
        assert cfg.mesh_edge_learner is False

    def test_to_dict_includes_mesh_retriever_enabled(self):
        from services.rag_config import RAGConfig
        d = RAGConfig().to_dict()
        assert "mesh_retriever_enabled" in d
        assert d["mesh_retriever_enabled"] is False

    def test_from_dict_round_trip(self):
        from services.rag_config import RAGConfig
        original = RAGConfig()
        original.mesh_edge_learner = True
        restored = RAGConfig.from_dict(original.to_dict())
        assert restored.mesh_edge_learner is True
        assert restored.mesh_retriever_enabled is False


# =============================================================================
# Test: flag disabled — legacy optimizer path is taken
# =============================================================================


class TestMeshFlagDisabled:
    @pytest.mark.asyncio
    async def test_legacy_path_when_flag_off(self):
        from unittest.mock import patch

        svc = _make_service(mesh_retriever_enabled=False)

        with patch("services.rag_service.RAGService._check_cache_tiers",
                   new_callable=AsyncMock, return_value=None), \
             patch("services.rag_service.RAGService.initialize",
                   new_callable=AsyncMock, return_value=True), \
             patch("services.rag_service.RAGService._emit_ranked_feedback",
                   new_callable=AsyncMock), \
             patch("services.rag_service.RAGService._run_mesh_retriever",
                   new_callable=AsyncMock) as mock_mesh:
            await svc.advanced_search("test query")
            mock_mesh.assert_not_called()
            svc.optimizer.advanced_search.assert_called_once()


# =============================================================================
# Test: flag enabled + retriever set — mesh path is taken
# =============================================================================


class TestMeshFlagEnabled:
    @pytest.mark.asyncio
    async def test_mesh_path_when_flag_on_and_retriever_injected(self):
        from advanced_rag_optimizer import RAGMetrics
        from unittest.mock import patch

        svc = _make_service(mesh_retriever_enabled=True)
        svc._mesh_retriever = MagicMock()  # non-None

        expected = _make_mesh_result(["c1", "c2"]).chunks
        metrics = RAGMetrics()

        with patch("services.rag_service.RAGService._check_cache_tiers",
                   new_callable=AsyncMock, return_value=None), \
             patch("services.rag_service.RAGService._emit_ranked_feedback",
                   new_callable=AsyncMock), \
             patch("services.rag_service.RAGService._run_mesh_retriever",
                   new_callable=AsyncMock, return_value=(expected, metrics)) as mock_mesh:
            results, _ = await svc.advanced_search("test query")
            mock_mesh.assert_called_once_with("test query", 5)
            assert results is expected


# =============================================================================
# Test: flag enabled but retriever None — falls through to legacy
# =============================================================================


class TestMeshFlagEnabledRetrieverNone:
    @pytest.mark.asyncio
    async def test_falls_through_when_retriever_not_injected(self):
        from unittest.mock import patch

        svc = _make_service(mesh_retriever_enabled=True)
        svc._mesh_retriever = None  # not injected yet

        with patch("services.rag_service.RAGService._check_cache_tiers",
                   new_callable=AsyncMock, return_value=None), \
             patch("services.rag_service.RAGService.initialize",
                   new_callable=AsyncMock, return_value=True), \
             patch("services.rag_service.RAGService._emit_ranked_feedback",
                   new_callable=AsyncMock), \
             patch("services.rag_service.RAGService._run_mesh_retriever",
                   new_callable=AsyncMock) as mock_mesh:
            await svc.advanced_search("test query")
            mock_mesh.assert_not_called()
            svc.optimizer.advanced_search.assert_called_once()


# =============================================================================
# Test: register_shared_mesh_retriever auto-wires on initialize() (#4757)
# =============================================================================


class TestSharedMeshRetrieverAutoWire:
    def setup_method(self):
        """Clear shared singleton before each test to avoid cross-test contamination."""
        import services.rag_service as _mod
        self._orig = _mod._shared_mesh_retriever
        _mod._shared_mesh_retriever = None

    def teardown_method(self):
        import services.rag_service as _mod
        _mod._shared_mesh_retriever = self._orig

    @pytest.mark.asyncio
    async def test_register_then_initialize_wires_retriever(self):
        """RAGService.initialize() picks up the shared singleton when _mesh_retriever is None."""
        from services.rag_service import RAGService, register_shared_mesh_retriever
        from services.rag_config import RAGConfig
        from unittest.mock import patch, AsyncMock

        sentinel = MagicMock(name="NeuralMeshRetriever")
        register_shared_mesh_retriever(sentinel)

        svc = RAGService.__new__(RAGService)
        svc._initialized = False
        svc._cache = {}
        svc._cache_lock = MagicMock()
        svc.config = RAGConfig()
        svc._mesh_retriever = None
        svc.kb_adapter = MagicMock()
        svc.kb_adapter.kb = MagicMock()

        with patch("services.rag_service.AdvancedRAGOptimizer") as MockOpt:
            mock_opt = MagicMock()
            mock_opt.initialize = AsyncMock(return_value=True)
            MockOpt.return_value = mock_opt

            result = await svc.initialize()

        assert result is True
        assert svc._mesh_retriever is sentinel
        assert svc.config.mesh_retriever_enabled is True

    @pytest.mark.asyncio
    async def test_already_set_retriever_not_overwritten(self):
        """An existing _mesh_retriever is not replaced by the shared singleton."""
        from services.rag_service import RAGService, register_shared_mesh_retriever
        from services.rag_config import RAGConfig
        from unittest.mock import patch, AsyncMock

        existing = MagicMock(name="existing_retriever")
        shared = MagicMock(name="shared_retriever")
        register_shared_mesh_retriever(shared)

        svc = RAGService.__new__(RAGService)
        svc._initialized = False
        svc._cache = {}
        svc._cache_lock = MagicMock()
        svc.config = RAGConfig()
        svc.config.mesh_retriever_enabled = True
        svc._mesh_retriever = existing
        svc.kb_adapter = MagicMock()
        svc.kb_adapter.kb = MagicMock()

        with patch("services.rag_service.AdvancedRAGOptimizer") as MockOpt:
            mock_opt = MagicMock()
            mock_opt.initialize = AsyncMock(return_value=True)
            MockOpt.return_value = mock_opt

            await svc.initialize()

        assert svc._mesh_retriever is existing  # not replaced
