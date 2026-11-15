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
        patch.object(audit, "existing_audit_issues_by_tracker") as dedupe,
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
            audit.existing_audit_issues_by_tracker()


def test_unreadable_registry_file_raises_naming_the_file(tmp_path: Path) -> None:
    (tmp_path / "bad_registry.py").write_bytes(b"\x80\x81\xfe\xff")
    with patch.object(audit, "ROUTER_REGISTRY_DIR", tmp_path):
        with pytest.raises(audit.TrackerLookupError, match="bad_registry.py"):
            audit.load_router_registry_modules()
