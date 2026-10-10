# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One score blend, one config, one MMR/stale pass across the retrieval branches (#18141).

Default-path ranking must not move: the fixtures below pin the order (and the exact scores)
the pre-#18141 formulas produced, and assert the shared code reproduces them.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from advanced_rag_optimizer import RankedResult
from knowledge.search_components.ranked_diversity import diversify_ranked_results
from knowledge.search_components.reranking import RerankWeights, apply_mmr_reorder_by_content
from services.graph_rag_service import GraphRAGService
from services.neural_mesh_retriever import NeuralMeshRetriever, to_ranked_results
from services.rag_config import RAGConfig

#: (base score, relationship strength) candidates, deliberately not already in score order.
_GRAPH_CANDIDATES = [(0.9, 0.2), (0.5, 1.0), (0.7, 0.9), (0.95, 0.0), (0.3, 1.0), (0.7, 0.4)]


def _legacy_graph_score(base: float, strength: float, w: float = 0.3) -> float:
    """The formula graph_rag_service.py inlined before #18141, copied verbatim."""
    proximity_score = base * strength
    return (1.0 - w) * base + w * proximity_score


def _graph_service(**kw) -> GraphRAGService:
    rag = MagicMock()
    rag.config = RAGConfig()
    return GraphRAGService(rag, AsyncMock(), **kw)


def _scored(svc: GraphRAGService) -> list[float]:
    out = []
    for base, strength in _GRAPH_CANDIDATES:
        entity = {"id": "e", "type": "t", "name": "n", "observations": ["x"]}
        relation = {"type": "r", "metadata": {"strength": strength}}
        out.append(svc._create_search_result_from_entity(entity, relation, "outgoing", base, 2).hybrid_score)
    return out


def test_graph_rag_scores_and_order_are_unchanged_by_the_shared_blend() -> None:
    expected = [_legacy_graph_score(b, s) for b, s in _GRAPH_CANDIDATES]
    actual = _scored(_graph_service())
    assert actual == expected
    order = lambda xs: sorted(range(len(xs)), key=lambda i: -xs[i])  # noqa: E731
    assert order(actual) == order(expected)


def test_graph_weight_comes_from_rag_config_and_an_override_wins() -> None:
    assert RAGConfig().graph_weight == 0.3
    assert _graph_service().graph_weight == 0.3
    svc = _graph_service(graph_weight=0.6)
    assert svc.graph_weight == 0.6
    assert _scored(svc) == [_legacy_graph_score(b, s, 0.6) for b, s in _GRAPH_CANDIDATES]


def test_rag_service_config_graph_weight_reaches_graph_rag() -> None:
    rag = MagicMock()
    rag.config = RAGConfig(graph_weight=0.45)
    assert GraphRAGService(rag, AsyncMock()).graph_weight == 0.45


def test_graph_weight_outside_unit_interval_is_rejected() -> None:
    with pytest.raises(ValueError, match="graph_weight"):
        RAGConfig(graph_weight=1.5)


def test_off_by_default_flags_are_untouched() -> None:
    cfg = RAGConfig()
    assert cfg.mesh_retriever_enabled is False
    assert cfg.enable_kag is False


# --- mesh path: same blend, same rerank weights, same MMR, same stale filter -------------


def _retriever(weights: RerankWeights | None, w: float) -> NeuralMeshRetriever:
    classifier = MagicMock()
    classifier.classify.return_value = MagicMock(value="moderate")
    ppr = AsyncMock()
    ppr.rank = AsyncMock(return_value=[("a", 0.5), ("b", 0.4)])
    reranker = AsyncMock()
    reranker.rerank = AsyncMock(side_effect=lambda q, merged, top_k=None, weights=None: merged)
    seeds = [{"metadata": {"chunk_id": "a"}, "score": 0.6, "content": "alpha"}]
    return NeuralMeshRetriever(
        chroma_search=AsyncMock(return_value=seeds),
        hybrid_search=AsyncMock(return_value=seeds),
        ppr=ppr,
        edge_learner=AsyncMock(),
        reranker=reranker,
        classifier=classifier,
        mesh_db=AsyncMock(),
        rerank_weights=weights,
        graph_weight=w,
    )


