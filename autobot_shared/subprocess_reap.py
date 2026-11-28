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

from autobot_shared.ssot_config import config

#: Seconds a SIGTERM may take, and a bounded final wait may last (AUTOBOT_TIMEOUT_SUBPROCESS_SHORT).
GRACE_SECONDS = config.timeout.subprocess_short


def _signal(process: asyncio.subprocess.Process, sig: int, process_group: bool) -> None:
    """Send *sig* (SIGTERM or SIGKILL) to the child, or its whole group; a child already gone is no error."""
    with contextlib.suppress(ProcessLookupError):
        if process_group:
            os.killpg(process.pid, sig)
        elif process.returncode is None:
            process.terminate() if sig == signal.SIGTERM else process.kill()


async def _exited_after_sigterm(process: asyncio.subprocess.Process, process_group: bool, grace: float) -> bool:
    """SIGTERM the child and report whether it exited within *grace* seconds."""
    _signal(process, signal.SIGTERM, process_group)
    try:
        await asyncio.wait_for(process.wait(), timeout=grace)
    except asyncio.TimeoutError:
        return False
    return True


async def kill_and_reap(
    process: asyncio.subprocess.Process,
    *,
    process_group: bool = False,
    terminate_first: bool = False,
    bounded: bool = False,
    grace: float = GRACE_SECONDS,
) -> None:
    """Stop *process* if it is still running and wait for it to exit, so no zombie is left.

    *process_group* signals the whole group instead, even when the leader has already exited
    (a backgrounded child outlives its shell). The child must lead its own group
    (``start_new_session=True``), which makes its pid the group id.

    *terminate_first* sends SIGTERM and gives the child *grace* seconds before SIGKILL, for a
    child that should flush on a lifecycle stop. *bounded* limits the final wait to *grace*
    seconds, for a caller that must not hang on a child stuck in uninterruptible sleep.
    """
    if terminate_first and await _exited_after_sigterm(process, process_group, grace):
        return
    _signal(process, signal.SIGKILL, process_group)
    if bounded:
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(process.wait(), timeout=grace)
    else:
        await process.wait()
