# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#20887: one persistent event loop per Celery worker process.

Celery tasks are synchronous, but the code they call is async and reaches
process-wide singletons (the SQLAlchemy async engine, async Redis pools, a
cached aiosqlite connection) that are bound to the loop that first used them.
A fresh ``asyncio.run`` per task closes that loop on return, so the second task
reuses a pool whose transports belong to a dead loop and fails with
``RuntimeError('Event loop is closed')``.

The fix is structural: every task drives its coroutine through
:func:`run_in_worker_loop`, which submits it to ONE loop that lives for the whole
worker process and is only stopped at process shutdown. Engines, session
factories and Redis pools are created on that loop once and reused.

Lifecycle (wired in ``celery_app.py``):

- ``worker_process_init`` -> :func:`start_worker_loop` (post-fork; also drops any
  state inherited from the parent).
- ``worker_process_shutdown`` -> :func:`stop_worker_loop`, which disposes the
  engine and Redis pools on the loop before stopping it.

Supported pool: prefork only (the deployed pool; ``autobot-celery.service`` passes no
``-P`` and uses ``--max-tasks-per-child``). The lifecycle hooks are
``worker_process_init`` and ``worker_process_shutdown``, which only the prefork pool fires
once per child process: the solo pool fires init once (in the main process) and never
shutdown, and the threads pool fires neither. Under those pools
:func:`run_in_worker_loop` does not raise; it lazily spawns the loop on first use, but
the fork reset, :func:`in_worker_process` (so ``run_or_schedule`` falls back to
``asyncio.run`` per call) and the shutdown disposal are not in effect. Submitting from
many threads is safe (the call is thread-safe).
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import os
import threading
from typing import Any, Awaitable, Callable, Coroutine, TypeVar

from autobot_shared.env_utils import env_float
from autobot_shared.logging_manager import get_logger

__all__ = [
    "get_worker_loop",
    "in_worker_process",
    "run_in_worker_loop",
    "run_on_loop",
    "start_worker_loop",
    "stop_worker_loop",
]

logger = get_logger(__name__)

T = TypeVar("T")

# Seconds to wait for the loop thread to report that it is running.
WORKER_LOOP_START_TIMEOUT = env_float("AUTOBOT_WORKER_LOOP_START_TIMEOUT", 10.0)
# Seconds the shutdown hook gives engine/Redis disposal before stopping anyway.
WORKER_LOOP_SHUTDOWN_TIMEOUT = env_float("AUTOBOT_WORKER_LOOP_SHUTDOWN_TIMEOUT", 15.0)

# Upper bound on how long run_on_loop() blocks for one coroutine. No Celery task time limit
# is configured (celery_app.py sets none), so the longest sweep is unbounded by Celery; one
# hour is far above any current sweep yet still turns a hung coroutine into an error
# instead of a permanently blocked thread. Override per deployment with the env var.
WORKER_LOOP_RUN_TIMEOUT = env_float("AUTOBOT_WORKER_LOOP_RUN_TIMEOUT", 3600.0)

_STATE_LOCK = threading.Lock()
_loop: asyncio.AbstractEventLoop | None = None
_thread: threading.Thread | None = None
# True only after celery_app started the loop in a worker child, so API-process
# callers of run_or_schedule are never routed here by a lazy start.
_worker_mode = False


def _reset_state_in_child() -> None:
    """Forget the parent's loop and thread; neither is usable in a forked child."""
    global _loop, _thread, _worker_mode, _STATE_LOCK
    # A thread that held the lock at fork time does not exist in the child; keeping the
    # inherited (locked) lock would deadlock the first _ensure_loop().
    _STATE_LOCK = threading.Lock()
    _loop = None
    _thread = None
    _worker_mode = False


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_reset_state_in_child)


def _loop_main(loop: asyncio.AbstractEventLoop, ready: threading.Event) -> None:
    asyncio.set_event_loop(loop)
    loop.call_soon(ready.set)
    try:
        loop.run_forever()
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        finally:
            loop.close()


def _spawn_loop() -> asyncio.AbstractEventLoop:
    loop = asyncio.new_event_loop()
    ready = threading.Event()
    thread = threading.Thread(target=_loop_main, args=(loop, ready), name="autobot-worker-loop", daemon=True)
    thread.start()
    if not ready.wait(WORKER_LOOP_START_TIMEOUT):
        raise RuntimeError("worker event loop did not start in time")
    global _thread
    _thread = thread
    return loop


def _ensure_loop() -> asyncio.AbstractEventLoop:
    global _loop
    with _STATE_LOCK:
        if _loop is None or _loop.is_closed():
            _loop = _spawn_loop()
        return _loop


