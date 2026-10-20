# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One graph blend, one config, one rerank-weight set, one stale filter across RAG branches (#18141)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autobot_memory_graph.owner_scope import UNSCOPED_ALL_USERS
from knowledge.search_components.graph_blend import blend_graph_score
from knowledge.search_components.reranking import RerankWeights
from knowledge.search_filters import SYSTEM_SCOPE
from services.graph_rag_service import GraphRAGService
from services.neural_mesh_retriever import MeshRetrievalResult
from services.neural_mesh_retriever_test import _make_retriever
from services.rag_config import RAGConfig
from services.rag_service_mesh_test import _make_service

_GRID = [i / 10 for i in range(11)]


class TestBlendFunction:
    def test_matches_the_graph_rag_formula_where_the_forks_agreed(self) -> None:
        """Old graph-RAG inline: (1-w)*base + w*(base*strength)."""
        for w in (0.0, 0.3, 0.7, 1.0):
            for base in _GRID:
                for strength in _GRID:
                    old = (1.0 - w) * base + w * (base * strength)
                    assert blend_graph_score(base, base * strength, w) == pytest.approx(old)

    def test_stays_in_unit_range_unlike_the_old_additive_mesh_boost(self) -> None:
        assert blend_graph_score(0.9, 0.9, 0.3) <= 1.0
        assert 0.9 + 0.9 > 1.0  # old mesh formula: score + ppr_boost

    def test_weight_is_clamped(self) -> None:
        assert blend_graph_score(0.4, 0.8, 5.0) == 0.8
        assert blend_graph_score(0.4, 0.8, -1.0) == 0.4


class TestOneGraphWeight:
    def test_graph_rag_reads_the_shared_config(self) -> None:
        with patch("services.graph_rag_service.get_rag_config", return_value=RAGConfig(graph_weight=0.55)):
            assert GraphRAGService(rag_service=MagicMock(), memory_graph=MagicMock()).graph_weight == 0.55

    def test_explicit_override_wins(self) -> None:
        assert GraphRAGService(rag_service=MagicMock(), memory_graph=MagicMock(), graph_weight=0.4).graph_weight == 0.4

    def test_mesh_retriever_uses_the_same_blend(self) -> None:
        retriever = _make_retriever()
        retriever.config = RAGConfig(graph_weight=0.3)
        out = retriever._as_dict({"score": 0.5, "metadata": {}}, ppr_boost=0.8)
        assert out["score"] == pytest.approx(blend_graph_score(0.5, 0.8, 0.3))

    def test_config_round_trip_and_validation(self) -> None:
        cfg = RAGConfig(graph_weight=0.2, graph_traversal_depth=3)
        restored = RAGConfig.from_dict(cfg.to_dict())
        assert (restored.graph_weight, restored.graph_traversal_depth) == (0.2, 3)
        with pytest.raises(ValueError):
            RAGConfig(graph_weight=1.5)


class TestMeshRerankWeights:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("tier", ["moderate", "complex"])
    async def test_expanded_tiers_pass_the_config_weights_to_the_reranker(self, tier: str) -> None:
        retriever = _make_retriever(complexity_value=tier)
        weights = RerankWeights(reranker=0.5, vector=0.5, mmr_lambda=0.4)
        retriever.config = RAGConfig(rerank_weights=weights)
        with patch.object(retriever, "_fire_learner"):
            await retriever.retrieve("q", top_k=2)
        assert retriever.reranker.rerank.await_args.kwargs["weights"] is weights


