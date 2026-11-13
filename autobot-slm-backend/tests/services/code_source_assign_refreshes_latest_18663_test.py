# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Assigning a code source re-points slm_agent_latest_commit at that branch's head (#18663).

Before a source is assigned the version checker tracks the default branch, so a node stamped from a
checkout of another branch read ``outdated`` right after install. The assign endpoint now refreshes
the latest commit from the remote-tracking ref of the branch it assigned, without a fetch and
without ever failing the request.
"""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from testkit.fake_async_session import FakeAsyncSession

_ROOT = Path(__file__).parent.parent.parent
_SPEC = importlib.util.spec_from_file_location("git_tracker_18663", _ROOT / "services" / "git_tracker.py")
git_tracker = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(git_tracker)

_SHA = "a" * 40


def _tracker(git_output: tuple[str, int]):
    """A real GitTracker whose only git access is a recorded stub, and whose fetch is a spy."""
    tracker = git_tracker.GitTracker(repo_path="/repo", branch="feature")
    tracker._run_git_command = AsyncMock(return_value=git_output)
    tracker.fetch_remote = AsyncMock()
    return tracker


async def _refresh(tracker, update):
    with (
        patch.object(git_tracker, "_is_git_repo", return_value=True),
        patch.object(git_tracker, "get_git_tracker", return_value=tracker),
        patch.object(git_tracker, "update_latest_version_setting", new=update),
    ):
        await git_tracker.refresh_latest_for_source(FakeAsyncSession(), "/repo", "feature")


@pytest.mark.asyncio
async def test_remote_tracking_ref_of_the_assigned_branch_is_stored_without_a_fetch() -> None:
    tracker, update = _tracker((_SHA, 0)), AsyncMock()
    await _refresh(tracker, update)
    tracker._run_git_command.assert_awaited_once_with("rev-parse", "origin/feature")
    tracker.fetch_remote.assert_not_awaited()
    assert update.await_args.args[1] == _SHA


@pytest.mark.asyncio
async def test_an_unresolvable_ref_writes_nothing() -> None:
    update = AsyncMock()
    await _refresh(_tracker(("", 128)), update)
    update.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_non_checkout_path_leaves_the_setting_alone() -> None:
    with (
        patch.object(git_tracker, "_is_git_repo", return_value=False),
        patch.object(git_tracker, "update_latest_version_setting", new=AsyncMock()) as update,
    ):
        await git_tracker.refresh_latest_for_source(FakeAsyncSession(), "/nowhere", "main")
    update.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_failed_write_is_logged_with_its_traceback_and_does_not_raise(caplog) -> None:
    update = AsyncMock(side_effect=RuntimeError("commit failed"))
    with caplog.at_level(logging.ERROR):
        await _refresh(_tracker((_SHA, 0)), update)
    record = next(r for r in caplog.records if "Could not refresh slm_agent_latest_commit" in r.getMessage())
    assert record.exc_info and record.exc_info[0] is RuntimeError


def test_assign_endpoint_calls_the_refresh() -> None:
    source = (_ROOT / "api" / "code_source.py").read_text(encoding="utf-8")
    body = source.split("async def assign_code_source", 1)[1].split("@router.delete", 1)[0]
    assert "refresh_latest_for_source(db, source.repo_path, source.branch)" in body
