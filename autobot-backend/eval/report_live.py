# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Per-model aggregation and rendering for live eval reports (#20843).

``not_run`` is its own state. A trajectory the harness could not run (the model or its infrastructure failed
before an answer) is neither a pass nor a model failure, and it is never counted as passed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Iterable, List

if TYPE_CHECKING:
    from eval.report import TrajectoryOutcome

PASS, FAIL, NOT_RUN = "pass", "fail", "not_run"
#: Model key for an outcome no model could be attributed to (a runner that raised before naming one).
UNATTRIBUTED = "unattributed"


def outcome_state(outcome: "TrajectoryOutcome") -> str:
    """``pass``, ``fail`` or ``not_run`` for one live outcome; ``not_run`` whenever it was never compared."""
    if outcome.classify() == "unmeasured":
        return NOT_RUN
    return PASS if outcome.passed else FAIL


def live_fields(outcome: "TrajectoryOutcome") -> Dict[str, Any]:
    """The live-only keys of a serialized trajectory; empty for a non-live outcome."""
    if not outcome.is_live:
        return {}
    return {
        "model": outcome.model,
        "provider": outcome.provider,
        "repeat": outcome.repeat,
        "state": outcome_state(outcome),
        "passed": outcome.passed,
        "failure_categories": list(outcome.failure_categories),
        "criteria_detail": outcome.criteria_detail,
        "tokens": outcome.tokens,
    }


def per_model(outcomes: Iterable["TrajectoryOutcome"]) -> Dict[str, Dict[str, Any]]:
    """Pass/fail/not_run counts per model and per task, plus a failure-category histogram per model."""
    models: Dict[str, Dict[str, Any]] = {}
    for outcome in outcomes:
        if not outcome.is_live:
            continue
        entry = models.setdefault(
            outcome.model or UNATTRIBUTED, {PASS: 0, FAIL: 0, NOT_RUN: 0, "categories": {}, "per_task": {}}
        )
        state = outcome_state(outcome)
        entry[state] += 1
        task = entry["per_task"].setdefault(outcome.trajectory_id, {PASS: 0, FAIL: 0, NOT_RUN: 0})
        task[state] += 1
        for category in outcome.failure_categories:
            entry["categories"][category] = entry["categories"].get(category, 0) + 1
    return models


def _md_cell(value: Any) -> str:
    from eval.report import _md_escape

    return _md_escape(value)


def _model_rows(models: Dict[str, Dict[str, Any]]) -> List[str]:
    rows = ["| Model | Pass | Fail | Not run | Failure categories |", "| --- | --- | --- | --- | --- |"]
    for name, entry in sorted(models.items()):
        cats = ", ".join(f"{c}={n}" for c, n in sorted(entry["categories"].items())) or "none"
        rows.append(f"| {_md_cell(name)} | {entry[PASS]} | {entry[FAIL]} | {entry[NOT_RUN]} | {_md_cell(cats)} |")
    return rows


def _task_rows(models: Dict[str, Dict[str, Any]]) -> List[str]:
    rows = ["| Model | Task | Pass | Fail | Not run |", "| --- | --- | --- | --- | --- |"]
    for name, entry in sorted(models.items()):
        for task, counts in sorted(entry["per_task"].items()):
            rows.append(
                f"| {_md_cell(name)} | {_md_cell(task)} | {counts[PASS]} | {counts[FAIL]} | {counts[NOT_RUN]} |"
            )
    return rows


def _pin_lines(run: Dict[str, Any] | None) -> List[str]:
    if not run:
        return []
    shown = {k: v for k, v in run.items() if k != "models"}
    lines = ["", "**Run pins:** " + ", ".join(f"{_md_cell(k)}={_md_cell(v)}" for k, v in sorted(shown.items()))]
    for pin in run.get("models") or []:
        lines.append("- " + ", ".join(f"{_md_cell(k)}={_md_cell(v)}" for k, v in sorted(pin.items())))
    return lines


def render_live_markdown(run: Dict[str, Any] | None, outcomes: Iterable["TrajectoryOutcome"]) -> List[str]:
    """Markdown lines for the pins block and the per-model tables; empty when the report has no live outcome."""
    models = per_model(outcomes)
    if not models:
        return []
    return [*_pin_lines(run), "", *_model_rows(models), "", *_task_rows(models)]
