# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for prompt optimizer and quality-diversity archive — Issue #2600, #3222."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.autoresearch.archive import Archive
from services.autoresearch.config import AutoResearchConfig
from services.autoresearch.models import VariantArchiveEntry
from services.autoresearch.prompt_optimizer import (
    OptimizationSession,
    PromptOptimizer,
    PromptOptTarget,
    PromptVariant,
)
from services.autoresearch.scorers import ScorerResult

# ---------------------------------------------------------------------------
# Helper factory
# ---------------------------------------------------------------------------


def _make_variant(vid: str, score: float, round_number: int = 1) -> PromptVariant:
    return PromptVariant(
        id=vid,
        prompt_text=f"prompt_{vid}",
        output=f"output_{vid}",
        scores={"s": score},
        final_score=score,
        round_number=round_number,
    )


def _make_entry(
    vid: str,
    score: float,
    valid_parent: bool = True,
    generation: int = 1,
) -> VariantArchiveEntry:
    return VariantArchiveEntry(
        variant_id=vid,
        variant=_make_variant(vid, score),
        score=score,
        parent_id=None,
        generation=generation,
        valid_parent=valid_parent,
    )


# ---------------------------------------------------------------------------
# PromptVariant
# ---------------------------------------------------------------------------


class TestPromptVariantModel:
    def test_to_dict(self) -> None:
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

    def test_from_dict_round_trip(self) -> None:
        v = _make_variant("v2", 0.5)
        restored = PromptVariant.from_dict(v.to_dict())
        assert restored.id == "v2"
        assert restored.final_score == 0.5
        assert restored.prompt_text == "prompt_v2"


# ---------------------------------------------------------------------------
# OptimizationSession
# ---------------------------------------------------------------------------


class TestOptimizationSession:
    def test_to_dict(self) -> None:
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


# ---------------------------------------------------------------------------
# Archive unit tests
# ---------------------------------------------------------------------------


class TestArchive:
    def test_add_retains_all_entries(self) -> None:
        archive = Archive()
        for i in range(5):
            archive.add(_make_entry(f"v{i}", score=float(i) * 0.1))
        assert archive.size == 5

    def test_best_returns_highest_score(self) -> None:
        archive = Archive()
        archive.add(_make_entry("low", score=0.1))
        archive.add(_make_entry("high", score=0.9))
        archive.add(_make_entry("mid", score=0.5))
        assert archive.best is not None
        assert archive.best.variant_id == "high"

    def test_valid_parents_excludes_invalid(self) -> None:
        archive = Archive()
        archive.add(_make_entry("good", score=0.8, valid_parent=True))
        archive.add(_make_entry("bad", score=0.2, valid_parent=False))
        parents = archive.valid_parents
        assert len(parents) == 1
        assert parents[0].variant_id == "good"

    def test_mark_invalid_excludes_entry(self) -> None:
        archive = Archive()
        archive.add(_make_entry("a", score=0.7))
        archive.add(_make_entry("b", score=0.3))
        archive.mark_invalid("a")
        parents = archive.valid_parents
        assert all(p.variant_id != "a" for p in parents)

    def test_select_parent_returns_valid_entry(self) -> None:
        archive = Archive()
        archive.add(_make_entry("x", score=0.6))
        archive.add(_make_entry("y", score=0.0, valid_parent=False))
        result = archive.select_parent()
        assert result is not None
        assert result.variant_id == "x"

    def test_select_parent_none_when_all_invalid(self) -> None:
        archive = Archive()
        archive.add(_make_entry("z", score=0.5, valid_parent=False))
        assert archive.select_parent() is None

    def test_select_parent_uniform_when_all_scores_zero(self) -> None:
        archive = Archive()
        for i in range(10):
            archive.add(_make_entry(f"v{i}", score=0.0))
        # Should not raise; should return one of the entries
        result = archive.select_parent()
        assert result is not None

    def test_prune_caps_size(self) -> None:
        archive = Archive(max_size=3)
        for i in range(5):
            archive.add(_make_entry(f"v{i}", score=float(i) * 0.1))
        assert archive.size == 3
        # Only the top-3 scoring entries should remain
        ids = {e.variant_id for e in archive.valid_parents}
        assert "v4" in ids  # score 0.4 — top 3

    def test_serialisation_round_trip(self) -> None:
        archive = Archive(max_size=10)
        archive.add(_make_entry("a", score=0.7))
        archive.add(_make_entry("b", score=0.3, valid_parent=False))
        serialised = archive.to_json()
        restored = Archive.from_json(serialised, PromptVariant)
        assert restored.size == 2
        assert restored.best is not None
        assert restored.best.variant_id == "a"
        invalid = [e for e in restored._entries if not e.valid_parent]
        assert len(invalid) == 1
        assert invalid[0].variant_id == "b"


