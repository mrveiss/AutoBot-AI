# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Memory Graph - Core Module

This module contains the core base class, constants, and initialization logic
for the modular autobot_memory_graph package.

Part of Issue #716 - Refactored from monolithic autobot_memory_graph.py
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Set

from autobot_shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)


# ============================================================================
# CONSTANTS
# ============================================================================

ENTITY_TYPES: Set[str] = {
    "CONVERSATION",
    "BUG",
    "FEATURE",
    "DECISION",
    "TASK",
    "USER",  # Issue #608
    "SECRET",  # Issue #608
    "TERMINAL_ACTIVITY",  # Issue #608
    "FILE_ACTIVITY",  # Issue #608
    "BROWSER_ACTIVITY",  # Issue #608
    "DESKTOP_ACTIVITY",  # Issue #608
    "SECRET_USAGE",  # Issue #608
}

RELATION_TYPES: Set[str] = {
    "contains",
    "depends_on",
    "implements",
    "references",
    "caused_by",
    "related_to",
    "leads_to",
    "blocks",
    "owns",  # Issue #608 - User owns Secret
    "has_secret",  # Issue #608 - User/Session has Secret
    "shared_with",  # Issue #608 - Secret shared with User
    "has_participant",  # Issue #608 - Session has User
    "performed_by",  # Issue #608 - Activity performed by User
    "used_secret",  # Issue #608 - Activity used Secret
}

VALID_ACTIVITY_TYPES: Set[str] = {
    "chat",
    "terminal",
    "file_browser",
    "browser",
    "novnc",
}

# Relation direction constants
OUTGOING_DIRECTIONS: Set[str] = {"outgoing", "both"}
INCOMING_DIRECTIONS: Set[str] = {"incoming", "both"}


# ============================================================================
# CONFIGURATION
# ============================================================================


class Config:
    """Configuration for AutoBotMemoryGraph."""

    def __init__(self):
        self.redis_host = "172.16.168.23"
        self.redis_port = 6379
        self.redis_db = 1  # knowledge database
        self.index_prefix = "autobot:entities"
        self.relations_prefix = "autobot:relations"
        self.embedding_model = "nomic-embed-text"
        self.embedding_dimensions = 768


config = Config()


# ============================================================================
# CORE BASE CLASS
# ============================================================================


class AutoBotMemoryGraphCore:
    """
    Core base class for AutoBotMemoryGraph.

    Provides initialization, configuration, and foundational methods
    that all mixin classes depend on.

    This class is not meant to be used directly. Instead, use the
    AutoBotMemoryGraph class which combines this core with all mixins.
    """

    def __init__(self):
        """Initialize the memory graph core."""
        self.redis_client: Optional[Any] = None
        self.chat_history_manager: Optional[Any] = None
        self.embedding_cache: Dict[str, List[float]] = {}
        self.embedding_model_name: str = config.embedding_model
        self.embedding_dimensions: int = config.embedding_dimensions
        self._initialized: bool = False
        self._lock: asyncio.Lock = asyncio.Lock()
        self.index_name: str = f"{config.index_prefix}:idx"

    async def initialize(self) -> None:
        """
        Initialize Redis connection and search indexes.

        This method is idempotent and thread-safe.
        """
        async with self._lock:
            if self._initialized:
                logger.debug("AutoBotMemoryGraph already initialized")
                return

            try:
                # Initialize Redis client
                self.redis_client = get_redis_client(
                    async_client=True, database="knowledge"
                )

                # Create search indexes if they don't exist
                await self._create_search_indexes()

                self._initialized = True
                logger.info("AutoBotMemoryGraph initialized successfully")

            except Exception as e:
                logger.error(f"Failed to initialize AutoBotMemoryGraph: {e}")
                raise

    async def close(self) -> None:
        """Close Redis connection and cleanup resources."""
        if self.redis_client:
            try:
                await self.redis_client.close()
                logger.info("AutoBotMemoryGraph closed successfully")
            except Exception as e:
                logger.error(f"Error closing AutoBotMemoryGraph: {e}")

        self._initialized = False
        self.embedding_cache.clear()

    async def _create_search_indexes(self) -> None:
        """
        Create Redis search indexes for entities if they don't exist.

        Issue #665: Helper for initialize()
        """
        try:
            # Check if index exists
            exists = await self._check_index_exists(self.index_name)
            if exists:
                logger.debug(f"Search index {self.index_name} already exists")
                return

            # Create index for entity search
            # Note: This is a simplified version. Full implementation
            # would include FT.CREATE with proper schema
            logger.info(f"Creating search index: {self.index_name}")

            # Index creation would go here
            # Actual implementation depends on RedisSearch version and schema

        except Exception as e:
            logger.warning(f"Error creating search indexes: {e}")
            # Don't fail initialization if index creation fails
            # Index may already exist or be created manually

    async def _check_index_exists(self, index_name: str) -> bool:
        """
        Check if a Redis search index exists.

        Issue #665: Helper for _create_search_indexes()

        Args:
            index_name: Name of the index to check

        Returns:
            True if index exists, False otherwise
        """
        try:
            if not self.redis_client:
                return False

            # Try to get index info
            # This is a simplified check
            info = await self.redis_client.execute_command("FT.INFO", index_name)
            return info is not None

        except Exception:
            # Index doesn't exist or error occurred
            return False


# ============================================================================
# PUBLIC EXPORTS
# ============================================================================

__all__ = [
    # Core class
    "AutoBotMemoryGraphCore",
    # Constants
    "ENTITY_TYPES",
    "RELATION_TYPES",
    "VALID_ACTIVITY_TYPES",
    "OUTGOING_DIRECTIONS",
    "INCOMING_DIRECTIONS",
    # Config
    "config",
]