@pytest.mark.asyncio
async def test_mesh_reranker_receives_the_configured_weights() -> None:
    weights = RerankWeights(reranker=0.5, vector=0.5, mmr_lambda=0.4)
    retriever = _retriever(weights, 0.3)
    with patch.object(retriever, "_fire_learner"):
        await retriever.retrieve("q", top_k=3)
    assert retriever.reranker.rerank.await_args.kwargs["weights"] is weights


@pytest.mark.asyncio
async def test_mesh_seed_score_uses_the_shared_graph_blend() -> None:
    retriever = _retriever(None, 0.3)
    with patch.object(retriever, "_fire_learner"):
        await retriever.retrieve("q", top_k=3)
    merged = retriever.reranker.rerank.await_args.args[1]
    seed = next(m for m in merged if m.get("metadata", {}).get("chunk_id") == "a")
    assert seed["score"] == pytest.approx(0.7 * 0.6 + 0.3 * (0.6 + 0.5))
    expanded_only = next(m for m in merged if m.get("chunk_id") == "b")
    assert expanded_only["score"] == 0.4  # no vector score: its graph score is its base


def test_a_mesh_seed_with_no_expansion_keeps_its_score_exactly() -> None:
    assert NeuralMeshRetriever._as_dict({"score": 0.37}, 0.0, 0.3)["score"] == 0.37


def _near_duplicates() -> list[dict]:
    text = "redis connection pool timeout configuration"
    return [
        {"chunk_id": "a", "content": text, "score": 0.9, "source_path": "a.md"},
        {"chunk_id": "b", "content": text, "score": 0.89, "source_path": "b.md"},
        {"chunk_id": "c", "content": "unrelated kubernetes ingress notes", "score": 0.7, "source_path": "c.md"},
    ]


def test_mesh_results_get_the_optimizers_mmr_ordering() -> None:
    ranked = to_ranked_results(_near_duplicates(), 0.5)
    expected = apply_mmr_reorder_by_content(
        to_ranked_results(_near_duplicates(), 0.0),
        0.5,
        content_getter=lambda r: r.content,
        score_getter=lambda r: r.rerank_score or 0.0,
    )
    assert [r.source_path for r in ranked] == [r.source_path for r in expected] == ["a.md", "c.md", "b.md"]
    assert [r.relevance_rank for r in ranked] == [1, 2, 3]


def test_mmr_off_leaves_the_order_alone() -> None:
    assert [r.source_path for r in to_ranked_results(_near_duplicates(), 0.0)] == ["a.md", "b.md", "c.md"]


def test_optimizer_and_mesh_share_one_mmr_function() -> None:
    items = to_ranked_results(_near_duplicates(), 0.0)
    assert [r.source_path for r in diversify_ranked_results(list(items), 0.5)] == ["a.md", "c.md", "b.md"]


@pytest.mark.asyncio
async def test_mesh_branch_runs_the_stale_filter_on_ranked_results() -> None:
    from services.rag_service import RAGService

    svc = RAGService.__new__(RAGService)
    svc.config = RAGConfig(mmr_lambda=0.5)
    svc._mesh_retriever = MagicMock()
    svc._mesh_retriever.retrieve = AsyncMock(return_value=MagicMock(chunks=_near_duplicates()))
    svc._emit_retrieval_feedback = AsyncMock()
    svc._store_feedback_in_stream = AsyncMock()
    seen: list[list[RankedResult]] = []

    async def _drop_b(results):
        seen.append(list(results))
        return [r for r in results if r.source_path != "b.md"]

    svc._filter_stale_chunks = _drop_b
    results, _ = await svc._run_mesh_retriever("q", 5)
    assert [r.source_path for r in seen[0]] == ["a.md", "c.md", "b.md"]  # MMR ran first
    assert [r.source_path for r in results] == ["a.md", "c.md"]  # then the stale filter
    assert all(isinstance(r, RankedResult) for r in results)