# ---------------------------------------------------------------------------
# PromptOptimizer integration (archive-aware)
# ---------------------------------------------------------------------------


class TestPromptOptimizerLoop:
    @pytest.fixture
    def mock_llm(self):
        llm = AsyncMock()
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
    async def test_archive_populated_after_round(self, optimizer, mock_scorer):
        """Archive must retain all variants, not just top-K."""
        target = PromptOptTarget(
            agent_name="test",
            current_prompt="base",
            scorer_chain=["test_scorer"],
            mutation_count=3,
            top_k=1,  # old top-K = 1; archive must still hold all 3
        )

        async def benchmark_fn(prompt: str) -> str:
            return f"output for: {prompt}"

        session = await optimizer.optimize(target, benchmark_fn, max_rounds=1)
        assert session.archive is not None
        assert session.archive.size == 3  # all variants retained

    @pytest.mark.asyncio
    async def test_subset_fraction_passed_to_first_scorer(self, mock_llm, mock_scorer):
        """First scorer in chain receives staged_eval_fraction; subsequent get None."""
        cheap_scorer = AsyncMock()
        cheap_scorer.name = "cheap"
        cheap_scorer.score.return_value = ScorerResult(score=0.9, raw_score=9, metadata={}, scorer_name="cheap")

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
        cheap_scorer.score.return_value = ScorerResult(score=0.2, raw_score=2, metadata={}, scorer_name="cheap")

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
        cheap_scorer.score.return_value = ScorerResult(score=0.8, raw_score=8, metadata={}, scorer_name="cheap")

        expensive_scorer = AsyncMock()
        expensive_scorer.name = "expensive"
        expensive_scorer.score.return_value = ScorerResult(score=0.9, raw_score=9, metadata={}, scorer_name="expensive")

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

    @pytest.mark.asyncio
    async def test_scorer_failure_marks_variant_invalid_in_archive(self, mock_llm):
        """Variants whose scorer raises must have valid_parent=False in archive."""
        failing_scorer = AsyncMock()
        failing_scorer.score.side_effect = RuntimeError("scorer exploded")
        opt = PromptOptimizer(
            scorers={"fail_scorer": failing_scorer},
            llm_service=mock_llm,
        )
        opt._redis = AsyncMock()

        target = PromptOptTarget(
            agent_name="test",
            current_prompt="base",
            scorer_chain=["fail_scorer"],
            mutation_count=3,
            top_k=1,
        )

        async def benchmark_fn(prompt: str) -> str:
            return "output"

        session = await opt.optimize(target, benchmark_fn, max_rounds=1)

        assert session.archive is not None
        invalid = [e for e in session.archive._entries if not e.valid_parent]
        assert len(invalid) == 3  # all variants failed scoring

    @pytest.mark.asyncio
    async def test_load_archive_returns_none_when_missing(self, optimizer) -> None:
        optimizer._redis.get.return_value = None
        result = await optimizer.load_archive("nonexistent-session-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_multi_scorer_final_score_is_average(self, mock_llm) -> None:
        """final_score must be the mean of all scorer scores — Issue #3211."""
        scorer_a = AsyncMock()
        scorer_a.name = "scorer_a"
        scorer_a.score.return_value = ScorerResult(score=0.6, raw_score=6, metadata={}, scorer_name="scorer_a")

        scorer_b = AsyncMock()
        scorer_b.name = "scorer_b"
        scorer_b.score.return_value = ScorerResult(score=0.8, raw_score=8, metadata={}, scorer_name="scorer_b")

        opt = PromptOptimizer(
            scorers={"scorer_a": scorer_a, "scorer_b": scorer_b},
            llm_service=mock_llm,
        )
        opt._redis = AsyncMock()

        target = PromptOptTarget(
            agent_name="test",
            current_prompt="base",
            scorer_chain=["scorer_a", "scorer_b"],
            mutation_count=1,
            top_k=1,
        )

        async def benchmark_fn(prompt: str) -> str:
            return "output"

        session = await opt.optimize(target, benchmark_fn, max_rounds=1)

        assert session.best_variant is not None
        assert (
            abs(session.best_variant.final_score - 0.7) < 1e-9
        ), f"Expected final_score=0.7 (average of 0.6+0.8), got {session.best_variant.final_score}"
