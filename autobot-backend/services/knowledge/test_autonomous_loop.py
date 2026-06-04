# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for AutonomousLoopRunner — Issue #4680.

Tests cover each phase (LEARN, HYPOTHESIZE, EXPERIMENT, ANALYZE, PROMOTE) and
the guardrails (dry-run, promotion threshold, hard-stop).

No external services required: LLM and evaluator are fully mocked.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.knowledge.autonomous_loop import (
    _DEFAULT_PROMOTION_THRESHOLD,
    AutonomousLoopRunner,
    LoopRunRecord,
    LoopStatus,
    get_loop_runner,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_llm(response_text: str = "") -> Any:
    """Return a mock LLM service whose chat() returns *response_text*."""
    llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = response_text
    llm.chat = AsyncMock(return_value=mock_response)
    return llm


def _make_orchestrator(
    *,
    dry_run: bool = True,
    promotion_threshold: float = _DEFAULT_PROMOTION_THRESHOLD,
    llm_response: str = "",
    max_variants: int = 3,
) -> AutonomousLoopRunner:
    llm = _make_llm(llm_response)
    return AutonomousLoopRunner(
        llm_service=llm,
        dry_run=dry_run,
        max_variants=max_variants,
        promotion_threshold=promotion_threshold,
    )


# ---------------------------------------------------------------------------
# Phase: LEARN
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_learn_returns_string_on_analyzer_failure() -> None:
    """LEARN phase must return a non-empty fallback string when services unavailable."""
    orch = _make_orchestrator()
    with patch(
        "services.knowledge.autonomous_loop.get_analyzer_service",
        side_effect=Exception("not available"),
    ):
        with patch(
            "services.knowledge.autonomous_loop.SynthesisProvenanceLog",
            side_effect=Exception("not available"),
        ):
            result = await orch._phase_learn("test-run")
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_learn_includes_analyzer_lessons() -> None:
    """LEARN phase appends AnalyzerService lessons when available."""
    orch = _make_orchestrator()
    mock_svc = MagicMock()
    mock_svc.get_lessons_context = AsyncMock(return_value="- Use semantic weight 0.8")
    with patch(
        "services.knowledge.autonomous_loop.get_analyzer_service",
        return_value=mock_svc,
    ):
        with patch(
            "services.knowledge.autonomous_loop.SynthesisProvenanceLog",
            side_effect=Exception("no redis"),
        ):
            result = await orch._phase_learn("test-run")
    assert "Use semantic weight" in result


# ---------------------------------------------------------------------------
# Phase: HYPOTHESIZE
# ---------------------------------------------------------------------------


_VALID_VARIANTS_JSON = json.dumps(
    [
        {
            "hybrid_weight_semantic": 0.7,
            "diversity_threshold": 0.3,
            "ucb1_exploration_constant": 1.5,
            "max_results_per_stage": 20,
        }
    ]
)


@pytest.mark.asyncio
async def test_hypothesize_parses_valid_llm_json() -> None:
    """HYPOTHESIZE phase parses a well-formed JSON array from the LLM."""
    orch = _make_orchestrator(llm_response=_VALID_VARIANTS_JSON)
    with patch("services.knowledge.autonomous_loop.get_rag_config") as mock_cfg:
        cfg = MagicMock()
        cfg.hybrid_weight_semantic = 0.7
        cfg.diversity_threshold = 0.3
        cfg.ucb1_exploration_constant = 1.414
        cfg.max_results_per_stage = 10
        mock_cfg.return_value = cfg
        variants = await orch._phase_hypothesize("no lessons", "run-1")

    assert isinstance(variants, list)
    assert len(variants) >= 1
    assert "hybrid_weight_semantic" in variants[0]


@pytest.mark.asyncio
async def test_hypothesize_fallback_on_invalid_llm_response() -> None:
    """HYPOTHESIZE phase uses random fallback variants when LLM returns invalid JSON."""
    orch = _make_orchestrator(llm_response="Not JSON at all")
    with patch("services.knowledge.autonomous_loop.get_rag_config") as mock_cfg:
        cfg = MagicMock()
        cfg.hybrid_weight_semantic = 0.7
        cfg.diversity_threshold = 0.3
        cfg.ucb1_exploration_constant = 1.414
        cfg.max_results_per_stage = 10
        mock_cfg.return_value = cfg
        variants = await orch._phase_hypothesize("no lessons", "run-2")

    assert isinstance(variants, list)
    assert len(variants) >= 1


@pytest.mark.asyncio
async def test_hypothesize_strips_markdown_fences() -> None:
    """HYPOTHESIZE phase strips ```json ... ``` markdown fences before parsing."""
    fenced = "```json\n" + _VALID_VARIANTS_JSON + "\n```"
    orch = _make_orchestrator(llm_response=fenced)
    with patch("services.knowledge.autonomous_loop.get_rag_config") as mock_cfg:
        cfg = MagicMock()
        cfg.hybrid_weight_semantic = 0.7
        cfg.diversity_threshold = 0.3
        cfg.ucb1_exploration_constant = 1.414
        cfg.max_results_per_stage = 10
        mock_cfg.return_value = cfg
        variants = await orch._phase_hypothesize("no lessons", "run-3")

    assert len(variants) >= 1


# ---------------------------------------------------------------------------
# Phase: EXPERIMENT
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_experiment_returns_one_result_per_variant() -> None:
    """EXPERIMENT phase returns exactly one VariantResult per input variant."""
    orch = _make_orchestrator()
    variants = [
        {
            "hybrid_weight_semantic": 0.7,
            "diversity_threshold": 0.3,
            "ucb1_exploration_constant": 1.5,
            "max_results_per_stage": 10,
        },
        {
            "hybrid_weight_semantic": 0.6,
            "diversity_threshold": 0.4,
            "ucb1_exploration_constant": 2.0,
            "max_results_per_stage": 20,
        },
    ]
    # Patch the evaluator so tests don't need ChromaDB
    orch._evaluator.score_variant = AsyncMock(side_effect=[0.8, 0.6])
    results = await orch._phase_experiment(variants)

    assert len(results) == 2
    assert results[0].composite_score == pytest.approx(0.8)
    assert results[1].composite_score == pytest.approx(0.6)


@pytest.mark.asyncio
async def test_experiment_handles_scoring_exception() -> None:
    """EXPERIMENT phase wraps exceptions and returns zero-score result."""
    orch = _make_orchestrator()
    variants = [{"hybrid_weight_semantic": 0.7, "diversity_threshold": 0.3}]
    orch._evaluator.score_variant = AsyncMock(side_effect=RuntimeError("chroma down"))
    results = await orch._phase_experiment(variants)

    assert len(results) == 1
    assert results[0].composite_score == pytest.approx(0.0)
    assert results[0].error is not None


# ---------------------------------------------------------------------------
# Phase: ANALYZE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_stores_lessons_on_improvement() -> None:
    """ANALYZE phase stores lessons when the best variant beats baseline."""
    from services.knowledge.autonomous_loop import VariantResult

    orch = _make_orchestrator()
    results = [
        VariantResult("v00", {}, 0.9, 0.9, 0.9),
        VariantResult("v01", {}, 0.7, 0.7, 0.7),
    ]

    mock_svc = MagicMock()
    mock_svc.analyze_synthesis_run = AsyncMock(return_value=[MagicMock()])
    mock_svc.store_lessons = AsyncMock()

    with patch(
        "services.knowledge.autonomous_loop.get_analyzer_service",
        return_value=mock_svc,
    ):
        count = await orch._phase_analyze(results, baseline_score=0.5, run_id="run-x")

    assert count == 1
    mock_svc.store_lessons.assert_awaited_once()


@pytest.mark.asyncio
async def test_analyze_graceful_on_failure() -> None:
    """ANALYZE phase returns 0 and doesn't raise on AnalyzerService failure."""
    from services.knowledge.autonomous_loop import VariantResult

    orch = _make_orchestrator()
    results = [VariantResult("v00", {}, 0.9, 0.9, 0.9)]

    with patch(
        "services.knowledge.autonomous_loop.get_analyzer_service",
        side_effect=Exception("analyzer down"),
    ):
        count = await orch._phase_analyze(results, 0.5, "run-fail")

    assert count == 0


@pytest.mark.asyncio
async def test_analyze_generates_lessons_when_all_variants_regress() -> None:
    """ANALYZE must produce lessons even when every variant scores below baseline.

    Regression path: score_delta < 0 → floored at _MIN_SCORE_DELTA so the
    analyzer's guard (score < _MIN_SCORE_DELTA → return []) is cleared and the
    LLM can distil "what to avoid" lessons from failed experiments.
    output_summary is also prefixed with [REGRESSION].
    """
    from services.knowledge.analyzer_service import _MIN_SCORE_DELTA
    from services.knowledge.autonomous_loop import VariantResult

    orch = _make_orchestrator()
    # All variants score below the baseline of 0.8 (delta = -0.3)
    results = [
        VariantResult("v00", {"hybrid_weight_semantic": 0.3}, 0.5, 0.5, 0.5),
        VariantResult("v01", {"hybrid_weight_semantic": 0.2}, 0.4, 0.4, 0.4),
    ]

    mock_svc = MagicMock()
    mock_svc.analyze_synthesis_run = AsyncMock(return_value=[MagicMock()])
    mock_svc.store_lessons = AsyncMock()

    with patch(
        "services.knowledge.autonomous_loop.get_analyzer_service",
        return_value=mock_svc,
    ):
        count = await orch._phase_analyze(results, baseline_score=0.8, run_id="run-regress")

    assert count == 1
    mock_svc.store_lessons.assert_awaited_once()

    # Score must be >= _MIN_SCORE_DELTA so the analyzer guard passes.
    call_kwargs = mock_svc.analyze_synthesis_run.call_args.kwargs
    assert call_kwargs["score"] >= _MIN_SCORE_DELTA
    assert call_kwargs["score"] == pytest.approx(_MIN_SCORE_DELTA)

    # Verify the regression context is prepended to the summary
    assert call_kwargs["output_summary"].startswith("[REGRESSION]")


# ---------------------------------------------------------------------------
# Phase: PROMOTE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_promote_dry_run_does_not_apply() -> None:
    """PROMOTE must NOT mutate RAGConfig when dry_run=True."""
    from services.knowledge.autonomous_loop import VariantResult

    orch = _make_orchestrator(dry_run=True, promotion_threshold=0.01)
    best = VariantResult("v00", {"hybrid_weight_semantic": 0.8}, 0.9, 0.9, 0.9)

    with patch("services.knowledge.autonomous_loop.update_rag_config") as mock_update:
        promoted = await orch._phase_promote(best, baseline_score=0.5, run_id="dr")

    assert promoted is False
    mock_update.assert_not_called()


@pytest.mark.asyncio
async def test_promote_applies_when_above_threshold() -> None:
    """PROMOTE applies params when improvement exceeds threshold and dry_run=False."""
    from services.knowledge.autonomous_loop import VariantResult

    orch = _make_orchestrator(dry_run=False, promotion_threshold=0.05)
    # 0.9 vs 0.5 baseline → 80 % improvement, well above 5 % threshold
    best = VariantResult("v00", {"hybrid_weight_semantic": 0.8}, 0.9, 0.9, 0.9)

    with (
        patch("services.knowledge.autonomous_loop.update_rag_config") as mock_update,
        patch("services.knowledge.autonomous_loop.SynthesisProvenanceLog") as MockPlog,
    ):
        MockPlog.return_value.log_run = AsyncMock()
        promoted = await orch._phase_promote(best, baseline_score=0.5, run_id="apply")

    assert promoted is True
    mock_update.assert_called_once()


@pytest.mark.asyncio
async def test_promote_stores_pending_when_below_threshold() -> None:
    """PROMOTE stores pending approval variant when below auto-promote threshold."""
    from services.knowledge.autonomous_loop import VariantResult

    orch = _make_orchestrator(dry_run=False, promotion_threshold=0.5)
    # 0.6 vs 0.5 baseline → 20 % improvement, below 50 % threshold
    best = VariantResult("v00", {"hybrid_weight_semantic": 0.75}, 0.6, 0.6, 0.6)

    with patch("services.knowledge.autonomous_loop.update_rag_config") as mock_update:
        promoted = await orch._phase_promote(best, baseline_score=0.5, run_id="pending")

    assert promoted is False
    mock_update.assert_not_called()
    assert orch._pending_approval is not None


@pytest.mark.asyncio
async def test_promote_never_promotes_degradation() -> None:
    """PROMOTE must return False when best score is <= baseline (guardrail)."""
    from services.knowledge.autonomous_loop import VariantResult

    orch = _make_orchestrator(dry_run=False, promotion_threshold=0.0)
    best = VariantResult("v00", {"hybrid_weight_semantic": 0.7}, 0.4, 0.4, 0.4)

    with patch("services.knowledge.autonomous_loop.update_rag_config") as mock_update:
        promoted = await orch._phase_promote(best, baseline_score=0.5, run_id="degrade")

    assert promoted is False
    mock_update.assert_not_called()


# ---------------------------------------------------------------------------
# approve_pending
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approve_pending_applies_and_clears() -> None:
    """approve_pending() applies the staged variant, clears in-memory, and removes Redis key."""
    orch = _make_orchestrator(dry_run=False)
    orch._pending_approval = {"hybrid_weight_semantic": 0.8}

    mock_redis = AsyncMock()
    with (
        patch("services.knowledge.autonomous_loop.update_rag_config") as mock_update,
        patch("services.knowledge.autonomous_loop.SynthesisProvenanceLog") as MockPlog,
        patch(
            "services.knowledge.autonomous_loop.get_async_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ),
    ):
        MockPlog.return_value.log_run = AsyncMock()
        result = await orch.approve_pending()

    assert result is True
    assert orch._pending_approval is None
    mock_update.assert_called_once()
    mock_redis.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_approve_pending_returns_false_when_none() -> None:
    """approve_pending() returns False when there is no pending variant."""
    orch = _make_orchestrator()
    result = await orch.approve_pending()
    assert result is False


# ---------------------------------------------------------------------------
# should_stop
# ---------------------------------------------------------------------------


def test_should_stop_false_initially() -> None:
    orch = _make_orchestrator()
    assert orch.should_stop() is False


def test_should_stop_true_after_max_rounds() -> None:
    orch = _make_orchestrator()
    orch._no_improvement_count = orch.max_no_improvement_rounds
    assert orch.should_stop() is True


# ---------------------------------------------------------------------------
# get_status
# ---------------------------------------------------------------------------


def test_get_status_returns_loop_status_object() -> None:
    orch = _make_orchestrator()
    with patch("services.knowledge.autonomous_loop.get_rag_config") as mock_cfg:
        cfg = MagicMock()
        cfg.autonomous_loop_enabled = False
        cfg.autonomous_loop_dry_run = True
        mock_cfg.return_value = cfg
        status = orch.get_status()

    assert isinstance(status, LoopStatus)
    d = status.to_dict()
    assert "enabled" in d
    assert "dry_run" in d
    assert "last_run" in d


# ---------------------------------------------------------------------------
# Full run_once (end-to-end with mocks)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_once_dry_run_produces_record() -> None:
    """Full run_once() in dry-run returns a LoopRunRecord without mutating config."""
    orch = _make_orchestrator(
        dry_run=True,
        llm_response=_VALID_VARIANTS_JSON,
    )

    # Mock evaluator
    orch._evaluator.score_variant = AsyncMock(return_value=0.75)
    orch._evaluator.score_baseline = AsyncMock(return_value=0.5)

    with (
        patch("services.knowledge.autonomous_loop.get_rag_config") as mock_cfg,
        patch("services.knowledge.autonomous_loop.get_analyzer_service", side_effect=ImportError),
        patch("services.knowledge.autonomous_loop.SynthesisProvenanceLog", side_effect=ImportError),
        patch("services.knowledge.autonomous_loop.update_rag_config") as mock_update,
    ):
        cfg = MagicMock()
        cfg.hybrid_weight_semantic = 0.7
        cfg.diversity_threshold = 0.3
        cfg.ucb1_exploration_constant = 1.414
        cfg.max_results_per_stage = 10
        mock_cfg.return_value = cfg

        record = await orch.run_once()

    assert isinstance(record, LoopRunRecord)
    assert record.dry_run is True
    assert record.variants_tested >= 1
    assert record.baseline_score == pytest.approx(0.5)
    assert record.best_score == pytest.approx(0.75)
    assert record.promoted is False  # dry_run prevents promotion
    mock_update.assert_not_called()
    assert record.finished_at != ""


@pytest.mark.asyncio
async def test_run_once_appends_to_history() -> None:
    """run_once() appends the record to the internal history list."""
    orch = _make_orchestrator(dry_run=True, llm_response=_VALID_VARIANTS_JSON)
    orch._evaluator.score_variant = AsyncMock(return_value=0.6)
    orch._evaluator.score_baseline = AsyncMock(return_value=0.5)

    assert len(orch._history) == 0
    with (
        patch("services.knowledge.autonomous_loop.get_rag_config") as mock_cfg,
        patch("services.knowledge.autonomous_loop.get_analyzer_service", side_effect=ImportError),
        patch("services.knowledge.autonomous_loop.SynthesisProvenanceLog", side_effect=ImportError),
    ):
        cfg = MagicMock()
        cfg.hybrid_weight_semantic = 0.7
        cfg.diversity_threshold = 0.3
        cfg.ucb1_exploration_constant = 1.414
        cfg.max_results_per_stage = 10
        mock_cfg.return_value = cfg
        await orch.run_once()

    assert len(orch._history) == 1


# ---------------------------------------------------------------------------
# Redis persistence (Issue #4792)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_promote_stores_pending_in_redis() -> None:
    """_phase_promote persists pending_approval to Redis when below auto-promote threshold."""
    from services.knowledge.autonomous_loop import VariantResult

    orch = _make_orchestrator(dry_run=False, promotion_threshold=0.5)
    best = VariantResult("v00", {"hybrid_weight_semantic": 0.75}, 0.6, 0.6, 0.6)

    mock_redis = AsyncMock()
    with (
        patch("services.knowledge.autonomous_loop.update_rag_config"),
        patch(
            "services.knowledge.autonomous_loop.get_async_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ),
    ):
        await orch._phase_promote(best, baseline_score=0.5, run_id="pending-redis")

    assert orch._pending_approval == best.params
    mock_redis.set.assert_awaited_once()
    call_args = mock_redis.set.call_args
    assert call_args[0][0] == "autobot:loop:pending_approval"
    stored = json.loads(call_args[0][1])
    # staged_at timestamp is injected; strip it before comparing params
    stored.pop("staged_at", None)
    assert stored == best.params
    # 7-day TTL must be set
    assert call_args[1].get("ex") == 7 * 24 * 3600


@pytest.mark.asyncio
async def test_reject_pending_clears_in_memory_and_redis() -> None:
    """reject_pending() clears _pending_approval in-memory and deletes the Redis key."""
    orch = _make_orchestrator()
    orch._pending_approval = {"hybrid_weight_semantic": 0.75}

    mock_redis = AsyncMock()
    with patch(
        "services.knowledge.autonomous_loop.get_async_redis_client",
        new=AsyncMock(return_value=mock_redis),
    ):
        result = await orch.reject_pending()

    assert result is True
    assert orch._pending_approval is None
    mock_redis.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_reject_pending_returns_false_when_none() -> None:
    """reject_pending() returns False when there is no pending variant."""
    orch = _make_orchestrator()
    result = await orch.reject_pending()
    assert result is False


@pytest.mark.asyncio
async def test_restore_state_loads_from_redis() -> None:
    """restore_state() reads persisted pending_approval from Redis and restores in-memory."""
    orch = _make_orchestrator()
    stored_params = {"hybrid_weight_semantic": 0.8, "diversity_threshold": 0.4}

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=json.dumps(stored_params))
    with patch(
        "services.knowledge.autonomous_loop.get_async_redis_client",
        new=AsyncMock(return_value=mock_redis),
    ):
        await orch.restore_state()

    assert orch._pending_approval == stored_params


@pytest.mark.asyncio
async def test_restore_state_no_op_when_redis_empty() -> None:
    """restore_state() leaves _pending_approval as None when Redis key is absent."""
    orch = _make_orchestrator()

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    with patch(
        "services.knowledge.autonomous_loop.get_async_redis_client",
        new=AsyncMock(return_value=mock_redis),
    ):
        await orch.restore_state()

    assert orch._pending_approval is None


@pytest.mark.asyncio
async def test_restore_state_graceful_on_redis_failure() -> None:
    """restore_state() silently skips when Redis is unavailable."""
    orch = _make_orchestrator()

    with patch(
        "services.knowledge.autonomous_loop.get_async_redis_client",
        new=AsyncMock(side_effect=Exception("redis down")),
    ):
        await orch.restore_state()  # must not raise

    assert orch._pending_approval is None


# ---------------------------------------------------------------------------
# _running flag — Issue #4937
# ---------------------------------------------------------------------------


def test_running_starts_false() -> None:
    """_running is False immediately after construction."""
    orch = _make_orchestrator()
    assert orch._running is False


@pytest.mark.asyncio
async def test_running_true_during_run_once(monkeypatch) -> None:
    """_running is True while run_once() is executing."""
    orch = _make_orchestrator()
    running_during = []

    async def fake_phase_learn(_run_id) -> None:
        running_during.append(orch._running)
        raise RuntimeError("stop early")

    monkeypatch.setattr(orch, "_phase_learn", fake_phase_learn)
    with patch(
        "services.knowledge.autonomous_loop.get_async_redis_client",
        new=AsyncMock(return_value=None),
    ):
        await orch.run_once()

    assert running_during == [True], "_running must be True inside run_once"


@pytest.mark.asyncio
async def test_running_false_after_run_once() -> None:
    """_running is reset to False after run_once() completes."""
    orch = _make_orchestrator()

    with patch.object(orch, "_phase_learn", new=AsyncMock(side_effect=RuntimeError("abort"))):
        with patch(
            "services.knowledge.autonomous_loop.get_async_redis_client",
            new=AsyncMock(return_value=None),
        ):
            await orch.run_once()

    assert orch._running is False


@pytest.mark.asyncio
async def test_get_loop_orchestrator_returns_singleton_when_running() -> None:
    """get_loop_runner() returns existing instance when _running=True."""
    import services.knowledge.autonomous_loop as mod

    original = mod._loop_orchestrator
    try:
        existing = _make_orchestrator()
        existing._running = True
        mod._loop_orchestrator = existing

        result = await get_loop_runner(llm_service=MagicMock())
        assert result is existing
    finally:
        mod._loop_orchestrator = original


@pytest.mark.asyncio
async def test_get_loop_orchestrator_replaces_when_not_running() -> None:
    """get_loop_runner() replaces the singleton when _running=False."""
    import services.knowledge.autonomous_loop as mod

    original = mod._loop_orchestrator
    try:
        existing = _make_orchestrator()
        existing._running = False
        existing._llm = None  # triggers the None-llm replacement path
        mod._loop_orchestrator = existing

        new_llm = MagicMock()
        with patch.object(
            AutonomousLoopRunner,
            "restore_state",
            new=AsyncMock(),
        ):
            result = await get_loop_runner(llm_service=new_llm)

        assert result is not existing
        assert result._llm is new_llm
    finally:
        mod._loop_orchestrator = original
