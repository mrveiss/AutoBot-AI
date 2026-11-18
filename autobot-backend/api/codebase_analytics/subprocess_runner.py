# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Isolated indexing subprocess launcher and watchdog.

Issue #2364: Extracted from scanner.py to isolate subprocess lifecycle from
the main scanning orchestration.

Public functions
----------------
- _handle_subprocess_crash  — mark task failed in Redis after crash
- _wait_with_watchdog       — wait for subprocess with progress watchdog
- _run_indexing_subprocess  — launch subprocess + supervise until exit
"""

import asyncio
import sys
from pathlib import Path

from autobot_shared.logging_manager import get_logger

from .indexing_executor import (
    _SUBPROCESS_HARD_TIMEOUT,
    _SUBPROCESS_PROGRESS_TIMEOUT,
    _SUBPROCESS_WATCHDOG_INTERVAL,
)
from .progress_tracker import _load_task_from_redis
from .run_status import (
    STATUS_CANCELLED,
    STATUS_FAILED,
    STATUS_KILLED,
    TERMINAL_STATUSES,
    RunKilled,
    hard_timeout_kill_reason,
    record_run_finished,
    record_run_started,
    status_for_returncode,
    watchdog_kill_reason,
)

logger = get_logger(__name__)


#: Reasons recorded for a terminal status recovered from the task state.  They are served to
#: readers, so they name the outcome only; the task's error text stays in the task state and the log.
_RECOVERED_REASONS = {
    STATUS_FAILED: "indexing failed",
    STATUS_KILLED: "indexing worker was killed",
    STATUS_CANCELLED: "cancelled by user",
}


async def _record_terminal_if_done(task_id: str, source_id: str | None) -> bool:
    """Backstop (#21003): a task left in a terminal state is recorded with that status.

    The worker records its own outcome, but the Redis state can say ``completed``
    or ``failed`` while that record write never landed (or the hard timeout fired
    in between); the record would stay ``running`` and later read ``abandoned``.
    ``record_run_finished`` keeps the first terminal status of a run, so this is
    idempotent when the record is already right.  True when the task was terminal.
    """
    status = (await _load_task_from_redis(task_id) or {}).get("status")
    if status not in TERMINAL_STATUSES:
        return False
    await record_run_finished(source_id, task_id, status, _RECOVERED_REASONS.get(status, ""))
    return True


async def _mark_crashed(task_id, returncode, mark_task_failed_fn, save_task_fn, source_id, kill_reason) -> None:
    """Mark the task failed/killed in Redis and record the run's terminal status (#21003)."""
    status = status_for_returncode(returncode)
    reason = kill_reason or f"Indexing subprocess crashed (exit code {returncode})"
    error_type = RunKilled if status == STATUS_KILLED else RuntimeError
    mark_task_failed_fn(task_id, error_type(reason))
    await save_task_fn(task_id)
    # The findings it stored stay, labelled partial.
    await record_run_finished(source_id, task_id, status, reason)


async def _handle_subprocess_crash(
    task_id: str,
    returncode: int,
    mark_task_failed_fn,
    save_task_fn,
    source_id: str | None = None,
    kill_reason: str = "",
) -> None:
    """Mark indexing task failed/killed in Redis after subprocess crash (#1180).

    Only updates state if the subprocess did not already write a terminal
    status (completed/failed/cancelled) before crashing.  A task already
    terminal is recorded with that status instead (#21003 backstop).

    Parameters
    ----------
    mark_task_failed_fn:
        Callable ``(task_id, error)`` bound to module-level indexing_tasks.
    save_task_fn:
        Async callable ``(task_id)`` that persists task state to Redis.
    kill_reason:
        Why the supervisor killed the worker (progress timeout or hard
        timeout), when it did; otherwise the exit code is the reason.
    """
    logger.error("[Task %s] Indexing subprocess crashed (exit code %d)", task_id, returncode)
    if not await _record_terminal_if_done(task_id, source_id):
        await _mark_crashed(task_id, returncode, mark_task_failed_fn, save_task_fn, source_id, kill_reason)


def _progress_signature(task_data: dict) -> tuple:
    """What counts as liveness in a task state: counters, operation and phase.

    #18055: a phase transition is liveness too.  Hashing only the progress
    counters made every legitimately-silent step fatal -- the bulk problem
    upsert ran past the window and the worker was killed before anything was
    persisted.
    `or {}`, not a default: a legacy or partial state dict can carry the key
    with an explicit null, and `.get(k, {})` returns that null.  An
    AttributeError here escapes the watchdog and leaves the child running
    unwatched -- the supervisor catches only TimeoutError.
    """
    progress = task_data.get("progress") or {}
    phases = task_data.get("phases") or {}
    return (
        progress.get("current"),
        progress.get("total"),
        progress.get("operation"),
        phases.get("current_phase"),
        len(phases.get("phases_completed") or []),
    )


async def _wait_with_watchdog(
    proc: asyncio.subprocess.Process,
    task_id: str,
    kill_reasons: list[str] | None = None,
) -> int:
    """Wait for subprocess with progress watchdog (#1341).

    Periodically checks if the subprocess is still making progress by reading
    the task state from Redis.  If no progress update is observed for
    ``_SUBPROCESS_PROGRESS_TIMEOUT`` seconds, the subprocess is killed.
    #21003: the cause is appended to ``kill_reasons`` first (both kill paths return -9).
    """
    last_progress_hash = None
    last_progress_time = asyncio.get_running_loop().time()

    while True:
        try:
            returncode = await asyncio.wait_for(
                proc.wait(),
                timeout=_SUBPROCESS_WATCHDOG_INTERVAL,
            )
            return returncode
        except asyncio.TimeoutError:
            pass  # Process still running — check progress

        task_data = await _load_task_from_redis(task_id)
        if task_data:
            if task_data.get("status") in TERMINAL_STATUSES:
                return await proc.wait()

            progress_hash = _progress_signature(task_data)
            now = asyncio.get_running_loop().time()

            if progress_hash != last_progress_hash:
                last_progress_hash = progress_hash
                last_progress_time = now
            elif now - last_progress_time > _SUBPROCESS_PROGRESS_TIMEOUT:
                idle = int(now - last_progress_time)
                logger.error("[Task %s] Subprocess stale for %d seconds, killing (no progress update)", task_id, idle)
                if kill_reasons is not None:
                    kill_reasons.append(watchdog_kill_reason(idle, _SUBPROCESS_PROGRESS_TIMEOUT))
                proc.kill()
                await proc.wait()
                return -9


async def _kill_worker(proc) -> None:
    """Kill the worker and reap it; a worker that already exited is not an error."""
    try:
        proc.kill()
    except ProcessLookupError:
        pass
    await proc.wait()


async def _wait_for_exit(proc, task_id: str, source_id: str | None, kill_reasons: list[str]) -> int:
    """Wait for the worker under the hard timeout; return its exit code (-9 when killed here).

    #21003: a cancelled supervisor must not leave the worker running -- the orphan
    would keep writing findings -- so it kills it, records the run ``cancelled``
    (a terminal status: a late ``completed`` from the orphan is ignored) and re-raises.
    """
    try:
        return await asyncio.wait_for(
            _wait_with_watchdog(proc, task_id, kill_reasons), timeout=_SUBPROCESS_HARD_TIMEOUT
        )
    except asyncio.TimeoutError:
        logger.error("[Task %s] Subprocess exceeded hard timeout of %d seconds", task_id, _SUBPROCESS_HARD_TIMEOUT)
        kill_reasons.append(hard_timeout_kill_reason(_SUBPROCESS_HARD_TIMEOUT))
        await _kill_worker(proc)
        return -9
    except asyncio.CancelledError:
        logger.warning("[Task %s] Indexing cancelled; killing the worker", task_id)
        await _kill_worker(proc)
        await record_run_finished(source_id, task_id, STATUS_CANCELLED, _RECOVERED_REASONS[STATUS_CANCELLED])
        raise


async def _spawn_worker(cmd: list[str], task_id: str, source_id: str | None):
    """Start the worker.  A start that fails after the run was recorded as started is recorded ``failed``."""
    try:
        return await asyncio.create_subprocess_exec(*cmd)
    except Exception as exc:
        await record_run_finished(
            source_id, task_id, STATUS_FAILED, f"worker could not be started ({type(exc).__name__})"
        )
        raise


async def _run_indexing_subprocess(
    task_id: str,
    root_path: str,
    indexing_tasks: dict,
    tasks_lock: asyncio.Lock,
    create_initial_state_fn,
    save_task_fn,
    mark_task_failed_fn,
    source_id: str | None = None,
) -> None:
    """Launch isolated indexing subprocess to prevent ChromaDB SIGSEGV (#1180).

    The subprocess runs ``do_indexing_with_progress`` in its own process so
    its ChromaDB PersistentClient does not conflict with the KB's concurrent
    client.  If the subprocess crashes (SIGSEGV), this coroutine catches the
    non-zero exit code and marks the task failed in Redis.

    Issue #1341: Added 30-minute hard timeout and 5-minute progress watchdog.
    Issue #1710: source_id scopes indexing to one project.

    Parameters
    ----------
    create_initial_state_fn:
        Callable ``() -> dict`` that returns the initial task-state dict.
    save_task_fn:
        Async callable ``(task_id)`` that persists task state to Redis.
    mark_task_failed_fn:
        Callable ``(task_id, error)`` that marks the task as failed.
    """
    worker_script = Path(__file__).parent / "indexing_worker.py"

    async with tasks_lock:
        # #20491: known from the first save, so no reader takes it for another source's job.
        indexing_tasks[task_id] = {**create_initial_state_fn(), "source_id": source_id}
        await save_task_fn(task_id)

    cmd = [sys.executable, str(worker_script), task_id, root_path]
    if source_id:
        cmd.append(source_id)

    await record_run_started(source_id, task_id)
    logger.info("[Task %s] Launching isolated indexing subprocess (#1180)", task_id)
    proc = await _spawn_worker(cmd, task_id, source_id)

    kill_reasons: list[str] = []
    returncode = await _wait_for_exit(proc, task_id, source_id, kill_reasons)
    if returncode != 0:
        await _handle_subprocess_crash(
            task_id,
            returncode,
            mark_task_failed_fn,
            save_task_fn,
            source_id=source_id,
            kill_reason=kill_reasons[0] if kill_reasons else "",
        )
    else:
        logger.info("[Task %s] Subprocess completed successfully (rc=0)", task_id)
        await _record_terminal_if_done(task_id, source_id)
