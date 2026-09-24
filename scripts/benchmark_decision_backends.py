#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Measure a decision backend against a labelled sample (#17308).

#17308's acceptance criterion: *a benchmark records accuracy and latency of
each backend against a labelled sample before any hosted backend becomes a
default -- a calibration claim without our own measurement is not evidence.*
This is that gate. It exists before a second backend does, so the number a
hosted candidate has to beat is measured rather than quoted.

What it reports, per backend:

* **accuracy** -- exact match against the labelled answer.
* **latency** -- p50 and p95 wall-clock per decision, measured here, not
  claimed by a vendor.
* **calibration** -- mean reported probability on the cases it got right
  versus on the cases it got wrong. A backend whose two means are the same is
  reporting a number with no information in it, whatever it calls it. This is
  what would justify promoting an answer's ``Calibration`` from
  ``SELF_REPORTED`` to ``MEASURED``, and nothing else does.

Running it costs real model calls: the default backend is the local
small-model path, so that cost is local compute, and a hosted backend added
later would bill. Nothing is promoted automatically -- the script prints, it
does not write config.

Usage::

    python3 scripts/benchmark_decision_backends.py --sample scripts/data/decision_benchmark_sample.json
    python3 scripts/benchmark_decision_backends.py --backend local_model --repeat 3

The sample file is a JSON list of cases::

    [{"id": "agree-1", "state": "...", "question": {...}, "expected": "agree"}]

where ``question`` is ``{"kind": "choice", "id": "...", "prompt": "...",
"options": [...]}`` or the ``score``/``boolean`` equivalent.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import statistics
import sys
import time
from dataclasses import dataclass
from typing import Any, Sequence

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "autobot-backend"))

from llm_shared.decisions import (  # noqa: E402  -- after the sys.path setup above
    BooleanQuestion,
    ChoiceQuestion,
    DecisionError,
    Question,
    ScoreQuestion,
    decide,
    get_backend,
    registered_backends,
)

#: Where the checked-in labelled sample lives.
DEFAULT_SAMPLE = _REPO_ROOT / "scripts" / "data" / "decision_benchmark_sample.json"


@dataclass
class CaseResult:
    """One labelled case, measured."""

    case_id: str
    correct: bool
    probability: float
    seconds: float
    failed: bool = False


def build_question(spec: dict[str, Any]) -> Question:
    """Return the question primitive *spec* describes."""
    kind = spec["kind"]
    if kind == "choice":
        return ChoiceQuestion(id=spec["id"], prompt=spec["prompt"], options=spec["options"])
    if kind == "score":
        return ScoreQuestion(
            id=spec["id"],
            prompt=spec["prompt"],
            minimum=float(spec.get("minimum", 0.0)),
            maximum=float(spec.get("maximum", 1.0)),
        )
    if kind == "boolean":
        return BooleanQuestion(id=spec["id"], prompt=spec["prompt"])
    raise SystemExit(f"unknown question kind {kind!r} -- expected choice, score or boolean")


def matches(expected: Any, actual: Any, tolerance: float) -> bool:
    """Return whether *actual* counts as the labelled answer."""
    if isinstance(expected, bool) or isinstance(actual, bool):
        return bool(expected) is bool(actual)
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return abs(float(expected) - float(actual)) <= tolerance
    return str(expected) == str(actual)


async def run_case(case: dict[str, Any], backend_name: str, tolerance: float) -> CaseResult:
    """Measure one labelled case against one backend."""
    question = build_question(case["question"])
    started = time.perf_counter()
    try:
        result = await decide(case["state"], [question], backend=get_backend(backend_name))
    except DecisionError as exc:
        # A refusal to answer is a recorded outcome, not a silent zero: a
        # backend that fails half the sample is not 100% accurate on the half
        # it answered, and reporting it that way would be the defect this
        # whole change is about.
        print(f"  {case['id']}: DECISION FAILED ({exc})")
        return CaseResult(
            case["id"], correct=False, probability=0.0, seconds=time.perf_counter() - started, failed=True
        )
    elapsed = time.perf_counter() - started
    answer = result[question.id]
    correct = matches(case["expected"], answer.value, tolerance)
    print(f"  {case['id']}: {'ok ' if correct else 'MISS'} value={answer.value!r} p={answer.probability:.2f}")
    return CaseResult(case["id"], correct=correct, probability=answer.probability, seconds=elapsed)


def report(backend_name: str, results: Sequence[CaseResult]) -> None:
    """Print the measured numbers for one backend."""
    answered = [r for r in results if not r.failed]
    correct = [r for r in answered if r.correct]
    wrong = [r for r in answered if not r.correct]
    latencies = sorted(r.seconds for r in answered)

    print(f"\nbackend: {backend_name}")
    print(f"  cases:           {len(results)} ({len(results) - len(answered)} refused to answer)")
    if not answered:
        print("  accuracy:        n/a -- nothing was answered, so nothing was measured")
        return
    print(f"  accuracy:        {len(correct)}/{len(answered)} = {len(correct) / len(answered):.0%}")
    print(f"  latency p50:     {statistics.median(latencies):.2f}s")
    p95 = latencies[min(len(latencies) - 1, int(round(0.95 * (len(latencies) - 1))))]
    print(f"  latency p95:     {p95:.2f}s")
    mean_right = statistics.mean(r.probability for r in correct) if correct else float("nan")
    mean_wrong = statistics.mean(r.probability for r in wrong) if wrong else float("nan")
    print(f"  mean p (right):  {mean_right:.2f}")
    print(f"  mean p (wrong):  {mean_wrong:.2f}")
    if correct and wrong:
        separation = mean_right - mean_wrong
        print(f"  separation:      {separation:+.2f}", end="  ")
        print("(a probability with information in it separates these two)" if separation > 0.05 else "(no signal)")
    else:
        print("  separation:      n/a -- needs both correct and incorrect cases in the sample")


async def main_async(args: argparse.Namespace) -> int:
    cases = json.loads(pathlib.Path(args.sample).read_text(encoding="utf-8"))
    if not cases:
        print("sample is empty -- nothing measured", file=sys.stderr)
        return 2
    backends = args.backend or registered_backends()
    for backend_name in backends:
        print(f"\n=== {backend_name} x{args.repeat} ===")
        results: list[CaseResult] = []
        for _ in range(args.repeat):
            for case in cases:
                results.append(await run_case(case, backend_name, args.tolerance))
        report(backend_name, results)
    print("\nNothing was promoted: this script measures, it does not change a default.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sample", default=str(DEFAULT_SAMPLE), help="labelled sample JSON (default: %(default)s)")
    parser.add_argument("--backend", action="append", help="backend name; repeatable (default: every registered one)")
    parser.add_argument("--repeat", type=int, default=1, help="passes over the sample (default: %(default)s)")
    parser.add_argument("--tolerance", type=float, default=0.15, help="score match tolerance (default: %(default)s)")
    args = parser.parse_args(argv)
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
