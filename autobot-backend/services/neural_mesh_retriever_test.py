# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for NeuralMeshRetriever (#1994, #2058).

All external dependencies are replaced with AsyncMock / MagicMock so the
tests run without a database, Redis, or model server.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.neural_mesh_retriever import MeshRetrievalResult, NeuralMeshRetriever

# =============================================================================
# Factories
# =============================================================================


def _make_result(chunk_id: str, score: float = 0.5) -> dict:
    """Return a minimal result dict used as a stand-in for a SearchResult."""
    return {"metadata": {"chunk_id": chunk_id}, "score": score, "content": "text"}


def _make_complexity_mock(value: str):
    """Return a MagicMock whose .value attribute equals *value*."""
    mock = MagicMock()
    mock.value = value
    return mock


def _make_retriever(
    complexity_value: str = "simple",
    chroma_results: list | None = None,
    hybrid_results: list | None = None,
    ppr_results: list | None = None,
    rerank_results: list | None = None,
    anchor_results: list | None = None,
) -> NeuralMeshRetriever:
    """Construct a NeuralMeshRetriever with controllable mock dependencies.

    Returns the retriever pre-configured for the given complexity tier.
    """
    chroma_results = chroma_results or [_make_result("c1"), _make_result("c2")]
    hybrid_results = hybrid_results or [_make_result("h1"), _make_result("h2")]
    ppr_results = ppr_results or [("h1", 0.8), ("h2", 0.6)]
    rerank_results = rerank_results or hybrid_results[:1]
    anchor_results = anchor_results or []

    classifier = MagicMock()
    classifier.classify.return_value = _make_complexity_mock(complexity_value)

    ppr = AsyncMock()
    ppr.rank = AsyncMock(return_value=ppr_results)

    edge_learner = AsyncMock()
    edge_learner.on_retrieval = AsyncMock()

    reranker = AsyncMock()
    reranker.rerank = AsyncMock(return_value=rerank_results)

    mesh_db = AsyncMock()
    mesh_db.get_anchor_neighbors = AsyncMock(return_value=anchor_results)

    return NeuralMeshRetriever(
        chroma_search=AsyncMock(return_value=chroma_results),
        hybrid_search=AsyncMock(return_value=hybrid_results),
        ppr=ppr,
        edge_learner=edge_learner,
        reranker=reranker,
        classifier=classifier,
        mesh_db=mesh_db,
    )


# =============================================================================
# Route selection
# =============================================================================


class TestRouting:
    """retrieve() dispatches to the correct path based on complexity."""

    @pytest.mark.asyncio
    async def test_simple_query_skips_ppr(self) -> None:
        """SIMPLE complexity must not call ppr.rank."""
        retriever = _make_retriever(complexity_value="simple")

        result = await retriever.retrieve("what is redis", top_k=3)

        retriever.ppr.rank.assert_not_called()
        assert isinstance(result, MeshRetrievalResult)
        assert result.complexity == "simple"
        assert result.expanded is False

    @pytest.mark.asyncio
    async def test_moderate_query_uses_ppr_expansion(self) -> None:
        """MODERATE complexity must call ppr.rank with seed IDs."""
        retriever = _make_retriever(complexity_value="moderate")

        result = await retriever.retrieve("how does redis relate to caching", top_k=3)

        retriever.ppr.rank.assert_called_once()
        call_args = retriever.ppr.rank.call_args
        seed_ids_arg = call_args.args[0] if call_args.args else call_args.kwargs.get("seed_node_ids", [])
        assert len(seed_ids_arg) > 0
        assert result.expanded is True
        assert result.complexity == "moderate"

    @pytest.mark.asyncio
    async def test_complex_query_checks_anchors(self) -> None:
        """COMPLEX complexity must call mesh_db.get_anchor_neighbors."""
        retriever = _make_retriever(complexity_value="complex")

        await retriever.retrieve("compare redis vs memcached advantages", top_k=3)

        retriever.mesh_db.get_anchor_neighbors.assert_called_once()

    @pytest.mark.asyncio
    async def test_multi_hop_uses_full_pipeline(self) -> None:
        """MULTI_HOP complexity routes through _full_retrieve (same as complex)."""
        retriever = _make_retriever(complexity_value="multi_hop")

        result = await retriever.retrieve("trace the chain of events that led to failure", top_k=3)

        retriever.mesh_db.get_anchor_neighbors.assert_called_once()
        assert result.expanded is True


