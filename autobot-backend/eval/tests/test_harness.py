# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Trajectory-eval harness tests (GH#10546).

The RLM scorer is mocked at ``ResponseQualityEvaluator._call_llm`` so every
assertion is deterministic (no live model).  The mock returns a SCORE line
keyed on the response text, letting us model a "good" candidate (matches
baseline) and a "deliberately worse" candidate (drops below baseline) — the
latter must be reported as a regression.
"""

from unittest.mock import AsyncMock

import pytest

from eval.candidates import baseline_candidate
from eval.report import RegressionReport, TrajectoryOutcome
from eval.runner import CandidateResult, TrajectoryReplayer
from eval.store import GoldenTrajectory, load_golden_set
from rlm.evaluator import ResponseQualityEvaluator


def _golden(tid: str = "t1", task_class: str = "code_fix", baseline: float = 0.9) -> GoldenTrajectory:
    return GoldenTrajectory(
        trajectory_id=tid,
        task_class=task_class,
        inputs={"prompt": "add a null guard"},
        expected_tools=["read_file", "edit_file", "run_tests"],
        baseline_score=baseline,
        expected_status="completed",
        expected_output_excerpt="Added guard; tests pass.",
    )


def _scorer(score: float) -> ResponseQualityEvaluator:
    """Evaluator whose LLM always returns *score* (deterministic)."""
    evaluator = ResponseQualityEvaluator()
    evaluator._call_llm = AsyncMock(return_value=f"SCORE: {score}\nCRITIQUE: None\nHINT: None")
    return evaluator


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


def test_seed_golden_set_loads():
    """The shipped seed goldens load and expose task-classes + tools."""
    goldens = load_golden_set()
    assert len(goldens) >= 2
    assert all(g.task_class for g in goldens)
    assert all(g.expected_tools for g in goldens)
    assert {g.task_class for g in goldens} >= {"code_fix", "knowledge_qa"}


# ---------------------------------------------------------------------------
# Runner — happy path (candidate matches baseline)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_golden_replay_produces_report_no_regression():
    """A candidate reproducing the golden outcome yields zero regressions."""
    replayer = TrajectoryReplayer(evaluator=_scorer(0.9))
    report = await replayer.run([_golden()], baseline_candidate)

    assert isinstance(report, RegressionReport)
    assert report.total_regressions == 0
    assert "code_fix" in report.per_class()
    assert report.per_class()["code_fix"].total == 1


# ---------------------------------------------------------------------------
# Runner — deliberately-worse candidate is caught (core acceptance test)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_worse_quality_score_flagged_as_regression():
    """A candidate whose RLM score drops below baseline is a regression."""
    replayer = TrajectoryReplayer(evaluator=_scorer(0.4))  # baseline is 0.9
    report = await replayer.run([_golden()], baseline_candidate)

    assert report.has_regressions
    assert report.total_regressions == 1
    assert report.per_class()["code_fix"].regressions == 1


@pytest.mark.asyncio
async def test_wrong_tool_sequence_flagged_as_regression():
    """A candidate that skips an expected tool is a hard regression."""

    async def broken_candidate(golden: GoldenTrajectory) -> CandidateResult:
        return CandidateResult(response_text="did it", tool_sequence=["read_file"], final_status="completed")

    replayer = TrajectoryReplayer(evaluator=_scorer(0.95))  # quality fine, tools wrong
    report = await replayer.run([_golden()], broken_candidate)

    assert report.has_regressions
    outcome = report.outcomes[0]
    assert outcome.classify() == "regression"
    assert not outcome.tools_ok
    assert "tools expected" in outcome.detail


# ---------------------------------------------------------------------------
# Report — regressions vs improvements distinguished per task-class
# ---------------------------------------------------------------------------


def test_report_distinguishes_regression_and_improvement_per_class():
    """Per-task-class buckets split regressions from improvements."""
    outcomes = [
        TrajectoryOutcome("a", "code_fix", baseline_score=0.9, candidate_score=0.5, tools_ok=True, status_ok=True),
        TrajectoryOutcome("b", "code_fix", baseline_score=0.6, candidate_score=0.9, tools_ok=True, status_ok=True),
        TrajectoryOutcome("c", "qa", baseline_score=0.8, candidate_score=0.81, tools_ok=True, status_ok=True),
    ]
    report = RegressionReport(outcomes=outcomes)

    per_class = report.per_class()
    assert per_class["code_fix"].regressions == 1
    assert per_class["code_fix"].improvements == 1
    assert per_class["qa"].unchanged == 1
    assert report.total_regressions == 1
    assert report.total_improvements == 1

    rendered = report.render_markdown()
    assert "1 regressions, 1 improvements" in rendered
    assert "code_fix" in rendered


def test_worse_prompt_candidate_end_to_end(tmp_path):
    """Integration: a worse-prompt candidate flips a golden to regression.

    Models a prompt change (`candidate_v2`) that no longer instructs the
    agent to run tests — it drops the `run_tests` tool, which the harness
    flags as a regression versus the golden baseline.
    """
    import asyncio

    async def worse_prompt_candidate(golden: GoldenTrajectory) -> CandidateResult:
        # Prompt change silently stopped running tests.
        return CandidateResult(
            response_text="Edited the file.",
            tool_sequence=["read_file", "edit_file"],
            final_status="completed",
        )

    replayer = TrajectoryReplayer(evaluator=_scorer(0.9))
    report = asyncio.run(replayer.run([_golden()], worse_prompt_candidate))

    assert report.has_regressions
    out = tmp_path / "report.json"
    import json

    out.write_text(json.dumps(report.to_dict()), encoding="utf-8")
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["summary"]["regressions"] == 1
