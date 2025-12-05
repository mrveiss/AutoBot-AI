# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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
    from src.chat_history import ChatHistoryManager

    manager = ChatHistoryManager()
    await manager.create_session()
    await manager.add_message("user", "Hello!")
"""

from typing import Optional

from src.chat_history.analysis import AnalysisMixin
from src.chat_history.base import ChatHistoryBase
from src.chat_history.cache import CacheMixin
from src.chat_history.deduplication import DeduplicationMixin
from src.chat_history.file_io import FileIOMixin
from src.chat_history.memory import MemoryMixin
from src.chat_history.messages import MessagesMixin
from src.chat_history.security import SecurityMixin
from src.chat_history.session import SessionMixin
from src.chat_history.session_listing import SessionListingMixin


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
            model_name="gpt-4"
        )

        # List all sessions
        sessions = await manager.list_sessions_fast()
    """

    def __init__(
        self,
        history_file: Optional[str] = None,
        use_redis: Optional[bool] = None,
        redis_host: Optional[str] = None,
        redis_port: Optional[int] = None,
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
