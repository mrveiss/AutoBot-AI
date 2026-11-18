# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Replay + score runner (GH#10546).

Replays each golden trajectory against a *candidate* (a model / prompt /
skill set expressed as a ``CandidateRunner``) and scores drift with two
independent checks:

- **Deterministic checks** — did the candidate call the expected tool
  sequence and reach the expected terminal status?  A wrong or missing
  tool call is a hard regression regardless of quality score.
- **RLM quality score** — ``rlm.evaluator.ResponseQualityEvaluator`` judges
  the candidate's final response against the golden's original query.  The
  score is compared to the golden's recorded baseline_score for drift.

The candidate is any async callable producing a ``CandidateResult``; this
keeps the harness decoupled from *how* a run is produced (a live agent
replay, a subprocess transcript, or a mock in tests).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Awaitable, Callable, List

from autobot_shared.env_utils import env_float
from autobot_shared.logging_manager import get_logger
from eval.report import RegressionReport, TrajectoryOutcome
from eval.store import GoldenTrajectory
from rlm.evaluator import ResponseQualityEvaluator
from rlm.types import ReflectionVerdict

# #11062: a hung/slow candidate must not stall the whole regression run.
_REPLAY_TIMEOUT_S = env_float("EVAL_REPLAY_TIMEOUT_S", 120.0)

logger = get_logger(__name__)


@dataclass
class CandidateResult:
    """What a candidate produced when replaying one golden's inputs."""

    response_text: str
    tool_sequence: List[str] = field(default_factory=list)
    final_status: str = "completed"
    #: Live-mode fields (#20843); all None/empty for the baseline and recorded candidates, which leave them alone.
    model: str | None = None
    provider: str | None = None
    failure_categories: List[str] = field(default_factory=list)
    passed: bool | None = None
    criteria_detail: str = ""
    tokens: int | None = None


# A candidate is any async fn: golden -> CandidateResult.  Real callers wire
# this to the LLC replay path; tests pass a deterministic stub.
CandidateRunner = Callable[[GoldenTrajectory], Awaitable[CandidateResult]]


class RecordingUnusable(RuntimeError):
    """A candidate cannot supply an actual side for one golden.

    Declared here rather than in ``eval.candidates`` because that module
    imports this one, and the layer that must *handle* the failure is this
    one. Concrete reasons (absent, unparseable, incomplete) subclass it there.
    """


def tools_match(expected: List[str], actual: List[str], mode: str = "exact") -> bool:
    """Tool-sequence check: ``exact`` equality, or ``subsequence`` (the expected tools in order, extras allowed)."""
    if mode == "subsequence":
        remaining = iter(actual)
        return all(any(tool == got for got in remaining) for tool in expected)
    return expected == actual


def _drift_detail(golden: GoldenTrajectory, result: CandidateResult, tools_ok: bool, status_ok: bool) -> str:
    """The first deterministic mismatch of a non-live replay, or an empty string."""
    if not tools_ok:
        return f"tools expected={golden.expected_tools} got={result.tool_sequence}"
    if not status_ok:
        return f"status expected={golden.expected_status} got={result.final_status}"
    return ""


def _live_detail(golden: GoldenTrajectory, result: CandidateResult, tools_ok: bool, status_ok: bool) -> str:
    """Why a live run failed, in one line: categories, criteria detail, then any tool/status mismatch."""
    parts = []
    if result.failure_categories:
        parts.append("categories: " + ", ".join(result.failure_categories))
    if result.criteria_detail:
        parts.append(result.criteria_detail)
    if not tools_ok:
        parts.append(f"tools expected={golden.expected_tools} got={result.tool_sequence}")
    if not status_ok:
        parts.append(f"status expected={golden.expected_status} got={result.final_status}")
    return " | ".join(parts)


