# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A live run keeps its identity when the host's ``btime`` steps (GH#20466).

On WSL2 the ``btime`` line of /proc/stat steps down every 10-60 s, so psutil's
absolute ``create_time()`` of one live process changes between two reads. An
identity check on that value reported the run as over seconds after the spawn,
and the scheduler then revoked the run's key while the agent still worked.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
from unittest.mock import patch

import psutil
import pytest

from llc.adapters.subprocess_support import probe_pid_identity, spawn_create_time, spawn_detached, terminate_pid
from llc.models.enums import LLCRunStatus

pytestmark = pytest.mark.skipif(os.name != "posix" or not hasattr(psutil, "_pslinux"), reason="Linux /proc/stat btime")


@contextlib.asynccontextmanager
async def _live_process():
    proc = await spawn_detached("sleep", "30", stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    try:
        yield proc
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGKILL)
        await proc.wait()


def _drifting_boot_time():
    """psutil's boot_time as the host reports it: one second lower on every read."""
    real = psutil._pslinux.boot_time()
    reads = iter(range(1, 1000))
    return patch("psutil._pslinux.boot_time", side_effect=lambda: real - next(reads))


@pytest.mark.asyncio
async def test_live_process_stays_running_across_boot_time_steps() -> None:
    async with _live_process() as proc:
        recorded = spawn_create_time(proc.pid)
        with _drifting_boot_time():
            assert psutil.Process(proc.pid).create_time() != psutil.Process(proc.pid).create_time()
            polls = [probe_pid_identity(proc.pid, recorded).status for _ in range(5)]
        assert polls == [LLCRunStatus.RUNNING] * 5


@pytest.mark.asyncio
async def test_exited_process_is_completed_after_several_running_polls() -> None:
    async with _live_process() as proc:
        recorded = spawn_create_time(proc.pid)
        assert [probe_pid_identity(proc.pid, recorded).status for _ in range(3)] == [LLCRunStatus.RUNNING] * 3
        os.killpg(proc.pid, signal.SIGKILL)
        await proc.wait()
        assert probe_pid_identity(proc.pid, recorded).status is LLCRunStatus.COMPLETED


@pytest.mark.asyncio
async def test_other_process_under_the_same_pid_is_still_not_this_run() -> None:
    async with _live_process() as proc:
        recorded = spawn_create_time(proc.pid)
        assert probe_pid_identity(proc.pid, recorded + 5.0).status is LLCRunStatus.COMPLETED


@pytest.mark.asyncio
async def test_terminate_still_signals_the_recorded_process_after_drift() -> None:
    async with _live_process() as proc:
        recorded = spawn_create_time(proc.pid)
        with _drifting_boot_time():
            await terminate_pid(proc.pid, grace_seconds=2, log_name="Drift20466", expected_create_time=recorded)
        assert await asyncio.wait_for(proc.wait(), timeout=10) is not None
