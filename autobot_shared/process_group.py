# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Process-group primitives: the one home for "is the group gone" and "stop the whole group".

A caller spawns with ``start_new_session=True``, so the child's pid is its process-group id and
every grandchild (ansible's forks and ssh children, ``npm run dev``'s vite) shares it. Stopping
only the leader orphans them; checking only the leader misses a survivor.

The async group kill is ``autobot_shared.subprocess_reap.kill_and_reap(process_group=True,
terminate_first=True)`` (#14524, #19475, #20924); it and the startup coordinator's synchronous stop
(#19496) both read :func:`process_group_is_dead` from here.
"""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import time


def process_group_is_dead(pgid: int) -> bool:
    """True if no process remains in *pgid*. Signal 0 sends nothing: an existence-only probe."""
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        # A process with this pgid exists but signalling it is refused (e.g. uid mismatch): not dead.
        return False
    return False


def _wait_until_dead(process: subprocess.Popen, timeout_s: float) -> bool:
    """Reap the leader and poll the whole group for up to *timeout_s*; True once it is gone."""
    deadline = time.monotonic() + timeout_s
    while True:
        process.poll()  # an unreaped leader is a zombie that still "belongs" to the group
        if process_group_is_dead(process.pid):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)


def stop_process_group(process: subprocess.Popen, grace_s: float = 5.0) -> bool:
    """SIGTERM, then SIGKILL after *grace_s*, the WHOLE group of *process*; False if it was already gone.

    The group is signalled even when the leader has exited: a grandchild can outlive it.
    """
    if process.poll() is not None and process_group_is_dead(process.pid):
        return False
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            break
        if _wait_until_dead(process, grace_s):
            break
    process.poll()
    return True


async def wait_for_process_group_death(pgid: int, timeout_s: float) -> bool:
    """Poll :func:`process_group_is_dead` for up to *timeout_s* seconds (#14524).

    Checks the GROUP, not the one pid asyncio tracks: a sibling can outlive the leader.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    poll_s = min(0.1, timeout_s) if timeout_s > 0 else 0.05
    while True:
        if process_group_is_dead(pgid):
            return True
        if loop.time() >= deadline:
            return process_group_is_dead(pgid)
        await asyncio.sleep(poll_s)
