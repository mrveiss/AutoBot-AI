# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A hung LLC agent run must not hold its slot for the full timeout (GH#13099).

`_status()` now inspects the output file's size/mtime -- a free liveness
signal for a detached, file-backed run -- to catch two conditions no overall
timeout alone catches: an agent that never produced output at all, and one
that stopped producing it mid-run. These tests use real processes (POSIX
process groups have no useful mock), so a stall-kill exercises the actual
GH#13097 terminate_pid() group-kill, not a mocked stand-in, and the small
windows flow through the real env-backed 3-tier resolvers.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import signal
import time

import psutil
import pytest

from autobot_shared.eventually import eventually
from llc.adapters.subprocess_base import (
    SubprocessLifecycleAdapter,
    resolve_first_output_deadline,
    resolve_stall_deadline,
)
from llc.adapters.subprocess_support import spawn_detached

_TEST_LOG_NAME = "StallWatchdogTest"
_POLL_DEADLINE_S = 10.0  # deadlock guard for the hand-rolled async poll below

_requires_posix = pytest.mark.skipif(os.name != "posix", reason="process-group signalling is POSIX-only")


def _pid_alive(pid: int) -> bool:
    """True if *pid* can still be signalled (existence check, no delivery)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


async def _reap(proc: asyncio.subprocess.Process) -> None:
    """Make sure *proc* is dead and reaped, whatever the test did to it."""
    with contextlib.suppress(ProcessLookupError):
        os.kill(proc.pid, signal.SIGKILL)
    with contextlib.suppress(ProcessLookupError):
        await proc.wait()


def _state_path(output_dir: str, run_id: str) -> str:
    return os.path.join(output_dir, f"stall_state_{run_id.replace('/', '_')}.json")


async def _read_grandchild_pid(pid_file) -> int:
    """The grandchild PID a test's shell command wrote to *pid_file*."""
    text = await asyncio.to_thread(pid_file.read_text, encoding="utf-8")
    return int(text.strip())


class _DummyAdapter(SubprocessLifecycleAdapter):
    """The bare shared lifecycle -- no adapter-specific spawn/parsing needed here."""

    _LOG_NAME = _TEST_LOG_NAME
    _state_path = staticmethod(_state_path)

    async def _invoke(self, agent_config: dict, context: dict) -> str:  # pragma: no cover - not exercised
        raise NotImplementedError


async def _spawn_and_register(
    tmp_path,
    monkeypatch,
    cmd: str,
    *,
    first_output_deadline: int,
    stall_deadline: int,
) -> tuple[_DummyAdapter, asyncio.subprocess.Process, dict, str]:
    """Spawn *cmd* detached and write the state file the base `_status()` reads.

    Mirrors what a real adapter's `_invoke` does (pre-create the empty output
    file, spawn detached, persist pid/output_file/deadlines) so the test
    exercises the actual shared lifecycle, not a stand-in. The deadlines flow
    through the real env-backed resolvers via small overrides -- the same
    path a live deployment would tune with -- so resolution is exercised too.
    """
    monkeypatch.setenv("AUTOBOT_LLC_FIRST_OUTPUT_DEADLINE_SECONDS", str(first_output_deadline))
    monkeypatch.setenv("AUTOBOT_LLC_STALL_DEADLINE_SECONDS", str(stall_deadline))

    output_file = str(tmp_path / "out.jsonl")
    out_fh = open(output_file, "w", encoding="utf-8")
    proc = await spawn_detached("sh", "-c", cmd, stdout=out_fh, stderr=asyncio.subprocess.DEVNULL)
    out_fh.close()

    run_id = f"{proc.pid}/session"
    cfg: dict = {}
    state = {
        "pid": proc.pid,
        "output_file": output_file,
        "started_at": time.time(),
        "create_time": psutil.Process(proc.pid).create_time(),  # PR#16284 review
        "timeout_seconds": 3600,
        "first_output_deadline_seconds": resolve_first_output_deadline(cfg),
        "stall_deadline_seconds": resolve_stall_deadline(cfg),
    }
    output_dir = str(tmp_path)
    with open(_state_path(output_dir, run_id), "w", encoding="utf-8") as fh:
        json.dump(state, fh)

    return _DummyAdapter(), proc, {"adapter_config": {"output_dir": output_dir}}, run_id


