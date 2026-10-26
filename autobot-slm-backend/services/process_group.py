# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Kill a timed-out subprocess's WHOLE process group (#14524, #19475).

Lifted out of ``PlaybookExecutor`` so every ansible runner bounds its child the same way:
the executor's timed-out playbook and git runs, and ``ansible_utils.run_single_host_playbook``.
A caller spawns with ``start_new_session=True`` so the child's pid is its process-group id.
"""

import asyncio
import os
import signal

from autobot_shared.env_utils import env_float_clamped
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# #14524: grace period between SIGTERM and SIGKILL when a timed-out playbook
# subprocess's WHOLE process group (see kill_process_group) does not exit on
# its own. Long enough for ansible-playbook's own signal handling / a forked
# ssh child to unwind cleanly; short enough that a wedged run does not become
# a second, unbounded wait stacked on top of the timeout that triggered it.
# Clamped, not bare (review, round 2): a bare env_float accepts 0 and
# negatives, and 0 here collapses the grace entirely -- SIGKILL fires with no
# chance for a well-behaved child to exit on SIGTERM first. `max_v` added
# (review, round 3): env_float_clamped's min-only clamp let
# AUTOBOT_PLAYBOOK_KILL_GRACE_S=inf produce `asyncio.wait_for(..., timeout=
# inf)` -- an unbounded wait inside the function that exists to bound one.
# 60s is already generous for a SIGTERM/SIGKILL grace; a process still alive
# that much later than an uncatchable SIGKILL is in D-state (uninterruptible
# I/O sleep), which no additional waiting here resolves.
KILL_GRACE_S = env_float_clamped("AUTOBOT_PLAYBOOK_KILL_GRACE_S", 5.0, min_v=0.1, max_v=60.0)


async def kill_process_group(process: asyncio.subprocess.Process, grace_s: float | None = None) -> None:
    """SIGTERM then SIGKILL the WHOLE process group of a timed-out run (#14524).

    ``ansible-playbook`` forks per-host workers (``forks=5``, ansible.cfg)
    and ssh children; killing only the direct PID leaves those running as
    orphans. ``start_new_session=True`` (the spawning call) makes the
    spawned pid its own process group id, so ``pgid = process.pid`` needs
    no ``os.getpgid()`` lookup -- review round 2, Case B: that lookup
    raised ``ProcessLookupError`` and returned, signalling NOTHING, the
    moment the direct child was already reaped while a SIBLING (e.g. a
    leader that exits on its own after backgrounding one) was still
    alive -- the only way an ATTACHED run wedges after ansible itself has
    exited. And escalation below checks the WHOLE GROUP via
    `process_group_is_dead` (signal 0 -- an existence probe, nothing
    sent), not `await process.wait()`'s one direct pid -- review round 2,
    Case C: a direct child that dies on SIGTERM while a sibling ignores
    it used to make the old, pid-only check return early, and SIGKILL was
    never sent to the survivor. Both fail-open shapes were reproduced
    against a standalone prototype before this fix, and fixed by it.
    """
    grace_s = KILL_GRACE_S if grace_s is None else grace_s  # read at call time, so a test can shorten it
    pgid = process.pid

    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            return  # whole group already gone -- nothing left to escalate to

        # Reap the direct child promptly: an unreaped zombie still
        # "belongs" to this pgid and would make the group-liveness probe
        # below always see something, masking whether a SIBLING is still
        # alive once the direct child itself is gone.
        try:
            await asyncio.wait_for(process.wait(), timeout=grace_s)
        except asyncio.TimeoutError:
            pass

        if await wait_for_process_group_death(pgid, grace_s):
            return

    logger.error("Process group %d survived SIGKILL after grace period (#14524)", pgid)


def process_group_is_dead(pgid: int) -> bool:
    """True if no process remains in *pgid*. Signal 0 sends nothing -- existence-only probe."""
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        # A process with this pgid exists but signalling it is refused
        # (e.g. uid mismatch) -- it still exists, so not dead.
        return False
    return False


async def wait_for_process_group_death(pgid: int, timeout_s: float) -> bool:
    """Poll `process_group_is_dead` for up to *timeout_s* (#14524).

    Helper for kill_process_group. Checking the GROUP, not the one pid
    `asyncio` tracks, is what makes the SIGTERM/SIGKILL escalation
    decision correct when a sibling -- not the direct child -- is the
    one still alive (review round 2, Case C).
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
