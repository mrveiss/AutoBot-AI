# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared test helpers for llc/adapters/tests (GH#9844).

Plain helper functions are preferred over pytest fixtures here because all
callers pass arguments — parametrised fixtures would require indirect= wiring
that adds noise without benefit.  Import directly in test modules.
"""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import psutil

# Captured at import: tests patch psutil.Process inside scoped_os_kill windows, which would hide real children.
_REAL_PSUTIL_PROCESS = psutil.Process


def agent_cfg(agent_id: str = "agent-1", output_dir: str | None = None, **kwargs) -> dict:
    """Build a minimal agent-config dict used across adapter test suites."""
    cfg: dict = {"agent_id": agent_id, "adapter_config": {**kwargs}}
    if output_dir:
        cfg["adapter_config"]["output_dir"] = output_dir
    return cfg


def make_fake_proc(pid: int = 12345) -> MagicMock:
    """Return a MagicMock that mimics an asyncio.subprocess.Process with the given PID."""
    proc = MagicMock()
    proc.pid = pid
    return proc


def _is_live_child(pid: int) -> bool:
    """True if ``pid`` is a live descendant of this process (psutil; no reaping)."""
    if pid <= 1:
        return False
    return any(c.pid == pid for c in _REAL_PSUTIL_PROCESS(os.getpid()).children(recursive=True))


def _check_foreign_kill(pid: int, sig: int) -> None:
    """Refuse a real signal to anything but this test process's own children (GH#16920).

    Signal 0 is a harmless liveness probe and always passes. A fabricated PID, or
    pid <= 1 (0 / -1 / negative group), would signal an unrelated host process.
    """
    if sig == 0:
        return
    if not _is_live_child(pid):
        raise AssertionError(f"scoped os.kill refused foreign non-child pid {pid} with signal {sig}")


@contextmanager
def scoped_os_kill(*pids: int, side_effect=None, return_value=None) -> Iterator[MagicMock]:
    """Patch ``os.kill`` for the given PID(s) only (GH#16920).

    ``patch("os.kill")`` replaces the function for the whole interpreter, so under
    xdist another test's real reap -- or a garbage-collected asyncio subprocess
    transport -- can land inside the patch window. Calls addressed to ``pids`` go
    to the yielded mock (which records them and applies ``side_effect`` /
    ``return_value``); every other PID goes to the REAL ``os.kill``, captured
    before patching, and is never recorded -- but only if it is a live child of
    this process (or the signal is 0); anything else raises ``AssertionError``.

    This is the only place under llc/adapters/tests allowed to patch ``os.kill``
    (enforced by ``test_os_kill_patch_scope.py``).
    """
    real_kill = os.kill
    targeted = frozenset(pids)
    mock_kill = MagicMock(side_effect=side_effect, return_value=return_value)

    def _scoped(pid, sig):
        if pid not in targeted:
            _check_foreign_kill(pid, sig)
            return real_kill(pid, sig)
        return mock_kill(pid, sig)

    with patch("os.kill", side_effect=_scoped):
        yield mock_kill
