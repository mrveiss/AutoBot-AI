# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""kill_and_reap stops a timed-out child and reaps it (#18056)."""

import asyncio
import os
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