async def _poll_until_failed(adapter: _DummyAdapter, agent_config: dict, run_id: str):
    """Poll `status()` until FAILED, bounded like `eventually()` (its condition is sync-only,
    but this one must await the adapter -- so it mirrors the same deadlock-guard shape).
    """

    async def _poll():
        while True:
            result = await adapter.status(agent_config, run_id)
            if result.status.value == "failed":
                return result
            await asyncio.sleep(0.05)

    return await asyncio.wait_for(_poll(), timeout=_POLL_DEADLINE_S)


@_requires_posix
@pytest.mark.asyncio
class TestStallKillsWholeGroup:
    async def test_stall_after_first_output_kills_group(self, tmp_path, monkeypatch) -> None:
        """A child that prints once then sleeps is killed after the stall window,
        its grandchild too, and the result names the stall."""
        grandchild_pid_file = tmp_path / "grandchild.pid"
        cmd = f"echo hello; sleep 300 & echo $! > {grandchild_pid_file}; wait"
        adapter, proc, agent_config, run_id = await _spawn_and_register(
            tmp_path, monkeypatch, cmd, first_output_deadline=1, stall_deadline=1
        )
        try:
            await eventually(lambda: grandchild_pid_file.exists() and grandchild_pid_file.stat().st_size > 0)
            grandchild_pid = await _read_grandchild_pid(grandchild_pid_file)
            assert _pid_alive(grandchild_pid)

            result = await _poll_until_failed(adapter, agent_config, run_id)
            assert "stalled: no output for" in (result.error or "")

            await eventually(lambda: not _pid_alive(proc.pid))
            await eventually(lambda: not _pid_alive(grandchild_pid))
        finally:
            await _reap(proc)
            if grandchild_pid_file.exists():
                with contextlib.suppress(ProcessLookupError, ValueError):
                    os.kill(await _read_grandchild_pid(grandchild_pid_file), signal.SIGKILL)

    async def test_never_produces_output_trips_first_output_deadline(self, tmp_path, monkeypatch) -> None:
        """A child that never prints trips the first-output deadline, distinctly from a stall."""
        adapter, proc, agent_config, run_id = await _spawn_and_register(
            tmp_path, monkeypatch, "sleep 300", first_output_deadline=1, stall_deadline=60
        )
        try:
            result = await _poll_until_failed(adapter, agent_config, run_id)
            assert "no output within" in (result.error or "")
            assert "stalled: no output for" not in (result.error or "")
            await eventually(lambda: not _pid_alive(proc.pid))
        finally:
            await _reap(proc)

    async def test_continuous_output_is_not_killed(self, tmp_path, monkeypatch) -> None:
        """A child that keeps printing within the window is left running."""
        cmd = "i=0; while [ $i -lt 40 ]; do echo tick; sleep 0.1; i=$((i+1)); done; sleep 300"
        adapter, proc, agent_config, run_id = await _spawn_and_register(
            tmp_path, monkeypatch, cmd, first_output_deadline=1, stall_deadline=2
        )
        try:
            deadline = time.monotonic() + 2.0  # well inside the ~4s printing window
            while time.monotonic() < deadline:
                result = await adapter.status(agent_config, run_id)
                assert result.status.value == "running", result.error
                await asyncio.sleep(0.2)
            assert _pid_alive(proc.pid)
        finally:
            await _reap(proc)

    async def test_legitimately_quiet_within_deadline_is_not_killed(self, tmp_path, monkeypatch) -> None:
        """#13099 AC5: a LIVE process quiet for longer than a short window, but
        still within its configured stall deadline, is NOT killed. Unlike
        ``test_continuous_output_is_not_killed`` (never actually quiet), this
        child prints once and then goes genuinely silent for the whole check."""
        cmd = "echo hello; sleep 3"
        adapter, proc, agent_config, run_id = await _spawn_and_register(
            tmp_path, monkeypatch, cmd, first_output_deadline=1, stall_deadline=10
        )
        output_file = tmp_path / "out.jsonl"
        try:
            await eventually(lambda: output_file.stat().st_size > 0)
            deadline = time.monotonic() + 2.5  # longer than a "short window", still << stall_deadline=10
            while time.monotonic() < deadline:
                result = await adapter.status(agent_config, run_id)
                assert result.status.value == "running", result.error
                await asyncio.sleep(0.2)
            assert _pid_alive(proc.pid)
        finally:
            await _reap(proc)
