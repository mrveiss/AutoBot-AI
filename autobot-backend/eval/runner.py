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

from dataclasses import dataclass, field
from typing import Awaitable, Callable, List

from autobot_shared.logging_manager import get_logger
from eval.report import RegressionReport, TrajectoryOutcome
from eval.store import GoldenTrajectory
from rlm.evaluator import ResponseQualityEvaluator

logger = get_logger(__name__)


@dataclass
class CandidateResult:
    """What a candidate produced when replaying one golden's inputs."""

    response_text: str
    tool_sequence: List[str] = field(default_factory=list)
    final_status: str = "completed"


# A candidate is any async fn: golden -> CandidateResult.  Real callers wire
# this to the LLC replay path; tests pass a deterministic stub.
CandidateRunner = Callable[[GoldenTrajectory], Awaitable[CandidateResult]]


def _check_tools(expected: List[str], actual: List[str]) -> bool:
    """Exact ordered tool-sequence match (deterministic check)."""
    return expected == actual


class TrajectoryReplayer:
    """Replays goldens against a candidate and scores drift."""

    def __init__(self, evaluator: ResponseQualityEvaluator | None = None):
        self.evaluator = evaluator or ResponseQualityEvaluator()

    async def replay_one(self, golden: GoldenTrajectory, candidate: CandidateRunner) -> TrajectoryOutcome:
        """Replay a single golden and produce its scored outcome."""
        result = await candidate(golden)

        tools_ok = _check_tools(golden.expected_tools, result.tool_sequence)
        status_ok = result.final_status == golden.expected_status

        reflection = await self.evaluator.evaluate(query=golden.query, response=result.response_text)

        detail = ""
        if not tools_ok:
            detail = f"tools expected={golden.expected_tools} got={result.tool_sequence}"
        elif not status_ok:
            detail = f"status expected={golden.expected_status} got={result.final_status}"

        return TrajectoryOutcome(
            trajectory_id=golden.trajectory_id,
            task_class=golden.task_class,
            baseline_score=golden.baseline_score,
            candidate_score=reflection.quality_score,
            tools_ok=tools_ok,
            status_ok=status_ok,
            candidate_tools=result.tool_sequence,
            detail=detail,
        )

    async def run(self, goldens: List[GoldenTrajectory], candidate: CandidateRunner) -> RegressionReport:
        """Replay every golden against *candidate* and build the report."""
        outcomes: List[TrajectoryOutcome] = []
        for golden in goldens:
            outcome = await self.replay_one(golden, candidate)
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
