# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Chat History Memory Mixin - Memory management and cleanup operations.

Provides memory optimization for chat history:
- Message cleanup when exceeding limits
- Periodic memory usage monitoring
- Session file cleanup
- Garbage collection management
- Memory statistics

Issue #718: Uses dedicated thread pool for file I/O to prevent blocking
when the main asyncio thread pool is saturated by indexing operations.
"""

import gc
import logging
import os
from typing import Any, Dict

from src.chat_history.file_io import run_in_chat_io_executor

logger = logging.getLogger(__name__)


class MemoryMixin:
    """
    Mixin providing memory management operations for chat history.

    Requires base class to have:
    - self.history: list
    - self.max_messages: int
    - self.cleanup_threshold: int
    - self.max_session_files: int
    - self.memory_check_counter: int
    - self.memory_check_interval: int
    - self._counter_lock: threading.Lock
    - self._get_chats_directory(): method
    """

    def _cleanup_messages_if_needed(self):
        """Clean up messages to prevent memory leaks."""
        if len(self.history) > self.cleanup_threshold:
            # Keep most recent messages within the limit
            old_count = len(self.history)
            self.history = self.history[-self.max_messages :]

            # Force garbage collection to free memory immediately
            collected_objects = gc.collect()

            logger.info(
                "CHAT CLEANUP: Trimmed messages from %d to %d "
                "(limit: %d), collected %d objects",
                old_count,
                len(self.history),
                self.max_messages,
                collected_objects,
            )

    def _periodic_memory_check(self):
        """Periodic memory usage monitoring (thread-safe)."""
        with self._counter_lock:
            self.memory_check_counter += 1
            should_check = self.memory_check_counter >= self.memory_check_interval
            if should_check:
                self.memory_check_counter = 0

        if not should_check:
            return

        # Check memory usage
        message_count = len(self.history)
        if message_count > self.max_messages * 0.8:  # 80% threshold warning
            logger.warning(
                "MEMORY WARNING: Chat history approaching limit - "
                "%d/%d messages (%.1f%%)",
                message_count,
                self.max_messages,
                (message_count / self.max_messages) * 100,
            )

        # Cleanup if needed
        self._cleanup_messages_if_needed()

    async def _cleanup_old_session_files(self):
        """Clean up old session files."""
        try:
            chats_directory = self._get_chats_directory()
            # Issue #718: Use dedicated executor to avoid blocking on saturated pool
            dir_exists = await run_in_chat_io_executor(os.path.exists, chats_directory)
            if not dir_exists:
                return

            # Get all chat files sorted by modification time
            chat_files = []
            filenames = await run_in_chat_io_executor(os.listdir, chats_directory)
            for filename in filenames:
                if filename.startswith("chat_") and filename.endswith(".json"):
                    file_path = os.path.join(chats_directory, filename)
                    mtime = await run_in_chat_io_executor(os.path.getmtime, file_path)
                    chat_files.append((file_path, mtime, filename))

            # Sort by modification time (newest first)
            chat_files.sort(key=lambda x: x[1], reverse=True)

            # Remove old files if exceeding limit
            if len(chat_files) > self.max_session_files:
                files_to_remove = chat_files[self.max_session_files :]
                for file_path, _, filename in files_to_remove:
                    try:
                        await run_in_chat_io_executor(os.remove, file_path)
                        logger.info("CLEANUP: Removed old session file: %s", filename)
                    except Exception as e:
                        logger.error(
                            "Failed to remove session file %s: %s", filename, e
                        )

                logger.info(
                    "SESSION CLEANUP: Removed %d old session files, "
                    "kept %d most recent",
                    len(files_to_remove),
                    self.max_session_files,
                )

        except Exception as e:
            logger.error("Error cleaning up session files: %s", e)

    async def clear_history(self):
        """
        Clear the entire chat history and save to file.

        Forces garbage collection after clear.
        """
        old_count = len(self.history)
        self.history = []

        # Force garbage collection to free memory
        collected_objects = gc.collect()

        await self._save_history()
        logger.info(
            "Chat history cleared: removed %d messages, collected %d objects",
            old_count,
            collected_objects,
        )

    def get_memory_stats(self) -> Dict[str, Any]:
        """Get current memory usage statistics."""
        return {
            "current_messages": len(self.history),
            "max_messages": self.max_messages,
            "cleanup_threshold": self.cleanup_threshold,
            "memory_usage_percent": (len(self.history) / self.max_messages) * 100,
            "memory_check_counter": self.memory_check_counter,
            "memory_check_interval": self.memory_check_interval,
            "needs_cleanup": len(self.history) > self.cleanup_threshold,
        }

    def force_cleanup(self) -> Dict[str, Any]:
        """Force memory cleanup and return statistics."""
        old_count = len(self.history)
        self._cleanup_messages_if_needed()
        collected_objects = gc.collect()

        return {
            "messages_before": old_count,
            "messages_after": len(self.history),
            "messages_removed": old_count - len(self.history),
            "objects_collected": collected_objects,
            "cleanup_performed": old_count > len(self.history),
        }
