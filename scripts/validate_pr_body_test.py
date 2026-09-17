# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the local PR-body validator (#16859).

``validate()`` must call the SAME functions CI calls, not a reimplementation --
that is the whole point of this script, so the tests that matter most assert
the gate functions are actually invoked (patched and checked for a call),
not just that some plausible-looking result comes back. The CLI tests below
that cover ``--pr`` never hit the network: ``subprocess.run`` is patched.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from validate_pr_body import PRLookupError, main, pr_fields, validate  # noqa: E402

_GOOD_BODY = (
    "## Thinking Path\nreasoning\n\n"
    "## What Changed\nstuff\n\n"
    "## Single-issue rationale\nnarrow fix\n\n"
    "## Verification\ntests pass\n\n"
    "## Model Used\nOpus 5\n\n"
    "Closes #1\n"
)

_MISSING_HEADINGS_BODY = "## Summary\nstuff\n\nCloses #1\n"


def _run(*args: str, capsys: pytest.CaptureFixture) -> tuple[int, str]:
    exit_code = main(list(args))
    return exit_code, capsys.readouterr().out


# ---------------------------------------------------------------------------
# validate(): must call the real gates, not reimplement them
# ---------------------------------------------------------------------------


def test_validate_calls_both_real_gate_functions():
    """The point of this script is dispatch, not a third rule set.

    Patched at the point ``validate_pr_body`` imported them, so a body that
    would pass CI's own gates must pass here through the identical code path.
    """
    with (
        patch("validate_pr_body.check_template_sections", return_value=(True, ["ok"])) as sections,
        patch("validate_pr_body.check_batching", return_value=(True, "ok")) as batching,
    ):
        assert validate("anything", actor="a", branch="b", title="t") is True

    sections.assert_called_once_with("anything")
    batching.assert_called_once_with("anything", actor="a", branch="b", title="t")


def test_validate_fails_when_either_gate_fails():
    with (
        patch("validate_pr_body.check_template_sections", return_value=(False, [])),
        patch("validate_pr_body.check_batching", return_value=(True, "ok")),
    ):
        assert validate("x") is False
    with (
        patch("validate_pr_body.check_template_sections", return_value=(True, [])),
        patch("validate_pr_body.check_batching", return_value=(False, "no")),
    ):
        assert validate("x") is False


def test_a_genuinely_complete_body_passes():
    """End-to-end against the real gates, not mocked -- the body a correct
    author would actually write."""
    assert validate(_GOOD_BODY) is True


def test_wrong_headings_fail():
    assert validate(_MISSING_HEADINGS_BODY) is False


def test_single_closing_keyword_without_rationale_fails():
    """The batching gate's own rule: even one Closes needs a stated reason."""
    body = "## Thinking Path\nx\n\n## What Changed\nx\n\n## Verification\nx\n\n" "## Model Used\nx\n\nCloses #1\n"
    assert validate(body) is False


# ---------------------------------------------------------------------------
# pr_fields(): field mapping must match pr-issue-validation.yml exactly
# ---------------------------------------------------------------------------


def test_pr_fields_maps_gh_json_to_the_ci_field_names():
    payload = {
        "body": "## Thinking Path\n...",
        "author": {"login": "mrveiss"},
        "headRefName": "issue-16859-pr-body-check",
        "title": "fix: wire the body gates into pre-push",
    }
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout=json.dumps(payload), stderr="")
    with patch("validate_pr_body.subprocess.run", return_value=completed) as run:
        fields = pr_fields("16859")

    assert fields == {
        "body": payload["body"],
        "actor": "mrveiss",
        "branch": "issue-16859-pr-body-check",
        "title": payload["title"],
    }
    args = run.call_args.args[0]
    assert args[:3] == ["gh", "pr", "view"]
    assert "16859" in args


def test_pr_fields_tolerates_missing_optional_json_keys():
    """A PR with no author on record (deleted account) must not crash the lookup."""
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout=json.dumps({"body": None}), stderr="")
    with patch("validate_pr_body.subprocess.run", return_value=completed):
        fields = pr_fields("16859")
    assert fields == {"body": "", "actor": "", "branch": "", "title": ""}


def test_pr_fields_raises_when_gh_is_missing():
    with patch("validate_pr_body.subprocess.run", side_effect=FileNotFoundError()):
        with pytest.raises(PRLookupError, match="gh CLI not found"):
            pr_fields("16859")


def test_pr_fields_raises_on_gh_failure_with_stderr_in_the_message():
    """The failure has to say WHY, not just that it failed -- otherwise a
    real 'no such PR' and a transient network error read identically."""
    err = subprocess.CalledProcessError(1, ["gh"], stderr="no pull requests found for branch")
    with patch("validate_pr_body.subprocess.run", side_effect=err):
        with pytest.raises(PRLookupError, match="no pull requests found"):
            pr_fields("no-such-branch")


def test_pr_fields_raises_on_timeout():
    with patch(
        "validate_pr_body.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd=["gh"], timeout=30),
    ):
        with pytest.raises(PRLookupError, match="timed out"):
            pr_fields("16859")


def test_pr_fields_raises_on_unparseable_json():
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="not json", stderr="")
    with patch("validate_pr_body.subprocess.run", return_value=completed):
        with pytest.raises(PRLookupError, match="unparseable"):
            pr_fields("16859")


# ---------------------------------------------------------------------------
# main(): CLI dispatch
# ---------------------------------------------------------------------------


def test_main_file_mode_exits_zero_on_a_good_body(tmp_path, capsys):
    body_file = tmp_path / "body.md"
    body_file.write_text(_GOOD_BODY, encoding="utf-8")
    exit_code, _ = _run("--file", str(body_file), capsys=capsys)
    assert exit_code == 0


def test_main_file_mode_exits_one_on_a_bad_body(tmp_path, capsys):
    body_file = tmp_path / "body.md"
    body_file.write_text(_MISSING_HEADINGS_BODY, encoding="utf-8")
    exit_code, out = _run("--file", str(body_file), capsys=capsys)
    assert exit_code == 1
    assert "Thinking Path" in out


def test_main_file_mode_reports_a_missing_file_without_a_traceback(tmp_path, capsys):
    missing = tmp_path / "does-not-exist.md"
    exit_code, _ = _run("--file", str(missing), capsys=capsys)
    assert exit_code == 1


def test_main_pr_mode_uses_the_fetched_fields(capsys):
    payload = {"body": _GOOD_BODY, "author": {"login": "mrveiss"}, "headRefName": "b", "title": "t"}
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout=json.dumps(payload), stderr="")
    with patch("validate_pr_body.subprocess.run", return_value=completed):
        exit_code, _ = _run("--pr", "16859", capsys=capsys)
    assert exit_code == 0


def test_main_pr_mode_surfaces_the_lookup_failure_as_an_error_not_a_crash(capsys):
    err = subprocess.CalledProcessError(1, ["gh"], stderr="no pull requests found")
    with patch("validate_pr_body.subprocess.run", side_effect=err):
        exit_code, out = _run("--pr", "999999", capsys=capsys)
    assert exit_code == 1
    assert "no pull requests found" in out


def test_file_and_pr_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        main(["--file", "x", "--pr", "1"])


def test_one_of_file_or_pr_is_required():
    with pytest.raises(SystemExit):
        main([])
