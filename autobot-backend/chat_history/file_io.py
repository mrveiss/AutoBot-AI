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
import fcntl
import functools
import json
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import AsyncIterator, Awaitable, Callable

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
    fd = await run_in_chat_io_executor(os.open, lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            async with asyncio.timeout(CHAT_LEASE_WAIT_S):
                while not _try_flock(fd):
                    await asyncio.sleep(CHAT_LEASE_POLL_S)
        except TimeoutError:
            raise SessionLeaseLost(
                "file lock on %s was not free within %.1fs; nothing written" % (name, CHAT_LEASE_WAIT_S)
            ) from None
        yield
    finally:
        os.close(fd)  # closing the descriptor releases the flock


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
        """
        Atomic file write with exclusive locking to prevent data corruption.

        Issue #718: Uses dedicated thread pool for file I/O operations to
        prevent blocking when the main asyncio pool is saturated by indexing.
        Temp files are created in the same directory as the target (required
        for atomic os.replace to work on the same filesystem).

        Args:
            file_path: Target file path
            content: Content to write
            before_replace: Awaited just before the rename; if it raises, nothing is replaced

        Raises:
            Exception: If write fails (temp file is cleaned up automatically)
        """
        dir_path = os.path.dirname(file_path)

        # Create temporary file in same directory (required for atomic rename)
        # Issue #718: Use dedicated executor to avoid blocking on saturated pool
        fd, temp_path = await self._run_in_io_executor(tempfile.mkstemp, ".json", ".tmp_chat_", dir_path)

        try:
            # Acquire exclusive lock - use dedicated executor
            await self._run_in_io_executor(fcntl.flock, fd, fcntl.LOCK_EX)

            # Write content to temporary file using aiofiles for async I/O
            os.close(fd)  # Close fd so aiofiles can open it
            async with aiofiles.open(temp_path, "w", encoding="utf-8") as f:
                await f.write(content)

            # #20862: the caller's last check (lease, on-disk generation) and the rename are one step
            # against every other writer of this file: both run under its sidecar flock.
            async with session_file_lock(file_path):
                if before_replace is not None:
                    await before_replace()
                await self._run_in_io_executor(os.replace, temp_path, file_path)

            logger.debug("Atomic write completed: %s", file_path)

        except Exception as e:
            logger.error("Atomic write failed for %s: %s", file_path, e)
            raise e

        finally:
            # Always cleanup temporary file if it exists
            try:
                if await self._run_in_io_executor(os.path.exists, temp_path):
                    await self._run_in_io_executor(os.unlink, temp_path)
            except Exception as cleanup_error:
                logger.warning("Failed to cleanup temp file %s: %s", temp_path, cleanup_error)

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
