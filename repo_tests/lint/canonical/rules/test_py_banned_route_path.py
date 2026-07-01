# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for the py-banned-route-path rule."""

import ast
from pathlib import Path

from tools.lint.canonical.context import Context
from tools.lint.canonical.rules import py_banned_route_path

FIXTURES = Path(__file__).parent.parent / "fixtures" / "py_banned_route_path"
REG_FIXTURES = FIXTURES / "initialization" / "router_registry"


def _check(name: str) -> list:
    path = FIXTURES / name
    ctx = Context(repo_root=path.parent)
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return py_banned_route_path.check(path, tree, ctx)


def _check_reg(name: str) -> list:
    path = REG_FIXTURES / name
    ctx = Context(repo_root=path.parent)
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return py_banned_route_path.check(path, tree, ctx)


# ── Decorator surface (Surface 1) + include_router (Surface 2) ─────────────


def test_positive_flags_era_marker_paths():
    # positive.py: 2 decorator violations + 1 include_router violation = 3 total
    diags = _check("positive.py")
    assert len(diags) == 3
    tokens = sorted(d.message.split("'")[3] for d in diags)
    assert tokens == ["consolidated", "enhanced", "unified"]
    assert all(d.severity == "block" for d in diags)


def test_negative_fixture_produces_no_diagnostics():
    # Descriptive paths + domain adjective (/advanced-stats) + /reporting → no diagnostics.
    assert _check("negative.py") == []


def test_waiver_fixture_produces_no_diagnostics():
    assert _check("waiver.py") == []


# ── Registry-config surface (Surface 3) ────────────────────────────────────


def test_positive_flags_registry_and_mount_prefixes():
    # positive_reg.py (under router_registry/): registry tuple + include_router → 2 diagnostics
    diags = _check_reg("positive_reg.py")
    assert len(diags) == 2
    tokens = sorted(d.message.split("'")[3] for d in diags)
    assert tokens == ["enhanced", "unified"]
    assert all(d.severity == "block" for d in diags)
    # Verify the registry-prefix diagnostic is labelled distinctly from a decorator path.
    labels = [d.message.split("'")[0].strip() for d in diags]
    assert "registry prefix" in labels or "mount prefix" in labels


def test_negative_registry_prefix_produces_no_diagnostics():
    # negative_reg.py: /reporting and /advanced-stats are descriptive — no violations.
    assert _check_reg("negative_reg.py") == []


# ── Rule metadata ───────────────────────────────────────────────────────────


def test_rule_metadata_present():
    for attr in ("RULE_ID", "ISSUE", "SEVERITY", "TARGETS", "DESCRIPTION", "FIX_HINT"):
        assert hasattr(py_banned_route_path, attr), f"missing {attr}"
    assert py_banned_route_path.SEVERITY == "block"
