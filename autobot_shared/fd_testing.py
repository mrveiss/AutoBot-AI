# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Test support: a PTY whose master descriptor lies at or above ``FD_SETSIZE`` (#22157).

``select.select()`` cannot address such a descriptor, which is the failure the
``fd_poll`` and PTY read-loop tests reproduce. Moved unchanged from the two test
files that each carried a copy; they differed only in the first descriptor number
tried, which each caller still passes. Importable from every tree, like
``env_registry_testing``.
"""

import fcntl
import os
import pty
import resource
from contextlib import contextmanager
from typing import Iterator, Tuple

# FD_SETSIZE on Linux. select() cannot address a descriptor at or above it.
FD_SETSIZE = 1024


def free_fd_at_or_above(start: int) -> int:
    """Return an unused descriptor number at or above ``start``."""
    for candidate in range(start, start + 64):
        try:
            fcntl.fcntl(candidate, fcntl.F_GETFD)
        except OSError:
            return candidate
    raise RuntimeError(f"no free descriptor number in [{start}, {start + 64})")


@contextmanager
def pty_above_fd_setsize(high_fd_base: int) -> Iterator[Tuple[int, int]]:
    """Yield ``(master_fd, slave_fd)`` with ``master_fd`` >= FD_SETSIZE.

    ``high_fd_base`` is the first descriptor number tried for the relocated master.
    """
    import pytest

    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    target = free_fd_at_or_above(high_fd_base)
    raised = False
    if soft <= target:
        if hard != resource.RLIM_INFINITY and hard <= target:
            pytest.skip(f"RLIMIT_NOFILE hard limit {hard} cannot reach descriptor {target}")
        resource.setrlimit(resource.RLIMIT_NOFILE, (target + 1, hard))
        raised = True

    master, slave = pty.openpty()
    try:
        os.dup2(master, target)
        os.close(master)
        yield target, slave
    finally:
        for fd in (target, slave):
            try:
                os.close(fd)
            except OSError:
                pass
        if raised:
            resource.setrlimit(resource.RLIMIT_NOFILE, (soft, hard))
