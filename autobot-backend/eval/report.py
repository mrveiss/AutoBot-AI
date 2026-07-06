# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression report types + rendering (GH#10546).

Turns per-trajectory candidate outcomes into a "candidate vs baseline"
diff grouped by task-class: N regressions, M improvements.  A trajectory
is a *regression* when it either (a) breaks a deterministic check the
baseline passed (wrong/missing tools, wrong terminal status) or (b) drops
its RLM quality score below baseline by more than ``score_epsilon``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

# A candidate score this far *below* baseline counts as a regression; within
# this band is treated as noise-equivalent (unchanged).
DEFAULT_SCORE_EPSILON = 0.05


@dataclass
class TrajectoryOutcome:
    """Result of replaying one golden trajectory against the candidate."""

    trajectory_id: str
    task_class: str
    baseline_score: float
    candidate_score: float
    tools_ok: bool
    status_ok: bool
    candidate_tools: List[str] = field(default_factory=list)
    detail: str = ""

    def classify(self, epsilon: float = DEFAULT_SCORE_EPSILON) -> str:
        """Return 'regression', 'improvement', or 'unchanged'."""
        if not self.tools_ok or not self.status_ok:
            return "regression"
        delta = self.candidate_score - self.baseline_score
        if delta < -epsilon:
            return "regression"
        if delta > epsilon:
            return "improvement"
        return "unchanged"


@dataclass
class TaskClassDelta:
    """Aggregated candidate-vs-baseline delta for one task-class."""

    task_class: str
    regressions: int = 0
    improvements: int = 0
    unchanged: int = 0

    @property
    def total(self) -> int:
        return self.regressions + self.improvements + self.unchanged


@dataclass
class RegressionReport:
    """Full candidate-vs-baseline report across all task-classes."""

    outcomes: List[TrajectoryOutcome]
    epsilon: float = DEFAULT_SCORE_EPSILON

    @property
    def has_regressions(self) -> bool:
        return any(o.classify(self.epsilon) == "regression" for o in self.outcomes)

    @property
    def total_regressions(self) -> int:
        return sum(1 for o in self.outcomes if o.classify(self.epsilon) == "regression")

    @property
    def total_improvements(self) -> int:
        return sum(1 for o in self.outcomes if o.classify(self.epsilon) == "improvement")

    def per_class(self) -> Dict[str, TaskClassDelta]:
        """Group outcomes into per-task-class regression/improvement counts."""
        deltas: Dict[str, TaskClassDelta] = {}
        for outcome in self.outcomes:
            delta = deltas.setdefault(outcome.task_class, TaskClassDelta(outcome.task_class))
            verdict = outcome.classify(self.epsilon)
            if verdict == "regression":
                delta.regressions += 1
            elif verdict == "improvement":
                delta.improvements += 1
            else:
                delta.unchanged += 1
        return deltas

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the report for JSON output / CI artifacts."""
        return {
            "summary": {
                "trajectories": len(self.outcomes),
                "regressions": self.total_regressions,
                "improvements": self.total_improvements,
                "has_regressions": self.has_regressions,
            },
            "per_task_class": {
                name: {
                    "regressions": d.regressions,
                    "improvements": d.improvements,
                    "unchanged": d.unchanged,
                }
                for name, d in self.per_class().items()
            },
            "trajectories": [
                {
                    "trajectory_id": o.trajectory_id,
                    "task_class": o.task_class,
                    "verdict": o.classify(self.epsilon),
                    "baseline_score": round(o.baseline_score, 3),
                    "candidate_score": round(o.candidate_score, 3),
                    "tools_ok": o.tools_ok,
                    "status_ok": o.status_ok,
                    "detail": o.detail,
                }
                for o in self.outcomes
            ],
        }

    def render_markdown(self) -> str:
        """Render a human-readable pass/regress report."""
        lines = ["# Trajectory eval — candidate vs baseline", ""]
        head = "REGRESSIONS FOUND" if self.has_regressions else "no regressions"
        lines.append(f"**{self.total_regressions} regressions, {self.total_improvements} improvements** ({head})")
        lines.append("")
        lines.append("| Task class | Regressions | Improvements | Unchanged |")
        lines.append("| --- | --- | --- | --- |")
        for name, d in sorted(self.per_class().items()):
            lines.append(f"| {name} | {d.regressions} | {d.improvements} | {d.unchanged} |")
        lines.append("")
        for outcome in self.outcomes:
            verdict = outcome.classify(self.epsilon).upper()
            lines.append(
                f"- [{verdict}] `{outcome.trajectory_id}` ({outcome.task_class}) "
                f"baseline={outcome.baseline_score:.2f} candidate={outcome.candidate_score:.2f}"
                + (f" — {outcome.detail}" if outcome.detail else "")
            )
        return "\n".join(lines)
