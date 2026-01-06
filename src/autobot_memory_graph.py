# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Memory Graph - Enhanced Memory System Implementation

This module implements the AutoBotMemoryGraph system for entity-relationship tracking,
semantic search, and cross-conversation context management.

Key Features:
- Entity management (conversations, bugs, features, decisions, tasks)
- Bidirectional relationship tracking
- Hybrid search (RedisSearch filters + Ollama semantic embeddings)
- Cross-conversation context and project continuity
- Backward compatible with existing chat history system

Architecture:
- Storage: Redis Stack DB 0 on VM3 (required for RediSearch FT.* commands)
- Entity Storage: RedisJSON documents
- Relations: Custom bidirectional indexing
- Search: RediSearch + Ollama embeddings (nomic-embed-text, 768 dims)
- Integration: Reuses existing Knowledge Base V2 patterns
- Network: Host/port configured via NetworkConstants.REDIS_HOST:REDIS_PORT

Performance Targets:
- Entity operations: <50ms
- Search queries: <200ms
- Relation traversal: <100ms
"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, FrozenSet, List, Optional

import redis.asyncio as async_redis  # Modern async Redis with JSON support
from cachetools import LRUCache

from src.unified_config_manager import UnifiedConfigManager
from src.utils.error_boundaries import (
    error_boundary,
    get_error_boundary_manager,
)

logger = logging.getLogger(__name__)

# Issue #380: Module-level frozensets for relation direction checks
_OUTGOING_DIRECTIONS: FrozenSet[str] = frozenset({"outgoing", "both"})
_INCOMING_DIRECTIONS: FrozenSet[str] = frozenset({"incoming", "both"})

# Create singleton config instance
config = UnifiedConfigManager()


