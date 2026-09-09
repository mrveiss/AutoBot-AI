# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""What CI actually replays against, as opposed to what the harness can detect (#16157).

`test_harness.py` already proves the replayer reports a regression when a
candidate deviates -- wrong tool sequence, worse score. Those tests pass and
have always passed, and they are the reason nobody looked at the layer below.

The gap they cannot see is which candidate CI hands the replayer. It hands the
self-consistency baseline, which replays each golden's *own* recorded outcome,
so every comparison is a file against itself and no input can make it red. The
detection works; the thing being detected is absent.

So these tests assert at the wiring layer rather than the unit layer: that a
real candidate's answers have a different origin from the golden's expectations,
that a missing recording is not silently a pass, and that the run refuses to
call the echo a measurement.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from eval.candidates import RecordingMissing, baseline_candidate
from eval.run import resolve_candidate
from eval.runner import TrajectoryReplayer
from eval.store import GoldenTrajectory
from rlm.evaluator import ResponseQualityEvaluator

EXPECTED_TOOLS = ["read_file", "edit_file", "run_tests"]


def _golden(tid: str = "t1") -> GoldenTrajectory:
    return GoldenTrajectory(
        trajectory_id=tid,
        task_class="code_fix",
        inputs={"prompt": "add a null guard"},
        expected_tools=list(EXPECTED_TOOLS),
        baseline_score=0.9,
        expected_status="completed",
        expected_output_excerpt="Added guard; tests pass.",
    )


def _scorer(score: float) -> ResponseQualityEvaluator:
    evaluator = ResponseQualityEvaluator()
    evaluator._call_llm = AsyncMock(return_value=f"SCORE: {score}\nCRITIQUE: None\nHINT: None")
    return evaluator


def _write_recording(directory: Path, tid: str, tools: list[str]) -> None:
    """A recorded run in the shape the candidate reads: events, text, status."""
    events = [{"type": "tool_call", "tool": name} for name in tools]
    payload = {"events": events, "output_text": "Added guard; tests pass.", "final_status": "completed"}
    (directory / f"{tid}.json").write_text(json.dumps(payload), encoding="utf-8")


# ---------------------------------------------------------------------------
# Which candidate the run resolves
# ---------------------------------------------------------------------------


def test_an_empty_recorded_dir_resolves_to_the_echo_and_admits_it(tmp_path: Path) -> None:
    """The fallback is allowed; reporting it as a real measurement is not."""
    candidate, is_real = resolve_candidate(tmp_path)

    assert candidate is baseline_candidate
    assert is_real is False, "the self-consistency baseline must not be reported as a real candidate"


def test_a_populated_recorded_dir_resolves_to_a_real_candidate(tmp_path: Path) -> None:
    _write_recording(tmp_path, "t1", EXPECTED_TOOLS)

    candidate, is_real = resolve_candidate(tmp_path)

    assert candidate is not baseline_candidate
    assert is_real is True


def test_a_missing_directory_is_not_treated_as_an_empty_measurement(tmp_path: Path) -> None:
    """A path that does not exist is the same as no recordings, not a clean run."""
    _, is_real = resolve_candidate(tmp_path / "does-not-exist")

    assert is_real is False


# ---------------------------------------------------------------------------
# The property that makes a comparison mean anything
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_recorded_candidate_can_disagree_with_the_golden(tmp_path: Path) -> None:
    """The falsifiability proof this layer was missing.

    `test_harness.py` proves the replayer flags a wrong tool sequence when a
    stub supplies one. This proves the *shipped* candidate can supply one: the
    recording drops `run_tests`, and because its tool sequence comes from the
    recorded events rather than from `golden.expected_tools`, the two disagree.
    Against `baseline_candidate` this same golden cannot fail at all.
    """
    _write_recording(tmp_path, "t1", ["read_file", "edit_file"])  # run_tests never happened
    candidate, is_real = resolve_candidate(tmp_path)
    assert is_real

    replayer = TrajectoryReplayer(evaluator=_scorer(0.95))  # quality fine, tools wrong
    report = await replayer.run([_golden()], candidate)

    assert report.has_regressions, "a recorded run that skipped a tool must be a regression"
    outcome = report.outcomes[0]
    assert not outcome.tools_ok
    assert "tools expected" in outcome.detail


@pytest.mark.asyncio
async def test_a_faithful_recording_is_not_a_regression(tmp_path: Path) -> None:
    """The contrast pair: the same wiring must not flag a run that matches."""
    _write_recording(tmp_path, "t1", EXPECTED_TOOLS)
    candidate, _ = resolve_candidate(tmp_path)

    replayer = TrajectoryReplayer(evaluator=_scorer(0.95))
    report = await replayer.run([_golden()], candidate)

    assert not report.has_regressions
    assert report.total_regressions == 0


@pytest.mark.asyncio
async def test_a_golden_with_no_recording_is_not_a_pass(tmp_path: Path) -> None:
    """Absence of evidence must be distinguishable from a clean trajectory.

    Falling back to the golden's own values here is exactly the defect this
    module exists to prevent, one trajectory at a time instead of all of them.
    """
    _write_recording(tmp_path, "t1", EXPECTED_TOOLS)
    candidate, _ = resolve_candidate(tmp_path)

    with pytest.raises(RecordingMissing):
        await candidate(_golden("never-recorded"))


@pytest.mark.asyncio
async def test_the_echo_cannot_fail_which_is_why_it_is_not_a_measurement() -> None:
    """Pins the premise of #16157 so it cannot rot into a claim nobody rechecks.

    A golden whose expectations are wrong in every way still passes against the
    baseline candidate, because the candidate answers with those same
    expectations. If this ever starts failing, the baseline has stopped being a
    self-consistency check and this module's reasoning needs revisiting.
    """
    golden = _golden()
    golden.expected_tools = ["a_tool_that_does_not_exist", "nor_this_one"]

    replayer = TrajectoryReplayer(evaluator=_scorer(0.95))
    report = await replayer.run([golden], baseline_candidate)

    assert not report.has_regressions, "the baseline candidate is expected to be unfalsifiable"
