# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for the py-banned-route-path rule."""

import ast
from pathlib import Path

from tools.lint.canonical.context import Context
from tools.lint.canonical.rules import py_banned_route_path

FIXTURES = Path(__file__).parent.parent / "fixtures" / "py_banned_route_path"


def _check(name: str) -> list:
    path = FIXTURES / name
    ctx = Context(repo_root=path.parent)
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return py_banned_route_path.check(path, tree, ctx)


def test_positive_flags_era_marker_paths():
    diags = _check("positive.py")
    assert len(diags) == 2
    tokens = sorted(d.message.split("'")[3] for d in diags)
    assert tokens == ["enhanced", "unified"]
    assert all(d.severity == "block" for d in diags)


def test_negative_fixture_produces_no_diagnostics():
    # Descriptive paths + domain adjective (/advanced-stats) -> no diagnostics.
    assert _check("negative.py") == []


def test_waiver_fixture_produces_no_diagnostics():
    assert _check("waiver.py") == []


def test_rule_metadata_present():
    for attr in ("RULE_ID", "ISSUE", "SEVERITY", "TARGETS", "DESCRIPTION", "FIX_HINT"):
        assert hasattr(py_banned_route_path, attr), f"missing {attr}"
    assert py_banned_route_path.SEVERITY == "block"
