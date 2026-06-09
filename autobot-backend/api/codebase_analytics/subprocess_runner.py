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

logger = get_logger(__name__)


async def _handle_subprocess_crash(
    task_id: str,
    returncode: int,
    mark_task_failed_fn,
    save_task_fn,
) -> None:
    """Mark indexing task failed in Redis after subprocess crash (#1180).

    Only updates state if the subprocess did not already write a terminal
    status (completed/failed/cancelled) before crashing.

    Parameters
    ----------
    mark_task_failed_fn:
        Callable ``(task_id, error)`` bound to module-level indexing_tasks.
    save_task_fn:
        Async callable ``(task_id)`` that persists task state to Redis.
    """
    logger.error("[Task %s] Indexing subprocess crashed (exit code %d)", task_id, returncode)
    task_data = await _load_task_from_redis(task_id) or {}
    if task_data.get("status") not in ("completed", "failed", "cancelled"):
        mark_task_failed_fn(
            task_id,
            RuntimeError(f"Indexing subprocess crashed (exit code {returncode})"),
        )
        await save_task_fn(task_id)


async def _wait_with_watchdog(
    proc: asyncio.subprocess.Process,
    task_id: str,
) -> int:
    """Wait for subprocess with progress watchdog (#1341).

    Periodically checks if the subprocess is still making progress by reading
    the task state from Redis.  If no progress update is observed for
    ``_SUBPROCESS_PROGRESS_TIMEOUT`` seconds, the subprocess is killed.
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
            status = task_data.get("status")
            if status in ("completed", "failed", "cancelled"):
                return await proc.wait()

            progress = task_data.get("progress", {})
            progress_hash = (
                progress.get("current"),
                progress.get("total"),
                progress.get("operation"),
            )
            now = asyncio.get_running_loop().time()

            if progress_hash != last_progress_hash:
                last_progress_hash = progress_hash
                last_progress_time = now
            elif now - last_progress_time > _SUBPROCESS_PROGRESS_TIMEOUT:
                logger.error(
                    "[Task %s] Subprocess stale for %d seconds, " "killing (no progress update)",
                    task_id,
                    int(now - last_progress_time),
                )
                proc.kill()
                await proc.wait()
                return -9


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
        indexing_tasks[task_id] = create_initial_state_fn()
        await save_task_fn(task_id)

    cmd = [sys.executable, str(worker_script), task_id, root_path]
    if source_id:
        cmd.append(source_id)

    logger.info("[Task %s] Launching isolated indexing subprocess (#1180)", task_id)
    proc = await asyncio.create_subprocess_exec(*cmd)

    try:
        returncode = await asyncio.wait_for(
            _wait_with_watchdog(proc, task_id),
            timeout=_SUBPROCESS_HARD_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.error(
            "[Task %s] Subprocess exceeded hard timeout of %d seconds",
            task_id,
            _SUBPROCESS_HARD_TIMEOUT,
        )
        proc.kill()
        await proc.wait()
        returncode = -9

    if returncode != 0:
        await _handle_subprocess_crash(task_id, returncode, mark_task_failed_fn, save_task_fn)
    else:
        logger.info("[Task %s] Subprocess completed successfully (rc=0)", task_id)
