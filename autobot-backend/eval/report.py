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


def _md_escape(value: Any) -> str:
    """Neutralize untrusted fields before interpolating into the markdown report (#11062).

    trajectory_id / task_class / detail originate from golden fixtures + candidate
    output, so a crafted value could inject backticks, table pipes, or newlines
    into the CI artifact. Collapse newlines and escape markdown-significant chars.
    """
    text = " ".join(str(value).split())
    return text.replace("\\", "\\\\").replace("`", "\\`").replace("|", "\\|")


@dataclass
class TrajectoryOutcome:
    """Result of replaying one golden trajectory against the candidate."""

    trajectory_id: str
    task_class: str
    baseline_score: float
    candidate_score: float
    #: True/False are comparison results; None means the comparison never
    #: happened, because the candidate supplied no actual side for it. The
    #: third state is load-bearing: recording a not-compared field as True
    #: writes a pass into the artifact for something nothing measured.
    tools_ok: bool | None
    status_ok: bool | None
    candidate_tools: List[str] = field(default_factory=list)
    detail: str = ""
    #: The scorer could not produce a verdict (evaluator infrastructure failure,
    #: `ReflectionVerdict.INDETERMINATE`). Its `candidate_score` is a
    #: pass-through default, not a measurement of this trajectory.
    score_indeterminate: bool = False

    def classify(self, epsilon: float = DEFAULT_SCORE_EPSILON) -> str:
        """Return 'regression', 'improvement', 'unchanged', or 'unmeasured'.

        `unmeasured` exists because the evaluator returns a default score when
        its infrastructure is unavailable, and 0.7 against a 0.9 baseline is
        arithmetically a regression while saying nothing about the candidate.
        Reporting that as drift means a Redis outage reads as a quality failure
        — and once one red means that, every red is discounted.

        The tool and status comparisons do NOT need the scorer, so they are
        checked first and still stand on their own during an outage. Only the
        score half becomes unmeasured.

        A tool/status value of None is not a failed comparison but an absent
        one, so it must be tested with ``is False`` rather than falsily: under
        ``not self.tools_ok`` a never-compared trajectory reported a regression,
        which is a claim about the candidate drawn from never having looked.
        """
        if self.tools_ok is False or self.status_ok is False:
            return "regression"
        if self.tools_ok is None or self.status_ok is None or self.score_indeterminate:
            return "unmeasured"
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
    unmeasured: int = 0

    @property
    def total(self) -> int:
        return self.regressions + self.improvements + self.unchanged + self.unmeasured


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

    @property
    def total_unmeasured(self) -> int:
        """Trajectories the scorer could not judge — neither pass nor regression."""
        return sum(1 for o in self.outcomes if o.classify(self.epsilon) == "unmeasured")

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
            elif verdict == "unmeasured":
                delta.unmeasured += 1
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
                "unmeasured": self.total_unmeasured,
                "has_regressions": self.has_regressions,
            },
            "per_task_class": {
                name: {
                    "regressions": d.regressions,
                    "improvements": d.improvements,
                    "unchanged": d.unchanged,
                    "unmeasured": d.unmeasured,
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
        lines.append(
            f"**{self.total_regressions} regressions, {self.total_improvements} improvements, "
            f"{self.total_unmeasured} unmeasured** ({head})"
        )
        if self.total_unmeasured:
            # Stated up front rather than inferred from a table: an unmeasured
            # trajectory is not a passing one, and "no regressions" above is a
            # claim about the ones that could be judged.
            lines.append("")
            lines.append(
                f"> {self.total_unmeasured} trajectory/ies could not be scored — the evaluator returned "
                "no verdict. Their tool and status checks still count; their quality scores assert nothing."
            )
        lines.append("")
        lines.append("| Task class | Regressions | Improvements | Unchanged | Unmeasured |")
        lines.append("| --- | --- | --- | --- | --- |")
        for name, d in sorted(self.per_class().items()):
            lines.append(
                f"| {_md_escape(name)} | {d.regressions} | {d.improvements} | {d.unchanged} | {d.unmeasured} |"
            )
        lines.append("")
        for outcome in self.outcomes:
            verdict = outcome.classify(self.epsilon).upper()
            lines.append(
                f"- [{verdict}] `{_md_escape(outcome.trajectory_id)}` ({_md_escape(outcome.task_class)}) "
                f"baseline={outcome.baseline_score:.2f} candidate={outcome.candidate_score:.2f}"
                + (f" — {_md_escape(outcome.detail)}" if outcome.detail else "")
            )
        return "\n".join(lines)
