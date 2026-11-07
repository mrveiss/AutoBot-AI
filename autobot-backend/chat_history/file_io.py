# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Chat History File I/O Mixin - File operations and persistence.

Provides file-based operations for chat history:
- Atomic file writes to prevent corruption
- Session file export in multiple formats
- Legacy history save operations

Issue #718: Uses dedicated thread pool for file I/O to prevent blocking
when the main asyncio thread pool is saturated by indexing operations.
"""

import asyncio
import contextlib
import fcntl
import functools
import json
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Awaitable, Callable

import aiofiles

from autobot_shared.logging_manager import get_logger
from autobot_shared.security.path_validator import validate_relative_path
from chat_history.session_lease import CHAT_LEASE_POLL_S, CHAT_LEASE_WAIT_S, SessionLeaseLost
from constants.ttl_constants import TTL_24_HOURS

logger = get_logger(__name__)

# Issue #718: Dedicated thread pool for chat file I/O operations
# This prevents chat saves from being blocked when the main asyncio thread pool
# is saturated by heavy operations like ChromaDB indexing
_CHAT_IO_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="chat_io_")


async def run_in_chat_io_executor(func, *args, **kwargs):
    """Run a function in the dedicated chat I/O thread pool.

    Issue #718: Module-level function for use across all chat history mixins.
    Uses dedicated thread pool to prevent blocking when the main asyncio
    thread pool is saturated by indexing operations.

    Issue #2958: loop.run_in_executor() only accepts positional arguments.
    When kwargs are provided, functools.partial is used to bind them before
    passing the callable to the executor.

    Args:
        func: Function to run
        *args: Positional arguments to pass to the function
        **kwargs: Keyword arguments to pass to the function

    Returns:
        Result of the function call
    """
    loop = asyncio.get_running_loop()
    if kwargs:
        func = functools.partial(func, **kwargs)
    return await loop.run_in_executor(_CHAT_IO_EXECUTOR, func, *args)


def existing_chat_path(name: str, directory: str) -> str | None:
    """The validated path of chat file *name* under *directory* if it exists, else None (#20030).

    Blocking (``realpath`` and ``stat``): run it through :func:`run_in_chat_io_executor`.
    """
    path = str(validate_relative_path(name, directory))
    return path if os.path.exists(path) else None


SESSION_FILE_LOCK_SUFFIX = ".lock"


@asynccontextmanager
async def session_file_lock(file_path: str) -> AsyncIterator[None]:
    """Exclusive flock on the session file's sidecar lock, held across check-then-replace (#20862).

    The Redis lease can be lost between a generation check and the rename; this lock cannot be
    taken by two processes at once, so "read the on-disk generation, compare, replace" is one step
    against every other writer of the file. The sidecar sits beside the file (validated against its
    directory) and is polled non-blocking so a waiter never parks one of the chat I/O threads the
    holder needs. A wait longer than the lease bound raises SessionLeaseLost: nothing is written.
    """
    directory, name = os.path.split(file_path)
    lock_path = str(validate_relative_path(name + SESSION_FILE_LOCK_SUFFIX, directory))
    try:
        async with asyncio.timeout(CHAT_LEASE_WAIT_S):
            fd = await _lock_current_inode(lock_path)
    except TimeoutError:
        raise SessionLeaseLost(
            "file lock on %s was not free within %.1fs; nothing written" % (name, CHAT_LEASE_WAIT_S)
        ) from None
    try:
        yield
    finally:
        os.close(fd)  # closing the descriptor releases the flock


async def _lock_current_inode(lock_path: str) -> int:
    """Open and flock the sidecar, retrying until the locked inode is the one now at *lock_path*.

    A delete unlinks the sidecar (while holding its flock). A waiter that locked the unlinked inode
    would share nothing with a writer that creates a fresh sidecar, so after the flock succeeds the
    descriptor's inode is compared with the path's; a mismatch or a missing path closes and retries.
    """
    while True:
        fd = await _open_sidecar(lock_path)
        try:
            while not _try_flock(fd):
                await asyncio.sleep(CHAT_LEASE_POLL_S)
            if _is_current_inode(fd, lock_path):
                return fd
        except BaseException:
            os.close(fd)
            raise
        os.close(fd)


async def _open_sidecar(lock_path: str) -> int:
    """Open the sidecar in the chat I/O executor without leaking the descriptor on timeout or cancel.

    The open runs to completion in its thread even when the awaiting task is cancelled, so it is
    shielded and a done-callback closes the descriptor nobody is left to receive.
    """
    opening = asyncio.ensure_future(run_in_chat_io_executor(os.open, lock_path, os.O_CREAT | os.O_RDWR, 0o600))
    try:
        return await asyncio.shield(opening)
    except BaseException:
        opening.add_done_callback(_close_orphaned_fd)
        raise


def _close_orphaned_fd(opened: "asyncio.Future[int]") -> None:
    """Close the descriptor of an open whose caller gave up."""
    if not opened.cancelled() and opened.exception() is None:
        os.close(opened.result())


def _is_current_inode(fd: int, lock_path: str) -> bool:
    """True when descriptor *fd* still refers to the file at *lock_path*."""
    try:
        return os.fstat(fd).st_ino == os.stat(lock_path).st_ino
    except FileNotFoundError:
        return False


def is_session_lock_file(path) -> bool:
    """True for a session sidecar lock, which listings, size walks and cleanups must leave alone."""
    return str(path).endswith(SESSION_FILE_LOCK_SUFFIX)


def remove_session_lock(name: str, directory: str) -> None:
    """Remove the sidecar lock of chat file *name* (the session is deleted, and the lease is held)."""
    try:
        os.unlink(str(validate_relative_path(name + SESSION_FILE_LOCK_SUFFIX, directory)))
    except FileNotFoundError:
        pass


def _try_flock(fd: int) -> bool:
    """Take the exclusive flock without blocking; False when another descriptor holds it."""
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return False
    return True


async def atomic_write(
    file_path: str,
    content: str,
    before_replace: Callable[[], Awaitable[None]] | None = None,
    *,
    run: Callable[..., Awaitable[Any]] = run_in_chat_io_executor,
) -> None:
    """Write *content* to *file_path*: the one write path for a session file (#20862).

    The content goes to a temp file beside the target (same filesystem, so ``os.replace`` is atomic),
    then, under the file's sidecar lock, *before_replace* runs (the caller's last check; if it raises,
    nothing is written) and the temp file is renamed over the target. A reader sees the old file or
    the new one, never a partial one. Issue #718: blocking calls go through *run*, the chat I/O executor.

    Fallback (#665): when the filesystem refuses the temp file or the rename (an ``OSError`` on the
    atomic path only), the content is written in place, in the same locked step and after the same
    *before_replace* check, so it is fenced and cannot resurrect a deleted file. Lock, lease and
    check failures never fall back; a failed in-place write raises.
    """
    temp_path = await _stage_temp(file_path, content, run)
    try:
        async with session_file_lock(file_path):
            if before_replace is not None:
                await before_replace()
            if temp_path is None or not await _replace(temp_path, file_path, run):
                await _write_in_place(file_path, content)
        logger.debug("Atomic write completed: %s", file_path)
    except Exception as e:
        logger.error("Session write failed for %s: %s", file_path, e)
        raise
    finally:
        if temp_path is not None:
            await _discard_temp(temp_path, run)


async def _stage_temp(file_path: str, content: str, run: Callable[..., Awaitable[Any]]) -> str | None:
    """Write *content* to a temp file beside *file_path*; None when the filesystem refuses (OSError)."""
    temp_path = None
    try:
        fd, temp_path = await run(tempfile.mkstemp, ".json", ".tmp_chat_", os.path.dirname(file_path))
        try:
            await run(fcntl.flock, fd, fcntl.LOCK_EX)
        finally:
            os.close(fd)  # closed so aiofiles can open the path
        async with aiofiles.open(temp_path, "w", encoding="utf-8") as f:
            await f.write(content)
    except OSError as e:
        logger.warning("Atomic write of %s unavailable, will write in place: %s", file_path, e)
        if temp_path is not None:
            await _discard_temp(temp_path, run)
        return None
    return temp_path


async def _replace(temp_path: str, file_path: str, run: Callable[..., Awaitable[Any]]) -> bool:
    """Rename *temp_path* over *file_path*; False when the filesystem refuses (OSError)."""
    try:
        await run(os.replace, temp_path, file_path)
    except OSError as e:
        logger.warning("Atomic replace of %s failed, will write in place: %s", file_path, e)
        return False
    return True


async def _write_in_place(file_path: str, content: str) -> None:
    """The fallback write; only called inside the session file lock, after the caller's check.

    A write that fails on a file this call created removes it, so no partial file is left behind.
    """
    existed = os.path.exists(file_path)
    try:
        async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
            await f.write(content)
    except BaseException:
        if not existed:
            with contextlib.suppress(OSError):
                os.unlink(file_path)
        raise


async def _discard_temp(temp_path: str, run: Callable[..., Awaitable[Any]]) -> None:
    """Remove the temp file if the replace did not consume it."""
    try:
        if await run(os.path.exists, temp_path):
            await run(os.unlink, temp_path)
    except Exception as cleanup_error:
        logger.warning("Failed to cleanup temp file %s: %s", temp_path, cleanup_error)


class FileIOMixin:
    """
    Mixin providing file I/O operations for chat history.

    Requires base class to have:
    - self.history: list
    - self.history_file: str
    - self.use_redis: bool
    - self.redis_client: Redis client or None
    - self._periodic_memory_check(): method
    """

    async def _run_in_io_executor(self, func, *args, **kwargs):
        """Run a function in the dedicated chat I/O thread pool.

        Issue #718: Uses dedicated thread pool to prevent blocking when the
        main asyncio thread pool is saturated by indexing operations.
        """
        return await run_in_chat_io_executor(func, *args, **kwargs)

    async def _atomic_write(
        self,
        file_path: str,
        content: str,
        before_replace: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        """Atomic file write under the session file lock: :func:`atomic_write` on this manager's executor seam.

        Issue #718: file I/O goes through ``_run_in_io_executor``. Raises if the write fails (the
        temp file is cleaned up); if *before_replace* raises, nothing is replaced.
        """
        await atomic_write(file_path, content, before_replace, run=self._run_in_io_executor)

    async def _save_history(self):
        """
        Save current chat history to the JSON file and optionally to Redis.

        Includes memory cleanup before save for performance.
        """
        # Check and cleanup memory before saving
        self._periodic_memory_check()

        # Save to file for persistence
        try:
            async with aiofiles.open(self.history_file, "w", encoding="utf-8") as f:
                await f.write(json.dumps(self.history, indent=2, ensure_ascii=False))
        except OSError as e:
            logger.error("Failed to write chat history file %s: %s", self.history_file, e)
        except Exception as e:
            logger.error("Error saving chat history to %s: %s", self.history_file, str(e))

        # Also save to Redis if enabled for fast access
        if self.use_redis and self.redis_client:
            try:
                # Issue #718: Use dedicated executor to avoid blocking on saturated pool
                await self._run_in_io_executor(
                    self.redis_client.set,
                    "autobot:chat_history",
                    json.dumps(self.history),
                )
                await self._run_in_io_executor(
                    self.redis_client.expire, "autobot:chat_history", TTL_24_HOURS
                )  # 1 day TTL
            except Exception as e:
                logger.error("Error saving chat history to Redis: %s", str(e))

    async def export_session(self, session_id: str, format: str = "json") -> str | None:
        """
        Export a session in the specified format.

        Args:
            session_id: The session identifier
            format: Export format ('json', 'txt', 'md')

        Returns:
            Exported data as string, or None on error
        """
        try:
            messages = await self.load_session(session_id)

            if format == "json":
                return json.dumps(messages, indent=2, ensure_ascii=False)
            elif format == "txt":
                lines = []
                for msg in messages:
                    timestamp = msg.get("timestamp", "")
                    sender = msg.get("sender", "unknown")
                    text = msg.get("text", "")
                    lines.append(f"[{timestamp}] {sender}: {text}")
                return "\n".join(lines)
            elif format == "md":
                lines = [f"# Chat Session: {session_id}\n"]
                for msg in messages:
                    timestamp = msg.get("timestamp", "")
                    sender = msg.get("sender", "unknown")
                    text = msg.get("text", "")
                    lines.append(f"**{sender}** ({timestamp}):\n{text}\n")
                return "\n".join(lines)
            else:
                logger.error("Unsupported export format: %s", format)
                return None

        except Exception as e:
            logger.error("Error exporting session %s: %s", session_id, e)
            return None
