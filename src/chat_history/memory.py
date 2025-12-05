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
"""

import asyncio
import gc
import logging
import os
from typing import Any, Dict

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
            self.history = self.history[-self.max_messages:]

            # Force garbage collection to free memory immediately
            collected_objects = gc.collect()

            logger.info(
                f"CHAT CLEANUP: Trimmed messages from {old_count} to {len(self.history)} "
                f"(limit: {self.max_messages}), collected {collected_objects} objects"
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
                f"{message_count}/{self.max_messages} messages "
                f"({(message_count / self.max_messages) * 100:.1f}%)"
            )

        # Cleanup if needed
        self._cleanup_messages_if_needed()

    async def _cleanup_old_session_files(self):
        """Clean up old session files."""
        try:
            chats_directory = self._get_chats_directory()
            dir_exists = await asyncio.to_thread(os.path.exists, chats_directory)
            if not dir_exists:
                return

            # Get all chat files sorted by modification time
            chat_files = []
            filenames = await asyncio.to_thread(os.listdir, chats_directory)
            for filename in filenames:
                if filename.startswith("chat_") and filename.endswith(".json"):
                    file_path = os.path.join(chats_directory, filename)
                    mtime = await asyncio.to_thread(os.path.getmtime, file_path)
                    chat_files.append((file_path, mtime, filename))

            # Sort by modification time (newest first)
            chat_files.sort(key=lambda x: x[1], reverse=True)

            # Remove old files if exceeding limit
            if len(chat_files) > self.max_session_files:
                files_to_remove = chat_files[self.max_session_files:]
                for file_path, _, filename in files_to_remove:
                    try:
                        await asyncio.to_thread(os.remove, file_path)
                        logger.info(f"CLEANUP: Removed old session file: {filename}")
                    except Exception as e:
                        logger.error(f"Failed to remove session file {filename}: {e}")

                logger.info(
                    f"SESSION CLEANUP: Removed {len(files_to_remove)} old session files, "
                    f"kept {self.max_session_files} most recent"
                )

        except Exception as e:
            logger.error(f"Error cleaning up session files: {e}")

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
            f"Chat history cleared: removed {old_count} messages, "
            f"collected {collected_objects} objects"
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
