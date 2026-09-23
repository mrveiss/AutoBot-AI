# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Retention for fire-and-forget tasks, local to the worker (#15522, #15642).

Mirrors ``autobot_shared/async_compat.py``'s :func:`fire_and_forget`, and is a
deliberate architecture exception recorded in
``docs/developer/ARCHITECTURE_EXCEPTIONS.md`` for the reason
``app/utils/redis_client.py`` is: the shared package is not on this worker's
disk, so the canonical helper cannot be imported and the retention has to be
local.

This module ships inside the standalone Windows package: PyInstaller's
``installer/npu_worker.spec`` analyses ``app/npu_worker.py`` with
``pathex=[app]``, and ``scripts/install.ps1`` copies only this tree. Nothing
here may import ``autobot_shared`` — it is not on the worker's disk.

The defect it fixes: the event loop holds only a WEAK reference to a task, so a
launch whose handle is discarded can be garbage-collected before the coroutine
runs — silently, because nothing awaits it and nothing reports how it ended.
The hard reference held below for the task's lifetime is what makes "fire and
forget" mean fire; the done callback releases that reference and logs a
failure that would otherwise vanish.

Sync cadence: when ``autobot_shared/async_compat.py``'s ``fire_and_forget``
changes, mirror the change here.
"""

import asyncio
import logging
from typing import Any, Coroutine

logger = logging.getLogger(__name__)

_BACKGROUND_TASKS: "set[asyncio.Task[Any]]" = set()


def fire_and_forget(coro: Coroutine[Any, Any, Any], *, name: str) -> "asyncio.Task[Any]":
    """Schedule *coro* on the running loop, retaining it until it finishes."""
    task = asyncio.create_task(coro, name=name)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_retire_background_task)
    return task


def _retire_background_task(task: "asyncio.Task[Any]") -> None:
    """Release the hard reference and report how *task* ended."""
    _BACKGROUND_TASKS.discard(task)
    if task.cancelled():
        logger.warning("background task %s was cancelled", task.get_name())
        return
    exc = task.exception()
    if exc is not None:
        logger.error("background task %s failed: %s", task.get_name(), exc, exc_info=exc)


def pending_background_tasks() -> "frozenset[asyncio.Task[Any]]":
    """Snapshot of the tasks :func:`fire_and_forget` is currently retaining."""
    return frozenset(_BACKGROUND_TASKS)
