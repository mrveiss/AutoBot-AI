# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for the py-banned-suffix-filename rule."""

import ast
from pathlib import Path

from tools.lint.canonical.context import Context
from tools.lint.canonical.rules import py_banned_suffix_filename

FIXTURES = Path(__file__).parent.parent / "fixtures" / "py_banned_suffix_filename"


def _check(name: str) -> list:
    path = FIXTURES / name
    ctx = Context(repo_root=path.parent)
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return py_banned_suffix_filename.check(path, tree, ctx)


def test_v2_suffix_flagged():
    diags = _check("sample_v2.py")
    assert len(diags) == 1
    assert diags[0].rule_id == "py-banned-suffix-filename"
    assert diags[0].severity == "block"


def test_fix_suffix_on_nontest_flagged():
    assert len(_check("widget_fix.py")) == 1


def test_fix_suffix_on_test_allowed():
    assert _check("test_widget_fix.py") == []


def test_clean_name_produces_no_diagnostics():
    assert _check("clean.py") == []


def test_rule_metadata_present():
    for attr in ("RULE_ID", "ISSUE", "SEVERITY", "TARGETS", "DESCRIPTION", "FIX_HINT"):
        assert hasattr(py_banned_suffix_filename, attr), f"missing {attr}"
    assert py_banned_suffix_filename.SEVERITY == "block"
