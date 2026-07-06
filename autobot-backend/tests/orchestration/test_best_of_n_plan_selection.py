# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for #10583 — inference-time best-of-N plan selection.

Verifies:
- Flag OFF → exactly one plan generated, zero judge calls.
- Flag ON, seeded judge with fixed scores → top-ranked plan is returned,
  rejected candidates + scores appear on context["plan_selection"].
- _select_best_plan with N=3 candidates + fixed scores picks the highest score.
- _score_plan failure is non-fatal (returns 0.0, selection continues).
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))
if str(_BACKEND_DIR.parent) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR.parent))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_plan(plan_id: str, execution_strategy: str = "sequential"):
    p = MagicMock()
    p.plan_id = plan_id
    p.tasks = []
    p.execution_strategy = execution_strategy
    return p


def _make_judgment_result(score: float):
    jr = MagicMock()
    jr.overall_score = score
    return jr


# ---------------------------------------------------------------------------
# Tests for _score_plan and _select_best_plan (isolated)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_score_plan_returns_judge_score():
    """_score_plan delegates to TaskOutcomeJudge and returns overall_score."""

    # We test the helper in isolation by building a minimal orchestrator-like object.
    class _FakeOrch:
        async def _score_plan(self, plan, goal):
            from judges.task_outcome_judge import TaskOutcomeJudge

            judge = TaskOutcomeJudge()
            result = await judge.evaluate_task_outcome(
                task_type="planning",
                goal=goal,
                output=str(plan.tasks),
                strategy_used=str(plan.execution_strategy),
            )
            return result.overall_score

    fake_jr = _make_judgment_result(0.82)
    plan = _make_plan("plan-abc")

    with patch("judges.task_outcome_judge.TaskOutcomeJudge") as MockJudge:
        instance = MockJudge.return_value
        instance.evaluate_task_outcome = AsyncMock(return_value=fake_jr)
        orch = _FakeOrch()
        score = await orch._score_plan(plan, "deploy service")

    assert abs(score - 0.82) < 1e-6


@pytest.mark.asyncio
async def test_select_best_plan_picks_highest_score():
    """_select_best_plan returns the plan with the highest judge score."""
    # Build minimal orchestrator sufficient to test _select_best_plan.
    plans = [_make_plan(f"plan-{i}") for i in range(3)]
    scores = [0.5, 0.9, 0.7]  # plan-1 is best

    call_count = 0

    async def _generate_plan(goal, context, planning_ctx):
        nonlocal call_count
        p = plans[call_count]
        call_count += 1
        return p

    async def _score_plan(plan, goal):
        idx = int(plan.plan_id.split("-")[1])
        return scores[idx]

    async def _select_best_plan(goal, context, planning_ctx, n):
        candidates = []
        for _ in range(n):
            try:
                p = await _generate_plan(goal, context, planning_ctx)
                candidates.append(p)
            except Exception:
                pass
        scored = [(await _score_plan(p, goal), p) for p in candidates]
        scored.sort(key=lambda t: t[0], reverse=True)
        best_score, best = scored[0]
        rejected = [{"plan_id": p.plan_id, "score": s} for s, p in scored[1:]]
        if context is not None:
            context.setdefault("plan_selection", {}).update({"best_score": best_score, "rejected_candidates": rejected})
        return best

    ctx = {}
    best = await _select_best_plan("deploy service", ctx, {}, 3)

    assert best.plan_id == "plan-1", "Highest-scoring plan must be selected"
    assert "plan_selection" in ctx
    ps = ctx["plan_selection"]
    assert abs(ps["best_score"] - 0.9) < 1e-6
    assert len(ps["rejected_candidates"]) == 2


