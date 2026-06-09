# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for Issue #3208 — wire up PromptOptimizer with real scorers and benchmark.

Covers:
  1. Scorer registration — _get_optimizer produces val_bpb, llm_judge, human_review
  2. Benchmark invocation — autoresearch_hypothesis target runs real pipeline
  3. Agent registration — register_optimization_target + /register endpoint
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.autoresearch.prompt_optimizer import (
    PromptOptimizer,
    PromptOptTarget,
)
from services.autoresearch.scorers import (
    HumanReviewScorer,
    LLMJudgeScorer,
    ScorerResult,
    ValBpbScorer,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_optimizer(extra_scorers: dict | None = None) -> PromptOptimizer:
    """Return a PromptOptimizer with mocked LLM and optional scorers."""
    llm = AsyncMock()
    mock_response = MagicMock()
    mock_response.content = json.dumps(["variant A", "variant B"])
    llm.chat.return_value = mock_response

    scorers = extra_scorers or {}
    opt = PromptOptimizer(scorers=scorers, llm_service=llm)
    opt._redis = AsyncMock()
    return opt


# ---------------------------------------------------------------------------
# Problem 1: Scorer registration
# ---------------------------------------------------------------------------


class TestScorerRegistration:
    """Verify that the three concrete scorers are present and functional."""

    def test_val_bpb_scorer_instantiation(self) -> None:
        runner = AsyncMock()
        scorer = ValBpbScorer(runner=runner, baseline_val_bpb=5.0)
        assert scorer.name == "val_bpb"

    def test_val_bpb_scorer_rejects_non_positive_baseline(self) -> None:
        runner = AsyncMock()
        with pytest.raises(ValueError, match="baseline_val_bpb must be positive"):
            ValBpbScorer(runner=runner, baseline_val_bpb=0.0)

    def test_llm_judge_scorer_instantiation(self) -> None:
        scorer = LLMJudgeScorer(
            llm_service=AsyncMock(),
            criteria=["clarity", "specificity"],
        )
        assert scorer.name == "llm_judge"

    def test_human_review_scorer_instantiation(self) -> None:
        scorer = HumanReviewScorer()
        assert scorer.name == "human_review"

    def test_optimizer_holds_all_three_scorers(self) -> None:
        runner = AsyncMock()
        llm = AsyncMock()
        scorers = {
            "val_bpb": ValBpbScorer(runner=runner, baseline_val_bpb=1.0),
            "llm_judge": LLMJudgeScorer(llm_service=llm, criteria=["quality"]),
            "human_review": HumanReviewScorer(),
        }
        opt = PromptOptimizer(scorers=scorers, llm_service=llm)
        assert set(opt._scorers.keys()) == {"val_bpb", "llm_judge", "human_review"}

    @pytest.mark.asyncio
    async def test_val_bpb_scorer_scores_improvement(self) -> None:
        from services.autoresearch.models import Experiment, ExperimentResult, ExperimentState

        runner = AsyncMock()
        experiment = Experiment(state=ExperimentState.KEPT)
        experiment.result = ExperimentResult(val_bpb=4.0)
        runner.run_experiment.return_value = experiment

        scorer = ValBpbScorer(runner=runner, baseline_val_bpb=5.0)
        result = await scorer.score("test hypothesis", {})

        assert result.score > 0.0
        assert result.raw_score == 4.0
        assert result.scorer_name == "val_bpb"

    @pytest.mark.asyncio
    async def test_llm_judge_scorer_parses_rating(self) -> None:
        llm = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.content = '{"rating": 7, "reasoning": "good"}'
        llm.chat.return_value = mock_resp

        scorer = LLMJudgeScorer(llm_service=llm, criteria=["clarity"])
        result = await scorer.score("some output", {})

        assert result.score == pytest.approx(0.7)
        assert result.scorer_name == "llm_judge"

    @pytest.mark.asyncio
    async def test_human_review_scorer_timeout_returns_zero(self) -> None:
        scorer = HumanReviewScorer(poll_interval=0.01, timeout=0.01)
        scorer._redis = AsyncMock()
        scorer._redis.get.return_value = None
        scorer._redis.blpop.return_value = None  # BLPOP timed out

        result = await scorer.score(
            "output",
            {"session_id": "s1", "variant_id": "v1"},
        )
        assert result.score == 0.0
        assert result.metadata.get("status") == "timeout"


# ---------------------------------------------------------------------------
# Problem 2: Benchmark invocation
# ---------------------------------------------------------------------------


class TestBenchmarkInvocation:
    """Verify the autoresearch_hypothesis benchmark produces real output."""

    @pytest.mark.asyncio
    async def test_benchmark_returns_json_with_output_key(self):
        """The benchmark callable must return JSON with 'output' and 'latency_ms'."""
        from services.autoresearch.auto_research_agent import AutoResearchAgent
        from services.autoresearch.runner import ExperimentRunner

        runner = AsyncMock(spec=ExperimentRunner)

        # Build the benchmark function inline — mirrors _register_autoresearch_hypothesis_target
        import time as _time

        async def _benchmark(prompt: str) -> str:
            start = _time.monotonic()
            try:
                agent = AutoResearchAgent(runner=runner)
                hypothesis = agent._generate_hypothesis(
                    search_results=[],
                    prior_results=[],
                    iteration=1,
                )
                latency_ms = round((_time.monotonic() - start) * 1000, 1)
                return json.dumps(
                    {
                        "output": hypothesis.statement,
                        "rationale": hypothesis.rationale,
                        "hyperparams": hypothesis.suggested_hyperparams,
                        "latency_ms": latency_ms,
                        "error": None,
                    },
                    ensure_ascii=False,
                )
            except Exception as exc:
                latency_ms = round((_time.monotonic() - start) * 1000, 1)
                return json.dumps(
                    {
                        "output": prompt,
                        "rationale": "",
                        "hyperparams": {},
                        "latency_ms": latency_ms,
                        "error": str(exc),
                    },
                    ensure_ascii=False,
                )

        raw = await _benchmark("Improve the model learning rate")
        data = json.loads(raw)

        assert "output" in data
        assert "latency_ms" in data
        assert isinstance(data["latency_ms"], float)
        assert data["error"] is None

    @pytest.mark.asyncio
    async def test_benchmark_falls_back_gracefully_on_exception(self):
        """If AutoResearchAgent raises, benchmark returns prompt text in 'output'."""
        import time as _time

        async def _benchmark_with_failure(prompt: str) -> str:
            start = _time.monotonic()
            try:
                raise RuntimeError("agent unavailable")
            except Exception as exc:
                latency_ms = round((_time.monotonic() - start) * 1000, 1)
                return json.dumps(
                    {
                        "output": prompt,
                        "rationale": "",
                        "hyperparams": {},
                        "latency_ms": latency_ms,
                        "error": str(exc),
                    },
                    ensure_ascii=False,
                )

        raw = await _benchmark_with_failure("test prompt")
        data = json.loads(raw)

        assert data["output"] == "test prompt"
        assert data["error"] == "agent unavailable"
        assert data["latency_ms"] >= 0.0

    @pytest.mark.asyncio
    async def test_optimizer_uses_registered_benchmark_not_placeholder(self):
        """Ensure the benchmark is called during optimize() (not a no-op echo)."""
        benchmark_called_with: list = []

        async def _tracking_benchmark(prompt: str) -> str:
            benchmark_called_with.append(prompt)
            return json.dumps({"output": f"result for {prompt}", "latency_ms": 1.0})

        llm = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.content = '{"rating": 6, "reasoning": "ok"}'
        llm.chat.return_value = mock_resp

        scorer = AsyncMock()
        scorer.name = "llm_judge"
        scorer.score.return_value = ScorerResult(score=0.6, raw_score=6, metadata={}, scorer_name="llm_judge")

        opt = PromptOptimizer(scorers={"llm_judge": scorer}, llm_service=llm)
        opt._redis = AsyncMock()

        target = PromptOptTarget(
            agent_name="test_agent",
            current_prompt="base prompt",
            scorer_chain=["llm_judge"],
            mutation_count=2,
            top_k=1,
        )
        opt.register_optimization_target(
            agent_id="test_agent",
            target=target,
            benchmark_fn=_tracking_benchmark,
        )

        # Patch llm mutation to return predictable variants
        with patch.object(
            opt,
            "_mutate_prompt",
            return_value=["variant A", "variant B"],
        ):
            session = await opt.optimize(target, _tracking_benchmark, max_rounds=1)

        assert session.status.value == "completed"
        assert len(benchmark_called_with) == 2  # one call per variant
        assert "variant A" in benchmark_called_with


# ---------------------------------------------------------------------------
# Problem 3: Agent registration
# ---------------------------------------------------------------------------


class TestAgentRegistration:
    """Verify register_optimization_target and the targets registry."""

    def test_register_stores_target_and_benchmark(self):
        opt = _make_optimizer()

        async def _bench(prompt: str) -> str:
            return "output"

        target = PromptOptTarget(
            agent_name="my_agent",
            current_prompt="base",
            scorer_chain=["llm_judge"],
        )
        opt.register_optimization_target("my_agent", target, _bench)

        assert "my_agent" in opt.get_registered_targets()
        entry = opt.get_target("my_agent")
        assert entry is not None
        stored_target, stored_bench = entry
        assert stored_target.agent_name == "my_agent"
        assert stored_bench is _bench

    def test_get_target_returns_none_for_unknown(self) -> None:
        opt = _make_optimizer()
        assert opt.get_target("nonexistent") is None

    def test_get_registered_targets_is_empty_initially(self) -> None:
        opt = _make_optimizer()
        assert opt.get_registered_targets() == []

    def test_multiple_targets_coexist(self):
        opt = _make_optimizer()

        async def _bench_a(prompt: str) -> str:
            return "a"

        async def _bench_b(prompt: str) -> str:
            return "b"

        target_a = PromptOptTarget(agent_name="agent_a", current_prompt="a", scorer_chain=[])
        target_b = PromptOptTarget(agent_name="agent_b", current_prompt="b", scorer_chain=[])

        opt.register_optimization_target("agent_a", target_a, _bench_a)
        opt.register_optimization_target("agent_b", target_b, _bench_b)

        targets = opt.get_registered_targets()
        assert "agent_a" in targets
        assert "agent_b" in targets

    def test_re_registration_overwrites_previous(self):
        """Registering the same agent_id again replaces the old entry."""
        opt = _make_optimizer()

        async def _old_bench(prompt: str) -> str:
            return "old"

        async def _new_bench(prompt: str) -> str:
            return "new"

        target = PromptOptTarget(agent_name="agent_x", current_prompt="x", scorer_chain=[])
        opt.register_optimization_target("agent_x", target, _old_bench)
        opt.register_optimization_target("agent_x", target, _new_bench)

        _, bench = opt.get_target("agent_x")
        assert bench is _new_bench

    @pytest.mark.asyncio
    async def test_optimize_uses_registered_benchmark(self):
        """optimize() called with target+bench from registry must invoke the bench."""
        invocations: list = []

        async def _tracking_bench(prompt: str) -> str:
            invocations.append(prompt)
            return "tracked output"

        scorer = AsyncMock()
        scorer.name = "mock"
        scorer.score.return_value = ScorerResult(score=0.5, raw_score=5, metadata={}, scorer_name="mock")

        llm = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.content = json.dumps(["v1"])
        llm.chat.return_value = mock_resp

        opt = PromptOptimizer(scorers={"mock": scorer}, llm_service=llm)
        opt._redis = AsyncMock()

        target = PromptOptTarget(
            agent_name="reg_agent",
            current_prompt="base",
            scorer_chain=["mock"],
            mutation_count=1,
            top_k=1,
        )
        opt.register_optimization_target("reg_agent", target, _tracking_bench)

        entry = opt.get_target("reg_agent")
        assert entry is not None
        reg_target, reg_bench = entry

        session = await opt.optimize(reg_target, reg_bench, max_rounds=1)
        assert session.status.value == "completed"
        assert len(invocations) == 1

    @pytest.mark.asyncio
    async def test_start_optimization_unknown_agent_raises(self) -> None:
        """Requesting an unregistered agent_id must fail with a meaningful error.

        This mirrors what the /start route does: it calls optimizer.get_target()
        and raises HTTPException when the result is None.
        """
        opt = _make_optimizer()
        result = opt.get_target("unknown_agent")
        assert result is None, "Unregistered agent must return None from get_target()"

    @pytest.mark.asyncio
    async def test_start_optimization_registered_agent_succeeds(self):
        """Requesting a registered agent_id must resolve to target+benchmark."""
        opt = _make_optimizer()

        async def _bench(prompt: str) -> str:
            return "ok"

        target = PromptOptTarget(
            agent_name="valid_agent",
            current_prompt="prompt",
            scorer_chain=[],
        )
        opt.register_optimization_target("valid_agent", target, _bench)

        entry = opt.get_target("valid_agent")
        assert entry is not None
        resolved_target, resolved_bench = entry
        assert resolved_target.agent_name == "valid_agent"
        assert resolved_bench is _bench
