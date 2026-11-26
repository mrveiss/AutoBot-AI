#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A failed tracker lookup fails the audit instead of reporting a clean run (#21582).

An empty closed-tracker set made ``scan`` skip every file, so ``gh`` failing looked like zero
findings. Exit codes: 0 clean, 1 findings, 2 the audit could not run.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import audit_issue_lookup as lookup
import audit_unwired_trackers as audit
import pytest


def _gh_fails(*_a, **_k):
    raise subprocess.CalledProcessError(4, ["gh", "issue", "list"])


def _run_main(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str]:
    with patch.object(sys, "argv", ["audit", *argv]):
        rc = audit.main()
    return rc, capsys.readouterr().out


def test_failing_gh_returns_lookup_code_and_writes_no_report(capsys: pytest.CaptureFixture[str]) -> None:
    with patch.object(audit.subprocess, "run", side_effect=_gh_fails):
        rc, out = _run_main(capsys, "--json")
    assert rc == audit.EXIT_LOOKUP_FAILED == 2
    assert out == ""  # no "[]" and no "No findings" claim


def test_unparsable_gh_output_returns_lookup_code_and_writes_no_report(capsys: pytest.CaptureFixture[str]) -> None:
    fake = MagicMock(returncode=0, stdout="<<not json>>", stderr="")
    with patch.object(audit.subprocess, "run", return_value=fake):
        rc, out = _run_main(capsys)
    assert rc == audit.EXIT_LOOKUP_FAILED
    assert out == ""


def test_file_issues_is_not_reached_from_a_degraded_scan(capsys: pytest.CaptureFixture[str]) -> None:
    with (
        patch.object(audit.subprocess, "run", side_effect=_gh_fails),
        patch.object(audit, "file_discovery_issue") as filed,
        patch.object(audit, "existing_audit_issue_keys") as dedupe,
    ):
        rc, _ = _run_main(capsys, "--file-issues")
    assert rc == audit.EXIT_LOOKUP_FAILED
    filed.assert_not_called()
    dedupe.assert_not_called()


def test_good_lookup_keeps_the_clean_and_findings_codes(capsys: pytest.CaptureFixture[str]) -> None:
    finding = audit.Finding(file="a/b.py", tracker=7, tracker_state="CLOSED", production_callers=0)
    with patch.object(audit, "scan", return_value=[]):
        rc, out = _run_main(capsys, "--json")
    assert (rc, json.loads(out)) == (audit.EXIT_CLEAN, [])
    with patch.object(audit, "scan", return_value=[finding]):
        rc, out = _run_main(capsys, "--json")
    assert rc == audit.EXIT_FINDINGS
    assert json.loads(out)[0]["tracker"] == 7


def test_failing_dedupe_lookup_files_nothing_and_returns_lookup_code(capsys: pytest.CaptureFixture[str]) -> None:
    finding = audit.Finding(file="a/b.py", tracker=7, tracker_state="CLOSED", production_callers=0)
    with (
        patch.object(audit, "scan", return_value=[finding]),
        patch.object(audit.subprocess, "run", side_effect=_gh_fails),
        patch.object(audit, "file_discovery_issue") as filed,
    ):
        rc, out = _run_main(capsys, "--file-issues")
    assert rc == audit.EXIT_LOOKUP_FAILED
    filed.assert_not_called()
    assert out == ""


def test_unparsable_dedupe_lookup_raises() -> None:
    fake = MagicMock(returncode=0, stdout="<<not json>>", stderr="")
    with patch.object(audit.subprocess, "run", return_value=fake):
        with pytest.raises(audit.TrackerLookupError):
            lookup.existing_audit_issue_keys()


def test_unreadable_registry_file_raises_naming_the_file(tmp_path: Path) -> None:
    (tmp_path / "bad_registry.py").write_bytes(b"\x80\x81\xfe\xff")
    with patch.object(audit, "ROUTER_REGISTRY_DIR", tmp_path):
        with pytest.raises(audit.TrackerLookupError, match="bad_registry.py"):
            audit.load_router_registry_modules()


