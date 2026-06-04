# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for QueryDecomposer (#2134).

All external dependencies (LLM, mesh retriever) are replaced with
AsyncMock / MagicMock so the tests run without a model server or database.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.neural_mesh.query_decomposer import (
    DecompositionPlan,
    DecompositionStep,
    QueryDecomposer,
    StepResult,
)

# =============================================================================
# Factories
# =============================================================================


def _make_retrieval_result(chunks: list[dict] | None = None):
    """Return a MagicMock that mimics MeshRetrievalResult with .chunks."""
    result = MagicMock()
    result.chunks = chunks or [{"chunk_id": "c1", "content": "evidence text", "score": 0.9}]
    return result


def _make_decomposer(
    llm_response: str | None = None,
    retrieval_result=None,
) -> QueryDecomposer:
    """Construct a QueryDecomposer with controllable mock dependencies."""
    default_steps = json.dumps(
        [
            {"step": 1, "query": "sub-query one", "depends_on": []},
            {"step": 2, "query": "sub-query two", "depends_on": [1]},
        ]
    )
    llm = AsyncMock(return_value=llm_response if llm_response is not None else default_steps)

    retriever = AsyncMock()
    retriever.retrieve = AsyncMock(
        return_value=(retrieval_result if retrieval_result is not None else _make_retrieval_result())
    )

    return QueryDecomposer(llm=llm, mesh_retriever=retriever)


# =============================================================================
# decompose()
# =============================================================================


class TestDecompose:
    """QueryDecomposer.decompose() builds a DecompositionPlan from LLM output."""

    @pytest.mark.asyncio
    async def test_decompose_calls_llm_with_query(self) -> None:
        """LLM callable must receive a prompt that contains the original query."""
        decomposer = _make_decomposer()
        query = "How does Redis clustering affect write latency?"

        await decomposer.decompose(query)

        decomposer.llm.assert_called_once()
        prompt_arg = decomposer.llm.call_args.args[0]
        assert query in prompt_arg

    @pytest.mark.asyncio
    async def test_decompose_parses_valid_json(self) -> None:
        """Valid JSON from LLM produces a DecompositionPlan with the expected steps."""
        steps_json = json.dumps(
            [
                {"step": 1, "query": "first sub-query", "depends_on": []},
                {"step": 2, "query": "second sub-query", "depends_on": [1]},
                {"step": 3, "query": "third sub-query", "depends_on": [1, 2]},
            ]
        )
        decomposer = _make_decomposer(llm_response=steps_json)

        plan = await decomposer.decompose("multi-hop question")

        assert isinstance(plan, DecompositionPlan)
        assert plan.original_query == "multi-hop question"
        assert len(plan.steps) == 3
        assert plan.steps[0].query == "first sub-query"
        assert plan.steps[1].depends_on == [1]
        assert plan.steps[2].depends_on == [1, 2]

    @pytest.mark.asyncio
    async def test_decompose_handles_malformed_json(self) -> None:
        """Malformed LLM output falls back to a single step with the original query."""
        decomposer = _make_decomposer(llm_response="Sorry, I cannot break that down.")

        plan = await decomposer.decompose("complex question that breaks the LLM")

        assert isinstance(plan, DecompositionPlan)
        assert len(plan.steps) == 1
        assert plan.steps[0].query == "complex question that breaks the LLM"
        assert plan.steps[0].step == 1

    @pytest.mark.asyncio
    async def test_decompose_tolerates_prose_around_json(self) -> None:
        """JSON array embedded in prose is extracted and parsed correctly."""
        prose_with_json = (
            "Sure! Here are the steps: "
            + json.dumps([{"step": 1, "query": "embedded query", "depends_on": []}])
            + " Hope that helps!"
        )
        decomposer = _make_decomposer(llm_response=prose_with_json)

        plan = await decomposer.decompose("wrapped query")

        assert len(plan.steps) == 1
        assert plan.steps[0].query == "embedded query"


# =============================================================================
# execute()
# =============================================================================


class TestExecute:
    """QueryDecomposer.execute() calls the retriever once per plan step."""

    @pytest.mark.asyncio
    async def test_execute_calls_retriever_per_step(self) -> None:
        """Three plan steps produce exactly three retrieve() calls."""
        decomposer = _make_decomposer()
        plan = DecompositionPlan(
            original_query="original",
            steps=[
                DecompositionStep(step=1, query="q1", depends_on=[]),
                DecompositionStep(step=2, query="q2", depends_on=[]),
                DecompositionStep(step=3, query="q3", depends_on=[]),
            ],
        )

        await decomposer.execute(plan)

        assert decomposer.mesh_retriever.retrieve.call_count == 3

    @pytest.mark.asyncio
    async def test_execute_passes_prior_context(self) -> None:
        """Step 2's retrieve query includes evidence content from step 1."""
        evidence_chunk = {
            "chunk_id": "e1",
            "content": "step one evidence",
            "score": 0.8,
        }
        retrieval = _make_retrieval_result(chunks=[evidence_chunk])
        decomposer = _make_decomposer(retrieval_result=retrieval)

        plan = DecompositionPlan(
            original_query="multi-hop",
            steps=[
                DecompositionStep(step=1, query="first query", depends_on=[]),
                DecompositionStep(step=2, query="second query", depends_on=[1]),
            ],
        )

        await decomposer.execute(plan)

        second_call_args = decomposer.mesh_retriever.retrieve.call_args_list[1]
        second_query = second_call_args.kwargs.get("query") or second_call_args.args[0]
        assert "step one evidence" in second_query

    @pytest.mark.asyncio
    async def test_step_result_contains_evidence(self) -> None:
        """Each StepResult has a non-empty evidence list from the retrieval."""
        chunks = [
            {"chunk_id": "a", "content": "alpha", "score": 0.9},
            {"chunk_id": "b", "content": "beta", "score": 0.7},
        ]
        decomposer = _make_decomposer(retrieval_result=_make_retrieval_result(chunks=chunks))

        plan = DecompositionPlan(
            original_query="single step",
            steps=[DecompositionStep(step=1, query="q1", depends_on=[])],
        )

        results = await decomposer.execute(plan)

        assert len(results) == 1
        assert isinstance(results[0], StepResult)
        assert len(results[0].evidence) == 2
        assert results[0].evidence[0]["chunk_id"] == "a"

    @pytest.mark.asyncio
    async def test_execute_returns_one_result_per_step(self) -> None:
        """execute() returns a StepResult list of the same length as plan.steps."""
        decomposer = _make_decomposer()
        steps = [DecompositionStep(step=i, query=f"q{i}", depends_on=[]) for i in range(1, 5)]
        plan = DecompositionPlan(original_query="four step plan", steps=steps)

        results = await decomposer.execute(plan)

        assert len(results) == 4
        for i, r in enumerate(results):
            assert r.step is steps[i]

    @pytest.mark.asyncio
    async def test_execute_step_without_deps_sends_query_only(self) -> None:
        """A step with no depends_on sends just its own query to the retriever."""
        decomposer = _make_decomposer()
        plan = DecompositionPlan(
            original_query="no deps",
            steps=[DecompositionStep(step=1, query="standalone query", depends_on=[])],
        )

        await decomposer.execute(plan)

        call_kwargs = decomposer.mesh_retriever.retrieve.call_args.kwargs
        query_sent = call_kwargs.get("query") or decomposer.mesh_retriever.retrieve.call_args.args[0]
        assert query_sent == "standalone query"
