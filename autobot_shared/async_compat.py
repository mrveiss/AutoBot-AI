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

__all__ = ["run_or_schedule"]


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