def test_closed_issue_list_at_the_limit_raises() -> None:
    """A result the size of --limit may be truncated; older closed trackers would read as open."""
    full = json.dumps([{"number": n} for n in range(lookup.CLOSED_ISSUE_LIMIT)])
    with patch.object(audit.subprocess, "run", return_value=MagicMock(returncode=0, stdout=full, stderr="")):
        with pytest.raises(audit.TrackerLookupError, match=str(lookup.CLOSED_ISSUE_LIMIT)):
            lookup.fetch_closed_tracker_set()


def test_closed_issue_list_under_the_limit_is_returned() -> None:
    short = json.dumps([{"number": n} for n in range(lookup.CLOSED_ISSUE_LIMIT - 1)])
    with patch.object(audit.subprocess, "run", return_value=MagicMock(returncode=0, stdout=short, stderr="")):
        assert len(lookup.fetch_closed_tracker_set()) == lookup.CLOSED_ISSUE_LIMIT - 1


# ---------------------------------------------------------------------------
# #22199 — search query shape, (module, tracker) dedup, truncation, closed-issue handling
# ---------------------------------------------------------------------------


def _issue(num: int, stem: str, tracker: int, path: str | None = None, **extra) -> dict:
    body = f"[`{path}`]({path}) cites tracker" if path else ""
    title = f"discovery(unwired-tracker): wire in {stem} (tracker #{tracker} closed prematurely)"
    return {"number": num, "title": title, "body": body, **extra}


def _finding(path: str, tracker: int) -> audit.Finding:
    return audit.Finding(file=path, tracker=tracker, tracker_state="CLOSED", production_callers=0)


def _gh_stub(open_items: list[dict], closed_items: list[dict]):
    """``_gh_json`` stand-in answering the open and the closed audit listing."""

    def fake(cmd: list[str], _timeout: int, _what: str) -> list[dict]:
        return closed_items if cmd[cmd.index("--state") + 1] == "closed" else open_items

    return fake


def _filed_files(open_items: list[dict], closed_items: list[dict], findings: list[audit.Finding]) -> list[str]:
    with (
        patch.object(lookup, "_gh_json", side_effect=_gh_stub(open_items, closed_items)),
        patch.object(audit, "file_discovery_issue", return_value=1) as filed,
    ):
        audit._file_new_issues(findings, 20)
    return [c.args[0].file for c in filed.call_args_list]


def _query_is_effective(q: str) -> bool:
    """GitHub drops parentheses from an unquoted term (0 hits); the phrase must be quoted and title-scoped."""
    return q.startswith('"discovery(unwired-tracker)"') and "in:title" in q


def test_audit_queries_are_a_quoted_title_phrase() -> None:
    for cmd in (lookup._OPEN_AUDIT_CMD, lookup._CLOSED_AUDIT_CMD):
        assert _query_is_effective(cmd[cmd.index("--search") + 1])
    assert not _query_is_effective("discovery(unwired-tracker)")  # contrast: the old, zero-hit form
    assert "stateReason" in lookup._CLOSED_AUDIT_CMD[-1] and "comments" in lookup._CLOSED_AUDIT_CMD[-1]


def test_same_tracker_different_modules_are_both_filed_once() -> None:
    findings = [_finding("a/hierarchical_agent.py", 657), _finding("b/delegate_tool.py", 657)]
    assert _filed_files([], [], findings) == ["a/hierarchical_agent.py", "b/delegate_tool.py"]


def test_open_issue_for_one_module_does_not_shadow_its_sibling() -> None:
    open_issues = [_issue(1, "hierarchical_agent", 657, "a/hierarchical_agent.py")]
    findings = [_finding("a/hierarchical_agent.py", 657), _finding("b/delegate_tool.py", 657)]
    assert _filed_files(open_issues, [], findings) == ["b/delegate_tool.py"]


def test_title_stem_fallback_dedups_an_issue_without_a_body_path() -> None:
    assert _filed_files([_issue(1, "foo", 5)], [], [_finding("x/foo.py", 5)]) == []


def test_not_planned_closed_issue_is_not_refiled() -> None:
    closed = [_issue(2, "foo", 5, "x/foo.py", stateReason="NOT_PLANNED", comments=[])]
    assert _filed_files([], closed, [_finding("x/foo.py", 5)]) == []


