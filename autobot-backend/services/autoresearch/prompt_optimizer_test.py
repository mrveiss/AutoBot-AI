# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for prompt optimizer — Issue #2600."""

from __future__ import annotations

import json

import pytest
from unittest.mock import AsyncMock, MagicMock

from services.autoresearch.config import AutoResearchConfig
from services.autoresearch.prompt_optimizer import (
    OptimizationSession,
    OptimizationStatus,
    PromptOptimizer,
    PromptOptTarget,
    PromptVariant,
)
from services.autoresearch.scorers import ScorerResult


class TestPromptVariantModel:
    def test_to_dict(self):
        variant = PromptVariant(
            id="v1",
            prompt_text="test prompt",
            output="test output",
            scores={"llm_judge": 0.8},
            final_score=0.8,
        )
        d = variant.to_dict()
        assert d["id"] == "v1"
        assert d["prompt_text"] == "test prompt"
        assert d["scores"] == {"llm_judge": 0.8}
        assert d["final_score"] == 0.8


class TestOptimizationSession:
    def test_to_dict(self):
        target = PromptOptTarget(
            agent_name="test_agent",
            current_prompt="base prompt",
            scorer_chain=["llm_judge"],
            mutation_count=3,
            top_k=1,
        )
        session = OptimizationSession(target=target)
        d = session.to_dict()
        assert d["status"] == "pending"
        assert d["target"]["agent_name"] == "test_agent"
        assert d["rounds_completed"] == 0


