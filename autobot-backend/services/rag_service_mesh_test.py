#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for Neural Mesh RAG feature flags and RAGService mesh path (#2059, #4724)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

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
    def test_defaults(self) -> None:
        from services.rag_config import RAGConfig

        cfg = RAGConfig()
        assert cfg.mesh_retriever_enabled is False
        assert cfg.mesh_seed_edges is True
        assert cfg.mesh_edge_learner is False

    def test_to_dict_includes_mesh_retriever_enabled(self) -> None:
        from services.rag_config import RAGConfig

        d = RAGConfig().to_dict()
        assert "mesh_retriever_enabled" in d
        assert d["mesh_retriever_enabled"] is False

    def test_from_dict_round_trip(self) -> None:
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
    async def test_legacy_path_when_flag_off(self) -> None:
        from unittest.mock import patch

        svc = _make_service(mesh_retriever_enabled=False)

        with (
            patch("services.rag_service.RAGService._check_cache_tiers", new_callable=AsyncMock, return_value=None),
            patch("services.rag_service.RAGService.initialize", new_callable=AsyncMock, return_value=True),
            patch("services.rag_service.RAGService._emit_ranked_feedback", new_callable=AsyncMock),
            patch("services.rag_service.RAGService._run_mesh_retriever", new_callable=AsyncMock) as mock_mesh,
        ):
            await svc.advanced_search("test query")
            mock_mesh.assert_not_called()
            svc.optimizer.advanced_search.assert_called_once()


# =============================================================================
# Test: flag enabled + retriever set — mesh path is taken
# =============================================================================


class TestMeshFlagEnabled:
    @pytest.mark.asyncio
    async def test_mesh_path_when_flag_on_and_retriever_injected(self) -> None:
        from unittest.mock import patch

        from advanced_rag_optimizer import RAGMetrics

        svc = _make_service(mesh_retriever_enabled=True)
        svc._mesh_retriever = MagicMock()  # non-None

        expected = _make_mesh_result(["c1", "c2"]).chunks
        metrics = RAGMetrics()

        with (
            patch("services.rag_service.RAGService._check_cache_tiers", new_callable=AsyncMock, return_value=None),
            patch("services.rag_service.RAGService._emit_ranked_feedback", new_callable=AsyncMock),
            patch(
                "services.rag_service.RAGService._run_mesh_retriever",
                new_callable=AsyncMock,
                return_value=(expected, metrics),
            ) as mock_mesh,
        ):
            results, _ = await svc.advanced_search("test query")
            mock_mesh.assert_called_once_with("test query", 5)
            assert results is expected


# =============================================================================
# Test: flag enabled but retriever None — falls through to legacy
# =============================================================================


class TestMeshFlagEnabledRetrieverNone:
    @pytest.mark.asyncio
    async def test_falls_through_when_retriever_not_injected(self) -> None:
        from unittest.mock import patch

        svc = _make_service(mesh_retriever_enabled=True)
        svc._mesh_retriever = None  # not injected yet

        with (
            patch("services.rag_service.RAGService._check_cache_tiers", new_callable=AsyncMock, return_value=None),
            patch("services.rag_service.RAGService.initialize", new_callable=AsyncMock, return_value=True),
            patch("services.rag_service.RAGService._emit_ranked_feedback", new_callable=AsyncMock),
            patch("services.rag_service.RAGService._run_mesh_retriever", new_callable=AsyncMock) as mock_mesh,
        ):
            await svc.advanced_search("test query")
            mock_mesh.assert_not_called()
            svc.optimizer.advanced_search.assert_called_once()


# =============================================================================
# Test: register_shared_mesh_components builds per-instance retriever (#4765)
# =============================================================================