def start_worker_loop() -> asyncio.AbstractEventLoop:
    """Start (or return) this process's worker loop and mark it as a worker."""
    global _worker_mode
    loop = _ensure_loop()
    _worker_mode = True
    return loop


def get_worker_loop() -> asyncio.AbstractEventLoop | None:
    """The live worker loop, or ``None`` when none has been started."""
    loop = _loop
    return loop if loop is not None and not loop.is_closed() else None


def in_worker_process() -> bool:
    """True when :func:`start_worker_loop` ran in this process (a Celery child)."""
    return _worker_mode and get_worker_loop() is not None


def _running_loop() -> asyncio.AbstractEventLoop | None:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


def run_in_worker_loop(coro: Coroutine[Any, Any, T], *, timeout: float | None = None) -> T:
    """Run ``coro`` on the worker loop and block for its result.

    ``timeout`` defaults to ``WORKER_LOOP_RUN_TIMEOUT`` (read at call time), so a hung
    coroutine never blocks the task thread forever. Raises whatever ``coro`` raises. If
    the waiting thread is interrupted (a Celery soft time limit, ``KeyboardInterrupt``)
    or the timeout elapses, the pending future is cancelled so a runaway task cannot
    hold the loop for later tasks.
    """
    if timeout is None:
        timeout = WORKER_LOOP_RUN_TIMEOUT
    loop = _ensure_loop()
    if _running_loop() is loop:
        coro.close()
        raise RuntimeError("run_in_worker_loop() called from the worker loop itself; await the coroutine instead")
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    try:
        return future.result(timeout)
    except BaseException:
        future.cancel()
        raise


def run_on_loop(coro: Coroutine[Any, Any, T], loop: asyncio.AbstractEventLoop) -> T:
    """Submit ``coro`` to ``loop`` from another thread and block for the result.

    Waits at most ``WORKER_LOOP_RUN_TIMEOUT`` seconds; on expiry the future is cancelled
    and a ``TimeoutError`` naming the coroutine is raised.
    """
    name = getattr(coro, "__qualname__", repr(coro))
    future: concurrent.futures.Future[T] = asyncio.run_coroutine_threadsafe(coro, loop)
    try:
        return future.result(WORKER_LOOP_RUN_TIMEOUT)
    except concurrent.futures.TimeoutError as exc:
        if future.done():
            # The coroutine itself raised TimeoutError (the same class since 3.11): not our wait.
            raise
        future.cancel()
        raise TimeoutError(
            f"coroutine {name} did not finish within {WORKER_LOOP_RUN_TIMEOUT}s on the worker loop"
        ) from exc
    except BaseException:
        future.cancel()
        raise


# (label, module, attribute): each attribute is an async no-arg disposer. A module that
# is not importable in this process (a worker without that component) is skipped.
_DISPOSERS: tuple[tuple[str, str, str], ...] = (
    ("database", "user_management.database", "close_database"),
    ("transcriber", "transcriber.database", "close_transcriber_db"),
    ("redis", "autobot_shared.redis_client", "close_all_redis_connections"),
)


async def _dispose_shared_resources() -> None:
    """Dispose the engine, transcriber DB and Redis pools; one failure never stops the rest."""
    import importlib

    for name, module, attr in _DISPOSERS:
        try:
            step: Callable[[], Awaitable[None]] = getattr(importlib.import_module(module), attr)
        except ImportError:
            logger.debug("worker loop shutdown: %s not importable here", module)
            continue
        try:
            await step()
        except Exception:  # noqa: BLE001 - shutdown must continue past one failed disposal
            logger.warning("worker loop shutdown: %s disposal failed", name, exc_info=True)


def stop_worker_loop() -> None:
    """Dispose shared async resources on the loop, then stop it (process shutdown)."""
    global _loop, _thread, _worker_mode
    with _STATE_LOCK:
        loop, thread = _loop, _thread
        _loop, _thread, _worker_mode = None, None, False
    if loop is None or loop.is_closed():
        return
    try:
        future = asyncio.run_coroutine_threadsafe(_dispose_shared_resources(), loop)
        future.result(WORKER_LOOP_SHUTDOWN_TIMEOUT)
    except Exception:  # noqa: BLE001 - stop the loop even if disposal timed out
        logger.warning("worker loop shutdown: resource disposal did not finish", exc_info=True)
    loop.call_soon_threadsafe(loop.stop)
    if thread is not None:
        thread.join(WORKER_LOOP_SHUTDOWN_TIMEOUT)
