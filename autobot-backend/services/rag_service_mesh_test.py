#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for Neural Mesh RAG feature flags and RAGService mesh path (#2059)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# =============================================================================
# Helpers
# =============================================================================


def _make_service(mesh_retriever_enabled: bool = False):
    """Build a RAGService with a stub config; no Redis or ChromaDB connections."""
    from services.rag_config import RAGConfig
    from services.rag_service import RAGService

    svc = RAGService.__new__(RAGService)
    svc._initialized = True
    cfg = RAGConfig()
    cfg.enable_advanced_rag = True
    cfg.mesh_retriever_enabled = mesh_retriever_enabled
    svc.config = cfg
    svc._mesh_retriever = None
    return svc


def _make_mesh_result(chunk_ids):
    """Return a mock MeshRetrievalResult whose .chunks list uses chunk_id metadata."""
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
# Test: flag disabled — legacy optimizer path is taken
# =============================================================================


class TestMeshFlagDisabledUsesLegacyPath:
    """When mesh_retriever_enabled=False, advanced_search uses the legacy optimizer."""

    @pytest.mark.asyncio
    async def test_mesh_flag_disabled_uses_legacy_path(self):
        """optimizer.advanced_search is invoked when mesh flag is False."""
        from advanced_rag_optimizer import RAGMetrics

        svc = _make_service(mesh_retriever_enabled=False)

        with patch(
            "services.rag_service.RAGService._check_cache_tiers",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "services.rag_service.RAGService.initialize",
            new_callable=AsyncMock,
            return_value=True,
        ), patch(
            "services.rag_service.RAGService._execute_and_cache_search",
            new_callable=AsyncMock,
            return_value=([], RAGMetrics()),
        ) as mock_exec, patch(
            "services.rag_service.RAGService._store_in_semantic_cache",
            new_callable=AsyncMock,
        ), patch(
            "services.rag_service.RAGService._store_in_topic_cache",
            new_callable=AsyncMock,
        ), patch(
            "services.rag_service.RAGService._emit_retrieval_feedback",
            new_callable=AsyncMock,
        ), patch(
            "services.rag_service.RAGService._store_feedback_in_stream",
            new_callable=AsyncMock,
        ):
            await svc.advanced_search(query="test query")

        mock_exec.assert_called_once()


# =============================================================================
# Test: flag enabled + retriever set — mesh path is taken
# =============================================================================


class TestMeshFlagEnabledUsesMeshRetriever:
    """When mesh_retriever_enabled=True and _mesh_retriever is set, mesh path runs."""

    @pytest.mark.asyncio
    async def test_mesh_flag_enabled_uses_mesh_retriever(self):
        """_mesh_retriever.retrieve() is called when flag is True and retriever is set."""
        svc = _make_service(mesh_retriever_enabled=True)
        mesh_result = _make_mesh_result(["c1", "c2"])
        svc._mesh_retriever = AsyncMock()
        svc._mesh_retriever.retrieve = AsyncMock(return_value=mesh_result)

        with patch(
            "services.rag_service.RAGService._check_cache_tiers",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "services.rag_service.RAGService._emit_retrieval_feedback",
            new_callable=AsyncMock,
        ), patch(
            "services.rag_service.RAGService._store_feedback_in_stream",
            new_callable=AsyncMock,
        ):
            results, metrics = await svc.advanced_search(
                query="mesh query", max_results=2
            )

        svc._mesh_retriever.retrieve.assert_called_once_with("mesh query", 2)
        assert len(results) == 2
        assert metrics.final_results_count == 2

    @pytest.mark.asyncio
    async def test_mesh_path_emits_feedback_events(self):
        """Mesh path calls _emit_retrieval_feedback and _store_feedback_in_stream."""
        svc = _make_service(mesh_retriever_enabled=True)
        mesh_result = _make_mesh_result(["c1"])
        svc._mesh_retriever = AsyncMock()
        svc._mesh_retriever.retrieve = AsyncMock(return_value=mesh_result)

        with patch(
            "services.rag_service.RAGService._check_cache_tiers",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "services.rag_service.RAGService._emit_retrieval_feedback",
            new_callable=AsyncMock,
        ) as mock_emit, patch(
            "services.rag_service.RAGService._store_feedback_in_stream",
            new_callable=AsyncMock,
        ) as mock_store:
            await svc.advanced_search(query="q")

        mock_emit.assert_called_once()
        mock_store.assert_called_once()