class TestPromptOptimizerLoop:
    @pytest.fixture
    def mock_llm(self):
        llm = AsyncMock()
        # Return 3 variants as JSON array
        mock_response = MagicMock()
        mock_response.content = json.dumps(["variant A", "variant B", "variant C"])
        llm.chat.return_value = mock_response
        return llm

    @pytest.fixture
    def mock_scorer(self):
        scorer = AsyncMock()
        scorer.name = "test_scorer"
        scorer.score.side_effect = [
            ScorerResult(score=0.3, raw_score=3, metadata={}, scorer_name="test_scorer"),
            ScorerResult(score=0.8, raw_score=8, metadata={}, scorer_name="test_scorer"),
            ScorerResult(score=0.5, raw_score=5, metadata={}, scorer_name="test_scorer"),
        ]
        return scorer

    @pytest.fixture
    def optimizer(self, mock_llm, mock_scorer):
        opt = PromptOptimizer(
            scorers={"test_scorer": mock_scorer},
            llm_service=mock_llm,
        )
        opt._redis = AsyncMock()
        return opt

    @pytest.mark.asyncio
    async def test_optimize_selects_best_variant(self, optimizer, mock_scorer):
        target = PromptOptTarget(
            agent_name="test",
            current_prompt="base prompt",
            scorer_chain=["test_scorer"],
            mutation_count=3,
            top_k=1,
        )

        async def benchmark_fn(prompt: str) -> str:
            return f"output for: {prompt}"

        session = await optimizer.optimize(target, benchmark_fn, max_rounds=1)

        assert session.status.value == "completed"
        assert session.rounds_completed == 1
        assert session.best_variant is not None
        assert session.best_variant.final_score == 0.8
        assert len(session.all_variants) == 3

    @pytest.mark.asyncio
    async def test_subset_fraction_passed_to_first_scorer(self, mock_llm, mock_scorer):
        """First scorer in chain receives staged_eval_fraction; subsequent get None."""
        cheap_scorer = AsyncMock()
        cheap_scorer.name = "cheap"
        cheap_scorer.score.return_value = ScorerResult(
            score=0.9, raw_score=9, metadata={}, scorer_name="cheap"
        )

        expensive_scorer = AsyncMock()
        expensive_scorer.name = "expensive"
        expensive_scorer.score.return_value = ScorerResult(
            score=0.85, raw_score=8, metadata={}, scorer_name="expensive"
        )

        cfg = AutoResearchConfig()
        cfg.staged_eval_fraction = 0.25
        cfg.staged_eval_threshold = 0.0  # pass all so both scorers run

        opt = PromptOptimizer(
            scorers={"cheap": cheap_scorer, "expensive": expensive_scorer},
            llm_service=mock_llm,
            config=cfg,
        )
        opt._redis = AsyncMock()

        target = PromptOptTarget(
            agent_name="test",
            current_prompt="base",
            scorer_chain=["cheap", "expensive"],
            mutation_count=1,
            top_k=1,
        )

        async def benchmark_fn(prompt: str) -> str:
            return "output"

        await opt.optimize(target, benchmark_fn, max_rounds=1)

        # cheap scorer must have been called with subset_fraction=0.25
        cheap_scorer.score.assert_awaited()
        call_kwargs = cheap_scorer.score.call_args
        assert call_kwargs.kwargs.get("subset_fraction") == 0.25

        # expensive scorer must have been called with subset_fraction=None
        expensive_scorer.score.assert_awaited()
        exp_kwargs = expensive_scorer.score.call_args
        assert exp_kwargs.kwargs.get("subset_fraction") is None

    @pytest.mark.asyncio
    async def test_staged_gate_blocks_low_scoring_variants(self, mock_llm):
        """Variants below staged_eval_threshold do not reach tier-2 scorer."""
        cheap_scorer = AsyncMock()
        cheap_scorer.name = "cheap"
        # All 3 variants score below threshold
        cheap_scorer.score.return_value = ScorerResult(
            score=0.2, raw_score=2, metadata={}, scorer_name="cheap"
        )

        expensive_scorer = AsyncMock()
        expensive_scorer.name = "expensive"

        cfg = AutoResearchConfig()
        cfg.staged_eval_fraction = 0.3
        cfg.staged_eval_threshold = 0.5  # 0.2 < 0.5 => all blocked

        opt = PromptOptimizer(
            scorers={"cheap": cheap_scorer, "expensive": expensive_scorer},
            llm_service=mock_llm,
            config=cfg,
        )
        opt._redis = AsyncMock()

        target = PromptOptTarget(
            agent_name="test",
            current_prompt="base",
            scorer_chain=["cheap", "expensive"],
            mutation_count=3,
            top_k=3,
        )

        async def benchmark_fn(prompt: str) -> str:
            return "output"

        session = await opt.optimize(target, benchmark_fn, max_rounds=1)

        # Cheap scorer ran for all 3 variants
        assert cheap_scorer.score.await_count == 3
        # Expensive scorer never ran
        expensive_scorer.score.assert_not_awaited()
        assert session.status.value == "completed"

    @pytest.mark.asyncio
    async def test_staged_gate_passes_high_scoring_variants(self, mock_llm):
        """Variants above threshold advance to tier-2."""
        cheap_scorer = AsyncMock()
        cheap_scorer.name = "cheap"
        cheap_scorer.score.return_value = ScorerResult(
            score=0.8, raw_score=8, metadata={}, scorer_name="cheap"
        )

        expensive_scorer = AsyncMock()
        expensive_scorer.name = "expensive"
        expensive_scorer.score.return_value = ScorerResult(
            score=0.9, raw_score=9, metadata={}, scorer_name="expensive"
        )

        cfg = AutoResearchConfig()
        cfg.staged_eval_fraction = 0.3
        cfg.staged_eval_threshold = 0.5  # 0.8 >= 0.5 => all pass

        opt = PromptOptimizer(
            scorers={"cheap": cheap_scorer, "expensive": expensive_scorer},
            llm_service=mock_llm,
            config=cfg,
        )
        opt._redis = AsyncMock()

        target = PromptOptTarget(
            agent_name="test",
            current_prompt="base",
            scorer_chain=["cheap", "expensive"],
            mutation_count=3,
            top_k=3,
        )

        async def benchmark_fn(prompt: str) -> str:
            return "output"

        session = await opt.optimize(target, benchmark_fn, max_rounds=1)

        assert cheap_scorer.score.await_count == 3
        assert expensive_scorer.score.await_count == 3
        assert session.status.value == "completed"

    @pytest.mark.asyncio
    async def test_optimize_cancel(self, optimizer):
        target = PromptOptTarget(
            agent_name="test",
            current_prompt="base",
            scorer_chain=["test_scorer"],
            mutation_count=1,
            top_k=1,
        )
        optimizer.cancel()

        async def benchmark_fn(prompt: str) -> str:
            return "output"

        session = await optimizer.optimize(target, benchmark_fn, max_rounds=5)
        assert session.status.value == "cancelled"
        assert session.rounds_completed == 0
