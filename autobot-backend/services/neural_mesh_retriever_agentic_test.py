# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for NeuralMeshRetriever A-RAG ReAct loop (#2136).

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


def _make_llm(responses: list[str]):
    """Return an AsyncMock LLM that returns *responses* in sequence."""
    llm = AsyncMock(side_effect=responses)
    return llm


def _make_retriever_agentic(
    complexity_value: str = "complex",
    llm_responses: list[str] | None = None,
    chroma_results: list | None = None,
    hybrid_results: list | None = None,
    ppr_results: list | None = None,
    rerank_results: list | None = None,
    anchor_results: list | None = None,
) -> NeuralMeshRetriever:
    """Construct a NeuralMeshRetriever with an LLM mock and controllable deps.

    Returns the retriever pre-configured for the given complexity tier.
    """
    chroma_results = chroma_results or [_make_result("c1")]
    hybrid_results = hybrid_results or [_make_result("h1")]
    ppr_results = ppr_results or [("h1", 0.8)]
    rerank_results = rerank_results or chroma_results[:1]
    anchor_results = anchor_results or []
    llm_responses = llm_responses or ['{"tool": "DONE"}']

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
        llm=_make_llm(llm_responses),
    )


# =============================================================================
# retrieve_agentic — loop behaviour
# =============================================================================


class TestRetrieveAgenticLoop:
    """retrieve_agentic() drives the ReAct loop correctly."""

    @pytest.mark.asyncio
    async def test_retrieve_agentic_calls_select_next_action(self) -> None:
        """LLM is called at each step until DONE is returned."""
        responses = [
            '{"tool": "semantic_search", "params": {}}',
            '{"tool": "DONE"}',
        ]
        retriever = _make_retriever_agentic(llm_responses=responses)

        with patch("asyncio.create_task"):
            await retriever.retrieve_agentic("what is mesh expansion", top_k=3)

        assert retriever.llm.call_count == 2

    @pytest.mark.asyncio
    async def test_retrieve_agentic_stops_on_done(self) -> None:
        """When the first LLM response is DONE the loop exits after one call."""
        retriever = _make_retriever_agentic(llm_responses=['{"tool": "DONE"}'])

        with patch("asyncio.create_task"):
            result = await retriever.retrieve_agentic("simple done query", top_k=3)

        retriever.llm.assert_called_once()
        assert isinstance(result, MeshRetrievalResult)

    @pytest.mark.asyncio
    async def test_retrieve_agentic_max_steps_limit(self) -> None:
        """Loop iterates exactly max_steps times when DONE is never returned."""
        # Always return semantic_search — never DONE
        never_done = ['{"tool": "semantic_search", "params": {}}'] * 10
        retriever = _make_retriever_agentic(llm_responses=never_done)

        with patch("asyncio.create_task"):
            await retriever.retrieve_agentic("multi step query", top_k=3, max_steps=3)

        assert retriever.llm.call_count == 3

    @pytest.mark.asyncio
    async def test_retrieve_agentic_returns_mesh_retrieval_result(self) -> None:
        """retrieve_agentic always returns a MeshRetrievalResult. Issue #2136."""
        retriever = _make_retriever_agentic(llm_responses=['{"tool": "DONE"}'])

        with patch("asyncio.create_task"):
            result = await retriever.retrieve_agentic("any query", top_k=2)

        assert isinstance(result, MeshRetrievalResult)
        assert result.complexity == "complex"
        assert result.expanded is True


# =============================================================================
# _execute_tool dispatch
# =============================================================================


class TestExecuteTool:
    """_execute_tool dispatches each tool name to the correct method."""

    @pytest.mark.asyncio
    async def test_execute_tool_semantic_search(self) -> None:
        """semantic_search dispatches to chroma_search callable."""
        retriever = _make_retriever_agentic()
        await retriever._execute_tool("semantic_search", {}, "redis caching")
        retriever.chroma_search.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_tool_keyword_search(self) -> None:
        """keyword_search dispatches to hybrid_search callable."""
        retriever = _make_retriever_agentic()
        await retriever._execute_tool("keyword_search", {}, "redis caching")
        retriever.hybrid_search.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_tool_mesh_expand(self) -> None:
        """mesh_expand calls hybrid_search then ppr.rank."""
        retriever = _make_retriever_agentic()
        await retriever._execute_tool("mesh_expand", {}, "redis caching")
        retriever.hybrid_search.assert_called_once()
        retriever.ppr.rank.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_tool_unknown_returns_empty(self) -> None:
        """An unrecognised tool name returns an empty list without raising."""
        retriever = _make_retriever_agentic()
        result = await retriever._execute_tool("nonexistent_tool", {}, "query")
        assert result == []

    @pytest.mark.asyncio
    async def test_execute_tool_anchor_lookup(self) -> None:
        """anchor_lookup calls hybrid_search and mesh_db.get_anchor_neighbors."""
        retriever = _make_retriever_agentic(anchor_results=["anchor-1"])
        await retriever._execute_tool("anchor_lookup", {}, "redis caching")
        retriever.hybrid_search.assert_called_once()
        retriever.mesh_db.get_anchor_neighbors.assert_called_once()


