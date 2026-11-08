# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Stop an asyncio subprocess whose wait timed out (#18056).

``asyncio.wait_for(process.communicate(), timeout=...)`` cancels the wait, not the
child: the process keeps running, and a caller that returns the timeout result
leaves it behind. Callers that start one child per request would stack them.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal


async def kill_and_reap(process: asyncio.subprocess.Process, *, process_group: bool = False) -> None:
    """Kill *process* if it is still running and wait for it to exit, so no zombie is left.

    *process_group* kills the whole group instead, even when the leader has already exited
    (a backgrounded child outlives its shell). The child must lead its own group
    (``start_new_session=True``), which makes its pid the group id.
    """
    if process_group:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
    elif process.returncode is None:
        with contextlib.suppress(ProcessLookupError):
            process.kill()
    await process.wait()
