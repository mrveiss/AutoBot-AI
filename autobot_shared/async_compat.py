# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#7469: shared defensive helpers for scheduling coroutines across contexts.

This module owns the canonical background-task launchers as well as the
``asyncio.run()`` re-entrancy guard it was created for: :func:`fire_and_forget`
(same thread, running loop), :func:`fire_and_forget_threadsafe` (a thread that
is *not* running the loop) and :func:`retain_until_done` (a launch something
must be able to cancel later). ``autobot_shared/fire_and_forget.py`` used to
hold a second, non-retaining launcher under the more obvious name; it is now
``autobot_shared/redis_write.py`` and delegates here (#15637).

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

  0. **Inside a Celery worker** (#20887) → the worker's persistent loop
     (``autobot_shared.worker_loop``), in both branches below.
  1. **No event loop in the current thread** → ``asyncio.run(coro)``
     directly. Standard sync-entry behavior.
  2. **Event loop is running in the current thread** → submit the coro to
     the API process's registered main loop (``register_main_loop``) and
     block until it returns (in a Celery worker the target is the worker's
     persistent loop instead). It falls back to a thread with its own loop
     only in the two situations listed under the fresh-loop fallback below.

  **Fresh-loop fallback (#21082, #20919).** Case 2 uses a thread with a brand-new
  loop in exactly two situations: (a) the target loop is unavailable (no main loop
  registered, or it is not running / is closed; no worker loop in a worker), or
  (b) the target loop IS the caller's own running loop. A fresh loop does not own the
  process-wide loop-bound singletons (async DB engine, Redis pools, aiosqlite
  connections), so touching them there can fail with ``Event loop is closed`` or
  attach them to a loop that dies on return. The first fallback per call site is
  logged as a warning; callers on the loop thread should ``await`` instead.

Use it only at the sync/async boundary — never as a substitute for
``await`` inside async code.

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
import inspect
import threading
from typing import Any, Coroutine, TypeVar

from autobot_shared.logging_once import first_time

__all__ = [
    "register_main_loop",
    "run_or_schedule",
    "fire_and_forget",
    "fire_and_forget_threadsafe",
    "pending_background_tasks",
    "pending_threadsafe_dispatches",
    "retain_until_done",
]


T = TypeVar("T")


# #20887: the API process's serving loop, registered by the lifespan. A sync
# caller on a different thread whose own loop is busy submits here, so the
# coroutine runs on the loop that owns the process-wide singletons.
_MAIN_LOOP: asyncio.AbstractEventLoop | None = None


def register_main_loop(loop: asyncio.AbstractEventLoop | None) -> None:
    """Record (or clear, with ``None``) the API process's serving loop."""
    global _MAIN_LOOP
    _MAIN_LOOP = loop


def _usable_main_loop() -> asyncio.AbstractEventLoop | None:
    loop = _MAIN_LOOP
    return loop if loop is not None and loop.is_running() and not loop.is_closed() else None


def _run_in_fresh_loop_thread(coro: Coroutine[Any, Any, T]) -> T:
    """Last resort: a thread with its own loop (no usable shared loop exists)."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _warn_fallback_once() -> None:
    """Log (once per call site per process) that a sync caller blocks the loop it needs (#20887)."""
    # frame 0 = here, 1 = _run_under_running_loop, 2 = run_or_schedule, 3 = the caller
    frame = inspect.stack()[3]
    site = (frame.frame.f_globals.get("__name__", "?"), frame.function)
    if not first_time(__name__, "fallback:%s.%s" % site):  # once per call site (module, function)
        return
    _log_threadsafe(
        "warning",
        "run_or_schedule called synchronously on the API loop thread; falling back to a "
        "private-loop thread (loop-bound singletons are unsafe there). Caller: %s.%s",
        *site,
    )


def _run_under_running_loop(coro: Coroutine[Any, Any, T], running: asyncio.AbstractEventLoop) -> T:
    """Delegate while the caller's thread is running ``running`` (#20887)."""
    from autobot_shared import worker_loop

    target = worker_loop.get_worker_loop() if worker_loop.in_worker_process() else _usable_main_loop()
    if target is None or target is running:
        # Blocking this thread on its own loop would deadlock, and there is no
        # other shared loop: keep the pre-#20887 detour rather than hang.
        _warn_fallback_once()
        return _run_in_fresh_loop_thread(coro)
    return worker_loop.run_on_loop(coro, target)


def run_or_schedule(coro: Coroutine[Any, Any, T]) -> T:
    """Run ``coro`` to completion from either sync or async context.

    See module docstring for the full contract. Inside a Celery worker the
    coroutine runs on the worker's persistent loop, except in the fresh-loop
    fallback cases below (running loop, target unavailable or the caller's own
    loop). Otherwise, with no
    loop running in this thread it uses ``asyncio.run``; with a loop running it
    is submitted to the worker loop or the API process's main loop; a fresh loop in a
    thread is used only in the fallback cases below, because it would touch loop-bound
    singletons from the wrong loop. Worker-loop lookup checks only that the loop is
    not closed, not ``is_running()``.

    Fresh-loop fallback (#21082, #20919): under a running loop the coroutine runs in a
    thread with its OWN new loop when (a) the target loop (worker loop, or registered
    main loop) is unavailable, or (b) the target is the caller's own loop, since blocking
    on it would deadlock. Loop-bound singletons (async DB engine, Redis pools) used there
    are bound to a loop that closes on return and may fail on later reuse; the first
    fallback per call site logs a warning.

    Raises whatever ``coro`` raises.
    """
    from autobot_shared import worker_loop

    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        if worker_loop.in_worker_process():
            return worker_loop.run_in_worker_loop(coro)
        return asyncio.run(coro)
    return _run_under_running_loop(coro, running)


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


# #15636: the same weak-reference problem, one thread boundary further out.
# ``asyncio.create_task`` — and therefore ``fire_and_forget`` — needs a loop
# running in the CALLING thread and raises ``RuntimeError: no running event
# loop`` when there is none. A watchdog ``Observer`` dispatches its callbacks on
# its own thread, so every launch made from one of those callbacks raised, on
# every event, and the work was never scheduled at all. The hand-off below is
# what a non-loop thread has to use instead, and the returned
# ``concurrent.futures.Future`` is retained here for exactly the reason a Task
# is: nothing awaits it, so nothing else holds it or reports how it ended.
_THREADSAFE_DISPATCHES: set[concurrent.futures.Future[Any]] = set()
# Unlike ``_BACKGROUND_TASKS`` this set is written from two threads — the caller
# adds, the loop thread retires — so the membership changes take a lock.
_THREADSAFE_LOCK = threading.Lock()


def fire_and_forget_threadsafe(
    coro: Coroutine[Any, Any, Any],
    *,
    name: str,
    loop: asyncio.AbstractEventLoop | None,
) -> concurrent.futures.Future[Any] | None:
    """Schedule *coro* on *loop* from a thread that is not running that loop.

    Use from a callback that runs on a foreign thread — a watchdog observer, a
    driver callback, any library that calls back on its own worker. From inside
    the loop's own thread use :func:`fire_and_forget` instead.

    Args:
        coro: Coroutine to run on *loop*.
        name: Identifies the launch in the failure log.
        loop: The loop captured while it was running, or ``None`` if the owner
            never captured one.

    Returns:
        The retained ``concurrent.futures.Future``, or ``None`` if the loop was
        missing or already closed — a falsy return means *nothing was
        scheduled*, and the caller must not record the work as done.
    """
    if loop is None or loop.is_closed():
        _log_threadsafe(
            "error",
            "cross-thread task %s dropped: no usable event loop was captured",
            name,
        )
        coro.close()
        return None
    try:
        future = asyncio.run_coroutine_threadsafe(coro, loop)
    except RuntimeError as exc:
        # The loop stopped between the is_closed() check and the hand-off.
        _log_threadsafe("error", "cross-thread task %s could not be scheduled: %s", name, exc)
        coro.close()
        return None
    with _THREADSAFE_LOCK:
        _THREADSAFE_DISPATCHES.add(future)
    future.add_done_callback(lambda done: _retire_threadsafe_dispatch(done, name))
    return future


def _retire_threadsafe_dispatch(future: concurrent.futures.Future[Any], name: str) -> None:
    """Release the hard reference and report how the cross-thread launch ended."""
    with _THREADSAFE_LOCK:
        _THREADSAFE_DISPATCHES.discard(future)
    if future.cancelled():
        _log_threadsafe("warning", "cross-thread task %s was cancelled", name)
        return
    exc = future.exception()
    if exc is not None:
        _log_threadsafe("error", "cross-thread task %s failed: %s", name, exc)


def _log_threadsafe(level: str, message: str, *args: Any) -> None:
    """Log at *level*, resolving the logger lazily.

    Bound here rather than at module scope for the same reason
    :func:`_retire_background_task` does it: importing ``logging_manager`` at
    import time builds a rotating file handler in every module that imports this
    one, which broke test modules that stub the logging config.
    """
    from autobot_shared.logging_manager import get_logger

    getattr(get_logger(__name__), level)(message, *args)


def pending_threadsafe_dispatches() -> frozenset[concurrent.futures.Future[Any]]:
    """Snapshot of the futures :func:`fire_and_forget_threadsafe` is retaining."""
    with _THREADSAFE_LOCK:
        return frozenset(_THREADSAFE_DISPATCHES)


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
