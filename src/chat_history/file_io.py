# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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
import json
import logging
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import aiofiles

logger = logging.getLogger(__name__)

# Issue #718: Dedicated thread pool for chat file I/O operations
# This prevents chat saves from being blocked when the main asyncio thread pool
# is saturated by heavy operations like ChromaDB indexing
_CHAT_IO_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="chat_io_")


async def run_in_chat_io_executor(func, *args):
    """Run a function in the dedicated chat I/O thread pool.

    Issue #718: Module-level function for use across all chat history mixins.
    Uses dedicated thread pool to prevent blocking when the main asyncio
    thread pool is saturated by indexing operations.

    Args:
        func: Function to run
        *args: Arguments to pass to the function

    Returns:
        Result of the function call
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_CHAT_IO_EXECUTOR, func, *args)


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

    async def _run_in_io_executor(self, func, *args):
        """Run a function in the dedicated chat I/O thread pool.

        Issue #718: Uses dedicated thread pool to prevent blocking when the
        main asyncio thread pool is saturated by indexing operations.
        """
        return await run_in_chat_io_executor(func, *args)

    async def _atomic_write(self, file_path: str, content: str) -> None:
        """
        Atomic file write with exclusive locking to prevent data corruption.

        Issue #718: Uses dedicated thread pool for file I/O operations to
        prevent blocking when the main asyncio pool is saturated by indexing.
        Temp files are created in the same directory as the target (required
        for atomic os.replace to work on the same filesystem).

        Args:
            file_path: Target file path
            content: Content to write

        Raises:
            Exception: If write fails (temp file is cleaned up automatically)
        """
        dir_path = os.path.dirname(file_path)

        # Create temporary file in same directory (required for atomic rename)
        # Issue #718: Use dedicated executor to avoid blocking on saturated pool
        fd, temp_path = await self._run_in_io_executor(
            tempfile.mkstemp, dir_path, ".tmp_chat_", ".json"
        )

        try:
            # Acquire exclusive lock - use dedicated executor
            await self._run_in_io_executor(fcntl.flock, fd, fcntl.LOCK_EX)

            # Write content to temporary file using aiofiles for async I/O
            os.close(fd)  # Close fd so aiofiles can open it
            async with aiofiles.open(temp_path, "w", encoding="utf-8") as f:
                await f.write(content)

            # Atomic rename (cross-platform atomic operation)
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
                logger.warning(
                    "Failed to cleanup temp file %s: %s", temp_path, cleanup_error
                )

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
                    self.redis_client.set, "autobot:chat_history", json.dumps(self.history)
                )
                await self._run_in_io_executor(
                    self.redis_client.expire, "autobot:chat_history", 86400
                )  # 1 day TTL
            except Exception as e:
                logger.error("Error saving chat history to Redis: %s", str(e))

    async def export_session(
        self, session_id: str, format: str = "json"
    ) -> Optional[str]:
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
