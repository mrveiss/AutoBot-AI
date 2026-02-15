# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Memory Graph - Core Module

This module contains the core AutoBotMemoryGraph class with initialization,
Redis connection management, and base configuration.

Part of the modular autobot_memory_graph package (Issue #716).
"""

import asyncio
import logging
from typing import Any, Dict, FrozenSet, Optional

import redis.asyncio as async_redis
from cachetools import LRUCache
from utils.error_boundaries import error_boundary, get_error_boundary_manager

from config import UnifiedConfigManager

logger = logging.getLogger(__name__)

# Issue #380: Module-level frozensets for relation direction checks
OUTGOING_DIRECTIONS: FrozenSet[str] = frozenset({"outgoing", "both"})
INCOMING_DIRECTIONS: FrozenSet[str] = frozenset({"incoming", "both"})

# Create singleton config instance
config = UnifiedConfigManager()


# Valid entity types
# Issue #608: Extended with user-centric session tracking types
ENTITY_TYPES = {
    # Core entity types
    "conversation",
    "bug_fix",
    "feature",
    "decision",
    "task",
    "user_preference",
    "context",
    "learning",
    "research",
    "implementation",
    # Issue #608: User-centric session tracking entity types
    "user",
    "chat_session",
    "terminal_activity",
    "file_activity",
    "browser_activity",
    "desktop_activity",
    "secret",
    "secret_usage",
}

# Valid relation types
# Issue #608: Extended with user-centric session tracking relations
RELATION_TYPES = {
    # Core relation types
    "relates_to",
    "depends_on",
    "implements",
    "fixes",
    "informs",
    "guides",
    "follows",
    "contains",
    "blocks",
    # Issue #608: User-session relationships
    "owns",
    "created_by",
    "has_participant",
    "has_session",
    # Issue #608: Activity relationships
    "has_activity",
    "has_message",
    "performed_by",
    # Issue #608: Secret relationships
    "has_secret",
    "uses_secret",
    "shared_with",
}

# Valid activity types (Issue #665)
VALID_ACTIVITY_TYPES = frozenset(
    {
        "terminal_activity",
        "file_activity",
        "browser_activity",
        "desktop_activity",
    }
)


class AutoBotMemoryGraphCore:
    """
    Core memory graph class with initialization and configuration.

    This class provides:
    - Redis connection management
    - Search index creation
    - Knowledge Base integration for embeddings
    - Configuration management

    Subclassed by the full AutoBotMemoryGraph to add entity, relation,
    and query operations.
    """

    def __init__(
        self,
        redis_host: Optional[str] = None,
        redis_port: Optional[int] = None,
        database: int = 0,
        chat_history_manager: Optional[Any] = None,
    ):
        """
        Initialize Memory Graph interface.

        Args:
            redis_host: Redis server hostname (default from config)
            redis_port: Redis server port (default from config)
            database: Redis database number (default: 0, required for RediSearch)
            chat_history_manager: Optional link to chat history manager
        """
        self.initialized = False
        self.initialization_lock = asyncio.Lock()

        # Error boundary manager for enhanced error tracking
        self.error_manager = get_error_boundary_manager()

        # Configuration
        self.redis_host = redis_host or config.get_host("redis")
        self.redis_port = redis_port or config.get_port("redis")
        self.redis_password = config.get("redis.password")
        self.redis_db = database

        # Connection clients
        self.redis_client: Optional[async_redis.Redis] = None

        # Chat history integration
        self.chat_history_manager = chat_history_manager

        # Embedding configuration (reuse from Knowledge Base V2)
        self.embedding_model_name = "nomic-embed-text"
        self.embedding_dimensions = 768

        # Search cache
        self.search_cache = LRUCache(maxsize=1000)
        self.embedding_cache: Dict[str, str] = {}

        # Knowledge Base integration (for embeddings)
        self.knowledge_base = None

        logger.info("AutoBotMemoryGraph instance created (not yet initialized)")

    @error_boundary(component="autobot_memory_graph", function="initialize")
    async def initialize(self) -> bool:
        """Async initialization method - must be called after construction."""
        if self.initialized:
            return True

        async with self.initialization_lock:
            if self.initialized:
                return True

            try:
                logger.info("Starting Memory Graph initialization...")

                # Step 1: Initialize Redis connection
                await self._init_redis_connection()

                # Step 2: Create search indexes
                await self._create_search_indexes()

                # Step 3: Initialize Knowledge Base for embeddings
                await self._init_knowledge_base()

                self.initialized = True
                logger.info("Memory Graph initialization completed successfully")
                return True

            except Exception as e:
                logger.error("Memory Graph initialization failed: %s", e)
                await self._cleanup_on_failure()
                return False

    async def _init_redis_connection(self) -> None:
        """
        Initialize Redis connection to DB 0.

        USES CANONICAL PATTERN: get_redis_client() from src/utils/redis_client.py
        This ensures Redis Stack JSON support is properly configured.

        NOTE: Memory uses DB 0 because RediSearch (FT.* commands) only works on DB 0.
        """
        try:
            from autobot_shared.redis_client import get_redis_client

            # CANONICAL: Use get_redis_client for proper Redis Stack support
            # Database 0 is required for RediSearch indexing (FT.* commands)
            self.redis_client = await get_redis_client(
                async_client=True,
                database="memory",
            )

            # Test connection
            await self.redis_client.ping()
            logger.info(
                "Memory Graph Redis client connected (database %s)", self.redis_db
            )

        except Exception as e:
            logger.error("Failed to initialize Redis connection: %s", e)
            raise

    def _get_entity_index_schema(self) -> list:
        """Issue #665: Extracted helper for RediSearch schema definition.

        Returns:
            List of schema arguments for FT.CREATE command
        """
        return [
            "$.type",
            "AS",
            "type",
            "TAG",
            "SORTABLE",
            "$.name",
            "AS",
            "name",
            "TEXT",
            "WEIGHT",
            "2.0",
            "SORTABLE",
            "$.observations[*]",
            "AS",
            "observations",
            "TEXT",
            "$.created_at",
            "AS",
            "created_at",
            "NUMERIC",
            "SORTABLE",
            "$.updated_at",
            "AS",
            "updated_at",
            "NUMERIC",
            "SORTABLE",
            "$.metadata.priority",
            "AS",
            "priority",
            "TAG",
            "$.metadata.status",
            "AS",
            "status",
            "TAG",
            "SORTABLE",
            "$.metadata.tags[*]",
            "AS",
            "tags",
            "TAG",
            "SEPARATOR",
            ",",
            "$.metadata.session_id",
            "AS",
            "session_id",
            "TAG",
        ]

    async def _check_index_exists(self, index_name: str) -> bool:
        """Issue #665: Check if a RediSearch index already exists.

        Args:
            index_name: Name of the index to check

        Returns:
            True if index exists, False otherwise
        """
        try:
            await self.redis_client.execute_command("FT.INFO", index_name)
            logger.info("Search index '%s' already exists", index_name)
            return True
        except Exception as e:
            logger.debug("Search index not found, will create: %s", e)
            return False

    async def _create_search_indexes(self) -> None:
        """Create RediSearch indexes for entity search."""
        try:
            if await self._check_index_exists("memory_entity_idx"):
                return

            schema = self._get_entity_index_schema()
            await self.redis_client.execute_command(
                "FT.CREATE",
                "memory_entity_idx",
                "ON",
                "JSON",
                "PREFIX",
                "1",
                "memory:entity:",
                "SCHEMA",
                *schema
            )
            logger.info("Created RediSearch index: memory_entity_idx")

        except Exception as e:
            logger.warning("Could not create search index: %s", e)

    async def _init_knowledge_base(self) -> None:
        """Initialize Knowledge Base for embedding generation."""
        try:
            from knowledge_base import KnowledgeBase

            self.knowledge_base = KnowledgeBase()
            await self.knowledge_base.initialize()

            logger.info("Knowledge Base initialized for embedding generation")

        except Exception as e:
            logger.warning(
                "Could not initialize Knowledge Base (embeddings unavailable): %s", e
            )
            self.knowledge_base = None

    async def _cleanup_on_failure(self) -> None:
        """Cleanup resources on initialization failure."""
        try:
            if self.redis_client:
                await self.redis_client.close()
                self.redis_client = None

            if self.knowledge_base:
                await self.knowledge_base.close()
                self.knowledge_base = None

            logger.info("Cleanup completed after initialization failure")

        except Exception as e:
            logger.warning("Error during cleanup: %s", e)

    def ensure_initialized(self) -> None:
        """Ensure the memory graph is initialized (raises exception if not)."""
        if not self.initialized:
            raise RuntimeError(
                "Memory Graph not initialized. "
                "Use 'await memory_graph.initialize()' first."
            )

    async def close(self) -> None:
        """Close all connections and cleanup resources."""
        try:
            if self.redis_client:
                await self.redis_client.close()

            if self.knowledge_base:
                await self.knowledge_base.close()

            self.initialized = False
            logger.info("Memory Graph connections closed")

        except Exception as e:
            logger.warning("Error during Memory Graph cleanup: %s", e)
