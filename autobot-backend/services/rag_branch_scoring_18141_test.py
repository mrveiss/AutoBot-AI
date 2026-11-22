# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every RAG branch scores, orders and stale-filters a chunk the same way (#18141).

The vector, mesh and KAG branches share one cross-encoder blend (``final_rerank_score``),
the ``RAGConfig.rerank_weights``, one ordering key and ``_filter_stale_chunks``; graph
traversal depth defaults are declared once in ``constants.rag_graph_constants``.
"""

import inspect
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from advanced_rag_optimizer import AdvancedRAGOptimizer, RankedResult
from api.schemas_knowledge import (
    GraphRagMetricsData,
    GraphRAGPathRequest,
    HybridSearchRequest,
    MemoryRelatedRequest,
    TraverseRequest,
)
from autobot_memory_graph.owner_scope import UNSCOPED_ALL_USERS
from constants.rag_graph_constants import (
    RAG_GRAPH_PATH_DEPTH,
    RAG_GRAPH_TRAVERSAL_DEPTH,
    RAG_PPR_MAX_HOPS,
    RAG_RELATION_DEPTH,
)
from knowledge.relations import RelationsMixin
from knowledge.search_components.reranking import RerankWeights, ResultReranker, final_rerank_score
from knowledge.search_filters import SYSTEM_SCOPE
from mcp_server.memory_tools import MemoryToolsMixin
from services.graph_rag_path import GraphPathMixin
from services.graph_rag_service import GraphRAGService
from services.mesh_brain.ppr import PersonalizedPageRank
from services.rag_config import RAGConfig
from services.rag_service_mesh_test import _make_service

_WEIGHTS = RerankWeights(reranker=0.6, vector=0.2, staleness=0.2)


def _ranked(content: str, hybrid: float, rerank: float | None = None, **metadata) -> RankedResult:
    result = RankedResult(
        content=content,
        metadata=metadata,
        semantic_score=hybrid,
        keyword_score=0.0,
        hybrid_score=hybrid,
        relevance_rank=0,
        source_path=f"{content}.md",
    )
    result.rerank_score = rerank
    return result


async def _vector_branch_score(staleness: dict) -> tuple[float, AsyncMock]:
    optimizer = AdvancedRAGOptimizer(rerank_weights=_WEIGHTS)
    optimizer._cross_encoder = MagicMock()
    optimizer._cross_encoder.predict.return_value = [1.0]
    result = _ranked("x", 0.4, chunk_id="c1", source_provenance="extracted")
    fetch = AsyncMock(return_value=staleness)
    with patch("advanced_rag_optimizer.fetch_staleness_scores", fetch):
        await optimizer._apply_cross_encoder_scores("q", [result])
    return result.rerank_score, fetch


class TestOneCrossEncoderBlend:
    @pytest.mark.asyncio
    async def test_vector_and_mesh_branches_score_a_chunk_identically(self) -> None:
        vector_score, fetch = await _vector_branch_score({"c1": 0.5})
        mesh = [{"chunk_id": "c1", "score": 0.4, "content": "x", "metadata": {"source_provenance": "extracted"}}]
        ResultReranker()._apply_rerank_scores(mesh, [1.0], weights=_WEIGHTS, staleness_map={"c1": 0.5})
        assert vector_score == pytest.approx(mesh[0]["rerank_score"])
        assert vector_score == pytest.approx(final_rerank_score(1.0, 0.4, _WEIGHTS, 0.5, "extracted"))
        assert fetch.await_args.args == (["c1"], _WEIGHTS)

    @pytest.mark.asyncio
    async def test_vector_branch_now_applies_the_staleness_penalty(self) -> None:
        fresh, _ = await _vector_branch_score({})
        stale, _ = await _vector_branch_score({"c1": 1.0})
        assert stale == pytest.approx(fresh - 0.2)  # weights.staleness * (1.0 - 0.0) of the total 1.0


class TestRerankWeightsOnEveryBranch:
    @pytest.mark.asyncio
    async def test_reranker_without_weights_uses_the_shared_config(self) -> None:
        """The KB-search reranker passed none and blended at a fixed 0.8/0.2 with MMR off."""
        reranker = ResultReranker()
        reranker._cross_encoder = MagicMock()
        reranker._cross_encoder.predict.return_value = [0.0]
        shared = RAGConfig(rerank_weights=RerankWeights(reranker=0.5, vector=0.5))
        results = [{"chunk_id": "c1", "score": 0.4, "content": "x"}]
        with (
            patch.dict(sys.modules, {"sentence_transformers": MagicMock()}),
            patch("services.rag_config.get_rag_config", return_value=shared),
        ):
            await reranker.rerank("q", results)
        assert results[0]["rerank_score"] == pytest.approx((0.5 * 0.5 + 0.5 * 0.4) / 1.0)

    @pytest.mark.asyncio
    async def test_kag_orders_by_the_reranked_score_not_the_pre_rerank_one(self) -> None:
        svc = GraphRAGService(rag_service=MagicMock(), memory_graph=MagicMock(), graph_weight=0.3)
        vector_top = _ranked("a", hybrid=0.9, rerank=0.2)
        rerank_top = _ranked("b", hybrid=0.5, rerank=0.8)
        graph_entity = _ranked("c", hybrid=0.6)
        ranked = await svc._deduplicate_and_rank([vector_top, rerank_top, graph_entity], 3)
        assert [r.content for r in ranked] == ["b", "c", "a"]


class TestKagBranchStaleFilter:
    @pytest.mark.asyncio
    async def test_kag_kb_leg_passes_the_stale_filter(self) -> None:
        rag = _make_service(mesh_retriever_enabled=False)
        rag._filter_stale_chunks = AsyncMock(return_value=[])
        svc = GraphRAGService(rag_service=rag, memory_graph=MagicMock(initialized=True), enable_entity_extraction=False)
        with (
            patch("services.rag_service.RAGService._check_cache_tiers", new_callable=AsyncMock, return_value=None),
            patch("services.rag_service.RAGService.initialize", new_callable=AsyncMock, return_value=True),
            patch("services.rag_service.RAGService._emit_ranked_feedback", new_callable=AsyncMock),
        ):
            await svc.graph_aware_search("q", principal=SYSTEM_SCOPE, owner=UNSCOPED_ALL_USERS)
        rag._filter_stale_chunks.assert_awaited_once()


class TestTraversalDepthDeclaredOnce:
    @pytest.mark.asyncio
    async def test_kag_without_a_depth_reads_rag_config(self) -> None:
        rag = MagicMock()
        rag.advanced_search = AsyncMock(return_value=([], MagicMock()))
        svc = GraphRAGService(rag_service=rag, memory_graph=MagicMock(initialized=True))
        svc._extract_and_expand_graph = AsyncMock(return_value=[])
        with patch("services.graph_rag_service.get_rag_config", return_value=RAGConfig(graph_traversal_depth=3)):
            await svc.graph_aware_search("q", principal=SYSTEM_SCOPE, owner=UNSCOPED_ALL_USERS)
        assert svc._extract_and_expand_graph.await_args.args[3] == 3

    def test_schema_defaults_reference_the_constants(self) -> None:
        assert TraverseRequest(start_fact_id="f").max_depth == RAG_GRAPH_TRAVERSAL_DEPTH
        assert MemoryRelatedRequest(entity="e").depth == RAG_GRAPH_TRAVERSAL_DEPTH
        assert GraphRAGPathRequest(from_entity="a", to_entity="b").max_depth == RAG_GRAPH_PATH_DEPTH
        assert HybridSearchRequest(query="q").relation_depth == RAG_RELATION_DEPTH
        assert GraphRagMetricsData.model_fields["graph_weight"].is_required()

    @pytest.mark.parametrize(
        ("func", "param", "expected"),
        [
            (RelationsMixin.traverse_relations, "max_depth", RAG_GRAPH_TRAVERSAL_DEPTH),
            (RelationsMixin.hybrid_search, "relation_depth", RAG_RELATION_DEPTH),
            (MemoryToolsMixin._memory_related, "depth", RAG_GRAPH_TRAVERSAL_DEPTH),
            (MemoryToolsMixin._memory_path, "max_depth", RAG_GRAPH_PATH_DEPTH),
            (GraphPathMixin.find_connection_path, "max_depth", RAG_GRAPH_PATH_DEPTH),
            (PersonalizedPageRank.rank, "max_hops", RAG_PPR_MAX_HOPS),
        ],
    )
    def test_service_defaults_reference_the_constants(self, func, param, expected) -> None:
        assert inspect.signature(inspect.unwrap(func)).parameters[param].default == expected
