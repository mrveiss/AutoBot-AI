# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for the three reporter formatters."""

import json
from pathlib import Path

import pytest

from tools.lint.canonical.diagnostic import Diagnostic
from tools.lint.canonical.reporter import to_json, to_markdown, to_pretty


@pytest.fixture
def sample_diagnostics() -> list[Diagnostic]:
    return [
        Diagnostic(
            rule_id="py-print-smoke",
            issue="#7458",
            severity="warn",
            file=Path("autobot-backend/api/foo.py"),
            line=42,
            col=4,
            message="print() in production",
            snippet="print('hi')",
            fix_hint="use logger",
        ),
        Diagnostic(
            rule_id="py-other",
            issue="#9999",
            severity="block",
            file=Path("autobot-backend/api/foo.py"),
            line=10,
            col=0,
            message="bad pattern",
            snippet="x",
            fix_hint="",
        ),
    ]


def test_to_pretty_groups_by_file(sample_diagnostics):
    out = to_pretty(sample_diagnostics)
    assert "autobot-backend/api/foo.py:10" in out
    assert "autobot-backend/api/foo.py:42" in out
    assert "py-print-smoke" in out
    assert "py-other" in out


def test_to_pretty_empty_returns_zero_violations():
    out = to_pretty([])
    assert "0 violations" in out


def test_to_json_is_round_trippable(sample_diagnostics):
    payload = to_json(sample_diagnostics)
    parsed = json.loads(payload)
    assert isinstance(parsed, list)
    assert parsed[0]["rule_id"] in {"py-print-smoke", "py-other"}
    assert parsed[0]["file"].endswith("foo.py")


def test_to_markdown_summary_table(sample_diagnostics):
    out = to_markdown(
        sample_diagnostics,
        scan_meta={
            "scanned_files": 100,
            "duration_seconds": 1.2,
            "rule_count": 2,
        },
    )
    assert "# Canonical-style audit" in out
    assert "block" in out
    assert "warn" in out
    assert "py-print-smoke" in out
    assert "scanned 100 files" in out


def test_to_markdown_handles_empty():
    out = to_markdown([], scan_meta={"scanned_files": 0, "duration_seconds": 0, "rule_count": 0})
    assert "no violations" in out.lower()
