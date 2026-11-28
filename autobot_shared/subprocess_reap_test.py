# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""kill_and_reap stops a timed-out child and reaps it (#18056)."""

import asyncio
import os
import signal
import sys

import pytest

from autobot_shared.subprocess_reap import kill_and_reap


@pytest.mark.asyncio
async def test_a_timed_out_child_is_killed_and_reaped():
    process = await asyncio.create_subprocess_exec(sys.executable, "-c", "import time; time.sleep(60)")
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(process.communicate(), timeout=0.2)
    assert process.returncode is None  # the wait was cancelled, the child was not
    await kill_and_reap(process)
    assert process.returncode is not None


@pytest.mark.asyncio
async def test_an_exited_child_is_a_no_op():
    process = await asyncio.create_subprocess_exec(sys.executable, "-c", "pass")
    await process.wait()
    await kill_and_reap(process)
    assert process.returncode == 0


@pytest.mark.asyncio
async def test_process_group_kills_the_grandchild_too():
    code = "import subprocess,sys,time; p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']); print(p.pid,flush=True); time.sleep(60)"
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-c", code, stdout=asyncio.subprocess.PIPE, start_new_session=True
    )
    grandchild = int((await process.stdout.readline()).decode())
    await kill_and_reap(process, process_group=True)
    assert process.returncode is not None
    for _ in range(50):
        try:
            os.kill(grandchild, 0)
        except ProcessLookupError:
            return
        await asyncio.sleep(0.1)
    pytest.fail("the grandchild survived the group kill")


_IGNORES_SIGTERM = (
    "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); print('up',flush=True); time.sleep(60)"
)


@pytest.mark.asyncio
async def test_terminate_first_lets_a_cooperative_child_exit_on_sigterm():
    process = await asyncio.create_subprocess_exec(sys.executable, "-c", "import time; time.sleep(60)")
    await kill_and_reap(process, terminate_first=True)
    assert process.returncode == -signal.SIGTERM  # SIGTERM was enough; no SIGKILL followed


@pytest.mark.asyncio
async def test_terminate_first_escalates_to_sigkill_after_the_grace():
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-c", _IGNORES_SIGTERM, stdout=asyncio.subprocess.PIPE
    )
    await process.stdout.readline()  # the handler is installed
    await kill_and_reap(process, terminate_first=True, grace=0.3)
    assert process.returncode == -signal.SIGKILL


@pytest.mark.asyncio
async def test_bounded_wait_returns_when_the_child_is_not_reaped_in_time(monkeypatch):
    process = await asyncio.create_subprocess_exec(sys.executable, "-c", "import time; time.sleep(60)")

    async def _never_exits():
        await asyncio.sleep(60)

    real_wait = process.wait
    monkeypatch.setattr(process, "wait", _never_exits)
    await asyncio.wait_for(kill_and_reap(process, bounded=True, grace=0.2), timeout=5)  # returns, does not hang
    monkeypatch.setattr(process, "wait", real_wait)
    await process.wait()
