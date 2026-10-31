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
async def test_a_failed_step_returns_its_exit_code_and_redacted_stderr(tmp_path) -> None:
    executor = _executor(tmp_path)
    stderr = f"fatal: unable to access https://user:{_SECRET}@host/r".encode()  # pragma: allowlist secret
    with patch.object(pe, "start_git", new=AsyncMock(return_value=_proc(128, stderr))):
        failure = await executor._run_git(tmp_path, "fetch", "--prune", "origin")
    assert failure.startswith("git fetch exited 128: fatal: unable to access")
    assert _SECRET not in failure


@pytest.mark.asyncio
async def test_a_timed_out_step_says_so(tmp_path, monkeypatch) -> None:
    executor = _executor(tmp_path)
    proc = MagicMock(communicate=AsyncMock(side_effect=asyncio.TimeoutError))
    monkeypatch.setattr(executor, "_kill_process_group", AsyncMock())
    with patch.object(pe, "start_git", new=AsyncMock(return_value=proc)):
        assert await executor._run_git(tmp_path, "fetch") == f"git fetch timed out after {pe.GIT_COMMAND_TIMEOUT_S}s"


def _scripted_git(executor, monkeypatch, fetch_failures: list[str]) -> list[str]:
    """_run_git answering each fetch from the list, and None for everything else."""
    monkeypatch.setattr(pe, "GIT_FETCH_RETRY_DELAY_S", 0)
    monkeypatch.setattr(executor, "_log_updated_head_commit", AsyncMock())
    calls: list[str] = []
    remaining = list(fetch_failures)

    async def run_git(_dir, *args):
        calls.append(args[0])
        return (remaining.pop(0) if remaining else None) if args[0] == "fetch" else None

    monkeypatch.setattr(executor, "_run_git", run_git)
    return calls


_LOCK = "git fetch exited 128: fatal: Unable to create '/r/.git/shallow.lock': File exists"
_HANGUP = "git fetch exited 128: fatal: the remote end hung up unexpectedly"


@pytest.mark.asyncio
async def test_a_transient_fetch_failure_is_retried_and_the_sync_succeeds(tmp_path, monkeypatch) -> None:
    executor = _executor(tmp_path)
    calls = _scripted_git(executor, monkeypatch, [_LOCK])
    assert await executor._update_code_source() is None
    assert calls == ["checkout", "fetch", "fetch", "reset"]


@pytest.mark.asyncio
async def test_a_fetch_that_fails_twice_returns_the_last_reason_and_does_not_reset(tmp_path, monkeypatch) -> None:
    executor = _executor(tmp_path)
    calls = _scripted_git(executor, monkeypatch, [_LOCK, _HANGUP])
    assert await executor._update_code_source() == _HANGUP
    assert calls == ["checkout", "fetch", "fetch"]


@pytest.mark.parametrize(
    "failure",
    [
        "git fetch exited 128: fatal: Authentication failed for 'https://host/r'",
        "git fetch timed out after 30s",
    ],
    ids=["auth", "timeout"],
)
@pytest.mark.asyncio
async def test_a_failure_a_retry_cannot_cure_is_not_retried(tmp_path, monkeypatch, failure) -> None:
    executor = _executor(tmp_path)
    calls = _scripted_git(executor, monkeypatch, [failure])
    assert await executor._update_code_source() == failure
    assert calls == ["checkout", "fetch"]


@pytest.mark.asyncio
async def test_an_unexpected_error_gives_its_own_redacted_reason(tmp_path, monkeypatch) -> None:
    executor = _executor(tmp_path)
    url = f"https://user:{_SECRET}@host/r"  # pragma: allowlist secret
    monkeypatch.setattr(executor, "_run_git", AsyncMock(side_effect=OSError(f"no such file: {url}")))
    failure = await executor._update_code_source()
    assert failure.startswith("unexpected error: no such file")
    assert _SECRET not in failure


@pytest.mark.asyncio
async def test_concurrent_syncs_each_report_their_own_reason(tmp_path, monkeypatch) -> None:
    """The executor is a singleton (#14570): a second caller's failure must not replace the first's."""
    executor = _executor(tmp_path)
    monkeypatch.setattr(executor, "_log_updated_head_commit", AsyncMock())
    first_failed, second_done = asyncio.Event(), asyncio.Event()

    async def run_git(_dir, *args):
        if args[0] != "fetch":
            return None
        if not first_failed.is_set():
            first_failed.set()
            await second_done.wait()
            return "git fetch exited 1: first"
        return "git fetch exited 1: second"

    monkeypatch.setattr(executor, "_run_git", run_git)
    first = asyncio.create_task(executor._update_code_source())
    await first_failed.wait()
    second = await executor._update_code_source()
    second_done.set()
    assert await first == "git fetch exited 1: first"
    assert second == "git fetch exited 1: second"


def test_the_refusal_names_the_reason() -> None:
    result = pe.PlaybookExecutor._code_source_sync_failure_result("u.yml", True, "git fetch exited 128: x")
    assert "git fetch exited 128: x" in result["output"] and result["success"] is False


def test_a_synced_run_has_nothing_to_refuse() -> None:
    assert pe.PlaybookExecutor._code_source_sync_failure_result("u.yml", True, None) is None