def test_deferral_note_in_a_comment_or_body_is_not_refiled() -> None:
    note = {"body": "### Wire-in deferred\nscaffold for a future feature"}
    in_comment = _issue(2, "foo", 5, "x/foo.py", stateReason="COMPLETED", comments=[note])
    in_body = _issue(3, "bar", 6, "x/bar.py", stateReason="COMPLETED", comments=[])
    in_body["body"] += "\n### Wire-in deferred\nnot needed"
    findings = [_finding("x/foo.py", 5), _finding("x/bar.py", 6)]
    assert _filed_files([], [in_comment, in_body], findings) == []


def test_template_mention_of_the_deferral_marker_is_not_a_deferral() -> None:
    """The body template names the marker inline in backticks; that must not count as a note."""
    templ = _issue(2, "foo", 5, "x/foo.py", stateReason="COMPLETED", comments=[])
    templ["body"] += "\n- [ ] Or this issue is closed with a `### Wire-in deferred` note"
    assert _filed_files([], [templ], [_finding("x/foo.py", 5)]) == ["x/foo.py"]


def test_a_longer_heading_that_starts_with_the_marker_is_not_a_deferral() -> None:
    """Only the exact heading counts: ``## Wire-in deferred-not`` is a different heading (#22199)."""
    other = _issue(2, "foo", 5, "x/foo.py", stateReason="COMPLETED", comments=[{"body": "## Wire-in deferred-not"}])
    assert _filed_files([], [other], [_finding("x/foo.py", 5)]) == ["x/foo.py"]


@pytest.mark.parametrize(
    "heading", ["## Wire-in deferred", "###### Wire-in deferred", "###\nWire-in deferred", "#Wire-in deferred"]
)
def test_only_the_exact_level_three_single_line_heading_is_a_deferral(heading: str) -> None:
    """Contrast: other heading levels and a heading split across lines are not the deferral note (#22199)."""
    other = _issue(2, "foo", 5, "x/foo.py", stateReason="COMPLETED", comments=[{"body": heading}])
    assert _filed_files([], [other], [_finding("x/foo.py", 5)]) == ["x/foo.py"]


def test_completed_closed_issue_that_is_still_unwired_is_refiled() -> None:
    """Regression: closed COMPLETED without a deferral note, yet the module is still unwired."""
    closed = [_issue(2, "foo", 5, "x/foo.py", stateReason="COMPLETED", comments=[{"body": "done"}])]
    assert _filed_files([], closed, [_finding("x/foo.py", 5)]) == ["x/foo.py"]


def test_audit_issue_lists_at_the_limit_raise() -> None:
    full = [_issue(n, f"m{n}", n, f"p/m{n}.py") for n in range(lookup.OPEN_AUDIT_ISSUE_LIMIT)]
    for open_items, closed_items in ((full, []), ([], full)):
        with patch.object(lookup, "_gh_json", side_effect=_gh_stub(open_items, closed_items)):
            with pytest.raises(audit.TrackerLookupError, match=str(lookup.OPEN_AUDIT_ISSUE_LIMIT)):
                lookup.existing_audit_issue_keys()
    # contrast: one under the limit is accepted
    with patch.object(lookup, "_gh_json", side_effect=_gh_stub(full[:-1], [])):
        assert len(lookup.existing_audit_issue_keys()) == lookup.OPEN_AUDIT_ISSUE_LIMIT - 1


def test_legacy_stem_issue_does_not_suppress_two_modules_sharing_the_stem() -> None:
    """A body-less issue names only a stem; with two same-stem findings it identifies neither module."""
    findings = [_finding("a/hierarchical_agent.py", 657), _finding("b/hierarchical_agent.py", 657)]
    assert _filed_files([_issue(1, "hierarchical_agent", 657)], [], findings) == [
        "a/hierarchical_agent.py",
        "b/hierarchical_agent.py",
    ]


def test_legacy_stem_issue_still_suppresses_its_one_unambiguous_module() -> None:
    findings = [_finding("a/hierarchical_agent.py", 657), _finding("b/delegate_tool.py", 657)]
    assert _filed_files([_issue(1, "hierarchical_agent", 657)], [], findings) == ["b/delegate_tool.py"]
