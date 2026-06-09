# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Chat History Package - Modular chat history management.

This package provides the refactored ChatHistoryManager composed from
focused mixins following the Single Responsibility Principle.

Architecture:
    ChatHistoryManager
    ├── ChatHistoryBase (core initialization, config, Redis)
    ├── SecurityMixin (encryption/decryption)
    ├── FileIOMixin (atomic writes, file operations)
    ├── AnalysisMixin (metadata extraction, topic detection)
    ├── MemoryMixin (cleanup, garbage collection)
    ├── CacheMixin (Redis caching)
    ├── DeduplicationMixin (streaming message dedup)
    ├── SessionMixin (session CRUD operations)
    ├── SessionListingMixin (session listing, orphan recovery)
    └── MessagesMixin (message operations)

Usage:
    from chat_history import ChatHistoryManager

    manager = ChatHistoryManager()
    await manager.create_session()
    await manager.add_message(sender="user", text="Hello!")
"""

import time
from typing import Any, Dict

import aiofiles

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

from chat_history.analysis import AnalysisMixin
from chat_history.base import ChatHistoryBase
from chat_history.cache import CacheMixin
from chat_history.deduplication import DeduplicationMixin
from chat_history.file_io import FileIOMixin
from chat_history.memory import MemoryMixin
from chat_history.messages import MessagesMixin
from chat_history.security import SecurityMixin
from chat_history.session import SessionMixin
from chat_history.session_listing import SessionListingMixin


class ChatHistoryManager(
    ChatHistoryBase,
    SecurityMixin,
    FileIOMixin,
    AnalysisMixin,
    MemoryMixin,
    CacheMixin,
    DeduplicationMixin,
    SessionMixin,
    SessionListingMixin,
    MessagesMixin,
):
    """
    Chat History Manager - Composed class for managing chat sessions and messages.

    This class combines focused mixins to provide complete chat history
    functionality while maintaining clean separation of concerns:

    - ChatHistoryBase: Core initialization, configuration, Redis setup
    - SecurityMixin: Encryption and decryption of chat data
    - FileIOMixin: Atomic file writes and session export
    - AnalysisMixin: Metadata extraction, topic detection, entity mentions
    - MemoryMixin: Memory cleanup, garbage collection, session file management
    - CacheMixin: Redis caching for session data
    - DeduplicationMixin: Streaming message consolidation (Issue #259)
    - SessionMixin: Session CRUD operations (create, load, save, delete, update)
    - SessionListingMixin: Session listing and orphaned file recovery
    - MessagesMixin: Message operations (add, get, update metadata, tool markers)

    Performance Features:
    - O(1) set lookups for keyword matching (Issue #326)
    - Redis cache-first strategy with write-through caching
    - Atomic file writes with fcntl locking
    - Streaming message deduplication
    - Model-aware context window limits

    Example:
        manager = ChatHistoryManager()

        # Create a new session
        session = await manager.create_session(title="My Chat")

        # Add messages
        await manager.add_message(
            sender="user",
            text="Hello!",
            session_id=session["id"]
        )

        # Get messages with model-aware limits
        messages = await manager.get_session_messages(
            session_id=session["id"],
            model_name="gpt-4"  # docstring example — use ModelConstants.DEFAULT_OPENAI_MODEL
        )

        # List all sessions
        sessions = await manager.list_sessions_fast()
    """

    def __init__(
        self,
        history_file: str | None = None,
        use_redis: bool | None = None,
        redis_host: str | None = None,
        redis_port: int | None = None,
    ):
        """
        Initialize the ChatHistoryManager with all mixins.

        Args:
            history_file: Path to the JSON file for persistent storage.
            use_redis: If True, attempts to use Redis for active memory storage.
            redis_host: Hostname for Redis server.
            redis_port: Port for Redis server.
        """
        # Initialize base class (handles all core setup)
        super().__init__(
            history_file=history_file,
            use_redis=use_redis,
            redis_host=redis_host,
            redis_port=redis_port,
        )

    async def update_session_metadata(self, session_id: str, metadata: dict) -> bool:
        """Merge provided metadata into the existing session metadata (#8993).

        Loads the session file, merges *metadata* into the existing
        ``metadata`` sub-dict, saves back to disk, and invalidates the
        Redis cache entry when Redis is available.

        Returns True if the update succeeded, False otherwise.
        """
        try:
            self._sanitize_session_id(session_id)
            chats_directory = self._get_chats_directory()
            chat_file = await self._resolve_session_file_path(session_id, chats_directory)
            if not chat_file:
                logger.warning("Session %s not found for metadata update", session_id)
                return False

            async with aiofiles.open(chat_file, "r", encoding="utf-8") as f:
                file_content = await f.read()
            chat_data = self._decrypt_data(file_content)

            existing_metadata = chat_data.get("metadata", {})
            existing_metadata.update(metadata)
            chat_data["metadata"] = existing_metadata
            chat_data["last_modified"] = time.strftime("%Y-%m-%d %H:%M:%S")

            await self._write_session_to_storage(chat_file, chat_data)
            await self._update_redis_session_cache(session_id, chat_data)

            logger.info("Session %s metadata updated successfully", session_id)
            return True

        except OSError as e:
            logger.error("Failed to read/write session file for %s: %s", session_id, e)
            return False
        except Exception as e:
            logger.error("Error updating session metadata %s: %s", session_id, e)
            return False

    async def get_statistics(self) -> Dict[str, Any]:
        """Aggregate basic counts for GET /chat/stats (#6490).

        Sums message counts per session via the SessionListing + Messages
        mixins. Cheap enough for an admin endpoint; not a hot path.
        """
        sessions = await self.list_sessions_fast()
        session_count = len(sessions)
        total_messages = 0
        for session in sessions:
            session_id = session.get("id") or session.get("session_id")
            if not session_id:
                continue
            try:
                total_messages += await self.get_session_message_count(session_id)
            except Exception:
                continue
        return {
            "session_count": session_count,
            "message_count": total_messages,
            "sessions": sessions[:10],
        }


# Convenience exports
__all__ = [
    "ChatHistoryManager",
    "ChatHistoryBase",
    "SecurityMixin",
    "FileIOMixin",
    "AnalysisMixin",
    "MemoryMixin",
    "CacheMixin",
    "DeduplicationMixin",
    "SessionMixin",
    "SessionListingMixin",
    "MessagesMixin",
]
