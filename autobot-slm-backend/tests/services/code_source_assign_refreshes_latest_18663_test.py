# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Assigning a code source re-points slm_agent_latest_commit at that branch's head (#18663).

Before a source is assigned the version checker tracks the default branch, so a node stamped from a
checkout of another branch read ``outdated`` right after install. The assign endpoint now refreshes
the latest commit from the tracker of the branch it assigned.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_PATH = Path(__file__).parent.parent.parent / "services" / "git_tracker.py"
_SPEC = importlib.util.spec_from_file_location("git_tracker_18663", _PATH)
git_tracker = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(git_tracker)


def _tracker(remote_commit):
    tracker = MagicMock()
    tracker.check_for_updates = AsyncMock(return_value={"remote_commit": remote_commit})
    return tracker


@pytest.mark.asyncio
async def test_assigned_branch_head_becomes_the_latest_commit() -> None:
    db, tracker = MagicMock(), _tracker("a" * 40)
    with (
        patch.object(git_tracker, "_is_git_repo", return_value=True),
        patch.object(git_tracker, "get_git_tracker", return_value=tracker) as get_tracker,
        patch.object(git_tracker, "update_latest_version_setting", new=AsyncMock()) as update,
    ):
        await git_tracker.refresh_latest_for_source(db, "/repo", "feature")
    get_tracker.assert_called_once_with(repo_path="/repo", branch="feature")
    update.assert_awaited_once_with(db, "a" * 40)


@pytest.mark.asyncio
async def test_a_non_checkout_path_leaves_the_setting_alone() -> None:
    with (
        patch.object(git_tracker, "_is_git_repo", return_value=False),
        patch.object(git_tracker, "update_latest_version_setting", new=AsyncMock()) as update,
    ):
        await git_tracker.refresh_latest_for_source(MagicMock(), "/nowhere", "main")
    update.assert_not_awaited()


def test_assign_endpoint_calls_the_refresh() -> None:
    source = (Path(__file__).parent.parent.parent / "api" / "code_source.py").read_text(encoding="utf-8")
    body = source.split("async def assign_code_source", 1)[1].split("@router.delete", 1)[0]
    assert "refresh_latest_for_source(db, source.repo_path, source.branch)" in body
