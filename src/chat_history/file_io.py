# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Chat History File I/O Mixin - File operations and persistence.

Provides file-based operations for chat history:
- Atomic file writes to prevent corruption
- Session file export in multiple formats
- Legacy history save operations
"""

import asyncio
import fcntl
import json
import logging
import os
import tempfile
from typing import Optional

import aiofiles

logger = logging.getLogger(__name__)


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

    async def _atomic_write(
        self, file_path: str, content: str, timeout_seconds: float = 30.0
    ) -> None:
        """
        Atomic file write with exclusive locking to prevent data corruption.

        Uses fcntl.flock() with non-blocking mode and retry logic to prevent
        indefinite blocking during I/O contention (e.g., during heavy indexing).

        Issue #718: Added timeout parameter and non-blocking lock acquisition
        to prevent chat save timeouts during heavy system load.

        Args:
            file_path: Target file path
            content: Content to write
            timeout_seconds: Maximum time to wait for lock (default 30s)

        Raises:
            TimeoutError: If lock cannot be acquired within timeout
            Exception: If write fails (temp file is cleaned up automatically)
        """
        import time

        dir_path = os.path.dirname(file_path)

        # Create temporary file in same directory (required for atomic rename)
        fd, temp_path = await asyncio.to_thread(
            tempfile.mkstemp, dir=dir_path, prefix=".tmp_chat_", suffix=".json"
        )

        try:
            # Issue #718: Use non-blocking lock with retry to prevent indefinite blocking
            start_time = time.monotonic()
            lock_acquired = False
            retry_delay = 0.1  # Start with 100ms delay

            while (time.monotonic() - start_time) < timeout_seconds:
                try:
                    # Try non-blocking lock
                    await asyncio.to_thread(
                        fcntl.flock, fd, fcntl.LOCK_EX | fcntl.LOCK_NB
                    )
                    lock_acquired = True
                    break
                except BlockingIOError:
                    # Lock is held by another process, wait and retry
                    await asyncio.sleep(retry_delay)
                    # Exponential backoff with cap at 1 second
                    retry_delay = min(retry_delay * 1.5, 1.0)

            if not lock_acquired:
                elapsed = time.monotonic() - start_time
                raise TimeoutError(
                    f"Could not acquire file lock for {file_path} "
                    f"after {elapsed:.1f}s (timeout: {timeout_seconds}s)"
                )

            # Write content to temporary file using aiofiles for async I/O
            os.close(fd)  # Close fd so aiofiles can open it
            async with aiofiles.open(temp_path, "w", encoding="utf-8") as f:
                await f.write(content)

            # Atomic rename (cross-platform atomic operation)
            await asyncio.to_thread(os.replace, temp_path, file_path)

            logger.debug("Atomic write completed: %s", file_path)

        except TimeoutError:
            # Re-raise timeout errors without logging as error (expected under load)
            logger.warning(
                "Atomic write lock timeout for %s - system may be under heavy I/O load",
                file_path
            )
            raise

        except Exception as e:
            logger.error("Atomic write failed for %s: %s", file_path, e)
            raise e

        finally:
            # Issue #718: Always cleanup temporary file
            try:
                temp_exists = await asyncio.to_thread(os.path.exists, temp_path)
                if temp_exists:
                    await asyncio.to_thread(os.unlink, temp_path)
            except Exception as cleanup_error:
                logger.warning(
                    f"Failed to cleanup temp file {temp_path}: {cleanup_error}"
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
                # Issue #361 - avoid blocking
                await asyncio.to_thread(
                    self.redis_client.set, "autobot:chat_history", json.dumps(self.history)
                )
                await asyncio.to_thread(
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
