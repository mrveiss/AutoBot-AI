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
            audit.existing_audit_issue_keys()


def test_unreadable_registry_file_raises_naming_the_file(tmp_path: Path) -> None:
    (tmp_path / "bad_registry.py").write_bytes(b"\x80\x81\xfe\xff")
    with patch.object(audit, "ROUTER_REGISTRY_DIR", tmp_path):
        with pytest.raises(audit.TrackerLookupError, match="bad_registry.py"):
            audit.load_router_registry_modules()


def test_closed_issue_list_at_the_limit_raises() -> None:
    """A result the size of --limit may be truncated; older closed trackers would read as open."""
    full = json.dumps([{"number": n} for n in range(audit.CLOSED_ISSUE_LIMIT)])
    with patch.object(audit.subprocess, "run", return_value=MagicMock(returncode=0, stdout=full, stderr="")):
        with pytest.raises(audit.TrackerLookupError, match=str(audit.CLOSED_ISSUE_LIMIT)):
            audit.fetch_closed_tracker_set()


def test_closed_issue_list_under_the_limit_is_returned() -> None:
    short = json.dumps([{"number": n} for n in range(audit.CLOSED_ISSUE_LIMIT - 1)])
    with patch.object(audit.subprocess, "run", return_value=MagicMock(returncode=0, stdout=short, stderr="")):
        assert len(audit.fetch_closed_tracker_set()) == audit.CLOSED_ISSUE_LIMIT - 1


# ---------------------------------------------------------------------------
# #22199 — search query shape, (module, tracker) dedup, open-list truncation
# ---------------------------------------------------------------------------


def _issue(num: int, stem: str, tracker: int, path: str | None = None) -> dict:
    body = f"[`{path}`]({path}) cites tracker" if path else ""
    return {
        "number": num,
        "title": f"discovery(unwired-tracker): wire in {stem} (tracker #{tracker} closed prematurely)",
        "body": body,
    }


def _finding(path: str, tracker: int) -> audit.Finding:
    return audit.Finding(file=path, tracker=tracker, tracker_state="CLOSED", production_callers=0)


def _search_arg(cmd: list[str]) -> str:
    return cmd[cmd.index("--search") + 1]


def _query_is_effective(q: str) -> bool:
    """GitHub drops parentheses from an unquoted term (0 hits); the phrase must be quoted and title-scoped."""
    return q.startswith('"discovery(unwired-tracker)"') and "in:title" in q


def test_open_audit_query_is_a_quoted_title_phrase() -> None:
    assert _query_is_effective(_search_arg(audit._OPEN_AUDIT_CMD))
    assert not _query_is_effective("discovery(unwired-tracker)")  # contrast: the old, zero-hit form


def test_same_tracker_different_modules_are_both_filed_once() -> None:
    findings = [_finding("a/hierarchical_agent.py", 657), _finding("b/delegate_tool.py", 657)]
    with (
        patch.object(audit, "existing_audit_issue_keys", return_value=set()),
        patch.object(audit, "file_discovery_issue", return_value=1) as filed,
    ):
        audit._file_new_issues(findings, 20)
    assert [c.args[0].file for c in filed.call_args_list] == ["a/hierarchical_agent.py", "b/delegate_tool.py"]


def test_open_issue_for_one_module_does_not_shadow_its_sibling() -> None:
    open_issues = [_issue(1, "hierarchical_agent", 657, "a/hierarchical_agent.py")]
    findings = [_finding("a/hierarchical_agent.py", 657), _finding("b/delegate_tool.py", 657)]
    with (
        patch.object(audit, "_gh_json", return_value=open_issues),
        patch.object(audit, "file_discovery_issue", return_value=2) as filed,
    ):
        audit._file_new_issues(findings, 20)
    assert [c.args[0].file for c in filed.call_args_list] == ["b/delegate_tool.py"]


def test_title_stem_fallback_dedups_an_issue_without_a_body_path() -> None:
    with (
        patch.object(audit, "_gh_json", return_value=[_issue(1, "foo", 5)]),
        patch.object(audit, "file_discovery_issue") as filed,
    ):
        audit._file_new_issues([_finding("x/foo.py", 5)], 20)
    filed.assert_not_called()


def test_open_audit_list_at_the_limit_raises() -> None:
    full = [_issue(n, f"m{n}", n, f"p/m{n}.py") for n in range(audit.OPEN_AUDIT_ISSUE_LIMIT)]
    with patch.object(audit, "_gh_json", return_value=full):
        with pytest.raises(audit.TrackerLookupError, match=str(audit.OPEN_AUDIT_ISSUE_LIMIT)):
            audit.existing_audit_issue_keys()
    with patch.object(audit, "_gh_json", return_value=full[:-1]):
        assert len(audit.existing_audit_issue_keys()) == audit.OPEN_AUDIT_ISSUE_LIMIT - 1