# =============================================================================
# EdgeLearner integration
# =============================================================================


class TestFireLearner:
    """_fire_learner schedules on_retrieval for every retrieval path."""

    @pytest.mark.asyncio
    async def test_fire_learner_called_after_simple_retrieval(self) -> None:
        """EdgeLearner.on_retrieval is scheduled after a SIMPLE retrieval."""
        retriever = _make_retriever(complexity_value="simple")

        with patch("asyncio.create_task") as mock_create_task:
            await retriever.retrieve("what is redis", top_k=3)

        mock_create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_fire_learner_called_after_retrieval(self) -> None:
        """on_retrieval is awaited with final_ranked_ids from ranked results."""
        retriever = _make_retriever(
            complexity_value="simple",
            chroma_results=[_make_result("id_alpha"), _make_result("id_beta")],
        )

        with patch("asyncio.create_task") as mock_create_task:
            await retriever.retrieve("query text", top_k=2)
            # Manually run the coroutine that was scheduled
            coro = mock_create_task.call_args.args[0]
            await coro

        retriever.edge_learner.on_retrieval.assert_called_once()
        event = retriever.edge_learner.on_retrieval.call_args.args[0]
        assert "final_ranked_ids" in event
        assert "id_alpha" in event["final_ranked_ids"]
        assert "timestamp" in event


# =============================================================================
# _chunk_id extraction
# =============================================================================


class TestChunkId:
    """_chunk_id extracts the correct ID from dict and object results."""

    def test_chunk_id_extracts_from_dict_with_metadata(self) -> None:
        """Dict with metadata.chunk_id returns that chunk_id."""
        retriever = _make_retriever()
        result = {"metadata": {"chunk_id": "abc-123"}, "score": 0.9}
        assert retriever._chunk_id(result) == "abc-123"

    def test_chunk_id_extracts_from_dict_with_top_level_chunk_id(self) -> None:
        """Dict with top-level chunk_id (no metadata) returns that ID."""
        retriever = _make_retriever()
        result = {"chunk_id": "top-level-id", "score": 0.7}
        assert retriever._chunk_id(result) == "top-level-id"

    def test_chunk_id_extracts_from_dict_source_path_fallback(self) -> None:
        """Dict with only source_path falls back to source_path."""
        retriever = _make_retriever()
        result = {"source_path": "/docs/file.md", "score": 0.5}
        assert retriever._chunk_id(result) == "/docs/file.md"

    def test_chunk_id_extracts_from_search_result_object(self) -> None:
        """Object with metadata.chunk_id attribute returns that chunk_id."""
        retriever = _make_retriever()

        class SearchResult:
            metadata = {"chunk_id": "obj-456"}
            source_path = "/some/path"
            score = 0.8

        assert retriever._chunk_id(SearchResult()) == "obj-456"

    def test_chunk_id_falls_back_to_source_path_on_object(self) -> None:
        """Object without metadata.chunk_id falls back to source_path."""
        retriever = _make_retriever()

        class SearchResult:
            metadata = {}
            source_path = "/fallback/path.md"
            score = 0.6

        assert retriever._chunk_id(SearchResult()) == "/fallback/path.md"

    def test_chunk_id_returns_empty_string_for_empty_dict(self) -> None:
        """Empty dict returns empty string without raising."""
        retriever = _make_retriever()
        assert retriever._chunk_id({}) == ""


# =============================================================================
# _merge_with_expansion
# =============================================================================