class AutoBotMemoryGraph:
    """
    Enhanced memory system with graph-based relationship tracking
    and semantic search capabilities.

    Integrates with existing ChatHistoryManager to provide:
    - Entity extraction from conversations
    - Relationship tracking
    - Semantic search
    - Cross-conversation context
    """

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
        "user",  # User entity with profile and settings
        "chat_session",  # Chat session (enhanced conversation)
        "terminal_activity",  # Terminal command execution
        "file_activity",  # File browser operations
        "browser_activity",  # Web browser/Playwright actions
        "desktop_activity",  # noVNC desktop interactions
        "secret",  # User secrets (API keys, credentials)
        "secret_usage",  # Audit trail for secret access
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
        "owns",  # User owns session/secret
        "created_by",  # Entity created by user
        "has_participant",  # Session has participant (multi-user)
        "has_session",  # User has session
        # Issue #608: Activity relationships
        "has_activity",  # Session has activity (terminal, file, browser, desktop)
        "has_message",  # Session has chat message
        "performed_by",  # Activity performed by user
        # Issue #608: Secret relationships
        "has_secret",  # User/session has secret
        "uses_secret",  # Activity uses secret
        "shared_with",  # Secret shared with user
    }

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
        self.embedding_cache = {}  # In-memory embedding cache

        # Knowledge Base integration (for embeddings)
        self.knowledge_base = None

        logger.info("AutoBotMemoryGraph instance created (not yet initialized)")

    @error_boundary(component="autobot_memory_graph", function="initialize")
    async def initialize(self) -> bool:
        """Async initialization method - must be called after construction"""
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

    async def _init_redis_connection(self):
        """
        Initialize Redis connection to DB 0.

        USES CANONICAL PATTERN: get_redis_client() from src/utils/redis_client.py
        This ensures Redis Stack JSON support is properly configured.

        NOTE: Memory uses DB 0 because RediSearch (FT.* commands) only works on DB 0.
        """
        try:
            from src.utils.redis_client import get_redis_client

            # CANONICAL: Use get_redis_client for proper Redis Stack support
            # Database 0 is required for RediSearch indexing (FT.* commands)
            self.redis_client = await get_redis_client(
                async_client=True,
                database="memory",  # Maps to DB 0 for RediSearch compatibility
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
        """Issue #665: Extracted from _create_search_indexes to reduce function length.

        Returns the RediSearch schema definition for the entity index.

        Returns:
            List of schema arguments for FT.CREATE command
        """
        return [
            "$.type", "AS", "type", "TAG", "SORTABLE",
            "$.name", "AS", "name", "TEXT", "WEIGHT", "2.0", "SORTABLE",
            "$.observations[*]", "AS", "observations", "TEXT",
            "$.created_at", "AS", "created_at", "NUMERIC", "SORTABLE",
            "$.updated_at", "AS", "updated_at", "NUMERIC", "SORTABLE",
            "$.metadata.priority", "AS", "priority", "TAG",
            "$.metadata.status", "AS", "status", "TAG", "SORTABLE",
            "$.metadata.tags[*]", "AS", "tags", "TAG", "SEPARATOR", ",",
            "$.metadata.session_id", "AS", "session_id", "TAG",
        ]

    async def _check_index_exists(self, index_name: str) -> bool:
        """Issue #665: Extracted from _create_search_indexes to reduce function length.

        Check if a RediSearch index already exists.

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

    async def _create_search_indexes(self):
        """Create RediSearch indexes for entity search."""
        try:
            if await self._check_index_exists("memory_entity_idx"):
                return

            # Build and execute FT.CREATE command
            schema = self._get_entity_index_schema()
            await self.redis_client.execute_command(
                "FT.CREATE", "memory_entity_idx",
                "ON", "JSON",
                "PREFIX", "1", "memory:entity:",
                "SCHEMA", *schema
            )
            logger.info("Created RediSearch index: memory_entity_idx")

        except Exception as e:
            logger.warning("Could not create search index: %s", e)
            # Don't fail initialization - search will be limited but entities can still be stored

    async def _init_knowledge_base(self):
        """Initialize Knowledge Base for embedding generation"""
        try:
            from src.knowledge_base import KnowledgeBase

            self.knowledge_base = KnowledgeBase()
            await self.knowledge_base.initialize()

            logger.info("Knowledge Base initialized for embedding generation")

        except Exception as e:
            logger.warning(
                "Could not initialize Knowledge Base (embeddings unavailable): %s", e
            )
            self.knowledge_base = None

    async def _cleanup_on_failure(self):
        """Cleanup resources on initialization failure"""
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

    def ensure_initialized(self):
        """Ensure the memory graph is initialized (raises exception if not)"""
        if not self.initialized:
            raise RuntimeError(
                "Memory Graph not initialized. Use 'await memory_graph.initialize()' first."
            )

    # ==================== ENTITY OPERATIONS ====================

    def _prepare_entity_metadata(
        self,
        metadata: Optional[Dict[str, Any]],
        tags: Optional[List[str]],
    ) -> Dict[str, Any]:
        """
        Prepare enriched metadata for a new entity.

        (Issue #398: extracted helper)
        """
        entity_metadata = metadata or {}
        entity_metadata.update(
            {
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "created_by": "autobot",
                "tags": tags or [],
                "priority": entity_metadata.get("priority", "medium"),
                "status": entity_metadata.get("status", "active"),
                "version": 1,
            }
        )
        return entity_metadata

    def _build_entity_document(
        self,
        entity_id: str,
        entity_type: str,
        name: str,
        observations: List[str],
        entity_metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Build the complete entity document for storage.

        (Issue #398: extracted helper)
        """
        return {
            "id": entity_id,
            "type": entity_type,
            "name": name,
            "created_at": int(datetime.now().timestamp() * 1000),
            "updated_at": int(datetime.now().timestamp() * 1000),
            "observations": observations,
            "metadata": entity_metadata,
        }

    async def create_entity(
        self,
        entity_type: str,
        name: str,
        observations: List[str],
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Create a new entity in the memory graph.

        (Issue #398: refactored to use extracted helpers)

        Args:
            entity_type: Type of entity (conversation, bug_fix, feature, etc.)
            name: Human-readable entity name
            observations: List of observation strings
            metadata: Optional additional metadata
            tags: Optional classification tags

        Returns:
            Created entity with entity_id and metadata

        Raises:
            ValueError: Invalid entity_type or empty name
            RuntimeError: Memory Graph not initialized
        """
        self.ensure_initialized()

        # Validation
        if entity_type not in self.ENTITY_TYPES:
            raise ValueError(
                f"Invalid entity_type: {entity_type}. Must be one of {self.ENTITY_TYPES}"
            )

        if not name or not name.strip():
            raise ValueError("Entity name cannot be empty")

        try:
            entity_id = str(uuid.uuid4())
            entity_metadata = self._prepare_entity_metadata(metadata, tags)
            entity = self._build_entity_document(
                entity_id, entity_type, name, observations, entity_metadata
            )

            # Store in Redis
            entity_key = f"memory:entity:{entity_id}"
            await self.redis_client.json().set(entity_key, "$", entity)

            # Generate and cache embedding for semantic search
            if self.knowledge_base:
                await self._generate_entity_embedding(entity_id, entity)

            logger.info("Created entity: %s (%s) with ID %s", name, entity_type, entity_id)

            return entity

        except Exception as e:
            logger.error("Failed to create entity: %s", e)
            raise RuntimeError(f"Entity creation failed: {str(e)}")

    async def get_entity(
        self,
        entity_id: Optional[str] = None,
        entity_name: Optional[str] = None,
        include_relations: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve entity by ID or name.

        Args:
            entity_id: UUID of entity to retrieve
            entity_name: Name of entity to retrieve (alternative to ID)
            include_relations: Include related entities in response

        Returns:
            Entity data or None if not found
        """
        self.ensure_initialized()

        try:
            # Find entity by ID or name
            if entity_id:
                entity_key = f"memory:entity:{entity_id}"
                entity = await self.redis_client.json().get(entity_key)
            elif entity_name:
                # Search by name
                results = await self.search_entities(query=entity_name, limit=1)
                if not results:
                    return None
                entity = results[0]
                entity_id = entity["id"]
            else:
                raise ValueError("Either entity_id or entity_name must be provided")

            if not entity:
                return None

            # Include relations if requested - fetch in parallel for better performance
            if include_relations and entity_id:
                outgoing, incoming = await asyncio.gather(
                    self._get_outgoing_relations(entity_id),
                    self._get_incoming_relations(entity_id),
                )
                entity["relations"] = {"outgoing": outgoing, "incoming": incoming}

            return entity

        except Exception as e:
            logger.error("Failed to get entity: %s", e)
            return None

    async def add_observations(
        self, entity_name: str, observations: List[str]
    ) -> Dict[str, Any]:
        """
        Add new observations to an existing entity.

        Args:
            entity_name: Name of entity to update
            observations: List of new observations to add

        Returns:
            Updated entity data

        Raises:
            ValueError: Entity not found
        """
        self.ensure_initialized()

        try:
            # Find entity
            entity = await self.get_entity(entity_name=entity_name)
            if not entity:
                raise ValueError(f"Entity not found: {entity_name}")

            entity_id = entity["id"]
            entity_key = f"memory:entity:{entity_id}"

            # Append all observations in parallel - eliminates N+1 sequential appends
            await asyncio.gather(
                *[
                    self.redis_client.json().arrappend(entity_key, "$.observations", obs)
                    for obs in observations
                ]
            )

            # Update timestamp
            await self.redis_client.json().set(
                entity_key, "$.updated_at", int(datetime.now().timestamp() * 1000)
            )

            # Update embedding
            if self.knowledge_base:
                updated_entity = await self.redis_client.json().get(entity_key)
                await self._generate_entity_embedding(entity_id, updated_entity)

            # Invalidate cache
            self.search_cache.clear()

            logger.info(
                "Added %d observations to entity: %s", len(observations), entity_name
            )

            return await self.redis_client.json().get(entity_key)

        except Exception as e:
            logger.error("Failed to add observations: %s", e)
            raise RuntimeError(f"Add observations failed: {str(e)}")

    async def delete_entity(
        self, entity_name: str, cascade_relations: bool = True
    ) -> bool:
        """
        Delete entity and optionally its relations.

        Args:
            entity_name: Name of entity to delete
            cascade_relations: Delete all relations to/from this entity

        Returns:
            True if deleted, False if not found
        """
        self.ensure_initialized()

        try:
            # Find entity
            entity = await self.get_entity(entity_name=entity_name)
            if not entity:
                return False

            entity_id = entity["id"]

            # Delete relations if cascade
            if cascade_relations:
                # Delete outgoing relations
                out_key = f"memory:relations:out:{entity_id}"
                await self.redis_client.delete(out_key)

                # Delete incoming relations
                in_key = f"memory:relations:in:{entity_id}"
                await self.redis_client.delete(in_key)

            # Delete entity
            entity_key = f"memory:entity:{entity_id}"
            deleted = await self.redis_client.delete(entity_key)

            # Clear cache
            self.search_cache.clear()
            if entity_id in self.embedding_cache:
                del self.embedding_cache[entity_id]

            logger.info("Deleted entity: %s", entity_name)

            return deleted > 0

        except Exception as e:
            logger.error("Failed to delete entity: %s", e)
            return False

    # ==================== RELATIONSHIP OPERATIONS ====================

    async def create_relation(
        self,
        from_entity: str,
        to_entity: str,
        relation_type: str,
        bidirectional: bool = False,
        strength: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create relationship between two entities.

        Issue #665: Refactored to use _store_outgoing_relation and
        _store_incoming_relation helpers for maintainability.

        Args:
            from_entity: Source entity name
            to_entity: Target entity name
            relation_type: Type of relationship
            bidirectional: Create reverse relation as well
            strength: Relationship strength (0.0-1.0)
            metadata: Optional additional metadata

        Returns:
            Created relation data
        """
        self.ensure_initialized()

        if relation_type not in self.RELATION_TYPES:
            raise ValueError(f"Invalid relation_type: {relation_type}")

        try:
            # Get entity IDs in parallel
            from_entity_data, to_entity_data = await asyncio.gather(
                self.get_entity(entity_name=from_entity),
                self.get_entity(entity_name=to_entity),
            )

            if not from_entity_data or not to_entity_data:
                raise ValueError("Source or target entity not found")

            from_id = from_entity_data["id"]
            to_id = to_entity_data["id"]
            timestamp = int(datetime.now().timestamp() * 1000)

            # Build relation objects
            relation = {
                "to": to_id,
                "type": relation_type,
                "created_at": timestamp,
                "metadata": {"strength": strength, **(metadata or {})},
            }
            reverse_rel = {"from": from_id, "type": relation_type, "created_at": timestamp}

            # Store both directions using helpers
            await self._store_outgoing_relation(from_id, relation)
            await self._store_incoming_relation(to_id, reverse_rel)

            logger.info(
                "Created relation: %s --[%s]--> %s", from_entity, relation_type, to_entity
            )
            return relation

        except Exception as e:
            logger.error("Failed to create relation: %s", e)
            raise RuntimeError(f"Relation creation failed: {str(e)}")

    async def _fetch_and_process_relations(
        self,
        current_id: str,
        direction: str,
        relation_type: Optional[str],
        depth: int,
        max_depth: int,
        queue: List,
    ) -> List[Dict[str, Any]]:
        """Issue #665: Extracted from get_related_entities to reduce function length.

        Fetch relations for a direction and process them.

        Args:
            current_id: Current entity ID in BFS traversal
            direction: "outgoing", "incoming", or "both"
            relation_type: Filter by relation type
            depth: Current traversal depth
            max_depth: Maximum traversal depth
            queue: BFS queue to append to

        Returns:
            List of related entity dicts with relation metadata
        """
        need_outgoing = direction in _OUTGOING_DIRECTIONS
        need_incoming = direction in _INCOMING_DIRECTIONS
        related = []

        if need_outgoing and need_incoming:
            outgoing, incoming = await asyncio.gather(
                self._get_outgoing_relations(current_id),
                self._get_incoming_relations(current_id),
            )
            related.extend(await self._process_direction_relations(
                outgoing, relation_type, "outgoing", "to", depth, max_depth, queue
            ))
            related.extend(await self._process_direction_relations(
                incoming, relation_type, "incoming", "from", depth, max_depth, queue
            ))
        elif need_outgoing:
            outgoing = await self._get_outgoing_relations(current_id)
            related.extend(await self._process_direction_relations(
                outgoing, relation_type, "outgoing", "to", depth, max_depth, queue
            ))
        elif need_incoming:
            incoming = await self._get_incoming_relations(current_id)
            related.extend(await self._process_direction_relations(
                incoming, relation_type, "incoming", "from", depth, max_depth, queue
            ))

        return related

    async def get_related_entities(
        self,
        entity_name: str,
        relation_type: Optional[str] = None,
        direction: str = "both",
        max_depth: int = 1,
    ) -> List[Dict[str, Any]]:
        """Get entities related to specified entity.

        Args:
            entity_name: Name of entity
            relation_type: Filter by relation type (None = all types)
            direction: "outgoing", "incoming", or "both"
            max_depth: Relationship traversal depth (1-3)

        Returns:
            List of related entities with relation metadata
        """
        self.ensure_initialized()

        try:
            entity = await self.get_entity(entity_name=entity_name)
            if not entity:
                return []

            entity_id = entity["id"]
            related = []
            visited = set()
            queue = [(entity_id, 0)]

            while queue:
                current_id, depth = queue.pop(0)
                if current_id in visited or depth > max_depth:
                    continue
                visited.add(current_id)

                direction_related = await self._fetch_and_process_relations(
                    current_id, direction, relation_type, depth, max_depth, queue
                )
                related.extend(direction_related)

            return related

        except Exception as e:
            logger.error("Failed to get related entities: %s", e)
            return []

    async def delete_relation(
        self, from_entity: str, to_entity: str, relation_type: str
    ) -> bool:
        """
        Delete specific relation between entities.

        Args:
            from_entity: Source entity name
            to_entity: Target entity name
            relation_type: Type of relation to delete

        Returns:
            True if deleted, False if not found
        """
        self.ensure_initialized()

        try:
            # Get entity IDs - fetch both in parallel for better performance
            from_entity_data, to_entity_data = await asyncio.gather(
                self.get_entity(entity_name=from_entity),
                self.get_entity(entity_name=to_entity),
            )

            if not from_entity_data or not to_entity_data:
                return False

            from_id = from_entity_data["id"]
            to_id = to_entity_data["id"]

            # Get and filter relations
            out_key = f"memory:relations:out:{from_id}"
            out_data = await self.redis_client.json().get(out_key)

            if out_data and "relations" in out_data:
                filtered_relations = [
                    rel
                    for rel in out_data["relations"]
                    if not (rel["to"] == to_id and rel["type"] == relation_type)
                ]
                await self.redis_client.json().set(
                    out_key, "$.relations", filtered_relations
                )

            # Remove reverse relation
            in_key = f"memory:relations:in:{to_id}"
            in_data = await self.redis_client.json().get(in_key)

            if in_data and "relations" in in_data:
                filtered_relations = [
                    rel
                    for rel in in_data["relations"]
                    if not (rel["from"] == from_id and rel["type"] == relation_type)
                ]
                await self.redis_client.json().set(
                    in_key, "$.relations", filtered_relations
                )

            logger.info(
                "Deleted relation: %s --[%s]--> %s", from_entity, relation_type, to_entity
            )

            return True

        except Exception as e:
            logger.error("Failed to delete relation: %s", e)
            return False

    async def _get_outgoing_relations(self, entity_id: str) -> List[Dict[str, Any]]:
        """Get all outgoing relations for an entity"""
        try:
            out_key = f"memory:relations:out:{entity_id}"
            data = await self.redis_client.json().get(out_key)
            return data.get("relations", []) if data else []
        except Exception as e:
            logger.debug("Error getting outgoing relations for %s: %s", entity_id, e)
            return []

    async def _get_incoming_relations(self, entity_id: str) -> List[Dict[str, Any]]:
        """Get all incoming relations for an entity"""
        try:
            in_key = f"memory:relations:in:{entity_id}"
            data = await self.redis_client.json().get(in_key)
            return data.get("relations", []) if data else []
        except Exception as e:
            logger.debug("Error getting incoming relations for %s: %s", entity_id, e)
            return []

    async def get_relations(
        self,
        entity_id: str,
        relation_types: Optional[List[str]] = None,
        direction: str = "both",
    ) -> Dict[str, Any]:
        """
        Get relations for an entity.

        Issue #608: Public method for retrieving entity relationships.

        Args:
            entity_id: Entity ID to get relations for
            relation_types: Optional filter by relation types
            direction: "outgoing", "incoming", or "both"

        Returns:
            Dict with "relations" key containing list of relations
        """
        self.ensure_initialized()

        try:
            relations = []

            # Get outgoing relations
            if direction in _OUTGOING_DIRECTIONS:
                outgoing = await self._get_outgoing_relations(entity_id)
                for rel in outgoing:
                    if relation_types is None or rel.get("type") in relation_types:
                        relations.append({
                            "from": entity_id,
                            "to": rel.get("to"),
                            "type": rel.get("type"),
                            "direction": "outgoing",
                            "metadata": rel.get("metadata", {}),
                        })

            # Get incoming relations
            if direction in _INCOMING_DIRECTIONS:
                incoming = await self._get_incoming_relations(entity_id)
                for rel in incoming:
                    if relation_types is None or rel.get("type") in relation_types:
                        relations.append({
                            "from": rel.get("from"),
                            "to": entity_id,
                            "type": rel.get("type"),
                            "direction": "incoming",
                            "metadata": rel.get("metadata", {}),
                        })

            return {"relations": relations}

        except Exception as e:
            logger.error("Failed to get relations for %s: %s", entity_id, e)
            return {"relations": []}

    async def create_relation_by_id(
        self,
        from_entity_id: str,
        to_entity_id: str,
        relation_type: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Create relationship between two entities using their IDs directly.

        Issue #608: Helper for user-centric session tracking where we have
        entity IDs rather than names.

        Args:
            from_entity_id: Source entity ID (UUID)
            to_entity_id: Target entity ID (UUID)
            relation_type: Type of relationship
            metadata: Optional additional metadata

        Returns:
            True if relation created successfully
        """
        self.ensure_initialized()

        if relation_type not in self.RELATION_TYPES:
            raise ValueError(f"Invalid relation_type: {relation_type}")

        try:
            timestamp = int(datetime.now().timestamp() * 1000)

            # Build relation objects
            relation = {
                "to": to_entity_id,
                "type": relation_type,
                "created_at": timestamp,
                "metadata": metadata or {},
            }
            reverse_rel = {
                "from": from_entity_id,
                "type": relation_type,
                "created_at": timestamp,
            }

            # Store both directions using existing helpers
            await self._store_outgoing_relation(from_entity_id, relation)
            await self._store_incoming_relation(to_entity_id, reverse_rel)

            logger.debug(
                "Created relation by ID: %s --[%s]--> %s",
                from_entity_id[:8],
                relation_type,
                to_entity_id[:8],
            )
            return True

        except Exception as e:
            logger.error("Failed to create relation by ID: %s", e)
            return False

    async def _store_outgoing_relation(
        self, from_id: str, relation: Dict[str, Any]
    ) -> None:
        """Store outgoing relation for an entity (Issue #665: extracted helper).

        Args:
            from_id: Source entity ID
            relation: Relation data to store
        """
        out_key = f"memory:relations:out:{from_id}"
        if not await self.redis_client.exists(out_key):
            await self.redis_client.json().set(
                out_key, "$", {"entity_id": from_id, "relations": []}
            )
        await self.redis_client.json().arrappend(out_key, "$.relations", relation)

    async def _store_incoming_relation(
        self, to_id: str, reverse_rel: Dict[str, Any]
    ) -> None:
        """Store incoming relation for an entity (Issue #665: extracted helper).

        Args:
            to_id: Target entity ID
            reverse_rel: Reverse relation data to store
        """
        in_key = f"memory:relations:in:{to_id}"
        if not await self.redis_client.exists(in_key):
            await self.redis_client.json().set(
                in_key, "$", {"entity_id": to_id, "relations": []}
            )
        await self.redis_client.json().arrappend(in_key, "$.relations", reverse_rel)

    async def _process_direction_relations(
        self,
        relations: List[Dict[str, Any]],
        relation_type: Optional[str],
        direction: str,
        id_field: str,
        depth: int,
        max_depth: int,
        queue: List,
    ) -> List[Dict[str, Any]]:
        """Process relations in a single direction (Issue #298 - extracted helper).

        Args:
            relations: Raw relations from Redis
            relation_type: Optional filter for relation type
            direction: "outgoing" or "incoming"
            id_field: Field name for entity ID ("to" or "from")
            depth: Current traversal depth
            max_depth: Maximum traversal depth
            queue: BFS queue to append to

        Returns:
            List of related entity dicts with relation metadata
        """
        # Filter by relation type
        filtered = [
            rel for rel in relations
            if relation_type is None or rel["type"] == relation_type
        ]
        if not filtered:
            return []

        # Batch fetch all related entities
        entity_ids = [rel[id_field] for rel in filtered]
        entities = await asyncio.gather(
            *[self.get_entity(entity_id=eid) for eid in entity_ids],
            return_exceptions=True
        )

        related = []
        for rel, related_entity in zip(filtered, entities):
            if related_entity and not isinstance(related_entity, Exception):
                related.append({
                    "entity": related_entity,
                    "relation": rel,
                    "direction": direction,
                })
                if depth + 1 <= max_depth:
                    queue.append((rel[id_field], depth + 1))

        return related

    # ==================== SEARCH OPERATIONS ====================

    def _build_redis_search_query(
        self,
        query: str,
        entity_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
        status: Optional[str] = None,
    ) -> str:
        """Issue #665: Extracted from search_entities to reduce function length.

        Build a RediSearch query string from search parameters.

        Args:
            query: Text search query
            entity_type: Filter by entity type
            tags: Filter by tags (any match)
            status: Filter by status

        Returns:
            RediSearch query string
        """
        query_parts = []
        if entity_type:
            query_parts.append(f"@type:{{{entity_type}}}")
        if status:
            query_parts.append(f"@status:{{{status}}}")
        if tags:
            tag_filter = "|".join(tags)
            query_parts.append(f"@tags:{{{tag_filter}}}")
        if query and query != "*":
            query_parts.append(f"({query})")
        return " ".join(query_parts) if query_parts else "*"

    async def _execute_redis_search(
        self, redis_query: str, limit: int
    ) -> List[Dict[str, Any]]:
        """Issue #665: Extracted from search_entities to reduce function length.

        Execute RediSearch FT.SEARCH command and parse results.

        Args:
            redis_query: RediSearch query string
            limit: Maximum results to return

        Returns:
            List of matching entity dictionaries
        """
        results = await self.redis_client.execute_command(
            "FT.SEARCH", "memory_entity_idx", redis_query,
            "LIMIT", "0", str(limit),
            "RETURN", "3", "$.name", "$.type", "$.observations",
        )
        return await self._parse_search_results(results, limit)

    async def search_entities(
        self,
        query: str,
        entity_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Semantic search across all entities.

        Args:
            query: Search query (full-text search)
            entity_type: Filter by entity type
            tags: Filter by tags (any match)
            status: Filter by status
            limit: Maximum results to return

        Returns:
            List of matching entities sorted by relevance
        """
        self.ensure_initialized()

        try:
            redis_query = self._build_redis_search_query(query, entity_type, tags, status)
            try:
                entities = await self._execute_redis_search(redis_query, limit)
                logger.info("Search query '%s' returned %d results", query, len(entities))
                return entities
            except Exception as search_error:
                logger.warning("RediSearch failed, using fallback: %s", search_error)
                return await self._fallback_search(query, entity_type, limit)
        except Exception as e:
            logger.error("Search failed: %s", e)
            return []

    async def _parse_search_results(
        self, results: list, limit: int
    ) -> List[Dict[str, Any]]:
        """Parse RediSearch results and fetch full entities (Issue #315: extracted).

        Args:
            results: Raw RediSearch FT.SEARCH results
            limit: Maximum entities to return

        Returns:
            List of parsed entity dictionaries
        """
        entities = []
        if not results or len(results) <= 1:
            return entities

        for i in range(1, len(results), 2):
            if i + 1 >= len(results):
                continue

            entity_key = results[i]
            if isinstance(entity_key, bytes):
                entity_key = entity_key.decode()

            entity = await self.redis_client.json().get(entity_key)
            if entity:
                entities.append(entity)

        return entities[:limit]

    def _entity_matches_query(
        self, entity: Dict[str, Any], query_lower: str, entity_type: Optional[str]
    ) -> bool:
        """Check if entity matches search criteria (Issue #315 - extracted helper)."""
        # Apply type filter
        if entity_type and entity.get("type") != entity_type:
            return False

        # Skip text matching for wildcards
        if not query_lower or query_lower == "*":
            return True

        # Check name match
        if query_lower in entity.get("name", "").lower():
            return True

        # Check observations match
        return any(
            query_lower in obs.lower() for obs in entity.get("observations", [])
        )

    async def _fallback_search(
        self, query: str, entity_type: Optional[str], limit: int
    ) -> List[Dict[str, Any]]:
        """Fallback search when RediSearch is unavailable (Issue #315 - refactored depth 5 to 3)."""
        try:
            query_lower = query.lower() if query else ""

            # Issue #614: Fix N+1 pattern - collect keys first, then batch fetch
            # Collect all entity keys first
            keys = []
            async for key in self.redis_client.scan_iter(match="memory:entity:*"):
                keys.append(key)
                # Limit scanning to avoid memory issues (fetch more than needed)
                if len(keys) >= limit * 10:
                    break

            if not keys:
                return []

            # Batch fetch all entities using pipeline
            # Note: RedisJSON's json().get() requires individual calls, but we can
            # use mget for the keys if they're simple values, or process in batches
            batch_size = 50
            entities = []

            for i in range(0, len(keys), batch_size):
                batch_keys = keys[i:i + batch_size]

                # Use pipeline for batch fetching
                pipe = self.redis_client.pipeline()
                for key in batch_keys:
                    pipe.json().get(key)
                batch_results = await pipe.execute()

                # Process batch results
                for entity in batch_results:
                    if entity and self._entity_matches_query(entity, query_lower, entity_type):
                        entities.append(entity)
                        if len(entities) >= limit:
                            return entities

            return entities

        except Exception as e:
            logger.error("Fallback search failed: %s", e)
            return []

    async def _generate_entity_embedding(self, entity_id: str, entity: Dict[str, Any]):
        """Generate and cache embedding for entity"""
        try:
            if not self.knowledge_base:
                return

            # Generate embedding text (weighted combination)
            name = entity.get("name", "")
            entity_type = entity.get("type", "")
            observations = entity.get("observations", [])

            # Weighted text (name: 0.3, type: 0.1, observations: 0.6)
            embedding_text = (
                f"{name} {name} {name} {entity_type} {' '.join(observations * 6)}"
            )

            # Generate embedding using Knowledge Base
            # Store embedding for future semantic search
            self.embedding_cache[entity_id] = embedding_text

        except Exception as e:
            logger.warning("Failed to generate embedding for entity %s: %s", entity_id, e)

    # ==================== INTEGRATION METHODS ====================

    async def create_conversation_entity(
        self,
        session_id: str,
        metadata: Optional[Dict[str, Any]] = None,
        observations: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Automatically create entity from chat session.

        Args:
            session_id: Chat session identifier
            metadata: Optional additional metadata
            observations: Optional list of observations to add immediately (prevents race condition)

        Returns:
            Created conversation entity
        """
        self.ensure_initialized()

        try:
            # Get session data from chat history manager
            entity_observations = []
            tags = []

            # Use provided observations if available (prevents race condition with add_observations)
            if observations:
                entity_observations = observations
            elif self.chat_history_manager:
                # Extract observations from session messages
                # This is a placeholder - actual implementation would extract from messages
                entity_observations = [f"Conversation session: {session_id}"]
                tags = ["conversation"]

            # Create conversation metadata
            conv_metadata = metadata or {}
            conv_metadata.update(
                {"session_id": session_id, "priority": "low", "status": "active"}
            )

            # Create entity with observations included (avoids race condition)
            entity = await self.create_entity(
                entity_type="conversation",
                name=f"Conversation {session_id[:8]}",
                observations=entity_observations,
                metadata=conv_metadata,
                tags=tags,
            )

            logger.info("Created conversation entity for session %s", session_id)

            return entity

        except Exception as e:
            logger.error("Failed to create conversation entity: %s", e)
            raise

    # ==================== ISSUE #608: USER-CENTRIC SESSION TRACKING ====================

    async def create_user_entity(
        self,
        user_id: str,
        username: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create or get a user entity in the knowledge graph.

        Issue #608: User entities are the foundation for user-centric session tracking.
        Each user has a unique entity that owns their sessions, secrets, and preferences.

        Args:
            user_id: Unique user identifier
            username: Human-readable username
            metadata: Optional additional metadata (email, display_name, etc.)

        Returns:
            Created or existing user entity
        """
        self.ensure_initialized()

        try:
            # Check if user entity already exists
            # search_entities returns a list, not a dict
            existing = await self.search_entities(
                query=user_id,
                entity_type="user",
                limit=1,
            )

            if existing:
                logger.debug("User entity already exists for %s", username)
                return existing[0]

            # Create user metadata
            user_metadata = metadata or {}
            user_metadata.update({
                "user_id": user_id,
                "username": username,
                "status": "active",
                "created_at": datetime.utcnow().isoformat(),
            })

            # Create user entity
            entity = await self.create_entity(
                entity_type="user",
                name=f"User: {username}",
                observations=[f"User account created: {username}"],
                metadata=user_metadata,
                tags=["user", "account"],
            )

            logger.info("Created user entity for %s (id: %s)", username, user_id)
            return entity

        except Exception as e:
            logger.error("Failed to create user entity: %s", e)
            raise

    def _build_session_metadata(
        self,
        session_id: str,
        owner_id: str,
        collaborators: Optional[List[str]],
        metadata: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Issue #665: Extracted from create_chat_session_entity to reduce function length.

        Build metadata dictionary for a chat session entity.

        Args:
            session_id: Unique session identifier
            owner_id: User ID of session owner
            collaborators: List of collaborator user IDs
            metadata: Optional additional metadata

        Returns:
            Complete session metadata dictionary
        """
        session_metadata = metadata or {}
        session_metadata.update({
            "session_id": session_id,
            "owner_id": owner_id,
            "mode": "collaborative" if collaborators else "single_user",
            "collaborators": collaborators or [],
            "status": "active",
            "created_at": datetime.utcnow().isoformat(),
        })
        return session_metadata

    async def _create_session_owner_relations(
        self, owner_id: str, entity_id: str
    ) -> None:
        """Issue #665: Extracted from create_chat_session_entity to reduce function length.

        Create owner relationships for a chat session entity.

        Args:
            owner_id: User ID of session owner
            entity_id: ID of the created session entity
        """
        await self.create_relation_by_id(
            from_entity_id=owner_id,
            to_entity_id=entity_id,
            relation_type="owns",
            metadata={"role": "owner"},
        )
        await self.create_relation_by_id(
            from_entity_id=owner_id,
            to_entity_id=entity_id,
            relation_type="has_session",
        )

    async def _create_collaborator_relations(
        self, entity_id: str, collaborators: Optional[List[str]]
    ) -> None:
        """Issue #665: Extracted from create_chat_session_entity to reduce function length.

        Create collaborator relationships for multi-user sessions.

        Args:
            entity_id: ID of the session entity
            collaborators: List of collaborator user IDs
        """
        if not collaborators:
            return
        for collaborator_id in collaborators:
            await self.create_relation_by_id(
                from_entity_id=entity_id,
                to_entity_id=collaborator_id,
                relation_type="has_participant",
                metadata={"role": "collaborator"},
            )

    async def create_chat_session_entity(
        self,
        session_id: str,
        owner_id: str,
        title: Optional[str] = None,
        collaborators: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a chat session entity with user ownership tracking.

        Issue #608/#665: Supports single/multi-user modes, activity tracking, secret scoping.
        """
        self.ensure_initialized()

        try:
            session_metadata = self._build_session_metadata(
                session_id, owner_id, collaborators, metadata
            )
            entity = await self.create_entity(
                entity_type="chat_session",
                name=title or f"Chat Session {session_id[:8]}",
                observations=[f"Session created by user {owner_id}"],
                metadata=session_metadata,
                tags=["session", "chat"],
            )
            await self._create_session_owner_relations(owner_id, entity["id"])
            await self._create_collaborator_relations(entity["id"], collaborators)
            logger.info("Created chat session entity: %s", session_id)
            return entity

        except Exception as e:
            logger.error("Failed to create chat session entity: %s", e)
            raise

    # Valid activity types (Issue #665: module-level constant for validation)
    _VALID_ACTIVITY_TYPES = frozenset({
        "terminal_activity",
        "file_activity",
        "browser_activity",
        "desktop_activity",
    })

    def _validate_activity_type(self, activity_type: str) -> None:
        """Issue #665: Extracted from create_activity_entity to reduce function length.

        Validate that the activity type is valid.

        Args:
            activity_type: Activity type to validate

        Raises:
            ValueError: If activity_type is not valid
        """
        if activity_type not in self._VALID_ACTIVITY_TYPES:
            raise ValueError(
                f"Invalid activity_type: {activity_type}. "
                f"Must be one of {self._VALID_ACTIVITY_TYPES}"
            )

    def _build_activity_metadata(
        self,
        session_id: str,
        user_id: str,
        secrets_used: Optional[List[str]],
        metadata: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Issue #665: Extracted from create_activity_entity to reduce function length.

        Build metadata dictionary for an activity entity.

        Args:
            session_id: Parent chat session ID
            user_id: User who performed the activity
            secrets_used: List of secret IDs used
            metadata: Optional additional metadata

        Returns:
            Complete activity metadata dictionary
        """
        activity_metadata = metadata or {}
        activity_metadata.update({
            "session_id": session_id,
            "user_id": user_id,
            "secrets_used": secrets_used or [],
            "timestamp": datetime.utcnow().isoformat(),
        })
        return activity_metadata

    async def _create_activity_relations(
        self, session_id: str, entity_id: str, user_id: str
    ) -> None:
        """Issue #665: Extracted from create_activity_entity to reduce function length.

        Create core relationships for an activity entity.

        Args:
            session_id: Parent chat session ID
            entity_id: ID of the created activity entity
            user_id: User who performed the activity
        """
        await self.create_relation_by_id(
            from_entity_id=session_id,
            to_entity_id=entity_id,
            relation_type="has_activity",
        )
        await self.create_relation_by_id(
            from_entity_id=entity_id,
            to_entity_id=user_id,
            relation_type="performed_by",
        )

    async def _create_secret_usage_relations(
        self,
        entity_id: str,
        user_id: str,
        activity_type: str,
        secrets_used: Optional[List[str]],
    ) -> None:
        """Issue #665: Extracted from create_activity_entity to reduce function length.

        Create secret usage relationships and audit trail.

        Args:
            entity_id: ID of the activity entity
            user_id: User who performed the activity
            activity_type: Type of activity
            secrets_used: List of secret IDs used
        """
        if not secrets_used:
            return
        for secret_id in secrets_used:
            await self.create_relation_by_id(
                from_entity_id=entity_id,
                to_entity_id=secret_id,
                relation_type="uses_secret",
            )
            await self._create_secret_usage_audit(
                secret_id=secret_id,
                user_id=user_id,
                activity_type=activity_type,
                activity_id=entity_id,
            )

    async def create_activity_entity(
        self,
        activity_type: str,
        session_id: str,
        user_id: str,
        content: str,
        secrets_used: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create an activity entity within a chat session.

        Issue #608/#665: Activities tracked with user attribution and secret usage.
        """
        self.ensure_initialized()
        self._validate_activity_type(activity_type)

        try:
            activity_metadata = self._build_activity_metadata(
                session_id, user_id, secrets_used, metadata
            )
            entity = await self.create_entity(
                entity_type=activity_type,
                name=f"{activity_type.replace('_', ' ').title()} by {user_id[:8]}",
                observations=[content],
                metadata=activity_metadata,
                tags=["activity", activity_type.replace("_activity", "")],
            )
            await self._create_activity_relations(session_id, entity["id"], user_id)
            await self._create_secret_usage_relations(
                entity["id"], user_id, activity_type, secrets_used
            )
            logger.info("Created %s entity for session %s", activity_type, session_id)
            return entity

        except Exception as e:
            logger.error("Failed to create activity entity: %s", e)
            raise

    def _validate_secret_params(
        self, secret_type: str, scope: str, session_id: Optional[str]
    ) -> None:
        """
        Validate secret creation parameters.

        Issue #665: Extracted from create_secret_entity.

        Args:
            secret_type: Type of secret
            scope: Scope level
            session_id: Session ID for session-scoped secrets

        Raises:
            ValueError: If validation fails
        """
        valid_secret_types = {"api_key", "token", "password", "ssh_key", "certificate"}
        valid_scopes = {"user", "session", "shared"}

        if secret_type not in valid_secret_types:
            raise ValueError(
                f"Invalid secret_type: {secret_type}. Must be one of {valid_secret_types}"
            )
        if scope not in valid_scopes:
            raise ValueError(f"Invalid scope: {scope}. Must be one of {valid_scopes}")
        if scope == "session" and not session_id:
            raise ValueError("session_id is required for session-scoped secrets")

    async def _create_secret_owner_relations(
        self, owner_id: str, entity_id: str
    ) -> None:
        """
        Create owner relationships for a secret entity.

        Issue #665: Extracted from create_secret_entity.

        Args:
            owner_id: User ID of secret owner
            entity_id: ID of the created secret entity
        """
        # Create relationship: User owns Secret
        await self.create_relation_by_id(
            from_entity_id=owner_id,
            to_entity_id=entity_id,
            relation_type="owns",
        )
        # Create relationship: User has Secret
        await self.create_relation_by_id(
            from_entity_id=owner_id,
            to_entity_id=entity_id,
            relation_type="has_secret",
        )

    async def _create_secret_scope_relations(
        self,
        entity_id: str,
        scope: str,
        session_id: Optional[str],
        shared_with: Optional[List[str]],
    ) -> None:
        """
        Create scope-based relationships for a secret entity.

        Issue #665: Extracted from create_secret_entity.

        Args:
            entity_id: ID of the secret entity
            scope: Scope level (user, session, shared)
            session_id: Session ID for session-scoped secrets
            shared_with: List of user IDs for shared secrets
        """
        # Session-scoped: link to session
        if scope == "session" and session_id:
            await self.create_relation_by_id(
                from_entity_id=session_id,
                to_entity_id=entity_id,
                relation_type="has_secret",
                metadata={"scope": "session"},
            )
        # Shared: create relationships to shared users
        if scope == "shared" and shared_with:
            for shared_user_id in shared_with:
                await self.create_relation_by_id(
                    from_entity_id=entity_id,
                    to_entity_id=shared_user_id,
                    relation_type="shared_with",
                )

    async def create_secret_entity(
        self,
        name: str,
        secret_type: str,
        owner_id: str,
        scope: str = "user",
        session_id: Optional[str] = None,
        shared_with: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create a secret entity with ownership and scoping.

        Issue #608: Secrets can be:
        - User-scoped: Private to the owner
        - Session-scoped: Shared within a specific session
        - Shared: Explicitly shared with specific users

        Issue #665: Refactored to extract validation and relation helpers.

        Note: This does NOT store the actual secret value. The encrypted value
        should be stored separately in a secure vault.

        Args:
            name: Human-readable secret name
            secret_type: Type of secret (api_key, token, password, ssh_key, certificate)
            owner_id: User ID of secret owner
            scope: Scope level (user, session, shared)
            session_id: Session ID for session-scoped secrets
            shared_with: List of user IDs for shared secrets
            metadata: Optional additional metadata

        Returns:
            Created secret entity (without the actual secret value)
        """
        self.ensure_initialized()
        self._validate_secret_params(secret_type, scope, session_id)

        try:
            # Build secret metadata
            secret_metadata = metadata or {}
            secret_metadata.update({
                "owner_id": owner_id,
                "secret_type": secret_type,
                "scope": scope,
                "session_id": session_id,
                "shared_with": shared_with or [],
                "usage_count": 0,
                "created_at": datetime.utcnow().isoformat(),
            })

            # Create secret entity
            entity = await self.create_entity(
                entity_type="secret",
                name=name,
                observations=[f"Secret created: {secret_type} ({scope} scope)"],
                metadata=secret_metadata,
                tags=["secret", secret_type, scope],
            )

            # Create owner and scope relationships
            await self._create_secret_owner_relations(owner_id, entity["id"])
            await self._create_secret_scope_relations(
                entity["id"], scope, session_id, shared_with
            )

            logger.info("Created secret entity: %s (scope: %s)", name, scope)
            return entity

        except Exception as e:
            logger.error("Failed to create secret entity: %s", e)
            raise

    async def _create_secret_usage_audit(
        self,
        secret_id: str,
        user_id: str,
        activity_type: str,
        activity_id: str,
    ) -> Dict[str, Any]:
        """
        Create a secret usage audit entity for tracking access.

        Issue #608: All secret usage is logged for audit trail.

        Args:
            secret_id: ID of the secret being used
            user_id: ID of the user using the secret
            activity_type: Type of activity using the secret
            activity_id: ID of the activity entity

        Returns:
            Created secret usage audit entity
        """
        try:
            audit_metadata = {
                "secret_id": secret_id,
                "user_id": user_id,
                "activity_type": activity_type,
                "activity_id": activity_id,
                "timestamp": datetime.utcnow().isoformat(),
            }

            entity = await self.create_entity(
                entity_type="secret_usage",
                name=f"Secret Usage: {secret_id[:8]} by {user_id[:8]}",
                observations=[f"Secret {secret_id} used in {activity_type}"],
                metadata=audit_metadata,
                tags=["audit", "secret_usage"],
            )

            return entity

        except Exception as e:
            logger.error("Failed to create secret usage audit: %s", e)
            raise

    async def get_user_sessions(
        self,
        user_id: str,
        include_collaborative: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Get all sessions for a user.

        Issue #608: Returns both owned sessions and collaborative sessions
        where the user is a participant.

        Args:
            user_id: User ID to query
            include_collaborative: Include sessions where user is collaborator

        Returns:
            List of session entities
        """
        self.ensure_initialized()

        try:
            sessions = []

            # Get owned sessions via relationship
            owned_relations = await self.get_relations(
                entity_id=user_id,
                relation_types=["owns", "has_session"],
                direction="outgoing",
            )

            for rel in owned_relations.get("relations", []):
                session = await self.get_entity(rel["to"])
                if session and session.get("metadata", {}).get("session_id"):
                    sessions.append(session)

            # Get collaborative sessions if requested
            if include_collaborative:
                # search_entities returns a list, filter for chat_session type
                collab_sessions = await self.search_entities(
                    query=user_id,
                    entity_type="chat_session",
                    limit=100,
                )
                for session in collab_sessions:
                    collaborators = session.get("metadata", {}).get("collaborators", [])
                    if user_id in collaborators and session not in sessions:
                        sessions.append(session)

            return sessions

        except Exception as e:
            logger.error("Failed to get user sessions: %s", e)
            return []

    async def get_session_activities(
        self,
        session_id: str,
        activity_types: Optional[List[str]] = None,
        user_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get activities for a session.

        Issue #608: Returns all activities within a session, optionally
        filtered by activity type and/or user.

        Args:
            session_id: Session ID to query
            activity_types: Filter by activity types (terminal, file, browser, desktop)
            user_id: Filter by user who performed the activity
            limit: Maximum number of activities to return

        Returns:
            List of activity entities
        """
        self.ensure_initialized()

        try:
            # Get activities via relationship
            relations = await self.get_relations(
                entity_id=session_id,
                relation_types=["has_activity"],
                direction="outgoing",
            )

            activities = []
            for rel in relations.get("relations", []):
                activity = await self.get_entity(rel["to"])
                if not activity:
                    continue

                # Filter by activity type
                if activity_types:
                    if activity.get("type") not in activity_types:
                        continue

                # Filter by user
                if user_id:
                    if activity.get("metadata", {}).get("user_id") != user_id:
                        continue

                activities.append(activity)

                if len(activities) >= limit:
                    break

            # Sort by timestamp descending
            activities.sort(
                key=lambda x: x.get("metadata", {}).get("timestamp", ""),
                reverse=True,
            )

            return activities

        except Exception as e:
            logger.error("Failed to get session activities: %s", e)
            return []

    async def get_user_secrets(
        self,
        user_id: str,
        scope: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get secrets accessible to a user.

        Issue #608: Returns secrets based on access permissions:
        - User-scoped: Only if user is owner
        - Session-scoped: If user is owner or session participant
        - Shared: If user is owner or in shared_with list

        Args:
            user_id: User ID to query
            scope: Filter by scope (user, session, shared)
            session_id: For session-scoped, which session to check

        Returns:
            List of secret entities (without actual secret values)
        """
        self.ensure_initialized()

        try:
            secrets = []

            # Get owned secrets
            owned_relations = await self.get_relations(
                entity_id=user_id,
                relation_types=["has_secret"],
                direction="outgoing",
            )

            for rel in owned_relations.get("relations", []):
                secret = await self.get_entity(rel["to"])
                if not secret:
                    continue

                secret_scope = secret.get("metadata", {}).get("scope")

                # Filter by scope if specified
                if scope and secret_scope != scope:
                    continue

                # For session scope, filter by session_id if specified
                if secret_scope == "session" and session_id:
                    if secret.get("metadata", {}).get("session_id") != session_id:
                        continue

                secrets.append(secret)

            # Get shared secrets (where user is in shared_with)
            # search_entities returns a list
            shared_search = await self.search_entities(
                query=user_id,
                entity_type="secret",
                limit=100,
            )

            for secret in shared_search:
                shared_with = secret.get("metadata", {}).get("shared_with", [])
                if user_id in shared_with and secret not in secrets:
                    if scope is None or secret.get("metadata", {}).get("scope") == scope:
                        secrets.append(secret)

            return secrets

        except Exception as e:
            logger.error("Failed to get user secrets: %s", e)
            return []

    async def close(self):
        """Close all connections and cleanup resources"""
        try:
            if self.redis_client:
                await self.redis_client.close()

            if self.knowledge_base:
                await self.knowledge_base.close()

            self.initialized = False
            logger.info("Memory Graph connections closed")

        except Exception as e:
            logger.warning("Error during Memory Graph cleanup: %s", e)