class TestSharedMeshComponentsPerInstanceBuild:
    """Per-instance NeuralMeshRetriever is built from shared components (#4765)."""

    def setup_method(self) -> None:
        import services.rag_service as _mod

        self._orig = _mod._shared_mesh_components
        _mod._shared_mesh_components = None

    def teardown_method(self) -> None:
        import services.rag_service as _mod

        _mod._shared_mesh_components = self._orig

    def _make_components(self):
        return {
            "mesh_db": MagicMock(name="mesh_db"),
            "ppr": MagicMock(name="ppr"),
            "edge_learner": MagicMock(name="edge_learner"),
            "reranker": MagicMock(name="reranker"),
            "classifier": MagicMock(name="classifier"),
            "llm": None,
        }

    @pytest.mark.asyncio
    async def test_builds_per_instance_retriever_on_initialize(self) -> None:
        """initialize() builds a fresh NeuralMeshRetriever bound to this instance's optimizer."""
        from unittest.mock import AsyncMock, patch

        from services.rag_config import RAGConfig
        from services.rag_service import RAGService, register_shared_mesh_components

        register_shared_mesh_components(self._make_components())

        svc = RAGService.__new__(RAGService)
        svc._initialized = False
        svc._cache = {}
        svc._cache_lock = MagicMock()
        svc.config = RAGConfig()
        svc._mesh_retriever = None
        svc.kb_adapter = MagicMock()
        svc.kb_adapter.kb = MagicMock()

        built_retriever = MagicMock(name="built_NeuralMeshRetriever")
        with (
            patch("services.rag_service.AdvancedRAGOptimizer") as MockOpt,
            patch("services.rag_service.NeuralMeshRetriever", return_value=built_retriever) as MockNMR,
        ):
            mock_opt = MagicMock()
            mock_opt.initialize = AsyncMock(return_value=True)
            MockOpt.return_value = mock_opt

            result = await svc.initialize()

        assert result is True
        assert MockNMR.called, "NeuralMeshRetriever should have been instantiated"
        # chroma_search and hybrid_search closures must be present
        kwargs = MockNMR.call_args.kwargs
        assert callable(kwargs.get("chroma_search")), "chroma_search closure missing"
        assert callable(kwargs.get("hybrid_search")), "hybrid_search closure missing"
        assert svc._mesh_retriever is built_retriever
        assert svc.config.mesh_retriever_enabled is True

    @pytest.mark.asyncio
    async def test_two_instances_get_independent_retrievers(self):
        """Two RAGService instances each get their own NeuralMeshRetriever."""
        from unittest.mock import AsyncMock, patch

        from services.rag_config import RAGConfig
        from services.rag_service import RAGService, register_shared_mesh_components

        register_shared_mesh_components(self._make_components())

        def _make_svc():
            svc = RAGService.__new__(RAGService)
            svc._initialized = False
            svc._cache = {}
            svc._cache_lock = MagicMock()
            svc.config = RAGConfig()
            svc._mesh_retriever = None
            svc.kb_adapter = MagicMock()
            svc.kb_adapter.kb = MagicMock()
            return svc

        svc1, svc2 = _make_svc(), _make_svc()

        call_count = {"n": 0}
        retrievers = []

        def _fake_nmr(**kwargs):
            r = MagicMock(name=f"retriever_{call_count['n']}")
            call_count["n"] += 1
            retrievers.append(r)
            return r

        with (
            patch("services.rag_service.AdvancedRAGOptimizer") as MockOpt,
            patch("services.rag_service.NeuralMeshRetriever", side_effect=_fake_nmr),
        ):
            mock_opt = MagicMock()
            mock_opt.initialize = AsyncMock(return_value=True)
            MockOpt.return_value = mock_opt

            await svc1.initialize()
            await svc2.initialize()

        assert len(retrievers) == 2, "Expected two distinct NeuralMeshRetriever instances"
        assert retrievers[0] is not retrievers[1], "Instances should be independent"
        assert svc1._mesh_retriever is not svc2._mesh_retriever

    @pytest.mark.asyncio
    async def test_already_set_retriever_not_overwritten(self) -> None:
        """An existing _mesh_retriever is NOT replaced even when components are registered."""
        from unittest.mock import AsyncMock, patch

        from services.rag_config import RAGConfig
        from services.rag_service import RAGService, register_shared_mesh_components

        register_shared_mesh_components(self._make_components())

        existing = MagicMock(name="existing_retriever")

        svc = RAGService.__new__(RAGService)
        svc._initialized = False
        svc._cache = {}
        svc._cache_lock = MagicMock()
        svc.config = RAGConfig()
        svc.config.mesh_retriever_enabled = True
        svc._mesh_retriever = existing
        svc.kb_adapter = MagicMock()
        svc.kb_adapter.kb = MagicMock()

        with (
            patch("services.rag_service.AdvancedRAGOptimizer") as MockOpt,
            patch("services.rag_service.NeuralMeshRetriever") as MockNMR,
        ):
            mock_opt = MagicMock()
            mock_opt.initialize = AsyncMock(return_value=True)
            MockOpt.return_value = mock_opt

            await svc.initialize()

        MockNMR.assert_not_called()
        assert svc._mesh_retriever is existing

    @pytest.mark.asyncio
    async def test_no_components_no_retriever_built(self) -> None:
        """If components are not registered, no retriever is built."""
        from unittest.mock import AsyncMock, patch

        from services.rag_config import RAGConfig
        from services.rag_service import RAGService

        # _shared_mesh_components is None (cleared in setup_method)

        svc = RAGService.__new__(RAGService)
        svc._initialized = False
        svc._cache = {}
        svc._cache_lock = MagicMock()
        svc.config = RAGConfig()
        svc._mesh_retriever = None
        svc.kb_adapter = MagicMock()
        svc.kb_adapter.kb = MagicMock()

        with (
            patch("services.rag_service.AdvancedRAGOptimizer") as MockOpt,
            patch("services.rag_service.NeuralMeshRetriever") as MockNMR,
        ):
            mock_opt = MagicMock()
            mock_opt.initialize = AsyncMock(return_value=True)
            MockOpt.return_value = mock_opt

            result = await svc.initialize()

        assert result is True
        MockNMR.assert_not_called()
        assert svc._mesh_retriever is None
        assert svc.config.mesh_retriever_enabled is False
