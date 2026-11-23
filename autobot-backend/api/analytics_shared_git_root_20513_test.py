# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`git_root_of` accepts only a repository of its own and nothing that redirects to another one (#20513)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api import analytics_shared as mod
from api.codebase_analytics import source_paths
from api.codebase_analytics.endpoints import report


def _real(tmp_path):
    root = tmp_path / "real"
    (root / ".git").mkdir(parents=True, exist_ok=True)
    return root


def _gitfile(tmp_path):
    root = tmp_path / "gitfile"
    root.mkdir()
    (root / ".git").write_text("gitdir: ../elsewhere\n", encoding="utf-8")
    return root


def _symlinked_git(tmp_path):
    root = tmp_path / "linked-git"
    root.mkdir()
    (root / ".git").symlink_to(_real(tmp_path) / ".git", target_is_directory=True)
    return root


def _symlinked_root(tmp_path):
    root = tmp_path / "linked-root"
    root.symlink_to(_real(tmp_path), target_is_directory=True)
    return root


def _no_git(tmp_path):
    root = tmp_path / "plain"
    root.mkdir()
    return root


def _escapes_the_clone_base(tmp_path, monkeypatch):
    base = tmp_path / "code-sources"
    base.mkdir()
    monkeypatch.setattr(source_paths, "CODE_SOURCES_BASE", base)
    (base / "dir").symlink_to(_real(tmp_path), target_is_directory=True)
    return base / "dir"


@pytest.mark.parametrize("make", [_gitfile, _symlinked_git, _symlinked_root, _no_git])
def test_a_redirected_or_missing_git_is_rejected(make, tmp_path):
    assert mod.git_root_of(make(tmp_path)) is None


def test_a_clone_resolving_outside_the_clone_base_is_rejected(tmp_path, monkeypatch):
    assert mod.git_root_of(_escapes_the_clone_base(tmp_path, monkeypatch)) is None


def test_a_real_repository_is_accepted(tmp_path):
    root = _real(tmp_path)
    assert mod.git_root_of(root) == root.resolve()


@pytest.mark.parametrize("make", [_gitfile, _symlinked_git, _symlinked_root, _no_git])
def test_bug_prediction_in_a_report_fails_closed_and_never_builds_the_predictor(make, tmp_path):
    predictor = MagicMock()
    with patch.object(report, "BugPredictor", predictor):
        result = asyncio.run(report._get_bug_prediction(project_root=str(make(tmp_path)), source_id="src-1"))
    assert result is None
    predictor.assert_not_called()


def test_bug_prediction_in_a_report_still_runs_on_a_real_repository(tmp_path):
    predictor = MagicMock()
    predictor.return_value.analyze_directory_async = AsyncMock(
        return_value=MagicMock(analyzed_files=0, high_risk_count=0)
    )
    with patch.object(report, "BugPredictor", predictor):
        result = asyncio.run(report._get_bug_prediction(project_root=str(_real(tmp_path)), source_id="src-1"))
    assert result is not None
    assert predictor.call_args.kwargs["project_root"] == str(_real(tmp_path).resolve())