# =============================================================================
# Test: flag enabled but retriever is None — falls back to legacy path
# =============================================================================


class TestMeshFlagEnabledButNoRetrieverFallsBack:
    """When mesh_retriever_enabled=True but _mesh_retriever is None, legacy path runs."""

    @pytest.mark.asyncio
    async def test_mesh_flag_enabled_but_no_retriever_falls_back(self):
        """_execute_and_cache_search is invoked when _mesh_retriever is None."""
        from advanced_rag_optimizer import RAGMetrics

        svc = _make_service(mesh_retriever_enabled=True)
        # _mesh_retriever stays None (set by _make_service)

        with patch(
            "services.rag_service.RAGService._check_cache_tiers",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "services.rag_service.RAGService.initialize",
            new_callable=AsyncMock,
            return_value=True,
        ), patch(
            "services.rag_service.RAGService._execute_and_cache_search",
            new_callable=AsyncMock,
            return_value=([], RAGMetrics()),
        ) as mock_exec, patch(
            "services.rag_service.RAGService._store_in_semantic_cache",
            new_callable=AsyncMock,
        ), patch(
            "services.rag_service.RAGService._store_in_topic_cache",
            new_callable=AsyncMock,
        ), patch(
            "services.rag_service.RAGService._emit_retrieval_feedback",
            new_callable=AsyncMock,
        ), patch(
            "services.rag_service.RAGService._store_feedback_in_stream",
            new_callable=AsyncMock,
        ):
            await svc.advanced_search(query="test")

        mock_exec.assert_called_once()


# =============================================================================
# Test: default values for all 6 mesh flags
# =============================================================================


class TestMeshFeatureFlagsDefaultValues:
    """All six mesh feature flags must have the correct defaults."""

    def test_mesh_feature_flags_default_values(self):
        """Verify all six mesh flags have correct defaults from RAGConfig()."""
        from services.rag_config import RAGConfig

        cfg = RAGConfig()
        assert cfg.mesh_retriever_enabled is False
        assert cfg.mesh_seed_edges is True
        assert cfg.mesh_edge_learner is False
        assert cfg.mesh_edge_discoverer is False
        assert cfg.mesh_pruner is False
        assert cfg.mesh_node_promoter is False


# =============================================================================
# Test: to_dict() includes all mesh flags
# =============================================================================


class TestRAGConfigSerializationIncludesMeshFlags:
    """RAGConfig.to_dict() must expose all six mesh flags for YAML round-trips."""

    def test_rag_config_serialization_includes_mesh_flags(self):
        """to_dict() contains all six mesh flag keys with correct default values."""
        from services.rag_config import RAGConfig

        d = RAGConfig().to_dict()
        assert d["mesh_retriever_enabled"] is False
        assert d["mesh_seed_edges"] is True
        assert d["mesh_edge_learner"] is False
        assert d["mesh_edge_discoverer"] is False
        assert d["mesh_pruner"] is False
        assert d["mesh_node_promoter"] is False

    def test_from_dict_round_trips_mesh_flags(self):
        """from_dict(to_dict()) preserves non-default mesh flag values."""
        from services.rag_config import RAGConfig

        original = RAGConfig()
        original.mesh_retriever_enabled = True
        original.mesh_edge_learner = True
        d = original.to_dict()

        restored = RAGConfig.from_dict(d)
        assert restored.mesh_retriever_enabled is True
        assert restored.mesh_edge_learner is True
        # Unmodified flags stay at defaults
        assert restored.mesh_seed_edges is True
        assert restored.mesh_edge_discoverer is False