class TrajectoryReplayer:
    """Replays goldens against a candidate and scores drift."""

    def __init__(self, evaluator: ResponseQualityEvaluator | None = None):
        self.evaluator = evaluator or ResponseQualityEvaluator()

    async def replay_one(self, golden: GoldenTrajectory, candidate: CandidateRunner) -> TrajectoryOutcome:
        """Replay a single golden and produce its scored outcome."""
        result = await candidate(golden)

        tools_ok = tools_match(golden.expected_tools, result.tool_sequence, golden.tool_match)
        status_ok = result.final_status == golden.expected_status
        if result.passed is not None:
            return self._live_outcome(golden, result, tools_ok, status_ok)
        return await self._scored_outcome(golden, result, tools_ok, status_ok)

    async def _scored_outcome(
        self, golden: GoldenTrajectory, result: CandidateResult, tools_ok: bool, status_ok: bool
    ) -> TrajectoryOutcome:
        """Non-live outcome: the deterministic checks plus the RLM quality score."""
        reflection = await self.evaluator.evaluate(query=golden.query, response=result.response_text)

        detail = _drift_detail(golden, result, tools_ok, status_ok)

        # The evaluator distinguishes "scored badly" from "could not score" via
        # INDETERMINATE, and until now this dropped that and kept only the
        # number. Its pass-through default is 0.7, which against a 0.9 baseline
        # is arithmetically a regression — so an evaluator outage reported as
        # quality drift (#16157).
        indeterminate = reflection.verdict == ReflectionVerdict.INDETERMINATE
        if indeterminate and not detail:
            detail = "evaluator returned no verdict; quality score not measured"

        return TrajectoryOutcome(
            trajectory_id=golden.trajectory_id,
            task_class=golden.task_class,
            baseline_score=golden.baseline_score,
            candidate_score=reflection.quality_score,
            tools_ok=tools_ok,
            status_ok=status_ok,
            candidate_tools=result.tool_sequence,
            detail=detail,
            score_indeterminate=indeterminate,
        )

    @staticmethod
    def _live_outcome(
        golden: GoldenTrajectory, result: CandidateResult, tools_ok: bool, status_ok: bool
    ) -> TrajectoryOutcome:
        """A live run is judged by the candidate's own pass/fail and categories, not by the RLM quality score.

        The quality evaluator calls whichever model the deployment configures, not the one under test, so a
        score from it would describe a different model than the report names.
        """
        detail = _live_detail(golden, result, tools_ok, status_ok)
        return TrajectoryOutcome(
            trajectory_id=golden.trajectory_id,
            task_class=golden.task_class,
            baseline_score=golden.baseline_score,
            candidate_score=1.0 if result.passed else 0.0,
            tools_ok=tools_ok,
            status_ok=status_ok,
            candidate_tools=result.tool_sequence,
            detail=detail,
            model=result.model,
            provider=result.provider,
            failure_categories=list(result.failure_categories),
            passed=result.passed,
            criteria_detail=result.criteria_detail,
            tokens=result.tokens,
        )

    @staticmethod
    def _live_timed_out(golden: GoldenTrajectory, candidate: CandidateRunner, timeout_s: float) -> TrajectoryOutcome:
        """A live turn that ran out of time: a ``loop_stall`` and a failure, never unmeasured (#20843)."""
        logger.error("live replay of %s timed out after %.0fs", golden.trajectory_id, timeout_s)
        return TrajectoryOutcome(
            trajectory_id=golden.trajectory_id,
            task_class=golden.task_class,
            baseline_score=golden.baseline_score,
            candidate_score=0.0,
            tools_ok=False,
            status_ok=False,
            detail=f"categories: loop_stall | live turn timed out after {timeout_s:.0f}s",
            model=getattr(candidate, "model", None),
            provider=getattr(candidate, "provider", None),
            failure_categories=["loop_stall"],
            passed=False,
        )

    @staticmethod
    def _timed_out(golden: GoldenTrajectory) -> TrajectoryOutcome:
        """A replay that ran out of time, recorded as a failure per #11062.

        Filed as a regression rather than unmeasured because that was #11062's
        recorded decision, not this module's. #16192 argues it belongs with the
        unmeasured states and must not be changed here unannounced.
        """
        logger.error(
            "replay of %s timed out after %.0fs — recording as failure (#11062)",
            golden.trajectory_id,
            _REPLAY_TIMEOUT_S,
        )
        return TrajectoryOutcome(
            trajectory_id=golden.trajectory_id,
            task_class=golden.task_class,
            baseline_score=golden.baseline_score,
            candidate_score=0.0,
            tools_ok=False,
            status_ok=False,
            detail=f"replay timed out after {_REPLAY_TIMEOUT_S:.0f}s",
        )

    @staticmethod
    def _unmeasured(
        golden: GoldenTrajectory, exc: RecordingUnusable, candidate: CandidateRunner | None = None
    ) -> TrajectoryOutcome:
        """A golden the candidate could supply no actual side for.

        `tools_ok` and `status_ok` are None rather than False: no comparison
        happened, and writing False would report a regression drawn from never
        having looked.
        """
        logger.warning("replay of %s is unmeasured: %s", golden.trajectory_id, exc)
        return TrajectoryOutcome(
            trajectory_id=golden.trajectory_id,
            task_class=golden.task_class,
            baseline_score=golden.baseline_score,
            candidate_score=0.0,
            tools_ok=None,
            status_ok=None,
            detail=f"not measured: {exc}",
            score_indeterminate=True,
            model=getattr(candidate, "model", None),
            provider=getattr(candidate, "provider", None),
        )

    async def _replay_bounded(self, golden: GoldenTrajectory, candidate: CandidateRunner) -> TrajectoryOutcome:
        """One golden under its time bound; a live candidate carries its own bound (``timeout_s``) and verdict."""
        live = bool(getattr(candidate, "live", False))
        timeout_s = getattr(candidate, "timeout_s", None) if live else _REPLAY_TIMEOUT_S
        try:
            return await asyncio.wait_for(self.replay_one(golden, candidate), timeout=timeout_s)
        except TimeoutError:
            return self._live_timed_out(golden, candidate, timeout_s) if live else self._timed_out(golden)
        except RecordingUnusable as exc:
            return self._unmeasured(golden, exc, candidate)

    async def run(self, goldens: List[GoldenTrajectory], candidate: CandidateRunner) -> RegressionReport:
        """Replay every golden against *candidate* and build the report.

        No exception from one golden may end the loop: a run that stops early
        emits no report at all, and an absent report exits under the code
        reserved for "a golden regressed" (#16157).
        """
        outcomes: List[TrajectoryOutcome] = []
        for golden in goldens:
            outcome = await self._replay_bounded(golden, candidate)
            logger.info(
                "replayed %s [%s] verdict=%s baseline=%.2f candidate=%.2f",
                outcome.trajectory_id,
                outcome.task_class,
                outcome.classify(),
                outcome.baseline_score,
                outcome.candidate_score,
            )
            outcomes.append(outcome)
        return RegressionReport(outcomes=outcomes)
