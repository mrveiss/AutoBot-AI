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
from eval.report import RegressionReport, TrajectoryOutcome
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


# ---------------------------------------------------------------------------
# "Could not judge" is not "judged and failed"
# ---------------------------------------------------------------------------


def test_an_unscoreable_trajectory_is_unmeasured_not_a_regression() -> None:
    """The evaluator's INDETERMINATE must not arrive as quality drift.

    Its pass-through default is 0.7; goldens carry a 0.9 baseline. Arithmetically
    that is a regression, and reporting it as one means an evaluator outage reads
    as the candidate getting worse.
    """
    outcome = TrajectoryOutcome(
        trajectory_id="t1",
        task_class="code_fix",
        baseline_score=0.9,
        candidate_score=0.7,
        tools_ok=True,
        status_ok=True,
        score_indeterminate=True,
    )

    assert outcome.classify() == "unmeasured"
    assert RegressionReport([outcome]).total_unmeasured == 1
    assert not RegressionReport([outcome]).has_regressions


def test_a_broken_tool_sequence_is_still_a_regression_when_unscoreable() -> None:
    """The deterministic half does not need the scorer and must survive it.

    Tool and status comparisons are computed locally, so an evaluator outage
    must not launder a genuinely wrong tool sequence into "unmeasured".
    """
    outcome = TrajectoryOutcome(
        trajectory_id="t1",
        task_class="code_fix",
        baseline_score=0.9,
        candidate_score=0.7,
        tools_ok=False,
        status_ok=True,
        score_indeterminate=True,
    )

    assert outcome.classify() == "regression"
    assert RegressionReport([outcome]).has_regressions


def test_a_real_score_drop_is_still_a_regression() -> None:
    """The contrast pair: `unmeasured` must not swallow genuine drift."""
    outcome = TrajectoryOutcome(
        trajectory_id="t1",
        task_class="code_fix",
        baseline_score=0.9,
        candidate_score=0.7,
        tools_ok=True,
        status_ok=True,
        score_indeterminate=False,
    )

    assert outcome.classify() == "regression"


def test_the_report_says_unmeasured_out_loud() -> None:
    """A reader must not have to infer it from a table column."""
    outcome = TrajectoryOutcome(
        trajectory_id="t1",
        task_class="code_fix",
        baseline_score=0.9,
        candidate_score=0.7,
        tools_ok=True,
        status_ok=True,
        score_indeterminate=True,
    )

    rendered = RegressionReport([outcome]).render_markdown()

    assert "unmeasured" in rendered.lower()
    assert "could not be scored" in rendered


# ---------------------------------------------------------------------------
# Exit codes: a claim about the corpus vs being unable to make one
# ---------------------------------------------------------------------------


def _report(unmeasured: bool) -> RegressionReport:
    return RegressionReport(
        [
            TrajectoryOutcome(
                trajectory_id="t1",
                task_class="code_fix",
                baseline_score=0.9,
                candidate_score=0.7 if unmeasured else 0.9,
                tools_ok=True,
                status_ok=True,
                score_indeterminate=unmeasured,
            )
        ]
    )


@pytest.mark.parametrize(
    ("real_candidate", "unmeasured", "argv"),
    [
        pytest.param(False, False, ["--require-real-candidate"], id="no-real-candidate"),
        pytest.param(True, True, ["--fail-on-regression"], id="scorer-gave-no-verdict-gated"),
        pytest.param(True, True, ["--require-real-candidate"], id="scorer-gave-no-verdict-required"),
    ],
)
def test_being_unable_to_judge_exits_two_not_one(monkeypatch, real_candidate, unmeasured, argv) -> None:
    """Both not-examined states use exit 2, and neither may use exit 1.

    Exit 1 is reserved for a claim about the corpus -- a golden regressed.
    "No real candidate" and "the scorer returned no verdict" are both the
    harness being unable to make that claim. Giving either of them exit 1 would
    reintroduce, in the exit code, exactly the conflation this module removes
    from the report -- which is what the first version of this file did.
    """
    import sys

    from eval import run as run_module

    monkeypatch.setattr(sys, "argv", ["eval.run", *argv])
    monkeypatch.setattr(run_module, "resolve_candidate", lambda _dir: (baseline_candidate, real_candidate))
    monkeypatch.setattr(run_module, "run_or_schedule", lambda _coro: _report(unmeasured))
    monkeypatch.setattr(run_module, "run_eval", lambda **_kw: None)

    assert run_module.main() == 2


def test_an_advisory_run_does_not_redden_a_pr_for_an_unmeasured_corpus(monkeypatch) -> None:
    """Ungated, an unjudgeable corpus reports and exits 0.

    Whether the eval setup can judge anything is a property of this repository,
    not of the pull request under test. Failing every PR for a standing gap
    misattributes it to whoever pushed and teaches readers that this check's red
    means nothing -- which spends the signal before it is worth anything. In a
    gated mode the opposite holds, and the parametrised test above pins that.
    """
    import sys

    from eval import run as run_module

    monkeypatch.setattr(sys, "argv", ["eval.run"])
    monkeypatch.setattr(run_module, "resolve_candidate", lambda _dir: (baseline_candidate, False))
    monkeypatch.setattr(run_module, "run_or_schedule", lambda _coro: _report(True))
    monkeypatch.setattr(run_module, "run_eval", lambda **_kw: None)

    assert run_module.main() == 0


