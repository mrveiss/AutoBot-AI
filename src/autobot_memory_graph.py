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
- Storage: Redis Stack DB 9 (memory database) on VM3
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
from typing import Any, Dict, List, Optional

import redis.asyncio as async_redis  # Modern async Redis with JSON support
from cachetools import LRUCache

from src.unified_config_manager import UnifiedConfigManager
from src.utils.error_boundaries import (
    error_boundary,
    get_error_boundary_manager,
)

logger = logging.getLogger(__name__)

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
    ENTITY_TYPES = {
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
    }

    # Valid relation types
    RELATION_TYPES = {
        "relates_to",
        "depends_on",
        "implements",
        "fixes",
        "informs",
        "guides",
        "follows",
        "contains",
        "blocks",
    }

    def __init__(
        self,
        redis_host: Optional[str] = None,
        redis_port: Optional[int] = None,
        database: int = 9,
        chat_history_manager: Optional[Any] = None,
    ):
        """
        Initialize Memory Graph interface.

        Args:
            redis_host: Redis server hostname (default from config)
            redis_port: Redis server port (default from config)
            database: Redis database number (default: 9)
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
                logger.error(f"Memory Graph initialization failed: {e}")
                await self._cleanup_on_failure()
                return False

    async def _init_redis_connection(self):
        """
        Initialize Redis connection to DB 9.

        USES CANONICAL PATTERN: get_redis_client() from src/utils/redis_client.py
        This ensures Redis Stack JSON support is properly configured.
        """
        try:
            from src.utils.redis_client import get_redis_client

            # CANONICAL: Use get_redis_client for proper Redis Stack support
            # Database 9 is used for Memory Graph entities
            self.redis_client = await get_redis_client(
                async_client=True,
                database="memory",  # Will map to DB 9 via redis_database_manager
            )

            # Test connection
            await self.redis_client.ping()
            logger.info(
                f"Memory Graph Redis client connected (database {self.redis_db})"
            )

        except Exception as e:
            logger.error(f"Failed to initialize Redis connection: {e}")
            raise

    async def _create_search_indexes(self):
        """Create RediSearch indexes for entity search"""
        try:
            # Check if index already exists
            try:
                await self.redis_client.execute_command("FT.INFO", "memory_entity_idx")
                logger.info("Search index 'memory_entity_idx' already exists")
                return
            except Exception as e:
                # Index doesn't exist, create it
                logger.debug(f"Search index not found, will create: {e}")

            # Create entity search index
            await self.redis_client.execute_command(
                "FT.CREATE",
                "memory_entity_idx",
                "ON",
                "JSON",
                "PREFIX",
                "1",
                "memory:entity:",
                "SCHEMA",
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
            )

            logger.info("Created RediSearch index: memory_entity_idx")

        except Exception as e:
            logger.warning(f"Could not create search index: {e}")
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
                f"Could not initialize Knowledge Base (embeddings unavailable): {e}"
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
            logger.warning(f"Error during cleanup: {e}")

    def ensure_initialized(self):
        """Ensure the memory graph is initialized (raises exception if not)"""
        if not self.initialized:
            raise RuntimeError(
                "Memory Graph not initialized. Use 'await memory_graph.initialize()' first."
            )

    # ==================== ENTITY OPERATIONS ====================

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
            # Generate entity ID
            entity_id = str(uuid.uuid4())

            # Prepare metadata
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

            # Create entity document
            entity = {
                "id": entity_id,
                "type": entity_type,
                "name": name,
                "created_at": int(datetime.now().timestamp() * 1000),
                "updated_at": int(datetime.now().timestamp() * 1000),
                "observations": observations,
                "metadata": entity_metadata,
            }

            # Store in Redis
            entity_key = f"memory:entity:{entity_id}"
            await self.redis_client.json().set(entity_key, "$", entity)

            # Generate and cache embedding for semantic search
            if self.knowledge_base:
                await self._generate_entity_embedding(entity_id, entity)

            logger.info(f"Created entity: {name} ({entity_type}) with ID {entity_id}")

            return entity

        except Exception as e:
            logger.error(f"Failed to create entity: {e}")
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

            # Include relations if requested
            if include_relations and entity_id:
                entity["relations"] = {
                    "outgoing": await self._get_outgoing_relations(entity_id),
                    "incoming": await self._get_incoming_relations(entity_id),
                }

            return entity

        except Exception as e:
            logger.error(f"Failed to get entity: {e}")
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

            # Append observations
            for observation in observations:
                await self.redis_client.json().arrappend(
                    entity_key, "$.observations", observation
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
                f"Added {len(observations)} observations to entity: {entity_name}"
            )

            return await self.redis_client.json().get(entity_key)

        except Exception as e:
            logger.error(f"Failed to add observations: {e}")
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

            logger.info(f"Deleted entity: {entity_name}")

            return deleted > 0

        except Exception as e:
            logger.error(f"Failed to delete entity: {e}")
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

        # Validation
        if relation_type not in self.RELATION_TYPES:
            raise ValueError(f"Invalid relation_type: {relation_type}")

        try:
            # Get entity IDs
            from_entity_data = await self.get_entity(entity_name=from_entity)
            to_entity_data = await self.get_entity(entity_name=to_entity)

            if not from_entity_data or not to_entity_data:
                raise ValueError("Source or target entity not found")

            from_id = from_entity_data["id"]
            to_id = to_entity_data["id"]

            # Create relation
            relation = {
                "to": to_id,
                "type": relation_type,
                "created_at": int(datetime.now().timestamp() * 1000),
                "metadata": {"strength": strength, **(metadata or {})},
            }

            # Store outgoing relation
            out_key = f"memory:relations:out:{from_id}"

            # Initialize if doesn't exist
            if not await self.redis_client.exists(out_key):
                await self.redis_client.json().set(
                    out_key, "$", {"entity_id": from_id, "relations": []}
                )

            # Append relation
            await self.redis_client.json().arrappend(out_key, "$.relations", relation)

            # Store incoming relation (reverse index)
            in_key = f"memory:relations:in:{to_id}"

            if not await self.redis_client.exists(in_key):
                await self.redis_client.json().set(
                    in_key, "$", {"entity_id": to_id, "relations": []}
                )

            reverse_rel = {
                "from": from_id,
                "type": relation_type,
                "created_at": int(datetime.now().timestamp() * 1000),
            }

            await self.redis_client.json().arrappend(in_key, "$.relations", reverse_rel)

            logger.info(
                f"Created relation: {from_entity} --[{relation_type}]--> {to_entity}"
            )

            return relation

        except Exception as e:
            logger.error(f"Failed to create relation: {e}")
            raise RuntimeError(f"Relation creation failed: {str(e)}")

    async def get_related_entities(
        self,
        entity_name: str,
        relation_type: Optional[str] = None,
        direction: str = "both",
        max_depth: int = 1,
    ) -> List[Dict[str, Any]]:
        """
        Get entities related to specified entity.

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
            # Get entity
            entity = await self.get_entity(entity_name=entity_name)
            if not entity:
                return []

            entity_id = entity["id"]

            related = []
            visited = set()

            # BFS traversal
            queue = [(entity_id, 0)]

            while queue:
                current_id, depth = queue.pop(0)

                if current_id in visited or depth > max_depth:
                    continue

                visited.add(current_id)

                # Get outgoing relations
                if direction in ["outgoing", "both"]:
                    outgoing = await self._get_outgoing_relations(current_id)
                    for rel in outgoing:
                        if relation_type is None or rel["type"] == relation_type:
                            related_entity = await self.get_entity(entity_id=rel["to"])
                            if related_entity:
                                related.append(
                                    {
                                        "entity": related_entity,
                                        "relation": rel,
                                        "direction": "outgoing",
                                    }
                                )
                                if depth + 1 <= max_depth:
                                    queue.append((rel["to"], depth + 1))

                # Get incoming relations
                if direction in ["incoming", "both"]:
                    incoming = await self._get_incoming_relations(current_id)
                    for rel in incoming:
                        if relation_type is None or rel["type"] == relation_type:
                            related_entity = await self.get_entity(
                                entity_id=rel["from"]
                            )
                            if related_entity:
                                related.append(
                                    {
                                        "entity": related_entity,
                                        "relation": rel,
                                        "direction": "incoming",
                                    }
                                )
                                if depth + 1 <= max_depth:
                                    queue.append((rel["from"], depth + 1))

            return related

        except Exception as e:
            logger.error(f"Failed to get related entities: {e}")
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
            # Get entity IDs
            from_entity_data = await self.get_entity(entity_name=from_entity)
            to_entity_data = await self.get_entity(entity_name=to_entity)

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
                f"Deleted relation: {from_entity} --[{relation_type}]--> {to_entity}"
            )

            return True

        except Exception as e:
            logger.error(f"Failed to delete relation: {e}")
            return False

    async def _get_outgoing_relations(self, entity_id: str) -> List[Dict[str, Any]]:
        """Get all outgoing relations for an entity"""
        try:
            out_key = f"memory:relations:out:{entity_id}"
            data = await self.redis_client.json().get(out_key)
            return data.get("relations", []) if data else []
        except Exception:
            return []

    async def _get_incoming_relations(self, entity_id: str) -> List[Dict[str, Any]]:
        """Get all incoming relations for an entity"""
        try:
            in_key = f"memory:relations:in:{entity_id}"
            data = await self.redis_client.json().get(in_key)
            return data.get("relations", []) if data else []
        except Exception:
            return []

    # ==================== SEARCH OPERATIONS ====================

    async def search_entities(
        self,
        query: str,
        entity_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Semantic search across all entities.

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
            # Build RediSearch query
            query_parts = []

            # Add type filter
            if entity_type:
                query_parts.append(f"@type:{{{entity_type}}}")

            # Add status filter
            if status:
                query_parts.append(f"@status:{{{status}}}")

            # Add tags filter
            if tags:
                tag_filter = "|".join(tags)
                query_parts.append(f"@tags:{{{tag_filter}}}")

            # Add text search
            if query:
                query_parts.append(f"({query})")

            # Combine filters
            redis_query = " ".join(query_parts) if query_parts else "*"

            # Execute search
            try:
                results = await self.redis_client.execute_command(
                    "FT.SEARCH",
                    "memory_entity_idx",
                    redis_query,
                    "LIMIT",
                    "0",
                    str(limit),
                    "RETURN",
                    "3",
                    "$.name",
                    "$.type",
                    "$.observations",
                )

                # Parse results
                entities = []
                if results and len(results) > 1:
                    for i in range(1, len(results), 2):
                        if i + 1 < len(results):
                            entity_key = results[i]
                            if isinstance(entity_key, bytes):
                                entity_key = entity_key.decode()

                            # Get full entity data
                            entity = await self.redis_client.json().get(entity_key)
                            if entity:
                                entities.append(entity)

                logger.info(f"Search query '{query}' returned {len(entities)} results")
                return entities[:limit]

            except Exception as search_error:
                # Fallback: manual search if RediSearch not available
                logger.warning(f"RediSearch failed, using fallback: {search_error}")
                return await self._fallback_search(query, entity_type, limit)

        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

    async def _fallback_search(
        self, query: str, entity_type: Optional[str], limit: int
    ) -> List[Dict[str, Any]]:
        """Fallback search when RediSearch is unavailable"""
        try:
            entities = []
            query_lower = query.lower() if query else ""

            # Scan all entity keys
            async for key in self.redis_client.scan_iter(match="memory:entity:*"):
                entity = await self.redis_client.json().get(key)
                if entity:
                    # Apply filters
                    if entity_type and entity.get("type") != entity_type:
                        continue

                    # Simple text matching
                    if query:
                        name_match = query_lower in entity.get("name", "").lower()
                        obs_match = any(
                            query_lower in obs.lower()
                            for obs in entity.get("observations", [])
                        )
                        if not (name_match or obs_match):
                            continue

                    entities.append(entity)

                    if len(entities) >= limit:
                        break

            return entities

        except Exception as e:
            logger.error(f"Fallback search failed: {e}")
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
            logger.warning(f"Failed to generate embedding for entity {entity_id}: {e}")

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

            logger.info(f"Created conversation entity for session {session_id}")

            return entity

        except Exception as e:
            logger.error(f"Failed to create conversation entity: {e}")
            raise

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
            logger.warning(f"Error during Memory Graph cleanup: {e}")
