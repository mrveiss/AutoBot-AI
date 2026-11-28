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

from autobot_shared.logging_manager import get_logger
from autobot_shared.process_group import wait_for_process_group_death
from autobot_shared.ssot_config import config

logger = get_logger(__name__)

#: Seconds a SIGTERM may take, and a bounded final wait may last (AUTOBOT_TIMEOUT_SUBPROCESS_SHORT).
GRACE_SECONDS = config.timeout.subprocess_short


def _signal(process: asyncio.subprocess.Process, sig: int, process_group: bool) -> None:
    """Send *sig* (SIGTERM or SIGKILL) to the child, or its whole group; a child already gone is no error."""
    with contextlib.suppress(ProcessLookupError):
        if process_group:
            os.killpg(process.pid, sig)
        elif process.returncode is None:
            process.terminate() if sig == signal.SIGTERM else process.kill()


async def _wait_leader(process: asyncio.subprocess.Process, grace: float) -> bool:
    """Wait up to *grace* seconds for the child to exit; False on timeout."""
    try:
        await asyncio.wait_for(process.wait(), timeout=grace)
    except asyncio.TimeoutError:
        return False
    return True


async def _exited_after_sigterm(process: asyncio.subprocess.Process, process_group: bool, grace: float) -> bool:
    """SIGTERM the child (or its group) and report whether everything exited within *grace* seconds.

    For a group the whole group is probed (signal 0), not just the leader: a leader that dies on
    SIGTERM while a sibling ignores it must still get the SIGKILL (#14524, #19475).
    """
    _signal(process, signal.SIGTERM, process_group)
    leader_gone = await _wait_leader(process, grace)
    if not process_group:
        return leader_gone
    return await wait_for_process_group_death(process.pid, grace)


async def _reap(process: asyncio.subprocess.Process, bounded: bool, grace: float) -> None:
    """Wait for the killed child; when *bounded*, give up after *grace* seconds and say so."""
    if not bounded:
        await process.wait()
    elif not await _wait_leader(process, grace):
        logger.warning(
            "Killed pid %s was not reaped within %.1fs; leaving it to the loop's child watcher", process.pid, grace
        )


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
    child that should flush on a lifecycle stop. With *process_group* the whole group must be
    gone within *grace* (a sibling that ignores SIGTERM earns the SIGKILL), and a group that
    survives SIGKILL is logged as an error (#14524, #19475). *bounded* limits the final wait
    to *grace* seconds, for a caller that must not hang on a child stuck in uninterruptible
    sleep; a wait that times out is logged as a warning.
    """
    if terminate_first and await _exited_after_sigterm(process, process_group, grace):
        return
    _signal(process, signal.SIGKILL, process_group)
    await _reap(process, bounded, grace)
    if terminate_first and process_group and not await wait_for_process_group_death(process.pid, grace):
        logger.error("Process group %d survived SIGKILL after %.1fs grace (#14524)", process.pid, grace)
