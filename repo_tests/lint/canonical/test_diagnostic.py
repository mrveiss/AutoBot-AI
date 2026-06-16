# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for the Diagnostic dataclass — the shared violation record."""

from pathlib import Path

import pytest

from tools.lint.canonical.diagnostic import Diagnostic


def test_diagnostic_required_fields():
    d = Diagnostic(
        rule_id="py-print-smoke",
        issue="#7458",
        severity="warn",
        file=Path("autobot-backend/foo.py"),
        line=1,
        col=0,
        message="print() in production",
        snippet="print('hi')",
    )
    assert d.rule_id == "py-print-smoke"
    assert d.fix_hint == ""
    assert d.auto_fixable is False


def test_diagnostic_is_frozen():
    d = Diagnostic(
        rule_id="r",
        issue="#1",
        severity="warn",
        file=Path("a.py"),
        line=1,
        col=0,
        message="m",
        snippet="s",
    )
    with pytest.raises(AttributeError):
        d.line = 2  # type: ignore[misc]


def test_diagnostic_to_dict_round_trip():
    d = Diagnostic(
        rule_id="r",
        issue="#1",
        severity="warn",
        file=Path("a.py"),
        line=1,
        col=0,
        message="m",
        snippet="s",
        fix_hint="use foo()",
        auto_fixable=True,
    )
    payload = d.to_dict()
    assert payload["file"] == "a.py"  # Path serialized to str
    assert payload["auto_fixable"] is True


def test_diagnostic_severity_validated():
    with pytest.raises(ValueError, match="severity"):
        Diagnostic(
            rule_id="r",
            issue="#1",
            severity="catastrophic",  # type: ignore[arg-type]
            file=Path("a.py"),
            line=1,
            col=0,
            message="m",
            snippet="s",
        )
