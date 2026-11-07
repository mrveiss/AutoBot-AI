#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#18098 -- `frontend_analysis_lib.IssueSeverity` is the canonical `Severity`.

The script used to declare its own four-rung ladder with the canonical's values. It only
compares members by identity and never iterates, serializes or renders by name, so the
alias must leave the issue list and the markdown report byte-identical. The expected
strings below were captured from the pre-alias module, not from the aliased one.
"""

from __future__ import annotations

import importlib.util
import sys
from types import ModuleType

import pytest
from repo_tests._paths import repo_root

from autobot_shared.status_enums import Severity

_LIB = repo_root() / "autobot-infrastructure" / "shared" / "scripts" / "debug" / "frontend_analysis_lib.py"

_EXPECTED_ISSUES = [
    ("console_error", "critical", "Cannot read x"),
    ("console_error", "high", "boom"),
    ("network_error", "critical", "HTTP 500: http://a/1"),
    ("network_error", "high", "HTTP 404: http://a/2"),
    ("script_error", "critical", "TypeError: y"),
]

_EXPECTED_REPORT = (
    "# Frontend Analysis Report\n\n## Summary\n\n- Console logs captured: 0\n- Page errors: 0\n"
    "- Network requests: 0\n- Issues detected: 6\n- Analysis complete: False\n\n## Detected Issues\n\n"
    "### Critical\n\n- **console_error**: Cannot read x\n  - Recommendation: Check browser console "
    "for stack trace\n- **network_error**: HTTP 500: http://a/1\n  - Recommendation: Check network "
    "tab and server logs\n- **script_error**: TypeError: y\n  - Recommendation: Check JavaScript "
    "console for details\n\n### High\n\n- **console_error**: boom\n- **network_error**: HTTP 404: "
    "http://a/2\n\n### Medium\n\n- **dom_error**: mid"
)


@pytest.fixture(scope="module")
def lib() -> ModuleType:
    spec = importlib.util.spec_from_file_location("frontend_analysis_lib_18098", _LIB)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(spec.name, None)


def _debugger(lib: ModuleType):
    dbg = lib.FrontendDebugger(verbose=False)
    dbg.console_logs = [
        lib.ConsoleLogEntry("error", "Cannot read x"),
        lib.ConsoleLogEntry("error", "boom", {"url": "u"}),
        lib.ConsoleLogEntry("log", "fine"),
    ]
    dbg.network_responses = [
        lib.NetworkResponseInfo("http://a/1", 500, False),
        lib.NetworkResponseInfo("http://a/2", 404, False),
        lib.NetworkResponseInfo("http://a/3", 200, True),
    ]
    dbg.errors = ["TypeError: y"]
    return dbg


def test_issue_severity_is_the_canonical_enum(lib: ModuleType) -> None:
    assert lib.IssueSeverity is Severity


def test_detected_issues_are_unchanged(lib: ModuleType) -> None:
    issues = _debugger(lib)._detect_issues()
    assert [(i.type.value, i.severity.value, i.message) for i in issues] == _EXPECTED_ISSUES


def test_the_markdown_report_is_unchanged(lib: ModuleType) -> None:
    issues = _debugger(lib)._detect_issues()
    issues.append(lib.FrontendIssue(lib.IssueType.DOM_ERROR, lib.IssueSeverity.MEDIUM, "mid"))
    assert lib.generate_issue_report(lib.AnalysisResult(issues=issues)) == _EXPECTED_REPORT
