# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Process-group primitives: the one home for "is the group gone" and "stop the whole group".

A caller spawns with ``start_new_session=True``, so the child's pid is its process-group id and
every grandchild (ansible's forks and ssh children, ``npm run dev``'s vite) shares it. Stopping
only the leader orphans them; checking only the leader misses a survivor.

The SLM's async ``kill_process_group`` (``autobot-slm-backend/services/process_group.py``,
#14524, #19475) and the startup coordinator's synchronous stop (#19496) both read
:func:`process_group_is_dead` from here.
"""

from __future__ import annotations

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
