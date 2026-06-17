# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for rule discovery + execution."""

import ast
import textwrap
from pathlib import Path
from types import ModuleType

import pytest

from tools.lint.canonical.context import Context
from tools.lint.canonical.diagnostic import Diagnostic
from tools.lint.canonical.registry import discover_rules, run_rules


def _make_rule_module(name: str, severity: str = "warn") -> ModuleType:
    mod = ModuleType(name)
    mod.RULE_ID = name.replace("_", "-")
    mod.ISSUE = "#7458"
    mod.SEVERITY = severity
    mod.TARGETS = ["pkg"]
    mod.DESCRIPTION = "test rule"
    mod.FIX_HINT = "fix it"

    def check(file_path: Path, tree: ast.AST, ctx: Context) -> list[Diagnostic]:
        return [
            Diagnostic(
                rule_id=mod.RULE_ID,
                issue=mod.ISSUE,
                severity=mod.SEVERITY,
                file=file_path,
                line=1,
                col=0,
                message="m",
                snippet="s",
            )
        ]

    mod.check = check
    return mod


def test_discover_rules_loads_canonical_smoke_module():
    rules = discover_rules("tools.lint.canonical.rules")
    rule_ids = {r.RULE_ID for r in rules}
    assert "py-print-smoke" in rule_ids


def test_run_rules_invokes_each_rule_per_file(tmp_path: Path):
    src = tmp_path / "pkg" / "x.py"
    src.parent.mkdir()
    src.write_text("x = 1\n", encoding="utf-8")
    ctx = Context(repo_root=tmp_path)
    rule = _make_rule_module("rule_a")
    diags = run_rules([rule], [src], ctx)
    assert len(diags) == 1
    assert diags[0].rule_id == "rule-a"


def test_run_rules_skips_files_outside_targets(tmp_path: Path):
    src = tmp_path / "other" / "x.py"
    src.parent.mkdir()
    src.write_text("x = 1\n", encoding="utf-8")
    ctx = Context(repo_root=tmp_path)
    rule = _make_rule_module("rule_a")  # TARGETS = ["pkg"]
    diags = run_rules([rule], [src], ctx)
    assert diags == []


def test_run_rules_skips_files_with_syntax_errors(tmp_path: Path):
    src = tmp_path / "pkg" / "broken.py"
    src.parent.mkdir()
    src.write_text("def (\n", encoding="utf-8")
    ctx = Context(repo_root=tmp_path)
    rule = _make_rule_module("rule_a")
    assert run_rules([rule], [src], ctx) == []