class TestMergeWithExpansion:
    """_merge_with_expansion combines seeds with PPR-scored expansion nodes."""

    def test_merge_keeps_seed_results(self) -> None:
        """All seed results must be present in the merged output."""
        retriever = _make_retriever()
        seeds = [_make_result("s1"), _make_result("s2")]
        expanded_scores = [("s1", 0.9), ("s2", 0.7)]

        merged = retriever._merge_with_expansion(seeds, expanded_scores)

        chunk_ids = {r.get("metadata", {}).get("chunk_id") or r.get("chunk_id") for r in merged}
        assert "s1" in chunk_ids
        assert "s2" in chunk_ids

    def test_merge_appends_expanded_nodes_not_in_seeds(self) -> None:
        """Nodes returned by PPR but absent from seeds are appended."""
        retriever = _make_retriever()
        seeds = [_make_result("s1")]
        expanded_scores = [("s1", 0.8), ("new_node", 0.4)]

        merged = retriever._merge_with_expansion(seeds, expanded_scores)

        merged_ids = {r.get("metadata", {}).get("chunk_id") or r.get("chunk_id") for r in merged}
        assert "new_node" in merged_ids

    def test_merge_boosts_seed_score_with_ppr(self) -> None:
        """Seed results receive their PPR score added to the base score."""
        retriever = _make_retriever()
        seeds = [{"metadata": {"chunk_id": "s1"}, "score": 0.3, "content": "x"}]
        expanded_scores = [("s1", 0.5)]

        merged = retriever._merge_with_expansion(seeds, expanded_scores)

        s1_result = next(r for r in merged if r.get("metadata", {}).get("chunk_id") == "s1")
        assert abs(s1_result["score"] - 0.8) < 1e-9

    def test_merge_with_empty_expansion(self) -> None:
        """Empty expanded_scores returns only seed results unchanged."""
        retriever = _make_retriever()
        seeds = [_make_result("s1")]

        merged = retriever._merge_with_expansion(seeds, [])

        assert len(merged) == 1

    def test_merge_deduplicates_expanded_ids(self) -> None:
        """A node already in seeds must not appear twice in merged output."""
        retriever = _make_retriever()
        seeds = [_make_result("shared")]
        expanded_scores = [("shared", 0.9), ("extra", 0.4)]

        merged = retriever._merge_with_expansion(seeds, expanded_scores)

        chunk_ids = [r.get("metadata", {}).get("chunk_id") or r.get("chunk_id") for r in merged]
        assert chunk_ids.count("shared") == 1


# =============================================================================
# Anchor injection
# =============================================================================


class TestAnchorInjection:
    """anchor_used flag and seed expansion when anchors are found."""

    @pytest.mark.asyncio
    async def test_anchor_used_true_when_anchors_found(self) -> None:
        """anchor_used is True when mesh_db returns non-empty anchor list."""
        retriever = _make_retriever(
            complexity_value="complex",
            anchor_results=["anchor-node-1"],
        )

        result = await retriever.retrieve("compare A vs B", top_k=3)

        assert result.anchor_used is True

    @pytest.mark.asyncio
    async def test_anchor_used_false_when_no_anchors(self) -> None:
        """anchor_used is False when mesh_db returns an empty list."""
        retriever = _make_retriever(
            complexity_value="complex",
            anchor_results=[],
        )

        result = await retriever.retrieve("compare A vs B", top_k=3)

        assert result.anchor_used is False

    @pytest.mark.asyncio
    async def test_anchor_failure_is_gracefully_handled(self) -> None:
        """If mesh_db.get_anchor_neighbors raises, retrieval still completes."""
        retriever = _make_retriever(complexity_value="complex")
        retriever.mesh_db.get_anchor_neighbors = AsyncMock(side_effect=RuntimeError("db error"))

        result = await retriever.retrieve("compare A vs B", top_k=3)

        assert result.anchor_used is False
        assert isinstance(result.chunks, list)
