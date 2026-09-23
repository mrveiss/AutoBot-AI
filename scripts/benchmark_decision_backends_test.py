# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The decision benchmark's own arithmetic, checked (#17308).

A benchmark is an instrument, and an instrument that has never been read
against a known input is not evidence of anything --
``docs/developer/MEASUREMENT_DISCIPLINE.md``: *a known positive is asserted
before any count is read*. These tests are that positive control: a hand-built
set of results whose accuracy, latency percentiles and probability separation
are known by construction.

The model-calling half of the script is not exercised here; it needs a live
local model, which is the point of it being a script rather than a test.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from scripts.benchmark_decision_backends import (
    DEFAULT_SAMPLE,
    CaseResult,
    build_question,
    main,
    matches,
    report,
)

# ------------------------------------------------------------------ matching


@pytest.mark.parametrize(
    ("expected", "actual", "want"),
    [
        ("agree", "agree", True),
        ("agree", "contradict", False),
        (True, True, True),
        (True, False, False),
        (8.0, 8.1, True),  # inside the default tolerance
        (8.0, 9.0, False),  # outside it
    ],
)
def test_matches_compares_each_answer_type(expected, actual, want) -> None:
    assert matches(expected, actual, tolerance=0.15) is want


def test_a_boolean_is_never_compared_as_a_number() -> None:
    """`True == 1` in Python; a boolean question must not match a score of 1."""
    assert matches(True, 1.0, tolerance=0.15) is True
    assert matches(False, 0.0, tolerance=0.15) is True
    assert matches(True, 0.0, tolerance=0.15) is False


# ----------------------------------------------------------------- questions


def test_build_question_covers_the_three_primitives() -> None:
    choice = build_question({"kind": "choice", "id": "a", "prompt": "p", "options": ["x", "y"]})
    score = build_question({"kind": "score", "id": "b", "prompt": "p", "minimum": 0, "maximum": 10})
    boolean = build_question({"kind": "boolean", "id": "c", "prompt": "p"})

    assert list(choice.options) == ["x", "y"]
    assert (score.minimum, score.maximum) == (0.0, 10.0)
    assert boolean.id == "c"


def test_an_unknown_question_kind_stops_the_run() -> None:
    with pytest.raises(SystemExit):
        build_question({"kind": "vibes", "id": "a", "prompt": "p"})


# ------------------------------------------------------------------ reporting


def test_report_counts_refusals_apart_from_wrong_answers(capsys) -> None:
    results = [
        CaseResult("a", correct=True, probability=0.9, seconds=0.1),
        CaseResult("b", correct=False, probability=0.4, seconds=0.2),
        CaseResult("c", correct=False, probability=0.0, seconds=0.3, failed=True),
    ]

    report("local_model", results)
    out = capsys.readouterr().out

    # Accuracy is over what was answered (1 of 2), and the refusal is named --
    # not folded into the denominator as if it had been a wrong answer.
    assert "1/2 = 50%" in out
    assert "(1 refused to answer)" in out
    assert "separation:      +0.50" in out


def test_report_says_nothing_was_measured_when_nothing_answered(capsys) -> None:
    report("local_model", [CaseResult("a", correct=False, probability=0.0, seconds=0.1, failed=True)])
    out = capsys.readouterr().out

    assert "nothing was answered, so nothing was measured" in out
    assert "accuracy:        n/a" in out


def test_report_withholds_separation_without_both_outcomes(capsys) -> None:
    report("local_model", [CaseResult("a", correct=True, probability=0.9, seconds=0.1)])

    assert "needs both correct and incorrect cases" in capsys.readouterr().out


# -------------------------------------------------------------- the sample


def test_the_checked_in_sample_is_usable() -> None:
    cases = json.loads(pathlib.Path(DEFAULT_SAMPLE).read_text(encoding="utf-8"))

    assert len(cases) >= 4
    for case in cases:
        assert {"id", "state", "question", "expected"} <= set(case)
        build_question(case["question"])  # every case's question must be buildable


def test_the_sample_covers_all_three_primitives_and_both_outcomes() -> None:
    """A sample of only easy cases cannot measure separation at all."""
    cases = json.loads(pathlib.Path(DEFAULT_SAMPLE).read_text(encoding="utf-8"))
    kinds = {case["question"]["kind"] for case in cases}
    choice_answers = {case["expected"] for case in cases if case["question"]["kind"] == "choice"}

    assert kinds == {"choice", "score", "boolean"}
    assert {"agree", "contradict", "unrelated"} <= choice_answers


def test_an_empty_sample_exits_nonzero(tmp_path) -> None:
    empty = tmp_path / "empty.json"
    empty.write_text("[]", encoding="utf-8")

    assert main(["--sample", str(empty)]) == 2
