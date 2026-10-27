# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the outward-wording detector (#19645).

Every rule is exercised in the three places it runs -- an issue body (the
``issue`` subcommand the workflow calls), a PR body (``report()``) and a commit
subject (the ``subject`` subcommand the commit-msg hook calls) -- and the contrast
cases (hex SHAs, issue numbers, ``a0`` inside identifiers, "train" alone, a code
span) must stay clean in all three.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_pr_template_sections import report  # noqa: E402
from outward_wording import LABEL, MARKER, find_hits, issue_comment, issue_decision, main  # noqa: E402

COMPLETE = "## Thinking Path\nwhy\n## What Changed\nwhat\n## Verification\nhow\n## Model Used\nmodel\n## Issue Link\nCloses #1\n"

# (text, the exact match it must produce) -- at least one per rule, in RULES order.
FLAGGED = [
    ("Picked up from autobot-ai-4d last night (#19645)", "autobot-ai-4d"),
    ("Picked up from session autobot-ai-cb last night (#19645)", "session autobot-ai-cb"),
    ("Reviewed (a0, 2026-10-24) and landed (#19645)", "(a0, 2026-10-24"),
    ("Reviewed (27, 2026-10-24) and landed (#19645)", "(27, 2026-10-24"),
    ("Handed over a0 → reviewer (#19645)", "Handed over a0 →"),
    ("Handed over from review → 4d (#19645)", "Handed over from review → 4d"),
    ("Asked the Trainmaster to queue it (#19645)", "Trainmaster"),
    ("Lands with train 85l tonight (#19645)", "train 85l"),
    ("Lands with train 91a next week (#19645)", "train 91a"),
    ("The M3 owner decided it (#19645)", "M3 owner"),
]
CLEAN = [
    "Fixed in a0b1c2d3e4 and 4d5e6f7a8b (#19645)",
    "Refs #19526, #1964 and #45 (#19645)",
    "Renamed data0 and abca0_id to x (#19645)",
    "The merge train (PR #19626) carried it (#19645)",
    "A train of thought about 85 trains (#19645)",
    "The `M2 owner` wording and `autobot-ai-4d` are quoted as examples (#19645)",
    "Maintainer decision (2026-10-26), tracked in #19526 (#19645)",
    "Mapped M1 → M2 milestones (#19645)",
    "Called f(10, 20) twice (#19645)",
    "We train 100 epochs, train 32 models and we train 85 classifiers (#19645)",
    "Then train 10k samples, train 50k, train 2m tokens and train 1b (#19645)",
    "Deployed autobot-ai-ui, autobot-ai-db and autobot-ai-backend (#19645)",
    "Split the store (db, cache) in two (#19645)",
    "Moved db → redis and ui → api (#19645)",
    "Bumped the schema v2 → v3 (#19645)",
    "Passed the db → redis migration (#19645)",
]


@pytest.mark.parametrize(("text", "match"), FLAGGED)
def test_each_rule_is_flagged_in_text(text: str, match: str) -> None:
    assert [hit.match for hit in find_hits(text)] == [match]


@pytest.mark.parametrize("text", CLEAN)
def test_contrast_cases_are_not_flagged(text: str) -> None:
    assert find_hits(text) == []


@pytest.mark.parametrize(("text", "match"), FLAGGED)
def test_each_rule_fails_the_pr_body(text: str, match: str) -> None:
    ok, lines = report(COMPLETE + text + "\n")
    assert not ok, lines
    assert any(match in line and line.startswith("::error::") for line in lines), lines
    assert any("maintainer decision (YYYY-MM-DD)" in line for line in lines), lines
    assert lines[-1].endswith("an internal process role."), lines


@pytest.mark.parametrize("text", CLEAN)
def test_contrast_cases_pass_the_pr_body(text: str) -> None:
    ok, lines = report(COMPLETE + text + "\n")
    assert ok, lines


def test_fenced_code_and_html_comments_are_skipped() -> None:
    body = "```\ntrainmaster (a0, x)\n```\n<!-- M3 owner -->\n~~~\ntrain 85l\n~~~\n"
    assert find_hits(body) == []
    assert report(COMPLETE + body)[0]


@pytest.mark.parametrize(("text", "match"), FLAGGED)
def test_each_rule_fails_a_commit_subject(text: str, match: str, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("INFO", logger="outward_wording"):
        assert main(["subject", f"ci(wording): {text}"]) == 1
    out = caplog.text
    assert match in out and "FAIL" in out and "tracked in #N" in out


@pytest.mark.parametrize("text", CLEAN)
def test_contrast_cases_pass_a_commit_subject(text: str) -> None:
    assert main(["subject", f"ci(wording): {text}"]) == 0


def _run_issue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str, labels: list[str]) -> tuple[dict, str]:
    event = {"issue": {"number": 7, "body": body, "labels": [{"name": name} for name in labels]}}
    (tmp_path / "event.json").write_text(json.dumps(event), encoding="utf-8")
    output = tmp_path / "out.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    assert main(["issue", "--event", str(tmp_path / "event.json"), "--out", str(tmp_path / "c.md")]) == 0
    pairs = (line.split("=", 1) for line in output.read_text(encoding="utf-8").splitlines())
    return dict(pairs), (tmp_path / "c.md").read_text(encoding="utf-8")


@pytest.mark.parametrize(("text", "match"), FLAGGED)
def test_each_rule_flags_an_issue_body(text: str, match: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    outputs, comment = _run_issue(tmp_path, monkeypatch, f"Some context.\n\n{text}\n", [])
    assert outputs == {
        "hit": "true",
        "comment": "true",
        "label": "add",
        "number": "7",
        "marker": MARKER,
        "label_name": LABEL,
    }
    assert comment.startswith(MARKER) and match in comment and "the merge train (PR #N)" in comment


@pytest.mark.parametrize("text", CLEAN)
def test_a_clean_unlabelled_issue_posts_nothing(text: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    outputs, _ = _run_issue(tmp_path, monkeypatch, text, ["bug"])
    assert (outputs["hit"], outputs["comment"], outputs["label"]) == ("false", "false", "none")


@pytest.mark.parametrize(
    ("body", "labels", "expected"),
    [
        ("trainmaster", [LABEL], ("true", "true", "keep")),
        ("clean now", [LABEL], ("false", "true", "remove")),
        ("clean", [], ("false", "false", "none")),
    ],
    ids=["still-flagged keeps the label", "fixed edit clears it", "clean posts nothing"],
)
def test_label_transitions(body: str, labels: list[str], expected: tuple[str, str, str]) -> None:
    issue = {"number": 1, "body": body, "labels": [{"name": name} for name in labels]}
    decision = issue_decision(issue, find_hits(body))
    assert (decision["hit"], decision["comment"], decision["label"]) == expected


def test_the_resolved_comment_says_so_without_listing_matches() -> None:
    comment = issue_comment([])
    assert comment.startswith(MARKER) and "passes" in comment and LABEL in comment


def test_raw_lines_are_never_echoed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Only the rule and the match leave the detector: no @mention, link or workflow command replays."""
    body = "::warning::@someone see https://example.invalid the trainmaster said so\n"
    with caplog.at_level("INFO", logger="outward_wording"):
        outputs, comment = _run_issue(tmp_path, monkeypatch, body, [])
    assert outputs["hit"] == "true" and "`trainmaster`" in comment
    for text in (comment, caplog.text):
        assert "@someone" not in text and "example.invalid" not in text and "::warning::" not in text
    ok, lines = report(COMPLETE + body)
    assert not ok and not any("@someone" in line for line in lines), lines
