# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A failed code_source sync says which git step failed and why, and a fetch gets one retry (#20089).

The self-update stopped with no cause anywhere: _run_git threw stderr away, so a timeout, a lock from a
concurrent sync and a network failure all read as "git fetch failed".
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _load_real_playbook_executor():
    """Past the conftest's session-global services stub, as the #14524 test does."""
    path = Path(__file__).resolve().parent / "playbook_executor.py"
    spec = importlib.util.spec_from_file_location("playbook_executor_under_sync_reason_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["playbook_executor_under_sync_reason_test"] = module
    spec.loader.exec_module(module)
    return module


pe = _load_real_playbook_executor()

_SECRET = "hunter2-very-secret"  # pragma: allowlist secret


def _executor(tmp_path) -> pe.PlaybookExecutor:
    (tmp_path / ".git").mkdir()
    ansible = tmp_path / "autobot-slm-backend" / "ansible"
    ansible.mkdir(parents=True)
    return pe.PlaybookExecutor(ansible_dir=ansible)


def _proc(returncode: int, stderr: bytes = b"") -> MagicMock:
    return MagicMock(returncode=returncode, communicate=AsyncMock(return_value=(b"", stderr)))


@pytest.mark.asyncio
async def test_a_failed_step_records_its_exit_code_and_redacted_stderr(tmp_path) -> None:
    executor = _executor(tmp_path)
    stderr = f"fatal: unable to access https://user:{_SECRET}@host/r".encode()  # pragma: allowlist secret
    with patch.object(pe, "start_git", new=AsyncMock(return_value=_proc(128, stderr))):
        assert await executor._run_git(tmp_path, "fetch", "--prune", "origin") == 128
    assert executor._git_failure.startswith("git fetch exited 128: fatal: unable to access")
    assert _SECRET not in executor._git_failure


@pytest.mark.asyncio
async def test_a_timed_out_step_says_so(tmp_path, monkeypatch) -> None:
    executor = _executor(tmp_path)
    proc = MagicMock(communicate=AsyncMock(side_effect=asyncio.TimeoutError))
    monkeypatch.setattr(executor, "_kill_process_group", AsyncMock())
    with patch.object(pe, "start_git", new=AsyncMock(return_value=proc)):
        assert await executor._run_git(tmp_path, "fetch") == -1
    assert executor._git_failure == f"git fetch timed out after {pe.GIT_COMMAND_TIMEOUT_S}s"


@pytest.mark.asyncio
async def test_one_failed_fetch_is_retried_and_the_sync_succeeds(tmp_path, monkeypatch) -> None:
    executor = _executor(tmp_path)
    monkeypatch.setattr(pe, "GIT_FETCH_RETRY_DELAY_S", 0)
    monkeypatch.setattr(executor, "_log_updated_head_commit", AsyncMock())
    calls = []

    async def run_git(_dir, *args):
        calls.append(args[0])
        return 1 if calls.count("fetch") == 1 and args[0] == "fetch" else 0

    monkeypatch.setattr(executor, "_run_git", run_git)
    assert await executor._update_code_source() is True
    assert calls == ["checkout", "fetch", "fetch", "reset"]


@pytest.mark.asyncio
async def test_a_fetch_that_fails_twice_fails_the_sync_and_does_not_reset(tmp_path, monkeypatch) -> None:
    executor = _executor(tmp_path)
    monkeypatch.setattr(pe, "GIT_FETCH_RETRY_DELAY_S", 0)
    calls = []

    async def run_git(_dir, *args):
        calls.append(args[0])
        return 1 if args[0] == "fetch" else 0

    monkeypatch.setattr(executor, "_run_git", run_git)
    assert await executor._update_code_source() is False
    assert calls == ["checkout", "fetch", "fetch"]


def test_the_refusal_names_the_reason(tmp_path) -> None:
    executor = _executor(tmp_path)
    executor._git_failure = "git fetch exited 128: x"
    result = executor._code_source_sync_failure_result("u.yml", True, False)
    assert "git fetch exited 128: x" in result["output"] and result["success"] is False
