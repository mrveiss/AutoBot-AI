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

    async def _atomic_write(self, file_path: str, content: str) -> None:
        """
        Atomic file write with exclusive locking to prevent data corruption.

        Uses fcntl.flock() for process-level locking and atomic rename to ensure
        that concurrent writes don't corrupt the file.

        Args:
            file_path: Target file path
            content: Content to write

        Raises:
            Exception: If write fails (temp file is cleaned up automatically)
        """
        dir_path = os.path.dirname(file_path)

        # Create temporary file in same directory (required for atomic rename)
        fd, temp_path = await asyncio.to_thread(
            tempfile.mkstemp, dir=dir_path, prefix=".tmp_chat_", suffix=".json"
        )

        try:
            # Acquire exclusive lock on the file descriptor
            await asyncio.to_thread(fcntl.flock, fd, fcntl.LOCK_EX)

            # Write content to temporary file using aiofiles for async I/O
            os.close(fd)  # Close fd so aiofiles can open it
            async with aiofiles.open(temp_path, "w", encoding="utf-8") as f:
                await f.write(content)

            # Atomic rename (cross-platform atomic operation)
            await asyncio.to_thread(os.replace, temp_path, file_path)

            logger.debug(f"Atomic write completed: {file_path}")

        except Exception as e:
            # Cleanup temporary file on failure
            try:
                temp_exists = await asyncio.to_thread(os.path.exists, temp_path)
                if temp_exists:
                    await asyncio.to_thread(os.unlink, temp_path)
            except Exception as cleanup_error:
                logger.warning(
                    f"Failed to cleanup temp file {temp_path}: {cleanup_error}"
                )

            logger.error(f"Atomic write failed for {file_path}: {e}")
            raise e

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
            logger.error(f"Failed to write chat history file {self.history_file}: {e}")
        except Exception as e:
            logger.error(f"Error saving chat history to {self.history_file}: {str(e)}")

        # Also save to Redis if enabled for fast access
        if self.use_redis and self.redis_client:
            try:
                self.redis_client.set("autobot:chat_history", json.dumps(self.history))
                self.redis_client.expire("autobot:chat_history", 86400)  # 1 day TTL
            except Exception as e:
                logger.error(f"Error saving chat history to Redis: {str(e)}")

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
                logger.error(f"Unsupported export format: {format}")
                return None

        except Exception as e:
            logger.error(f"Error exporting session {session_id}: {e}")
            return None
