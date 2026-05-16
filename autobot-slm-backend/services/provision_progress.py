# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Provision Progress Tracker (Issue #3033)

Provides heartbeat / elapsed-time messages during long-running Ansible tasks
(e.g. ``ollama pull``, ``npm install``, ``pip install``) that emit no output
for extended periods and would otherwise leave the UI appearing stuck.

Usage::

    async with TaskProgressTracker(task_name, progress_callback) as tracker:
        # ... await long operation ...

The tracker fires a "Still running..." heartbeat via ``progress_callback``
every ``HEARTBEAT_INTERVAL_SECONDS`` while the ``async with`` block is active.
"""

import asyncio
import logging
import re
import time
from typing import Callable

logger = logging.getLogger(__name__)

# How often (in seconds) to emit a heartbeat for a silent task.
HEARTBEAT_INTERVAL_SECONDS: int = 5

# Known slow task patterns mapped to human-readable duration estimates.
# Patterns are matched (case-insensitively) against the Ansible task name.
SLOW_TASK_HINTS: dict[str, str] = {
    r"ollama\s+pull": "5-15 min per model",
    r"npm\s+install": "1-3 min",
    r"npm\s+ci": "1-3 min",
    r"npm\s+run\s+build": "1-3 min",
    r"rebuild.*frontend": "1-3 min",
    r"frontend.*rebuild": "1-3 min",
    r"build.*frontend": "1-3 min",
    r"pip\s+install": "2-5 min",
    r"pip3\s+install": "2-5 min",
    r"install.*requirements": "2-5 min",
    r"vite\s+build": "30-60s",
    r"apt(-get)?\s+(install|upgrade|dist-upgrade)": "1-5 min",
    r"docker\s+pull": "2-10 min",
    r"git\s+clone": "30s-5 min",
    r"wait.*healthy": "up to 10 min",
    r"wait.*backend": "up to 10 min",
    r"create.*venv|virtualenv": "30-60s",
    r"filtered.*requirements": "2-5 min",
    r"requirements.*filtered": "2-5 min",
    r"install.*package": "1-3 min",
    r"sync.*code": "30-60s",
    r"rsync": "30-60s",
}

_TASK_NAME_MAX_LEN = 60


def _get_slow_task_hint(task_name: str) -> str | None:
    """Return an estimated-duration hint for *task_name*, or ``None``.

    Tries each pattern in ``SLOW_TASK_HINTS`` against the full task name using
    a case-insensitive substring search.

    Args:
        task_name: Ansible task name string to match.

    Returns:
        Human-readable estimate string, e.g. ``"5-15 min per model"``, or
        ``None`` when no pattern matches.
    """
    lower = task_name.lower()
    for pattern, hint in SLOW_TASK_HINTS.items():
        if re.search(pattern, lower):
            return hint
    return None


def format_elapsed(seconds: float) -> str:
    """Format *seconds* as a human-readable elapsed string.

    Examples::

        format_elapsed(45)    -> "45s"
        format_elapsed(90)    -> "1m 30s"
        format_elapsed(3665)  -> "1h 1m 5s"

    Args:
        seconds: Elapsed time in seconds (may be fractional).

    Returns:
        Compact human-readable string.
    """
    secs = int(seconds)
    if secs < 60:
        return f"{secs}s"
    minutes, secs = divmod(secs, 60)
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m {secs}s"


class TaskProgressTracker:
    """Async context manager that sends periodic heartbeats during a task.

    While the ``async with`` block is active a background coroutine wakes up
    every ``HEARTBEAT_INTERVAL_SECONDS`` and calls *progress_callback* with::

        {
            "stage": "heartbeat",
            "message": "Still running... (elapsed: 2m 15s) [npm install — est. 1-3 min]"
        }

    The task name (truncated to 60 chars) is always included so the user can
    see what is running.  The ``— est. <hint>`` suffix is added when the task
    name matches a pattern in ``SLOW_TASK_HINTS``.

    Args:
        task_name: Ansible task name (used for slow-task hint lookup and logs).
        progress_callback: Async callable that accepts a ``dict`` with ``stage``
            and ``message`` keys.  Must not raise — errors are swallowed and
            logged at DEBUG level to avoid disrupting the calling coroutine.
        heartbeat_interval: Override the default heartbeat cadence (seconds).
            Primarily used in tests.
    """

    def __init__(
        self,
        task_name: str,
        progress_callback: Callable | None,
        *,
        heartbeat_interval: int = HEARTBEAT_INTERVAL_SECONDS,
    ) -> None:
        self._task_name = task_name
        self._progress_callback = progress_callback
        self._heartbeat_interval = heartbeat_interval
        self._start_time: float = 0.0
        self._heartbeat_task: asyncio.Task | None = None

    async def __aenter__(self) -> "TaskProgressTracker":
        self._start_time = time.monotonic()
        if self._progress_callback is not None:
            self._heartbeat_task = asyncio.ensure_future(self._heartbeat_loop())
            logger.debug("TaskProgressTracker started for task: %s", self._task_name)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None
            logger.debug(
                "TaskProgressTracker stopped for task: %s (elapsed: %s)",
                self._task_name,
                format_elapsed(time.monotonic() - self._start_time),
            )

    @property
    def elapsed_seconds(self) -> float:
        """Seconds since the tracker was entered."""
        return time.monotonic() - self._start_time

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeat messages until cancelled."""
        hint = _get_slow_task_hint(self._task_name)
        display_name = (
            self._task_name[:_TASK_NAME_MAX_LEN] + "…" if len(self._task_name) > _TASK_NAME_MAX_LEN else self._task_name
        )
        try:
            while True:
                await asyncio.sleep(self._heartbeat_interval)
                elapsed_str = format_elapsed(self.elapsed_seconds)
                if hint:
                    msg = f"Still running... (elapsed: {elapsed_str}) [{display_name} — est. {hint}]"
                else:
                    msg = f"Still running... (elapsed: {elapsed_str}) [{display_name}]"
                try:
                    await self._progress_callback({"stage": "heartbeat", "message": msg})
                except Exception as exc:
                    logger.debug("TaskProgressTracker: progress_callback error: %s", exc)
        except asyncio.CancelledError:
            pass
