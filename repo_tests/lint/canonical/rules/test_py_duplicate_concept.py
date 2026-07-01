# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for the py-duplicate-concept rule."""

import ast
from pathlib import Path

from tools.lint.canonical.context import Context
from tools.lint.canonical.rules import py_duplicate_concept

FIXTURES = Path(__file__).parent.parent / "fixtures" / "py_duplicate_concept"


def _check(name: str) -> list:
    path = FIXTURES / name
    ctx = Context(repo_root=path.parent)
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return py_duplicate_concept.check(path, tree, ctx)


def test_positive_flags_enhanced_with_base():
    diags = _check("positive.py")
    assert len(diags) == 1
    assert diags[0].rule_id == "py-duplicate-concept"
    assert diags[0].severity == "block"
    assert "EnhancedFoo" in diags[0].message


def test_positive_flags_infix_and_standalone():
    """Infix (AIStackEnhancedSearchData) + function names fire without a base."""
    diags = _check("positive_infix.py")
    names = {d.message.split("'")[1] for d in diags}
    assert names == {
        "AIStackEnhancedSearchData",
        "KnowledgeUnifiedSearchResponse",
        "get_consolidated_stats",
    }
    assert all(d.severity == "block" for d in diags)


def test_negative_fixture_produces_no_diagnostics():
    # Canonical names + allow-listed 'unified diff' git term -> no diagnostics.
    assert _check("negative.py") == []


def test_waiver_fixture_produces_no_diagnostics():
    assert _check("waiver.py") == []


def test_rule_metadata_present():
    for attr in ("RULE_ID", "ISSUE", "SEVERITY", "TARGETS", "DESCRIPTION", "FIX_HINT"):
        assert hasattr(py_duplicate_concept, attr), f"missing {attr}"
    assert py_duplicate_concept.SEVERITY == "block"
