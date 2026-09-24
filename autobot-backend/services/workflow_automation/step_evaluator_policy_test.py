# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
A judge nobody could read must not silently approve the step (#17307).

The defect: ``judges/__init__.py`` indexed required keys out of a single-shot
reply, a ``KeyError`` became an error judgment, and ``_check_judge_errors``
turned that into ``should_proceed: True`` with a ``logger.warning``. An
approval-by-default and an approval-by-judgment were the same payload, so
nothing downstream could tell them apart and no metric counted them.

These tests hold the two halves of the fix: the outcome follows a named
policy, and the payload says which one happened either way.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import judges
from judges import DEGRADATION_EVALUATION_ERROR, DEGRADATION_JUDGE_UNAVAILABLE, ERROR_MODEL_SENTINEL
from services.workflow_automation.step_evaluator import WorkflowStepEvaluator


def _judgment(model_used: str, reasoning: str = "could not parse the judge reply") -> MagicMock:
    """A judgment double: ``llm_model_used`` is the sentinel the gate reads."""
    judgment = MagicMock()
    judgment.llm_model_used = model_used
    judgment.reasoning = reasoning
    return judgment


@pytest.fixture
def evaluator() -> WorkflowStepEvaluator:
    """An evaluator with no judges wired -- these tests drive the gate directly."""
    return WorkflowStepEvaluator()


@pytest.fixture(autouse=True)
def _no_metrics_backend():
    """Keep the metric calls from reaching a real registry in unit tests."""
    with patch("services.workflow_automation.step_evaluator.get_metrics_manager") as factory:
        yield factory


# ------------------------------------------------------ the fail-open default


def test_an_unreadable_judge_approves_by_default_but_says_so(evaluator):
    judgments = (_judgment(ERROR_MODEL_SENTINEL), _judgment("gpt-4o-mini"))

    with patch.object(judges, "JUDGE_FAIL_CLOSED", False):
        result = evaluator._check_judge_errors(judgments, "step-1")

    assert result["should_proceed"] is True
    assert result["judge_available"] is False
    assert result["degradation"] == DEGRADATION_JUDGE_UNAVAILABLE
    assert result["fail_closed"] is False


def test_the_degraded_approval_is_distinguishable_from_a_judgment(evaluator):
    """The point of #17307: a consumer can branch on this without parsing prose."""
    with patch.object(judges, "JUDGE_FAIL_CLOSED", False):
        degraded = evaluator._check_judge_errors((_judgment(ERROR_MODEL_SENTINEL),), "step-1")

    healthy = evaluator._check_judge_errors((_judgment("gpt-4o-mini"),), "step-1")

    assert healthy is None  # no degradation -> the real judgment path runs
    assert degraded["judge_available"] is False


def test_the_outcome_and_its_cause_are_both_counted(evaluator, _no_metrics_backend):
    metrics = _no_metrics_backend.return_value

    with patch.object(judges, "JUDGE_FAIL_CLOSED", False):
        evaluator._check_judge_errors((_judgment(ERROR_MODEL_SENTINEL),), "step-1")

    metrics.record_workflow_approval.assert_called_once_with("step_evaluation", "approved_judge_unavailable")
    metrics.record_error.assert_called_once_with(
        DEGRADATION_JUDGE_UNAVAILABLE, "workflow_step_evaluator", "approved_judge_unavailable"
    )


def test_a_metrics_backend_that_is_down_does_not_break_the_step(evaluator, _no_metrics_backend):
    _no_metrics_backend.side_effect = RuntimeError("no registry")

    with patch.object(judges, "JUDGE_FAIL_CLOSED", False):
        result = evaluator._check_judge_errors((_judgment(ERROR_MODEL_SENTINEL),), "step-1")

    assert result["should_proceed"] is True


# ------------------------------------------------------------- fail-closed


def test_fail_closed_holds_the_step_instead_of_approving_it(evaluator):
    with patch.object(judges, "JUDGE_FAIL_CLOSED", True):
        result = evaluator._check_judge_errors((_judgment(ERROR_MODEL_SENTINEL),), "step-1")

    assert result["should_proceed"] is False
    assert result["fail_closed"] is True
    assert result["degradation"] == DEGRADATION_JUDGE_UNAVAILABLE
    assert "Held" in result["reason"]


def test_fail_closed_counts_the_block_under_its_own_decision_label(evaluator, _no_metrics_backend):
    metrics = _no_metrics_backend.return_value

    with patch.object(judges, "JUDGE_FAIL_CLOSED", True):
        evaluator._check_judge_errors((_judgment(ERROR_MODEL_SENTINEL),), "step-1")

    metrics.record_workflow_approval.assert_called_once_with("step_evaluation", "blocked_judge_unavailable")


# ---------------------------------------------- a healthy judge is untouched


def test_healthy_judgments_are_not_intercepted(evaluator):
    assert evaluator._check_judge_errors((_judgment("gpt-4o-mini"), _judgment("claude")), "step-1") is None


# --------------------------------------- the evaluator's own failure path


def test_an_evaluator_crash_follows_the_same_policy(evaluator):
    """#17307: this returned a bare `should_proceed: True` for any exception."""
    with patch.object(judges, "JUDGE_FAIL_CLOSED", False):
        open_result = evaluator._build_evaluation_error_response(RuntimeError("boom"), "step-9")
    with patch.object(judges, "JUDGE_FAIL_CLOSED", True):
        closed_result = evaluator._build_evaluation_error_response(RuntimeError("boom"), "step-9")

    assert open_result["should_proceed"] is True
    assert closed_result["should_proceed"] is False
    for result in (open_result, closed_result):
        assert result["degradation"] == DEGRADATION_EVALUATION_ERROR
        assert result["judge_available"] is False
        assert "boom" in result["reason"]


def test_judges_disabled_is_not_a_degradation(evaluator):
    """Judges switched off is a configuration, not a failure to read one."""
    evaluator.judges_enabled = False

    # evaluate_step short-circuits before any judge runs; the payload it
    # returns must not claim a degradation that did not happen.
    import asyncio

    result = asyncio.run(evaluator.evaluate_step(MagicMock(), MagicMock()))

    assert result["should_proceed"] is True
    assert "degradation" not in result