@pytest.mark.asyncio
async def test_vector_branch_runs_the_stale_filter() -> None:
    from advanced_rag_optimizer import RAGMetrics
    from services.rag_service import RAGService

    svc = RAGService.__new__(RAGService)
    svc.config = RAGConfig()
    svc._mesh_retriever = None
    svc._initialized = True
    stale = AsyncMock(side_effect=lambda r: r)
    svc._filter_stale_chunks = stale
    svc._check_cache_tiers = AsyncMock(return_value=None)
    svc.initialize = AsyncMock(return_value=True)
    svc._lookup_retrieval_pattern = AsyncMock(return_value=None)
    svc._execute_and_cache_search = AsyncMock(return_value=([], RAGMetrics()))
    for name in (
        "_store_in_semantic_cache",
        "_store_in_topic_cache",
        "_emit_ranked_feedback",
        "_record_retrieval_outcome",
    ):
        setattr(svc, name, AsyncMock())
    svc.optimizer = None
    await svc.advanced_search("q", categories=["x"])
    stale.assert_awaited_once()


@pytest.mark.asyncio
async def test_kag_branch_rides_the_shared_search_and_stale_filtered_rag_results() -> None:
    """graph_aware_search takes its candidates from RAGService.advanced_search (the filtered path)."""
    rag = MagicMock()
    rag.config = RAGConfig()
    rag.advanced_search = AsyncMock(return_value=([], MagicMock(total_time=0.0)))
    graph = AsyncMock()
    graph.initialized = True
    svc = GraphRAGService(rag, graph, enable_entity_extraction=False)
    await svc.graph_aware_search("q")
    rag.advanced_search.assert_awaited_once()


# --- graph-RAG keeps its own 10 s budget, as one named setting ---------------------------


def _timeout_service(rag_config: RAGConfig | None = None):
    rag = MagicMock()
    rag.config = rag_config or RAGConfig()
    rag.advanced_search = AsyncMock(return_value=([], MagicMock(total_time=0.0)))
    graph = AsyncMock()
    graph.initialized = True
    return rag, GraphRAGService(rag, graph, enable_entity_extraction=False)


@pytest.mark.asyncio
async def test_graph_rag_search_budget_is_ten_seconds_by_default() -> None:
    rag, svc = _timeout_service()
    await svc.graph_aware_search("q")
    assert rag.advanced_search.await_args.kwargs["timeout"] == 10.0
    assert RAGConfig().timeout_seconds != 10.0  # the general RAG budget is untouched


@pytest.mark.asyncio
async def test_graph_rag_budget_follows_config_and_an_explicit_timeout_wins() -> None:
    rag, svc = _timeout_service(RAGConfig(graph_rag_timeout_seconds=25.0))
    await svc.graph_aware_search("q")
    assert rag.advanced_search.await_args.kwargs["timeout"] == 25.0
    await svc.graph_aware_search("q", timeout=3.0)
    assert rag.advanced_search.await_args.kwargs["timeout"] == 3.0


def test_graph_rag_budget_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib

    import autobot_shared.graph_retrieval as gr

    monkeypatch.setenv("AUTOBOT_GRAPH_RAG_TIMEOUT_SECONDS", "42")
    try:
        assert importlib.reload(gr).GRAPH_RAG_TIMEOUT_SECONDS == 42.0
    finally:
        monkeypatch.delenv("AUTOBOT_GRAPH_RAG_TIMEOUT_SECONDS")
        assert importlib.reload(gr).GRAPH_RAG_TIMEOUT_SECONDS == 10.0


def test_mesh_seed_blend_is_pinned_at_the_default_weight() -> None:
    from autobot_shared.graph_retrieval import GRAPH_WEIGHT_DEFAULT, blend_graph_score

    s, p = 0.6, 0.5
    out = NeuralMeshRetriever._as_dict({"score": s}, p, GRAPH_WEIGHT_DEFAULT)["score"]
    assert out == blend_graph_score(s, s + p, GRAPH_WEIGHT_DEFAULT)
    assert out == pytest.approx(0.7 * 0.6 + 0.3 * 1.1)