# =============================================================================
# _parse_action
# =============================================================================


class TestParseAction:
    """_parse_action parses valid JSON and falls back to DONE on failure."""

    def test_parse_action_valid_json(self) -> None:
        """Valid JSON with a tool key is returned as-is."""
        retriever = _make_retriever_agentic()
        action = retriever._parse_action('{"tool": "semantic_search", "params": {"top_k": 5}}')
        assert action["tool"] == "semantic_search"
        assert action["params"]["top_k"] == 5

    def test_parse_action_done_json(self) -> None:
        """JSON with tool=DONE is returned directly."""
        retriever = _make_retriever_agentic()
        action = retriever._parse_action('{"tool": "DONE"}')
        assert action["tool"] == "DONE"

    def test_parse_action_invalid_json_returns_done(self) -> None:
        """Non-JSON output returns {"tool": "DONE"} without raising."""
        retriever = _make_retriever_agentic()
        action = retriever._parse_action("not valid json at all")
        assert action == {"tool": "DONE"}

    def test_parse_action_json_missing_tool_key_returns_done(self) -> None:
        """Valid JSON that lacks a 'tool' key falls back to DONE."""
        retriever = _make_retriever_agentic()
        action = retriever._parse_action('{"action": "search"}')
        assert action == {"tool": "DONE"}

    def test_parse_action_empty_string_returns_done(self) -> None:
        """Empty string falls back to DONE without raising."""
        retriever = _make_retriever_agentic()
        action = retriever._parse_action("")
        assert action == {"tool": "DONE"}


# =============================================================================
# retrieve() routing to agentic path
# =============================================================================


class TestRetrieveAgenticRouting:
    """retrieve() directs COMPLEX/MULTI_HOP to retrieve_agentic when llm is set."""

    @pytest.mark.asyncio
    async def test_retrieve_routes_complex_to_agentic(self) -> None:
        """complexity=COMPLEX with llm set calls retrieve_agentic. Issue #2136."""
        retriever = _make_retriever_agentic(
            complexity_value="complex",
            llm_responses=['{"tool": "DONE"}'],
        )

        with patch.object(retriever, "retrieve_agentic", wraps=retriever.retrieve_agentic) as spy:
            with patch("asyncio.create_task"):
                await retriever.retrieve("complex multi-faceted query", top_k=3)

        spy.assert_called_once()

    @pytest.mark.asyncio
    async def test_retrieve_routes_multi_hop_to_agentic(self) -> None:
        """complexity=MULTI_HOP with llm set calls retrieve_agentic. Issue #2136."""
        retriever = _make_retriever_agentic(
            complexity_value="multi_hop",
            llm_responses=['{"tool": "DONE"}'],
        )

        with patch.object(retriever, "retrieve_agentic", wraps=retriever.retrieve_agentic) as spy:
            with patch("asyncio.create_task"):
                await retriever.retrieve("trace the chain of events", top_k=3)

        spy.assert_called_once()

    @pytest.mark.asyncio
    async def test_retrieve_complex_without_llm_uses_full_retrieve(self) -> None:
        """COMPLEX query with no llm falls through to _full_retrieve. Issue #2136."""
        # Build retriever without llm by passing None explicitly
        retriever = _make_retriever_agentic(complexity_value="complex")
        retriever.llm = None

        with patch.object(retriever, "_full_retrieve", wraps=retriever._full_retrieve) as spy:
            with patch("asyncio.create_task"):
                await retriever.retrieve("complex query without llm", top_k=3)

        spy.assert_called_once()
