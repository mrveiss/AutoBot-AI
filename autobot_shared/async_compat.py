# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#7469: shared defensive helper for ``asyncio.run()`` re-entrancy.

## Why

``asyncio.run(coro)`` cannot be called from inside an already-running event
loop — it raises ``RuntimeError: asyncio.run() cannot be called from a
running event loop`` and crashes the caller. This happens silently and
intermittently for sync code paths that *sometimes* run from sync
entrypoints and *sometimes* run from async contexts:

  - Error-boundary decorators wrapping mixed sync/async functions
  - Celery worker callbacks that schedule async writes
  - GUI button handlers that may dispatch into async services

Several places in the codebase already implemented the defensive
try-loop-running pattern locally (``autobot-backend/memory/compat.py``,
``autobot-backend/memory/manager.py``). This module hoists the pattern
into ``autobot_shared`` so all callers share one implementation.

## Contract

  ``run_or_schedule(coro)`` runs ``coro`` to completion and returns its
  result, regardless of whether the caller is in a sync or async context:

  1. **No event loop in the current thread** → ``asyncio.run(coro)``
     directly. Standard sync-entry behavior.
  2. **Event loop is running in the current thread** → schedule the coro
     in a ThreadPoolExecutor that owns its own loop, then block until
     it returns. This is the only safe option because the current loop
     is busy and we can't await without making the caller async.

The threadpool-detour costs a thread spawn per call (and gives up
asyncio's I/O concurrency for the duration of the coro). Use it only at
the sync/async boundary — never as a substitute for ``await`` inside
async code.

## Migration target

Replace this pattern:

```python
try:
    asyncio.get_running_loop()
    # Already in async context — error
    ...
except RuntimeError:
    return asyncio.run(coro)
```

With:

```python
from autobot_shared.async_compat import run_or_schedule
return run_or_schedule(coro)
```
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from typing import Any, Coroutine, TypeVar

__all__ = ["run_or_schedule", "fire_and_forget", "pending_background_tasks"]


T = TypeVar("T")


def run_or_schedule(coro: Coroutine[Any, Any, T]) -> T:
    """Run ``coro`` to completion from either sync or async context.

    See module docstring for the full contract. Sync entry: uses
    ``asyncio.run``. Already-in-loop entry: spawns a thread pool that
    owns its own loop, runs ``coro`` there, and blocks for the result.

    Raises whatever ``coro`` raises (after unwrapping the
    concurrent.futures.Future indirection in the threaded path).
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No loop in this thread — standard sync entry.
        return asyncio.run(coro)

    # Loop is running. Hand off to a worker thread that creates its own
    # loop. Single-shot ThreadPoolExecutor with one worker; the future
    # blocks the calling thread which is what we want at the sync/async
    # boundary.
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, coro)
        return future.result()


# #15522: the event loop keeps only a WEAK reference to a task, so a task whose
# only other reference was the discarded return of ``asyncio.create_task`` can be
# garbage-collected mid-flight. Observed live on the SLM self-update path: one
# firing executed, an identical firing minutes later produced no executor call,
# no inventory file, no transient unit and no log write. A hard reference held
# here for the task's lifetime is what makes "fire and forget" mean fire.
_BACKGROUND_TASKS: set[asyncio.Task[Any]] = set()


def fire_and_forget(coro: Coroutine[Any, Any, Any], *, name: str) -> asyncio.Task[Any]:
    """Schedule *coro* on the running loop, retaining it until it finishes.

    Use instead of a bare ``asyncio.create_task(...)`` whose result is thrown
    away. The returned task is held in a module-level set until it completes,
    and its completion callback both releases that reference and LOGS a failure
    — nothing awaits these tasks, so without the callback an exception raised
    inside *coro* has nowhere to surface.
    """
    task = asyncio.create_task(coro, name=name)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_retire_background_task)
    return task


def _retire_background_task(task: asyncio.Task[Any]) -> None:
    """Release the hard reference and report how *task* ended."""
    # Imported here, not at module scope: this module is a low-level utility
    # imported by API modules, and LoggingManager builds a real rotating file
    # handler on first use. Binding it at import time made merely importing
    # ``code_sync`` construct that handler, which broke test modules that stub
    # the logging config. A background task's outcome is rare enough to pay the
    # lookup here instead.
    from autobot_shared.logging_manager import get_logger

    logger = get_logger(__name__)
    _BACKGROUND_TASKS.discard(task)
    if task.cancelled():
        logger.warning("background task %s was cancelled", task.get_name())
        return
    exc = task.exception()
    if exc is not None:
        logger.error("background task %s failed: %s", task.get_name(), exc, exc_info=exc)


def pending_background_tasks() -> frozenset[asyncio.Task[Any]]:
    """Snapshot of the tasks :func:`fire_and_forget` is currently retaining."""
    return frozenset(_BACKGROUND_TASKS)


def retain_until_done(
    registry: dict[str, asyncio.Task[Any]], key: str, coro: Coroutine[Any, Any, Any]
) -> asyncio.Task[Any]:
    """Schedule *coro*, hold it in *registry* under *key*, and drop it when done.

    A discarded ``create_task`` result can be garbage-collected before its
    coroutine runs (#15524), so a caller that needs the task cancellable later
    must keep a reference. A reference that is never released leaks for the life
    of the process, so the done callback removes it. Prefer
    :func:`fire_and_forget` unless something must be able to cancel the task.
    """
    task = asyncio.create_task(coro)
    registry[key] = task
    task.add_done_callback(lambda _: registry.pop(key, None))
    return task
