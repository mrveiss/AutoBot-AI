# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for self-improvement write path wiring (#10602).

Verifies that _record_outcome_for_learning:
- Calls TaskOutcomeJudge.evaluate_task_outcome (persists outcome to Redis write path).
- Calls TaskPatternLearner.learn_from_outcomes when MIN_OUTCOMES_TO_LEARN is reached.
- Errors are swallowed — never break workflow execution.
- SELF_IMPROVEMENT_ENABLED=false → task is never scheduled (no-op).
"""

from __future__ import annotations

import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestration.workflow_runner import WorkflowRunner


def _make_plan(goal: str = "test goal", strategy: str = "sequential") -> types.SimpleNamespace:
    return types.SimpleNamespace(
        plan_id="plan-1",
        goal=goal,
        strategy=types.SimpleNamespace(value=strategy),
        tasks=[],
        task_type=None,
    )


def _make_result(success: bool = True) -> dict:
    return {"success": success, "results": {"out": "value"}, "execution_time": 1.0}


class TestRecordOutcomeForLearning:
    @pytest.mark.asyncio
    async def test_evaluate_task_outcome_called(self):
        """evaluate_task_outcome is called with plan data — write path fires."""
        plan = _make_plan("analyse logs")

        fake_judgment = MagicMock(overall_score=0.8)
        mock_judge = AsyncMock()
        mock_judge.evaluate_task_outcome = AsyncMock(return_value=fake_judgment)
        mock_judge.get_outcomes = AsyncMock(return_value=[])  # not enough to learn

        mock_learner = AsyncMock()
        mock_learner.learn_from_outcomes = AsyncMock()

        with (
            patch("orchestration.workflow_runner._get_task_outcome_judge", return_value=mock_judge),
            patch(
                "orchestration.workflow_runner._get_task_pattern_learner",
                return_value=(0, mock_learner),
            ),
        ):
            await WorkflowRunner._record_outcome_for_learning(object(), plan, _make_result())

        mock_judge.evaluate_task_outcome.assert_called_once()
        call_kwargs = mock_judge.evaluate_task_outcome.call_args
        assert call_kwargs.kwargs["goal"] == "analyse logs"
        assert call_kwargs.kwargs["strategy_used"] == "sequential"

    @pytest.mark.asyncio
    async def test_learn_from_outcomes_called_when_threshold_met(self):
        """learn_from_outcomes is called when MIN_OUTCOMES_TO_LEARN outcomes exist."""
        from agents.task_pattern_learner import MIN_OUTCOMES_TO_LEARN

        plan = _make_plan()

        fake_judgment = MagicMock(overall_score=0.9)
        fake_outcomes = [
            types.SimpleNamespace(
                score=0.8, task_type="t", goal="g", output_summary="o", strategy_used="s", rationale="r", timestamp="ts"
            )
            for _ in range(MIN_OUTCOMES_TO_LEARN)
        ]

        mock_judge_inst = AsyncMock()
        mock_judge_inst.evaluate_task_outcome = AsyncMock(return_value=fake_judgment)
        mock_judge_inst.get_outcomes = AsyncMock(return_value=fake_outcomes)

        mock_learner_inst = AsyncMock()
        mock_learner_inst.learn_from_outcomes = AsyncMock(return_value=None)

        with (
            patch(
                "orchestration.workflow_runner._get_task_outcome_judge",
                return_value=mock_judge_inst,
            ),
            patch(
                "orchestration.workflow_runner._get_task_pattern_learner",
                return_value=(MIN_OUTCOMES_TO_LEARN, mock_learner_inst),
            ),
        ):
            await WorkflowRunner._record_outcome_for_learning(object(), plan, _make_result())

        mock_learner_inst.learn_from_outcomes.assert_called_once()
        _, outcomes_arg = mock_learner_inst.learn_from_outcomes.call_args.args
        assert len(outcomes_arg) == MIN_OUTCOMES_TO_LEARN

    @pytest.mark.asyncio
    async def test_learn_not_called_when_below_threshold(self):
        """learn_from_outcomes is NOT called when outcomes < MIN_OUTCOMES_TO_LEARN."""
        from agents.task_pattern_learner import MIN_OUTCOMES_TO_LEARN

        plan = _make_plan()
        fake_judgment = MagicMock(overall_score=0.5)
        # Return one fewer than the minimum
        fake_outcomes = [
            types.SimpleNamespace(
                score=0.5, task_type="t", goal="g", output_summary="o", strategy_used="s", rationale="r", timestamp="ts"
            )
            for _ in range(MIN_OUTCOMES_TO_LEARN - 1)
        ]

        mock_judge_inst = AsyncMock()
        mock_judge_inst.evaluate_task_outcome = AsyncMock(return_value=fake_judgment)
        mock_judge_inst.get_outcomes = AsyncMock(return_value=fake_outcomes)

        mock_learner_inst = AsyncMock()
        mock_learner_inst.learn_from_outcomes = AsyncMock()

        with (
            patch(
                "orchestration.workflow_runner._get_task_outcome_judge",
                return_value=mock_judge_inst,
            ),
            patch(
                "orchestration.workflow_runner._get_task_pattern_learner",
                return_value=(MIN_OUTCOMES_TO_LEARN, mock_learner_inst),
            ),
        ):
            await WorkflowRunner._record_outcome_for_learning(object(), plan, _make_result())

        mock_learner_inst.learn_from_outcomes.assert_not_called()

    @pytest.mark.asyncio
    async def test_errors_swallowed(self):
        """Any exception in outcome recording must not propagate."""
        plan = _make_plan()

        with patch(
            "orchestration.workflow_runner._get_task_outcome_judge",
            side_effect=RuntimeError("redis down"),
        ):
            # Must not raise
            await WorkflowRunner._record_outcome_for_learning(object(), plan, _make_result())

    @pytest.mark.asyncio
    async def test_flag_off_skips_task_creation(self, monkeypatch):
        """SELF_IMPROVEMENT_ENABLED=false → asyncio.create_task never called."""
        monkeypatch.setattr("orchestration.workflow_runner.SELF_IMPROVEMENT_ENABLED", False)

        created_tasks = []

        def _fake_create_task(coro, **kwargs):
            created_tasks.append(coro)
            # Close coro to avoid warnings
            coro.close()
            return MagicMock()

        # We need a minimal runner with enough attrs to call the method.
        plan = _make_plan()

        with patch("orchestration.workflow_runner.asyncio.create_task", side_effect=_fake_create_task):
            # Import and monkey-patch the success handler.
            runner = MagicMock()
            runner._evaluate_workflow_criteria = AsyncMock(return_value={"overall": "full", "score": 1.0})
            runner._perf = MagicMock()
            runner._perf.update_from_plan = MagicMock()
            runner._publish_workflow_event = AsyncMock()
            runner._strategy_planner = MagicMock()
            runner._strategy_planner.summarize_results = MagicMock(return_value="ok")
            runner._capture_trajectory = AsyncMock()

            import time

            await WorkflowRunner._handle_workflow_execution_success(runner, plan, {}, time.time())

        assert created_tasks == [], "create_task should not be called when flag is off"
