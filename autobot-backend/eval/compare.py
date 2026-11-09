# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Before/after comparison of two live eval reports (#20843).

Usage::

    cd autobot-backend
    python -m eval.compare before.json after.json

Exit codes follow ``eval.run``: ``0`` compared, ``2`` refused (the reports are not comparable, so no claim is made).
Two reports are comparable only when their pins agree on the model set, the step budget, the timeout and the corpus
size: a difference in any of them moves the pass rate without the change under test having moved anything.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from eval.report_live import FAIL, NOT_RUN, PASS

logger = get_logger(__name__)

#: Pins that must be equal for two reports to be comparable.
COMPARED_PINS = (
    "step_budget",
    "loop_abort_threshold",
    "timeout",
    "corpus_size",
    "repeats",
    "judge_model",
    "local_only",
    "kb_status",
)
#: Per-model pins that must also agree: where the prompts went, not just which model answered.
COMPARED_MODEL_PINS = ("provider", "endpoint_class", "local_only")


class NotComparable(ValueError):
    """The two reports were produced under different pins."""


def _model_names(report: Dict[str, Any]) -> List[str]:
    return sorted(m["model"] for m in (report.get("run") or {}).get("models", []))


def check_comparable(before: Dict[str, Any], after: Dict[str, Any]) -> None:
    """Raise ``NotComparable`` naming every pin that differs, or that a report does not carry."""
    run_a, run_b = before.get("run"), after.get("run")
    if not run_a or not run_b:
        raise NotComparable("a report has no `run` pins block, so it is not a live report")
    problems = []
    if _model_names(before) != _model_names(after):
        problems.append(f"model: {_model_names(before)} vs {_model_names(after)}")
    for pin in COMPARED_PINS:
        if run_a.get(pin) != run_b.get(pin):
            problems.append(f"{pin}: {run_a.get(pin)!r} vs {run_b.get(pin)!r}")
    problems += _model_pin_problems(run_a, run_b)
    if problems:
        raise NotComparable("; ".join(problems))


def _model_pin_problems(run_a: Dict[str, Any], run_b: Dict[str, Any]) -> List[str]:
    """Per-model pin differences, for the models both reports name."""
    by_name = {m["model"]: m for m in run_b.get("models", [])}
    problems = []
    for pin in run_a.get("models", []):
        other = by_name.get(pin["model"])
        for key in COMPARED_MODEL_PINS:
            if other is not None and pin.get(key) != other.get(key):
                problems.append(f"{pin['model']} {key}: {pin.get(key)!r} vs {other.get(key)!r}")
    return problems


def _rate(entry: Dict[str, Any]) -> float:
    """Pass rate over every run, so a run that never happened lowers it instead of vanishing."""
    total = entry[PASS] + entry[FAIL] + entry[NOT_RUN]
    return entry[PASS] / total if total else 0.0


def _category_delta(before: Dict[str, int], after: Dict[str, int]) -> Dict[str, Dict[str, int]]:
    return {c: {"before": before.get(c, 0), "after": after.get(c, 0)} for c in sorted(set(before) | set(after))}


def _model_delta(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    tasks = sorted(set(before["per_task"]) | set(after["per_task"]))
    empty = {PASS: 0, FAIL: 0, NOT_RUN: 0}
    return {
        "pass_rate": {"before": round(_rate(before), 4), "after": round(_rate(after), 4)},
        "counts": {
            "before": {k: before[k] for k in empty},
            "after": {k: after[k] for k in empty},
        },
        "categories": _category_delta(before["categories"], after["categories"]),
        "per_task": {
            t: {"before": before["per_task"].get(t, empty), "after": after["per_task"].get(t, empty)} for t in tasks
        },
    }


def compare_reports(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    """Per-model before/after deltas; raises ``NotComparable`` when the pins differ."""
    check_comparable(before, after)
    return {
        "label": {"before": before["run"].get("label"), "after": after["run"].get("label")},
        "models": {
            name: _model_delta(before["per_model"][name], after["per_model"][name])
            for name in sorted(before["per_model"])
            if name in after["per_model"]
        },
    }


def render_markdown(delta: Dict[str, Any]) -> str:
    """A markdown table per model; model names and labels go through the report's own escaper."""
    from eval.report import _md_escape

    lines = ["# Live eval — before vs after", ""]
    lines.append(f"before=`{_md_escape(delta['label']['before'])}` after=`{_md_escape(delta['label']['after'])}`")
    lines += ["", "| Model | Pass rate before | Pass rate after |", "| --- | --- | --- |"]
    for name, d in delta["models"].items():
        lines.append(f"| {_md_escape(name)} | {d['pass_rate']['before']:.2f} | {d['pass_rate']['after']:.2f} |")
    return "\n".join(lines)


def _load(path: str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare two live eval reports per model")
    parser.add_argument("before")
    parser.add_argument("after")
    parser.add_argument("--json", default="", help="Write the machine-readable delta to this path")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        delta = compare_reports(_load(args.before), _load(args.after))
    except (NotComparable, OSError, ValueError, KeyError) as exc:
        logger.error("NOT COMPARED: %s", exc)
        return 2
    logger.info("%s", render_markdown(delta))
    if args.json:
        Path(args.json).write_text(json.dumps(delta, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