# ---------------------------------------------------------------------------
# One unusable recording must not decide the fate of the whole corpus
#
# The tests above prove `RecordingMissing` is raised when the candidate is
# awaited directly. That is the raise site, not the consequence. Nothing
# exercised what a real corpus does when one golden lacks a recording, so the
# suite passed while the exception propagated out of the replayer, out of
# `main()`, and exited 1 -- the code reserved for "a golden regressed" --
# without emitting a report at all. Absence of evidence has to be
# distinguishable from a clean trajectory *in the report*, not only at a raise.
# ---------------------------------------------------------------------------


def _write_corrupt_recording(directory: Path, tid: str) -> None:
    """A file that exists and is not JSON.

    Written from a sync helper rather than inline in the async test: #7444
    forbids blocking I/O inside an ``async def`` body, and the point of the
    test is the replay path, not the write.
    """
    (directory / f"{tid}.json").write_text("{not json at all", encoding="utf-8")


def _write_partial_recording(directory: Path, tid: str, **omit: bool) -> None:
    """A recording missing one field the comparison depends on."""
    payload = {
        "events": [{"type": "tool_call", "tool": name} for name in EXPECTED_TOOLS],
        "output_text": "Added guard; tests pass.",
        "final_status": "completed",
    }
    for key in omit:
        payload.pop(key, None)
    (directory / f"{tid}.json").write_text(json.dumps(payload), encoding="utf-8")


@pytest.mark.asyncio
async def test_one_missing_recording_does_not_suppress_the_others(tmp_path: Path) -> None:
    """A partially populated corpus reports every golden, not none of them."""
    _write_recording(tmp_path, "recorded", EXPECTED_TOOLS)
    candidate, is_real = resolve_candidate(tmp_path)
    assert is_real

    replayer = TrajectoryReplayer(evaluator=_scorer(0.95))
    report = await replayer.run([_golden("recorded"), _golden("never-recorded")], candidate)

    assert len(report.outcomes) == 2, "the unrecorded golden must still appear in the report"
    verdicts = {o.trajectory_id: o.classify() for o in report.outcomes}
    assert verdicts["recorded"] == "unchanged"
    assert verdicts["never-recorded"] == "unmeasured"
    assert not report.has_regressions, "never measured is not the same as regressed"


@pytest.mark.asyncio
async def test_a_corrupt_recording_is_unmeasured_not_a_crash(tmp_path: Path) -> None:
    """A file that is not JSON costs its own trajectory, not the whole run."""
    _write_recording(tmp_path, "good", EXPECTED_TOOLS)
    _write_corrupt_recording(tmp_path, "corrupt")
    candidate, _ = resolve_candidate(tmp_path)

    replayer = TrajectoryReplayer(evaluator=_scorer(0.95))
    report = await replayer.run([_golden("good"), _golden("corrupt")], candidate)

    assert {o.classify() for o in report.outcomes} == {"unchanged", "unmeasured"}
    assert report.total_unmeasured == 1


@pytest.mark.asyncio
async def test_an_unrecorded_status_is_not_compared_against_the_golden_default(tmp_path: Path) -> None:
    """The defaults-collide trap, pinned.

    `GoldenTrajectory.expected_status` defaults to "completed". Defaulting the
    candidate's `final_status` to the same string made `status_ok` True for a
    field no recording contained -- a pass asserted about something nothing
    measured, and the one failure mode this module exists to prevent.
    """
    _write_partial_recording(tmp_path, "t1", final_status=True)
    candidate, _ = resolve_candidate(tmp_path)

    replayer = TrajectoryReplayer(evaluator=_scorer(0.95))
    report = await replayer.run([_golden("t1")], candidate)

    outcome = report.outcomes[0]
    assert outcome.classify() == "unmeasured"
    assert outcome.status_ok is None, "a comparison that never happened must not record a result"
    assert "final_status" in outcome.detail


def test_a_not_compared_field_serialises_as_null_not_as_a_pass() -> None:
    """The artifact a human reads must not show True for an absent comparison."""
    outcome = TrajectoryOutcome(
        trajectory_id="t1",
        task_class="code_fix",
        baseline_score=0.9,
        candidate_score=0.0,
        tools_ok=None,
        status_ok=None,
        score_indeterminate=True,
    )

    payload = RegressionReport([outcome]).to_dict()["trajectories"][0]

    assert payload["tools_ok"] is None
    assert payload["status_ok"] is None
    assert payload["verdict"] == "unmeasured"


def test_a_crash_exits_two_not_one(monkeypatch) -> None:
    """Any uncaught failure is "could not examine", never "a golden regressed".

    Python exits 1 on an uncaught exception, and 1 is this CLI's code for a
    real regression. Without the wrapper, every crash published a verdict about
    a corpus it had not read.
    """
    import sys

    from eval import run as run_module

    def _boom(_args):
        raise RuntimeError("the corpus could not be read")

    monkeypatch.setattr(sys, "argv", ["eval.run"])
    monkeypatch.setattr(run_module, "_run", _boom)

    assert run_module.main() == 2
