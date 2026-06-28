# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for the py-adhoc-db-engine rule."""

import ast
from pathlib import Path

from tools.lint.canonical.context import Context
from tools.lint.canonical.rules import py_adhoc_db_engine

FIXTURES = Path(__file__).parent.parent / "fixtures" / "py_adhoc_db_engine"


def _check(name: str) -> list:
    path = FIXTURES / name
    ctx = Context(repo_root=path.parent)
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return py_adhoc_db_engine.check(path, tree, ctx)


def test_positive_fixture_flags_engine_and_session():
    diags = _check("positive.py")
    assert len(diags) == 2
    assert all(d.rule_id == "py-adhoc-db-engine" for d in diags)
    assert all(d.severity == "warn" for d in diags)


def test_negative_fixture_produces_no_diagnostics():
    assert _check("negative.py") == []


def test_waiver_fixture_produces_no_diagnostics():
    assert _check("waiver.py") == []


def test_rule_metadata_present():
    for attr in ("RULE_ID", "ISSUE", "SEVERITY", "TARGETS", "DESCRIPTION", "FIX_HINT"):
        assert hasattr(py_adhoc_db_engine, attr), f"missing {attr}"
    assert py_adhoc_db_engine.SEVERITY == "warn"