class TestStaleFilterOnEveryBranch:
    @pytest.mark.asyncio
    async def test_mesh_branch_filters_stale_chunks_and_returns_ranked_results(self) -> None:
        svc = _make_service(mesh_retriever_enabled=True)
        dict_chunks = [
            {
                "chunk_id": "a.md",
                "content": "x",
                "score": 0.7,
                "metadata": {"visibility": "system"},
                "source_path": "a.md",
            }
        ]
        svc._mesh_retriever = MagicMock()
        svc._mesh_retriever.retrieve = AsyncMock(return_value=MeshRetrievalResult(dict_chunks, False, "simple"))
        svc._emit_retrieval_feedback = AsyncMock()
        svc._store_feedback_in_stream = AsyncMock()
        svc._filter_stale_chunks = AsyncMock(side_effect=lambda r: r)
        results, _ = await svc._run_mesh_retriever("q", 5, SYSTEM_SCOPE)
        svc._filter_stale_chunks.assert_awaited_once()
        assert results[0].source_path == "a.md"

    @pytest.mark.asyncio
    async def test_vector_branch_filters_stale_chunks(self) -> None:
        svc = _make_service(mesh_retriever_enabled=False)
        svc._filter_stale_chunks = AsyncMock(return_value=[])
        with (
            patch("services.rag_service.RAGService._check_cache_tiers", new_callable=AsyncMock, return_value=None),
            patch("services.rag_service.RAGService.initialize", new_callable=AsyncMock, return_value=True),
            patch("services.rag_service.RAGService._emit_ranked_feedback", new_callable=AsyncMock),
        ):
            await svc.advanced_search("q", principal=SYSTEM_SCOPE)
        svc._filter_stale_chunks.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_fallback_branch_filters_stale_chunks(self) -> None:
        svc = _make_service()
        svc.kb_adapter = MagicMock()
        svc.kb_adapter.search = AsyncMock(return_value=[])
        svc._filter_stale_chunks = AsyncMock(return_value=[])
        await svc._fallback_basic_search("q", 5, principal=SYSTEM_SCOPE)
        svc._filter_stale_chunks.assert_awaited_once()


class TestGraphSearchTimeout:
    """The graph path keeps its 10 s default as a named, env-backed RAGConfig field (#18141)."""

    def test_default_is_ten_seconds_and_general_budget_is_untouched(self, monkeypatch) -> None:
        monkeypatch.delenv("AUTOBOT_RAG_GRAPH_TIMEOUT_SECONDS", raising=False)
        import importlib

        import constants.rag_graph_constants as consts

        importlib.reload(consts)
        assert consts.RAG_GRAPH_TIMEOUT_SECONDS == 10.0
        assert RAGConfig().timeout_seconds != 10.0

    def test_env_overrides_the_default(self, monkeypatch) -> None:
        import importlib

        import constants.rag_graph_constants as consts

        monkeypatch.setenv("AUTOBOT_RAG_GRAPH_TIMEOUT_SECONDS", "25")
        try:
            assert importlib.reload(consts).RAG_GRAPH_TIMEOUT_SECONDS == 25.0
        finally:
            monkeypatch.delenv("AUTOBOT_RAG_GRAPH_TIMEOUT_SECONDS")
            importlib.reload(consts)

    @pytest.mark.asyncio
    async def test_graph_search_applies_the_graph_timeout_when_none_is_given(self) -> None:
        rag = MagicMock()
        rag.advanced_search = AsyncMock(return_value=([], MagicMock()))
        graph = MagicMock(initialized=True)
        svc = GraphRAGService(rag_service=rag, memory_graph=graph, enable_entity_extraction=False)
        with patch("services.graph_rag_service.get_rag_config", return_value=RAGConfig(graph_timeout_seconds=10.0)):
            await svc.graph_aware_search("q", principal=SYSTEM_SCOPE, owner=UNSCOPED_ALL_USERS)
        assert rag.advanced_search.await_args.kwargs["timeout"] == 10.0
        assert rag.advanced_search.await_args.kwargs["principal"] is SYSTEM_SCOPE
        with patch("services.graph_rag_service.get_rag_config", return_value=RAGConfig(graph_timeout_seconds=10.0)):
            await svc.graph_aware_search("q", timeout=3.0, principal=SYSTEM_SCOPE, owner=UNSCOPED_ALL_USERS)
        assert rag.advanced_search.await_args.kwargs["timeout"] == 3.0
