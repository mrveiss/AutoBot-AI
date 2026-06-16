# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for Context — file iteration + AST cache."""

import ast
from pathlib import Path

import pytest

from tools.lint.canonical.context import Context, file_in_targets


def test_parse_caches_ast(tmp_path: Path) -> None:
    src = tmp_path / "sample.py"
    src.write_text("x = 1\n", encoding="utf-8")
    ctx = Context(repo_root=tmp_path)
    tree_a = ctx.parse(src)
    tree_b = ctx.parse(src)
    assert tree_a is tree_b
    assert isinstance(tree_a, ast.Module)


def test_parse_returns_none_on_syntax_error(tmp_path: Path) -> None:
    src = tmp_path / "broken.py"
    src.write_text("def (\n", encoding="utf-8")
    ctx = Context(repo_root=tmp_path)
    assert ctx.parse(src) is None


def test_parse_returns_none_for_missing_file(tmp_path: Path) -> None:
    ctx = Context(repo_root=tmp_path)
    assert ctx.parse(tmp_path / "nope.py") is None


def test_file_in_targets_matches_prefix(tmp_path: Path) -> None:
    f = tmp_path / "autobot-backend" / "api" / "foo.py"
    f.parent.mkdir(parents=True)
    f.write_text("", encoding="utf-8")
    assert file_in_targets(f, ["autobot-backend"], repo_root=tmp_path) is True
    assert file_in_targets(f, ["autobot-frontend"], repo_root=tmp_path) is False


def test_file_in_targets_handles_absolute_path(tmp_path: Path) -> None:
    f = tmp_path / "autobot-backend" / "x.py"
    f.parent.mkdir(parents=True)
    f.write_text("", encoding="utf-8")
    assert file_in_targets(f, ["autobot-backend"], repo_root=tmp_path) is True


def test_iter_targets_walks_only_targets(tmp_path: Path) -> None:
    (tmp_path / "autobot-backend").mkdir()
    (tmp_path / "autobot-backend" / "a.py").write_text("", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "b.py").write_text("", encoding="utf-8")
    ctx = Context(repo_root=tmp_path)
    files = list(ctx.iter_targets(["autobot-backend"], suffixes={".py"}))
    assert len(files) == 1
    assert files[0].name == "a.py"


def test_iter_targets_skips_excluded_dirs(tmp_path: Path) -> None:
    (tmp_path / "autobot-backend").mkdir()
    (tmp_path / "autobot-backend" / "a.py").write_text("", encoding="utf-8")
    cache = tmp_path / "autobot-backend" / "__pycache__"
    cache.mkdir()
    (cache / "b.py").write_text("", encoding="utf-8")
    ctx = Context(repo_root=tmp_path)
    files = list(ctx.iter_targets(["autobot-backend"], suffixes={".py"}))
    assert len(files) == 1
    assert "__pycache__" not in str(files[0])


def test_iter_targets_does_not_exclude_via_parent_path(tmp_path: Path) -> None:
    """Regression: _EXCLUDED_DIRS matched against the absolute path's parts
    used to filter out every file when the audit ran from inside an excluded
    parent dir (e.g. .worktrees/issue-XXXX/). The check must be relative to
    the target's base, not the absolute path."""
    parent = tmp_path / ".worktrees" / "issue-9999"
    target = parent / "autobot-backend"
    target.mkdir(parents=True)
    (target / "a.py").write_text("x = 1\n", encoding="utf-8")
    ctx = Context(repo_root=parent)
    files = list(ctx.iter_targets(["autobot-backend"], suffixes={".py"}))
    assert len(files) == 1
    assert files[0].name == "a.py"