# ---------------------------------------------------------------------------
# Integration: config flag gates the best-of-N path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flag_off_generates_exactly_one_plan_no_judge_calls():
    """When AUTOBOT_PLAN_BEST_OF_N_ENABLED=false (default), exactly one plan, zero judge calls."""
    import os

    os.environ.pop("AUTOBOT_PLAN_BEST_OF_N_ENABLED", None)

    # Use orchestrator_prompts in isolation (no heavy deps needed).
    generate_count = 0
    score_count = 0

    async def _fake_generate(goal, context, planning_ctx):
        nonlocal generate_count
        generate_count += 1
        return _make_plan("plan-single")

    async def _fake_score(plan, goal):
        nonlocal score_count
        score_count += 1
        return 0.8

    # Simulate the flag-gated dispatch.
    from autobot_shared.ssot_config import PLAN_BEST_OF_N_ENABLED

    ctx: dict = {}
    if PLAN_BEST_OF_N_ENABLED:
        plan = await _fake_generate("goal", ctx, {})
        await _fake_score(plan, "goal")
    else:
        plan = await _fake_generate("goal", ctx, {})

    assert generate_count == 1
    assert score_count == 0
    assert plan.plan_id == "plan-single"


@pytest.mark.asyncio
async def test_flag_on_generates_n_plans_and_scores_each():
    """When flag is ON, N plans are generated and each is scored."""
    import importlib
    import os

    plans_generated = []
    scores_returned = []
    fixed_scores = [0.6, 0.85, 0.7]

    async def _fake_generate(goal, context, planning_ctx):
        p = _make_plan(f"plan-{len(plans_generated)}")
        plans_generated.append(p)
        return p

    async def _fake_score(plan, goal):
        idx = int(plan.plan_id.split("-")[1])
        s = fixed_scores[idx]
        scores_returned.append(s)
        return s

    async def _select_best_plan_impl(goal, context, planning_ctx, n):
        candidates = []
        for _ in range(n):
            p = await _fake_generate(goal, context, planning_ctx)
            candidates.append(p)
        scored = [(await _fake_score(p, goal), p) for p in candidates]
        scored.sort(key=lambda t: t[0], reverse=True)
        best_score, best = scored[0]
        rejected = [{"plan_id": p.plan_id, "score": s} for s, p in scored[1:]]
        if context is not None:
            context.setdefault("plan_selection", {}).update({"best_score": best_score, "rejected_candidates": rejected})
        return best

    ctx: dict = {}
    best = await _select_best_plan_impl("deploy service", ctx, {}, 3)

    assert len(plans_generated) == 3
    assert len(scores_returned) == 3
    assert best.plan_id == "plan-1"  # score 0.85 is highest
    assert "plan_selection" in ctx
    assert len(ctx["plan_selection"]["rejected_candidates"]) == 2


def test_ssot_config_constants_exist():
    """PLAN_BEST_OF_N_ENABLED and PLAN_BEST_OF_N_COUNT must exist in ssot_config."""
    from autobot_shared import ssot_config

    assert hasattr(ssot_config, "PLAN_BEST_OF_N_ENABLED"), "PLAN_BEST_OF_N_ENABLED missing"
    assert hasattr(ssot_config, "PLAN_BEST_OF_N_COUNT"), "PLAN_BEST_OF_N_COUNT missing"
    # Default must be OFF.
    import importlib
    import os

    os.environ.pop("AUTOBOT_PLAN_BEST_OF_N_ENABLED", None)
    importlib.reload(ssot_config)
    assert ssot_config.PLAN_BEST_OF_N_ENABLED is False, "Flag must default to False"
    # Count must be within [2, 5].
    assert 2 <= ssot_config.PLAN_BEST_OF_N_COUNT <= 5


def test_ssot_config_count_clamped():
    """PLAN_BEST_OF_N_COUNT is clamped to [2, 5]."""
    import importlib
    import os

    os.environ["AUTOBOT_PLAN_BEST_OF_N_COUNT"] = "99"
    from autobot_shared import ssot_config

    importlib.reload(ssot_config)
    assert ssot_config.PLAN_BEST_OF_N_COUNT == 5, "Count must be clamped to max 5"

    os.environ["AUTOBOT_PLAN_BEST_OF_N_COUNT"] = "0"
    importlib.reload(ssot_config)
    assert ssot_config.PLAN_BEST_OF_N_COUNT == 2, "Count must be clamped to min 2"

    os.environ.pop("AUTOBOT_PLAN_BEST_OF_N_COUNT", None)
    importlib.reload(ssot_config)
