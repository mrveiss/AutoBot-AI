# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Process Adapter Service (#1406, #1751)

Spawns background subprocesses, tracks their lifecycle, and enforces
per-agent concurrency limits. Queued processes run automatically when
a concurrency slot opens.

Boundary with long_running_operations (#1751):
    ProcessAdapterService — OS-level subprocess management.
        Runs external programs via asyncio.create_subprocess_exec, captures
        stdout/stderr, enforces timeouts and per-agent concurrency, persists
        exit codes and logs to the process_runs SQL table.

    long_running_operations (utils/) — In-process async task framework.
        Manages Python coroutines (indexing, test suites, security scans)
        with checkpoint/resume, WebSocket progress streaming, and
        OperationStatus tracking via the OperationManager singleton.

    When to use which:
        - External CLI tool / shell command  →  ProcessAdapterService
        - Python async function / coroutine  →  long_running_operations
"""

import asyncio
import os
import signal as signal_module
import uuid
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import now_utc
from constants.threshold_constants import TimingConstants
from models.process_run import ProcessRun, ProcessRunStatus

logger = get_logger(__name__)

_LOG_DIR = "/var/log/autobot/processes"
_LOG_EXCERPT_MAX = 8 * 1024  # 8 KB
_DEFAULT_TIMEOUT = 300
_DEFAULT_MAX_CONCURRENCY = 1
_ABS_MAX_CONCURRENCY = 10
_VALID_SIGNALS = {"SIGTERM": signal_module.SIGTERM, "SIGKILL": signal_module.SIGKILL}


class ProcessAdapterService:
    """
    Spawns and manages background subprocesses for agents (#1406).

    Concurrency control: each agent has a configurable slot limit
    (default 1, max 10). Excess requests are queued and dispatched
    when a slot opens.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker,
        max_concurrency: int = _DEFAULT_MAX_CONCURRENCY,
    ) -> None:
        self._session_factory = session_factory
        self._max_concurrency = min(max_concurrency, _ABS_MAX_CONCURRENCY)
        self._running_counts: Dict[str, int] = {}
        self._queue: asyncio.Queue = asyncio.Queue()
        self._processes: Dict[str, asyncio.subprocess.Process] = {}
        self._dispatcher_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Launch the background queue dispatcher (#1406)."""
        if self._dispatcher_task is None or self._dispatcher_task.done():
            self._dispatcher_task = asyncio.create_task(self._dispatch_loop(), name="process-dispatcher")
            logger.info("ProcessAdapterService dispatcher started")

    async def stop(self) -> None:
        """Stop the dispatcher and cancel pending processes (#1406)."""
        if self._dispatcher_task:
            self._dispatcher_task.cancel()
            try:
                await self._dispatcher_task
            except asyncio.CancelledError:
                pass
        logger.info("ProcessAdapterService dispatcher stopped")

    async def spawn_process(
        self,
        agent_id: str,
        command: str,
        args: List[str] | None = None,
        timeout_seconds: int = _DEFAULT_TIMEOUT,
        task_id: str | None = None,
    ) -> str:
        """
        Create a ProcessRun row and schedule the subprocess (#1406).

        Returns the process_run UUID string.
        """
        run_id = await self._create_run_row(agent_id, command, args or [], timeout_seconds, task_id)
        await self._queue.put(run_id)
        logger.info("Process %s queued for agent %s", run_id, agent_id)
        return str(run_id)

    async def get_process_status(self, process_id: str) -> Dict[str, Any] | None:
        """Return current status dict for process_id, or None if not found (#1406)."""
        async with self._session_factory() as session:
            row = await session.get(ProcessRun, uuid.UUID(process_id))
        if row is None:
            return None
        return _run_to_dict(row)

    async def signal_process(self, process_id: str, sig: str) -> bool:
        """
        Send a POSIX signal to a running process (#1406).

        Returns True if the signal was delivered, False otherwise.
        """
        sig_val = _VALID_SIGNALS.get(sig.upper())
        if sig_val is None:
            raise ValueError(f"Unknown signal: {sig!r}. Allowed: {list(_VALID_SIGNALS)}")
        proc = self._processes.get(process_id)
        if proc is None or proc.returncode is not None:
            logger.warning("Signal %s ignored: process %s not running", sig, process_id)
            return False
        try:
            proc.send_signal(sig_val)
            logger.info("Signal %s sent to process %s", sig, process_id)
            return True
        except ProcessLookupError:
            logger.warning("Signal %s failed: process %s already exited", sig, process_id)
            return False

    async def get_agent_processes(
        self,
        agent_id: str,
        status_filter: str | None = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Return recent ProcessRun records for agent_id (#1406)."""
        async with self._session_factory() as session:
            rows = await _query_agent_runs(session, agent_id, status_filter, limit)
        return [_run_to_dict(r) for r in rows]

    # -- Internal helpers --------------------------------------------------

    async def _dispatch_loop(self) -> None:
        """Consume from the queue and launch processes when slots open (#1406)."""
        logger.debug("Dispatcher loop running")
        while True:
            try:
                run_id = await self._queue.get()
                await self._wait_for_slot_and_run(run_id)
            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("Dispatcher loop error (continuing)")

    async def _wait_for_slot_and_run(self, run_id: uuid.UUID) -> None:
        """Block until agent has a free concurrency slot, then launch (#1406)."""
        agent_id = await self._fetch_agent_id(run_id)
        if agent_id is None:
            return
        while self._running_counts.get(agent_id, 0) >= self._max_concurrency:
            await asyncio.sleep(TimingConstants.SHORT_DELAY)
        self._running_counts[agent_id] = self._running_counts.get(agent_id, 0) + 1
        asyncio.create_task(self._run_process(run_id, agent_id), name=f"proc-{run_id}")

    async def _fetch_agent_id(self, run_id: uuid.UUID) -> str | None:
        """Load agent_id for a run. Helper (#1406)."""
        async with self._session_factory() as session:
            row = await session.get(ProcessRun, run_id)
            return row.agent_id if row else None

    async def _run_process(self, run_id: uuid.UUID, agent_id: str) -> None:
        """Execute subprocess and persist outcome (#1406)."""
        try:
            command, args, timeout = await self._mark_running(run_id)
            proc = await _spawn_subprocess(command, args)
            self._processes[str(run_id)] = proc
            stdout, stderr, timed_out = await self._collect_output(proc, run_id, timeout)
            exit_code = proc.returncode if not timed_out else None
            sig_name = "SIGKILL" if timed_out else None
            status = (
                ProcessRunStatus.TIMED_OUT.value
                if timed_out
                else (ProcessRunStatus.COMPLETED.value if exit_code == 0 else ProcessRunStatus.FAILED.value)
            )
            excerpt, log_path = await _persist_log(run_id, stdout, stderr)
            await self._finalize_run(run_id, status, exit_code, sig_name, excerpt, log_path)
        except Exception:
            logger.exception("Unexpected error in process run %s", run_id)
            await self._mark_failed(run_id, "Internal process runner error")
        finally:
            self._processes.pop(str(run_id), None)
            self._running_counts[agent_id] = max(0, self._running_counts.get(agent_id, 1) - 1)
            logger.info("Process slot released for agent %s", agent_id)

    async def _mark_running(self, run_id: uuid.UUID) -> tuple[str, List[str], int]:
        """Transition row to RUNNING; return (command, args, timeout) (#1406)."""
        async with self._session_factory() as session:
            row = await session.get(ProcessRun, run_id)
            row.status = ProcessRunStatus.RUNNING.value
            row.started_at = now_utc()
            cmd, args, timeout = row.command, row.args or [], row.timeout_seconds
            await session.commit()
        logger.info("Process %s started", run_id)
        return cmd, args, timeout

    async def _collect_output(
        self,
        proc: asyncio.subprocess.Process,
        run_id: uuid.UUID,
        timeout: int,
    ) -> tuple[bytes, bytes, bool]:
        """Wait for subprocess with timeout. Return (stdout, stderr, timed_out) (#1406)."""
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=float(timeout))
            return stdout or b"", stderr or b"", False
        except asyncio.TimeoutError:
            logger.warning("Process %s timed out after %ss", run_id, timeout)
            try:
                proc.kill()
                await proc.communicate()
            except Exception:
                pass
            return b"", b"timeout exceeded", True

    async def _finalize_run(
        self,
        run_id: uuid.UUID,
        status: str,
        exit_code: int | None,
        sig_name: str | None,
        excerpt: str,
        log_path: str,
    ) -> None:
        """Persist final status, exit_code, logs to DB (#1406)."""
        async with self._session_factory() as session:
            row = await session.get(ProcessRun, run_id)
            if row:
                row.status = status
                row.exit_code = exit_code
                row.signal = sig_name
                row.log_excerpt = excerpt
                row.log_path = log_path
                row.completed_at = now_utc()
            await session.commit()
        logger.info("Process %s finalised: status=%s exit=%s", run_id, status, exit_code)

    async def _mark_failed(self, run_id: uuid.UUID, reason: str) -> None:
        """Set status=failed with a short reason in log_excerpt (#1406)."""
        async with self._session_factory() as session:
            row = await session.get(ProcessRun, run_id)
            if row:
                row.status = ProcessRunStatus.FAILED.value
                row.log_excerpt = reason[:_LOG_EXCERPT_MAX]
                row.completed_at = now_utc()
            await session.commit()

    async def _create_run_row(
        self,
        agent_id: str,
        command: str,
        args: List[str],
        timeout_seconds: int,
        task_id: str | None,
    ) -> uuid.UUID:
        """Insert a QUEUED ProcessRun row and return its UUID (#1406)."""
        run_id = uuid.uuid4()
        async with self._session_factory() as session:
            session.add(
                ProcessRun(
                    id=run_id,
                    agent_id=agent_id,
                    task_id=task_id,
                    command=command,
                    args=args,
                    status=ProcessRunStatus.QUEUED.value,
                    timeout_seconds=timeout_seconds,
                )
            )
            await session.commit()
        return run_id


# -- Module-level helpers --------------------------------------------------


async def _spawn_subprocess(command: str, args: List[str]) -> asyncio.subprocess.Process:
    """Launch the subprocess. Raises OSError on failure (#1406)."""
    return await asyncio.create_subprocess_exec(
        command,
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )


async def _persist_log(run_id: uuid.UUID, stdout: bytes, stderr: bytes) -> tuple[str, str]:
    """
    Write combined output to a log file; return (excerpt, log_path) (#1406).

    Excerpt is capped at _LOG_EXCERPT_MAX bytes. The full log is written
    to _LOG_DIR/<run_id>.log using UTF-8 encoding.
    """
    combined = stdout + stderr
    excerpt = combined[:_LOG_EXCERPT_MAX].decode("utf-8", errors="replace")
    os.makedirs(_LOG_DIR, exist_ok=True)
    log_path = os.path.join(_LOG_DIR, f"{run_id}.log")
    with open(log_path, "w", encoding="utf-8") as fh:
        fh.write(combined.decode("utf-8", errors="replace"))
    return excerpt, log_path


async def _query_agent_runs(
    session: AsyncSession,
    agent_id: str,
    status_filter: str | None,
    limit: int,
) -> List[ProcessRun]:
    """Query ProcessRun rows for agent_id with optional status filter (#1406)."""
    stmt = select(ProcessRun).where(ProcessRun.agent_id == agent_id).order_by(ProcessRun.created_at.desc()).limit(limit)
    if status_filter:
        stmt = stmt.where(ProcessRun.status == status_filter)
    result = await session.execute(stmt)
    return list(result.scalars().all())


def _run_to_dict(row: ProcessRun) -> Dict[str, Any]:
    """Serialise a ProcessRun ORM row to a plain dict (#1406)."""
    return {
        "id": str(row.id),
        "agent_id": row.agent_id,
        "task_id": row.task_id,
        "command": row.command,
        "args": row.args,
        "status": row.status,
        "exit_code": row.exit_code,
        "signal": row.signal,
        "log_excerpt": row.log_excerpt,
        "log_path": row.log_path,
        "timeout_seconds": row.timeout_seconds,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
