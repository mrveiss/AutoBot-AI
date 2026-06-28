# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for the py-sync-requests-in-async rule."""

import ast
from pathlib import Path

from tools.lint.canonical.context import Context
from tools.lint.canonical.rules import py_sync_requests_in_async

FIXTURES = Path(__file__).parent.parent / "fixtures" / "py_sync_requests_in_async"


def _check(name: str) -> list:
    path = FIXTURES / name
    ctx = Context(repo_root=path.parent)
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return py_sync_requests_in_async.check(path, tree, ctx)


def test_positive_flags_only_the_async_call():
    diags = _check("positive.py")
    assert len(diags) == 1
    assert diags[0].rule_id == "py-sync-requests-in-async"
    assert diags[0].severity == "warn"


def test_negative_fixture_produces_no_diagnostics():
    assert _check("negative.py") == []


def test_waiver_fixture_produces_no_diagnostics():
    assert _check("waiver.py") == []


def test_rule_metadata_present():
    for attr in ("RULE_ID", "ISSUE", "SEVERITY", "TARGETS", "DESCRIPTION", "FIX_HINT"):
        assert hasattr(py_sync_requests_in_async, attr), f"missing {attr}"
    assert py_sync_requests_in_async.SEVERITY == "warn"
