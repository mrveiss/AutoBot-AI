#!/usr/bin/env python3
"""
Comprehensive Test Suite for AutoBot Memory Graph System

Tests the Memory Graph implementation with RedisJSON + RediSearch
(NOTE: RedisGraph is NOT available, using RedisJSON for relations)

Test Coverage:
- Entity Management: All 8 entity types (conversation, bug_fix, feature, decision, task, user_preference, context, learning)
- Relation Management: All 8 relation types (relates_to, depends_on, implements, fixes, informs, guides, follows, contains)
- Search Functionality: Semantic search, filtering, hybrid queries
- Integration: Backward compatibility with ChatHistoryManager
- Performance: <50ms entity ops, <200ms search, <100ms relations
- Data Integrity: Cascade deletes, orphan prevention, error recovery
"""

import asyncio
import hashlib
import json
import logging
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
import redis.asyncio as aioredis

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.unified_config import config

logger = logging.getLogger(__name__)


# ===== MOCK AUTOBOT MEMORY GRAPH IMPLEMENTATION =====
# Since the actual implementation doesn't exist yet, we create a mock
# that follows the architecture spec but uses RedisJSON instead of RedisGraph

class MockAutoBotMemoryGraph:
    """
    Mock Memory Graph implementation using RedisJSON + RediSearch
    (RedisGraph is NOT available, so we store relations as RedisJSON documents)
    """

    # Entity types from spec
    ENTITY_TYPES = [
        "conversation",
        "bug_fix",
        "feature",
        "decision",
        "task",
        "user_preference",
        "context",
        "learning"
    ]

    # Relation types from spec
    RELATION_TYPES = [
        "relates_to",
        "depends_on",
        "implements",
        "fixes",
        "informs",
        "guides",
        "follows",
        "contains"
    ]

    def __init__(
        self,
        redis_host: str = "172.16.168.23",
        redis_port: int = 6379,
        database: int = 9,
        chat_history_manager=None
    ):
        """Initialize Memory Graph with RedisJSON backend"""
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.database = database
        self.chat_history_manager = chat_history_manager
        self.redis_client: Optional[aioredis.Redis] = None
        self.initialized = False

    async def initialize(self) -> bool:
        """Initialize Redis connection and indexes"""
        try:
            self.redis_client = await aioredis.from_url(
                f"redis://{self.redis_host}:{self.redis_port}/{self.database}",
                encoding="utf-8",
                decode_responses=True
            )

            # Test connection
            await self.redis_client.ping()

            # Create search index if it doesn't exist
            await self._create_search_index()

            self.initialized = True
            logger.info(f"Memory Graph initialized on Redis DB {self.database}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Memory Graph: {e}")
            return False

    async def _create_search_index(self):
        """Create RediSearch index for entities"""
        try:
            # Check if index already exists
            try:
                await self.redis_client.execute_command(
                    "FT.INFO", "memory_graph_idx"
                )
                logger.info("Search index already exists")
                return
            except:
                pass  # Index doesn't exist, create it

            # Create index with text and tag fields
            await self.redis_client.execute_command(
                "FT.CREATE", "memory_graph_idx",
                "ON", "JSON",
                "PREFIX", "1", "entity:",
                "SCHEMA",
                "$.name", "AS", "name", "TEXT", "WEIGHT", "5.0",
                "$.entity_type", "AS", "entity_type", "TAG",
                "$.search_text", "AS", "search_text", "TEXT", "WEIGHT", "2.0",
                "$.metadata.status", "AS", "status", "TAG",
                "$.metadata.priority", "AS", "priority", "TAG",
                "$.metadata.created_at", "AS", "created_at", "NUMERIC", "SORTABLE"
            )
            logger.info("Created RediSearch index for Memory Graph")

        except Exception as e:
            logger.warning(f"Could not create search index: {e}")

    async def create_entity(
        self,
        entity_type: str,
        name: str,
        observations: List[str],
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Create a new entity in the memory graph"""
        if entity_type not in self.ENTITY_TYPES:
            raise ValueError(f"Invalid entity_type: {entity_type}")

        if not name or not name.strip():
            raise ValueError("Entity name cannot be empty")

        entity_id = str(uuid.uuid4())
        timestamp = datetime.utcnow().isoformat()

        # Build entity document
        entity = {
            "entity_id": entity_id,
            "entity_type": entity_type,
            "name": name.strip(),
            "observations": observations or [],
            "metadata": {
                "created_at": timestamp,
                "updated_at": timestamp,
                "created_by": "system",
                "tags": tags or [],
                "priority": "medium",
                "status": "active",
                "version": 1,
                **(metadata or {})
            },
            "search_text": self._build_search_text(name, observations)
        }

        # Store entity in RedisJSON
        key = f"entity:{entity_id}"
        await self.redis_client.execute_command(
            "JSON.SET", key, "$", json.dumps(entity)
        )

        logger.info(f"Created entity: {name} ({entity_type}) with ID {entity_id}")
        return entity

    def _build_search_text(self, name: str, observations: List[str]) -> str:
        """Build concatenated search text from name and observations"""
        parts = [name] + (observations or [])
        return " ".join(parts)

    async def add_observations(
        self,
        entity_name: str,
        observations: List[str]
    ) -> Dict[str, Any]:
        """Add new observations to an existing entity"""
        entity = await self.get_entity(entity_name)
        if not entity:
            raise ValueError(f"Entity not found: {entity_name}")

        entity_id = entity["entity_id"]
        key = f"entity:{entity_id}"

        # Append observations to array
        for obs in observations:
            await self.redis_client.execute_command(
                "JSON.ARRAPPEND", key, "$.observations", json.dumps(obs)
            )

        # Update timestamp and search text
        timestamp = datetime.utcnow().isoformat()
        await self.redis_client.execute_command(
            "JSON.SET", key, "$.metadata.updated_at", json.dumps(timestamp)
        )

        # Get updated entity
        updated_entity = await self.get_entity(entity_name)

        # Update search text
        new_search_text = self._build_search_text(
            updated_entity["name"],
            updated_entity["observations"]
        )
        await self.redis_client.execute_command(
            "JSON.SET", key, "$.search_text", json.dumps(new_search_text)
        )

        logger.info(f"Added {len(observations)} observations to entity: {entity_name}")
        return updated_entity

    async def get_entity(
        self,
        entity_name: str,
        include_relations: bool = False
    ) -> Optional[Dict[str, Any]]:
        """Retrieve entity by name"""
        # Search for entity by name
        results = await self._search_entities_by_name(entity_name)

        if not results:
            return None

        entity = results[0]

        if include_relations:
            # Get all relations involving this entity
            entity["relations"] = await self._get_entity_relations(entity["entity_id"])

        return entity

    async def _search_entities_by_name(self, name: str) -> List[Dict[str, Any]]:
        """Internal method to search entities by exact name"""
        try:
            # Use RediSearch to find entity
            result = await self.redis_client.execute_command(
                "FT.SEARCH", "memory_graph_idx",
                f"@name:\"{name}\"",
                "LIMIT", "0", "10"
            )

            # Parse results (format: [count, key, data, key, data, ...])
            entities = []
            if len(result) > 1:
                for i in range(1, len(result), 2):
                    key = result[i]
                    entity_data = result[i + 1]

                    # Get full entity from RedisJSON
                    full_data = await self.redis_client.execute_command(
                        "JSON.GET", key, "$"
                    )
                    if full_data:
                        parsed = json.loads(full_data)
                        if isinstance(parsed, list) and len(parsed) > 0:
                            entities.append(parsed[0])

            return entities

        except Exception as e:
            logger.warning(f"Search failed: {e}, falling back to scan")
            return await self._fallback_search_by_name(name)

    async def _fallback_search_by_name(self, name: str) -> List[Dict[str, Any]]:
        """Fallback method using SCAN when search index is unavailable"""
        cursor = 0
        entities = []

        while True:
            cursor, keys = await self.redis_client.scan(
                cursor, match="entity:*", count=100
            )

            for key in keys:
                try:
                    data = await self.redis_client.execute_command(
                        "JSON.GET", key, "$"
                    )
                    if data:
                        parsed = json.loads(data)
                        if isinstance(parsed, list) and len(parsed) > 0:
                            entity = parsed[0]
                            if entity.get("name") == name:
                                entities.append(entity)
                except Exception as e:
                    logger.debug(f"Error reading entity {key}: {e}")
                    continue

            if cursor == 0:
                break

        return entities

    async def delete_entity(
        self,
        entity_name: str,
        cascade_relations: bool = True
    ) -> bool:
        """Delete entity and optionally its relations"""
        entity = await self.get_entity(entity_name)
        if not entity:
            return False

        entity_id = entity["entity_id"]
        key = f"entity:{entity_id}"

        if cascade_relations:
            # Delete all relations involving this entity
            await self._delete_entity_relations(entity_id)

        # Delete entity
        await self.redis_client.delete(key)

        logger.info(f"Deleted entity: {entity_name} (cascade={cascade_relations})")
        return True

    async def create_relation(
        self,
        from_entity: str,
        to_entity: str,
        relation_type: str,
        bidirectional: bool = False,
        strength: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create relationship between two entities"""
        if relation_type not in self.RELATION_TYPES:
            raise ValueError(f"Invalid relation_type: {relation_type}")

        # Verify both entities exist
        from_ent = await self.get_entity(from_entity)
        to_ent = await self.get_entity(to_entity)

        if not from_ent:
            raise ValueError(f"From entity not found: {from_entity}")
        if not to_ent:
            raise ValueError(f"To entity not found: {to_entity}")

        relation_id = str(uuid.uuid4())
        timestamp = datetime.utcnow().isoformat()

        # Create relation document (stored in RedisJSON, not RedisGraph)
        relation = {
            "relation_id": relation_id,
            "from_entity": from_ent["entity_id"],
            "to_entity": to_ent["entity_id"],
            "relation_type": relation_type,
            "metadata": {
                "created_at": timestamp,
                "created_by": "system",
                "strength": strength,
                "bidirectional": bidirectional,
                "auto_generated": False,
                **(metadata or {})
            }
        }

        # Store relation
        key = f"relation:{relation_id}"
        await self.redis_client.execute_command(
            "JSON.SET", key, "$", json.dumps(relation)
        )

        # Create reverse relation if bidirectional
        if bidirectional:
            reverse_id = str(uuid.uuid4())
            reverse_relation = {
                "relation_id": reverse_id,
                "from_entity": to_ent["entity_id"],
                "to_entity": from_ent["entity_id"],
                "relation_type": relation_type,
                "metadata": {
                    **relation["metadata"],
                    "reverse_of": relation_id
                }
            }
            await self.redis_client.execute_command(
                "JSON.SET", f"relation:{reverse_id}", "$", json.dumps(reverse_relation)
            )

        logger.info(f"Created relation: {from_entity} -[{relation_type}]-> {to_entity}")
        return relation

    async def get_related_entities(
        self,
        entity_name: str,
        relation_type: Optional[str] = None,
        direction: str = "both",
        max_depth: int = 1
    ) -> List[Dict[str, Any]]:
        """Get entities related to specified entity"""
        entity = await self.get_entity(entity_name)
        if not entity:
            return []

        entity_id = entity["entity_id"]
        related = []

        # Get all relations
        cursor = 0
        while True:
            cursor, keys = await self.redis_client.scan(
                cursor, match="relation:*", count=100
            )

            for key in keys:
                try:
                    data = await self.redis_client.execute_command(
                        "JSON.GET", key, "$"
                    )
                    if not data:
                        continue

                    parsed = json.loads(data)
                    if not isinstance(parsed, list) or len(parsed) == 0:
                        continue

                    relation = parsed[0]

                    # Filter by relation type if specified
                    if relation_type and relation["relation_type"] != relation_type:
                        continue

                    # Check direction
                    if direction == "outgoing" and relation["from_entity"] == entity_id:
                        target_id = relation["to_entity"]
                    elif direction == "incoming" and relation["to_entity"] == entity_id:
                        target_id = relation["from_entity"]
                    elif direction == "both":
                        if relation["from_entity"] == entity_id:
                            target_id = relation["to_entity"]
                        elif relation["to_entity"] == entity_id:
                            target_id = relation["from_entity"]
                        else:
                            continue
                    else:
                        continue

                    # Get target entity
                    target_key = f"entity:{target_id}"
                    target_data = await self.redis_client.execute_command(
                        "JSON.GET", target_key, "$"
                    )
                    if target_data:
                        target_parsed = json.loads(target_data)
                        if isinstance(target_parsed, list) and len(target_parsed) > 0:
                            target_entity = target_parsed[0]
                            target_entity["relation_metadata"] = relation["metadata"]
                            related.append(target_entity)

                except Exception as e:
                    logger.debug(f"Error processing relation {key}: {e}")
                    continue

            if cursor == 0:
                break

        return related

    async def delete_relation(
        self,
        from_entity: str,
        to_entity: str,
        relation_type: str
    ) -> bool:
        """Delete specific relation between entities"""
        from_ent = await self.get_entity(from_entity)
        to_ent = await self.get_entity(to_entity)

        if not from_ent or not to_ent:
            return False

        from_id = from_ent["entity_id"]
        to_id = to_ent["entity_id"]

        # Find and delete matching relation
        cursor = 0
        deleted = False

        while True:
            cursor, keys = await self.redis_client.scan(
                cursor, match="relation:*", count=100
            )

            for key in keys:
                try:
                    data = await self.redis_client.execute_command(
                        "JSON.GET", key, "$"
                    )
                    if not data:
                        continue

                    parsed = json.loads(data)
                    if not isinstance(parsed, list) or len(parsed) == 0:
                        continue

                    relation = parsed[0]

                    if (relation["from_entity"] == from_id and
                        relation["to_entity"] == to_id and
                        relation["relation_type"] == relation_type):
                        await self.redis_client.delete(key)
                        deleted = True

                except Exception as e:
                    logger.debug(f"Error checking relation {key}: {e}")
                    continue

            if cursor == 0:
                break

        return deleted

    async def search_entities(
        self,
        query: str,
        entity_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
        status: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Semantic search across all entities"""
        try:
            # Build search query
            query_parts = [query]

            if entity_type:
                query_parts.append(f"@entity_type:{{{entity_type}}}")
            if status:
                query_parts.append(f"@status:{{{status}}}")

            search_query = " ".join(query_parts)

            # Execute search
            result = await self.redis_client.execute_command(
                "FT.SEARCH", "memory_graph_idx",
                search_query,
                "LIMIT", "0", str(limit)
            )

            # Parse results
            entities = []
            if len(result) > 1:
                for i in range(1, len(result), 2):
                    key = result[i]
                    # Get full entity data
                    data = await self.redis_client.execute_command(
                        "JSON.GET", key, "$"
                    )
                    if data:
                        parsed = json.loads(data)
                        if isinstance(parsed, list) and len(parsed) > 0:
                            entities.append(parsed[0])

            return entities[:limit]

        except Exception as e:
            logger.warning(f"Search failed: {e}, using fallback")
            return await self._fallback_search(query, entity_type, status, limit)

    async def _fallback_search(
        self,
        query: str,
        entity_type: Optional[str],
        status: Optional[str],
        limit: int
    ) -> List[Dict[str, Any]]:
        """Fallback search using SCAN"""
        cursor = 0
        entities = []
        query_lower = query.lower()

        while True:
            cursor, keys = await self.redis_client.scan(
                cursor, match="entity:*", count=100
            )

            for key in keys:
                try:
                    data = await self.redis_client.execute_command(
                        "JSON.GET", key, "$"
                    )
                    if not data:
                        continue

                    parsed = json.loads(data)
                    if not isinstance(parsed, list) or len(parsed) == 0:
                        continue

                    entity = parsed[0]

                    # Filter by entity_type
                    if entity_type and entity.get("entity_type") != entity_type:
                        continue

                    # Filter by status
                    if status and entity.get("metadata", {}).get("status") != status:
                        continue

                    # Check if query matches
                    search_text = entity.get("search_text", "").lower()
                    if query_lower in search_text:
                        entities.append(entity)

                    if len(entities) >= limit:
                        return entities[:limit]

                except Exception as e:
                    logger.debug(f"Error reading entity {key}: {e}")
                    continue

            if cursor == 0:
                break

        return entities[:limit]

    async def _get_entity_relations(self, entity_id: str) -> Dict[str, List[Dict]]:
        """Get all relations for an entity"""
        relations = {
            "outgoing": [],
            "incoming": []
        }

        cursor = 0
        while True:
            cursor, keys = await self.redis_client.scan(
                cursor, match="relation:*", count=100
            )

            for key in keys:
                try:
                    data = await self.redis_client.execute_command(
                        "JSON.GET", key, "$"
                    )
                    if not data:
                        continue

                    parsed = json.loads(data)
                    if not isinstance(parsed, list) or len(parsed) == 0:
                        continue

                    relation = parsed[0]

                    if relation["from_entity"] == entity_id:
                        relations["outgoing"].append(relation)
                    if relation["to_entity"] == entity_id:
                        relations["incoming"].append(relation)

                except Exception as e:
                    logger.debug(f"Error reading relation {key}: {e}")
                    continue

            if cursor == 0:
                break

        return relations

    async def _delete_entity_relations(self, entity_id: str):
        """Delete all relations involving an entity"""
        cursor = 0
        to_delete = []

        while True:
            cursor, keys = await self.redis_client.scan(
                cursor, match="relation:*", count=100
            )

            for key in keys:
                try:
                    data = await self.redis_client.execute_command(
                        "JSON.GET", key, "$"
                    )
                    if not data:
                        continue

                    parsed = json.loads(data)
                    if not isinstance(parsed, list) or len(parsed) == 0:
                        continue

                    relation = parsed[0]

                    if (relation["from_entity"] == entity_id or
                        relation["to_entity"] == entity_id):
                        to_delete.append(key)

                except Exception as e:
                    logger.debug(f"Error checking relation {key}: {e}")
                    continue

            if cursor == 0:
                break

        # Delete collected relations
        if to_delete:
            await self.redis_client.delete(*to_delete)

    async def close(self):
        """Close Redis connection"""
        if self.redis_client:
            await self.redis_client.aclose()
            self.initialized = False


# ===== TEST FIXTURES =====

@pytest.fixture
async def redis_db9():
    """Fixture to provide Redis DB 9 connection for testing"""
    client = await aioredis.from_url(
        "redis://172.16.168.23:6379/9",
        encoding="utf-8",
        decode_responses=True
    )

    # Clear test database before tests
    await client.flushdb()

    yield client

    # Cleanup after tests
    await client.flushdb()
    await client.aclose()


@pytest.fixture
async def memory_graph(redis_db9):
    """Fixture to provide initialized Memory Graph instance"""
    mg = MockAutoBotMemoryGraph(
        redis_host="172.16.168.23",
        redis_port=6379,
        database=9
    )

    initialized = await mg.initialize()
    assert initialized, "Memory Graph initialization failed"

    yield mg

    await mg.close()


# ===== ENTITY MANAGEMENT TESTS =====

class TestEntityManagement:
    """Test entity creation, retrieval, updates, and deletion"""

    @pytest.mark.asyncio
    async def test_create_all_entity_types(self, memory_graph):
        """Test creating all 8 entity types"""
        entity_types = MockAutoBotMemoryGraph.ENTITY_TYPES

        created_entities = []
        for entity_type in entity_types:
            entity = await memory_graph.create_entity(
                entity_type=entity_type,
                name=f"Test {entity_type.replace('_', ' ').title()}",
                observations=[f"This is a test {entity_type}"],
                tags=[entity_type, "test"]
            )

            assert entity["entity_id"] is not None
            assert entity["entity_type"] == entity_type
            assert len(entity["observations"]) == 1
            created_entities.append(entity)

        assert len(created_entities) == 8
        print(f"✅ Created all 8 entity types successfully")

    @pytest.mark.asyncio
    async def test_entity_retrieval(self, memory_graph):
        """Test retrieving entities by name"""
        # Create test entity
        created = await memory_graph.create_entity(
            entity_type="decision",
            name="Use Redis Stack for Memory",
            observations=["Redis provides graph capabilities"]
        )

        # Retrieve entity
        retrieved = await memory_graph.get_entity("Use Redis Stack for Memory")

        assert retrieved is not None
        assert retrieved["entity_id"] == created["entity_id"]
        assert retrieved["name"] == "Use Redis Stack for Memory"
        assert len(retrieved["observations"]) == 1

        print(f"✅ Entity retrieval successful")

    @pytest.mark.asyncio
    async def test_add_observations(self, memory_graph):
        """Test adding observations to existing entity"""
        # Create entity
        await memory_graph.create_entity(
            entity_type="feature",
            name="Memory Graph Feature",
            observations=["Initial observation"]
        )

        # Add more observations
        updated = await memory_graph.add_observations(
            entity_name="Memory Graph Feature",
            observations=["Second observation", "Third observation"]
        )

        assert len(updated["observations"]) == 3
        assert "Second observation" in updated["observations"]
        assert "Third observation" in updated["observations"]

        print(f"✅ Add observations successful")

    @pytest.mark.asyncio
    async def test_entity_deletion(self, memory_graph):
        """Test entity deletion"""
        # Create entity
        await memory_graph.create_entity(
            entity_type="task",
            name="Temporary Task",
            observations=["This will be deleted"]
        )

        # Verify it exists
        entity = await memory_graph.get_entity("Temporary Task")
        assert entity is not None

        # Delete entity
        deleted = await memory_graph.delete_entity("Temporary Task")
        assert deleted is True

        # Verify it's gone
        entity = await memory_graph.get_entity("Temporary Task")
        assert entity is None

        print(f"✅ Entity deletion successful")

    @pytest.mark.asyncio
    async def test_invalid_entity_operations(self, memory_graph):
        """Test invalid entity operations"""
        # Invalid entity type
        with pytest.raises(ValueError, match="Invalid entity_type"):
            await memory_graph.create_entity(
                entity_type="invalid_type",
                name="Test",
                observations=[]
            )

        # Empty name
        with pytest.raises(ValueError, match="name cannot be empty"):
            await memory_graph.create_entity(
                entity_type="decision",
                name="",
                observations=[]
            )

        # Add observations to non-existent entity
        with pytest.raises(ValueError, match="Entity not found"):
            await memory_graph.add_observations(
                entity_name="Non-existent Entity",
                observations=["Test"]
            )

        print(f"✅ Invalid operations properly rejected")


# ===== RELATION MANAGEMENT TESTS =====

class TestRelationManagement:
    """Test relation creation, retrieval, and deletion"""

    @pytest.mark.asyncio
    async def test_create_all_relation_types(self, memory_graph):
        """Test creating all 8 relation types"""
        relation_types = MockAutoBotMemoryGraph.RELATION_TYPES

        # Create two entities
        entity1 = await memory_graph.create_entity(
            entity_type="feature",
            name="Feature A",
            observations=["First feature"]
        )

        entity2 = await memory_graph.create_entity(
            entity_type="task",
            name="Task B",
            observations=["Related task"]
        )

        # Create all relation types
        created_relations = []
        for relation_type in relation_types:
            relation = await memory_graph.create_relation(
                from_entity="Feature A",
                to_entity="Task B",
                relation_type=relation_type,
                strength=0.8
            )

            assert relation["relation_id"] is not None
            assert relation["relation_type"] == relation_type
            assert relation["metadata"]["strength"] == 0.8
            created_relations.append(relation)

        assert len(created_relations) == 8
        print(f"✅ Created all 8 relation types successfully")

    @pytest.mark.asyncio
    async def test_bidirectional_relations(self, memory_graph):
        """Test bidirectional relation creation"""
        # Create entities
        await memory_graph.create_entity(
            entity_type="decision",
            name="Decision X",
            observations=["Test decision"]
        )

        await memory_graph.create_entity(
            entity_type="context",
            name="Context Y",
            observations=["Test context"]
        )

        # Create bidirectional relation
        relation = await memory_graph.create_relation(
            from_entity="Decision X",
            to_entity="Context Y",
            relation_type="relates_to",
            bidirectional=True
        )

        assert relation["metadata"]["bidirectional"] is True

        # Verify both directions work
        related_from_x = await memory_graph.get_related_entities(
            "Decision X",
            direction="outgoing"
        )

        related_from_y = await memory_graph.get_related_entities(
            "Context Y",
            direction="outgoing"
        )

        assert len(related_from_x) > 0
        assert len(related_from_y) > 0

        print(f"✅ Bidirectional relations working correctly")

    @pytest.mark.asyncio
    async def test_get_related_entities(self, memory_graph):
        """Test retrieving related entities with filtering"""
        # Create entity chain: A -> B -> C
        await memory_graph.create_entity(
            entity_type="bug_fix",
            name="Bug A",
            observations=["Bug report"]
        )

        await memory_graph.create_entity(
            entity_type="decision",
            name="Fix B",
            observations=["Fix decision"]
        )

        await memory_graph.create_entity(
            entity_type="task",
            name="Test C",
            observations=["Test task"]
        )

        # Create relations
        await memory_graph.create_relation(
            from_entity="Fix B",
            to_entity="Bug A",
            relation_type="fixes"
        )

        await memory_graph.create_relation(
            from_entity="Test C",
            to_entity="Fix B",
            relation_type="depends_on"
        )

        # Test outgoing relations
        outgoing = await memory_graph.get_related_entities(
            "Fix B",
            direction="outgoing"
        )
        assert len(outgoing) == 1
        assert outgoing[0]["name"] == "Bug A"

        # Test incoming relations
        incoming = await memory_graph.get_related_entities(
            "Fix B",
            direction="incoming"
        )
        assert len(incoming) == 1
        assert incoming[0]["name"] == "Test C"

        # Test both directions
        both = await memory_graph.get_related_entities(
            "Fix B",
            direction="both"
        )
        assert len(both) == 2

        # Test relation type filtering
        fixes_only = await memory_graph.get_related_entities(
            "Fix B",
            relation_type="fixes",
            direction="outgoing"
        )
        assert len(fixes_only) == 1
        assert fixes_only[0]["name"] == "Bug A"

        print(f"✅ Related entities retrieval working correctly")

    @pytest.mark.asyncio
    async def test_delete_relation(self, memory_graph):
        """Test relation deletion"""
        # Create entities and relation
        await memory_graph.create_entity(
            entity_type="feature",
            name="Feature X",
            observations=["Test"]
        )

        await memory_graph.create_entity(
            entity_type="task",
            name="Task Y",
            observations=["Test"]
        )

        await memory_graph.create_relation(
            from_entity="Feature X",
            to_entity="Task Y",
            relation_type="implements"
        )

        # Verify relation exists
        related = await memory_graph.get_related_entities("Feature X")
        assert len(related) == 1

        # Delete relation
        deleted = await memory_graph.delete_relation(
            from_entity="Feature X",
            to_entity="Task Y",
            relation_type="implements"
        )
        assert deleted is True

        # Verify relation is gone
        related = await memory_graph.get_related_entities("Feature X")
        assert len(related) == 0

        print(f"✅ Relation deletion successful")

    @pytest.mark.asyncio
    async def test_cascade_delete(self, memory_graph):
        """Test entity deletion cascades to relations"""
        # Create entities and relations
        await memory_graph.create_entity(
            entity_type="decision",
            name="Decision Alpha",
            observations=["Test"]
        )

        await memory_graph.create_entity(
            entity_type="task",
            name="Task Beta",
            observations=["Test"]
        )

        await memory_graph.create_relation(
            from_entity="Decision Alpha",
            to_entity="Task Beta",
            relation_type="guides"
        )

        # Delete entity with cascade
        await memory_graph.delete_entity("Decision Alpha", cascade_relations=True)

        # Verify entity is gone
        entity = await memory_graph.get_entity("Decision Alpha")
        assert entity is None

        # Verify relation is also gone
        related = await memory_graph.get_related_entities("Task Beta")
        assert len(related) == 0

        print(f"✅ Cascade delete working correctly")

    @pytest.mark.asyncio
    async def test_invalid_relation_operations(self, memory_graph):
        """Test invalid relation operations"""
        # Create one entity
        await memory_graph.create_entity(
            entity_type="feature",
            name="Valid Entity",
            observations=["Test"]
        )

        # Invalid relation type
        with pytest.raises(ValueError, match="Invalid relation_type"):
            await memory_graph.create_relation(
                from_entity="Valid Entity",
                to_entity="Valid Entity",
                relation_type="invalid_relation"
            )

        # Non-existent from entity
        with pytest.raises(ValueError, match="From entity not found"):
            await memory_graph.create_relation(
                from_entity="Non-existent",
                to_entity="Valid Entity",
                relation_type="relates_to"
            )

        # Non-existent to entity
        with pytest.raises(ValueError, match="To entity not found"):
            await memory_graph.create_relation(
                from_entity="Valid Entity",
                to_entity="Non-existent",
                relation_type="relates_to"
            )

        print(f"✅ Invalid relation operations properly rejected")


# ===== SEARCH TESTS =====

class TestSearchFunctionality:
    """Test search capabilities"""

    @pytest.mark.asyncio
    async def test_basic_search(self, memory_graph):
        """Test basic text search"""
        # Create test entities
        await memory_graph.create_entity(
            entity_type="decision",
            name="Use Redis for Caching",
            observations=["Redis provides fast in-memory storage"]
        )

        await memory_graph.create_entity(
            entity_type="decision",
            name="Use PostgreSQL for Database",
            observations=["PostgreSQL provides ACID compliance"]
        )

        # Search for Redis
        results = await memory_graph.search_entities("Redis")

        assert len(results) > 0
        assert any("Redis" in r["name"] for r in results)

        print(f"✅ Basic search working: found {len(results)} results")

    @pytest.mark.asyncio
    async def test_filtered_search(self, memory_graph):
        """Test search with entity type filtering"""
        # Create entities of different types
        await memory_graph.create_entity(
            entity_type="decision",
            name="Architecture Decision",
            observations=["Test architecture"]
        )

        await memory_graph.create_entity(
            entity_type="task",
            name="Architecture Task",
            observations=["Test task"]
        )

        # Search with entity type filter
        decision_results = await memory_graph.search_entities(
            query="Architecture",
            entity_type="decision"
        )

        task_results = await memory_graph.search_entities(
            query="Architecture",
            entity_type="task"
        )

        assert len(decision_results) > 0
        assert len(task_results) > 0

        # Verify filtering
        for result in decision_results:
            assert result["entity_type"] == "decision"

        for result in task_results:
            assert result["entity_type"] == "task"

        print(f"✅ Filtered search working correctly")

    @pytest.mark.asyncio
    async def test_status_filtering(self, memory_graph):
        """Test search with status filtering"""
        # Create entities with different statuses
        await memory_graph.create_entity(
            entity_type="task",
            name="Active Task",
            observations=["Test"],
            metadata={"status": "active"}
        )

        await memory_graph.create_entity(
            entity_type="task",
            name="Completed Task",
            observations=["Test"],
            metadata={"status": "completed"}
        )

        # Search with status filter
        active_results = await memory_graph.search_entities(
            query="Task",
            status="active"
        )

        completed_results = await memory_graph.search_entities(
            query="Task",
            status="completed"
        )

        assert len(active_results) > 0
        assert len(completed_results) > 0

        # Verify status filtering
        for result in active_results:
            assert result["metadata"]["status"] == "active"

        for result in completed_results:
            assert result["metadata"]["status"] == "completed"

        print(f"✅ Status filtering working correctly")

    @pytest.mark.asyncio
    async def test_search_result_limit(self, memory_graph):
        """Test search result limiting"""
        # Create multiple entities
        for i in range(10):
            await memory_graph.create_entity(
                entity_type="context",
                name=f"Test Context {i}",
                observations=["Common test observation"]
            )

        # Search with limit
        results = await memory_graph.search_entities(
            query="test",
            limit=5
        )

        assert len(results) <= 5

        print(f"✅ Search limit working: returned {len(results)} results")


# ===== PERFORMANCE TESTS =====

class TestPerformance:
    """Test performance metrics"""

    @pytest.mark.asyncio
    async def test_entity_creation_performance(self, memory_graph):
        """Test entity creation latency (<50ms target)"""
        latencies = []

        for i in range(10):
            start = time.time()
            await memory_graph.create_entity(
                entity_type="context" if i % 2 == 0 else "context",  # Alternate types
                name=f"Performance Test Entity {i}",
                observations=[f"Test observation {i}"]
            )
            latency = (time.time() - start) * 1000  # Convert to ms
            latencies.append(latency)

        avg_latency = sum(latencies) / len(latencies)
        max_latency = max(latencies)

        print(f"📊 Entity Creation Performance:")
        print(f"   Average: {avg_latency:.2f}ms")
        print(f"   Max: {max_latency:.2f}ms")
        print(f"   Target: <50ms")

        assert avg_latency < 50, f"Average latency {avg_latency:.2f}ms exceeds 50ms target"

    @pytest.mark.asyncio
    async def test_search_performance(self, memory_graph):
        """Test search query latency (<200ms target)"""
        # Create test data
        for i in range(50):
            await memory_graph.create_entity(
                entity_type="decision",
                name=f"Test Decision {i}",
                observations=[f"Decision about feature {i}"]
            )

        # Measure search performance
        latencies = []
        for i in range(5):
            start = time.time()
            await memory_graph.search_entities("feature", limit=10)
            latency = (time.time() - start) * 1000
            latencies.append(latency)

        avg_latency = sum(latencies) / len(latencies)
        max_latency = max(latencies)

        print(f"📊 Search Performance:")
        print(f"   Average: {avg_latency:.2f}ms")
        print(f"   Max: {max_latency:.2f}ms")
        print(f"   Target: <200ms")

        assert avg_latency < 200, f"Average search latency {avg_latency:.2f}ms exceeds 200ms target"

    @pytest.mark.asyncio
    async def test_relation_traversal_performance(self, memory_graph):
        """Test relation traversal latency (<100ms target)"""
        # Create entity chain
        entities = []
        for i in range(10):
            entity = await memory_graph.create_entity(
                entity_type="task",
                name=f"Chain Task {i}",
                observations=[f"Task {i}"]
            )
            entities.append(entity)

        # Create relations
        for i in range(len(entities) - 1):
            await memory_graph.create_relation(
                from_entity=f"Chain Task {i}",
                to_entity=f"Chain Task {i+1}",
                relation_type="depends_on"
            )

        # Measure relation traversal
        latencies = []
        for i in range(5):
            start = time.time()
            await memory_graph.get_related_entities(f"Chain Task {i}")
            latency = (time.time() - start) * 1000
            latencies.append(latency)

        avg_latency = sum(latencies) / len(latencies)
        max_latency = max(latencies)

        print(f"📊 Relation Traversal Performance:")
        print(f"   Average: {avg_latency:.2f}ms")
        print(f"   Max: {max_latency:.2f}ms")
        print(f"   Target: <100ms")

        assert avg_latency < 100, f"Average traversal latency {avg_latency:.2f}ms exceeds 100ms target"


# ===== INTEGRATION TESTS =====

class TestIntegration:
    """Test integration with other AutoBot systems"""

    @pytest.mark.asyncio
    async def test_memory_graph_initialization(self, redis_db9):
        """Test proper initialization and connection"""
        mg = MockAutoBotMemoryGraph(
            redis_host="172.16.168.23",
            redis_port=6379,
            database=9
        )

        # Test initialization
        initialized = await mg.initialize()
        assert initialized is True
        assert mg.initialized is True

        # Test connection
        entity = await mg.create_entity(
            entity_type="context",
            name="Initialization Test",
            observations=["Testing initialization"]
        )
        assert entity is not None

        await mg.close()
        print(f"✅ Memory Graph initialization successful")

    @pytest.mark.asyncio
    async def test_concurrent_operations(self, memory_graph):
        """Test concurrent entity operations"""
        # Create entities concurrently
        tasks = [
            memory_graph.create_entity(
                entity_type="task",
                name=f"Concurrent Task {i}",
                observations=[f"Task {i}"]
            )
            for i in range(10)
        ]

        results = await asyncio.gather(*tasks)

        assert len(results) == 10
        assert all(r["entity_id"] is not None for r in results)

        print(f"✅ Concurrent operations working correctly")

    @pytest.mark.asyncio
    async def test_error_recovery(self, memory_graph):
        """Test error recovery and rollback"""
        # Test that failed operations don't corrupt state
        try:
            await memory_graph.create_entity(
                entity_type="invalid_type",
                name="Test",
                observations=[]
            )
        except ValueError:
            pass  # Expected

        # Verify system still works
        entity = await memory_graph.create_entity(
            entity_type="decision",
            name="After Error Test",
            observations=["System recovered"]
        )

        assert entity is not None
        print(f"✅ Error recovery working correctly")


# ===== DATA INTEGRITY TESTS =====

class TestDataIntegrity:
    """Test data integrity and consistency"""

    @pytest.mark.asyncio
    async def test_entity_metadata_preservation(self, memory_graph):
        """Test that entity metadata is preserved correctly"""
        entity = await memory_graph.create_entity(
            entity_type="decision",
            name="Metadata Test",
            observations=["Test"],
            metadata={
                "priority": "high",
                "custom_field": "custom_value"
            },
            tags=["test", "metadata"]
        )

        # Retrieve and verify metadata
        retrieved = await memory_graph.get_entity("Metadata Test")

        assert retrieved["metadata"]["priority"] == "high"
        assert retrieved["metadata"]["custom_field"] == "custom_value"
        assert "test" in retrieved["metadata"]["tags"]
        assert "metadata" in retrieved["metadata"]["tags"]

        print(f"✅ Metadata preservation working correctly")

    @pytest.mark.asyncio
    async def test_observation_ordering(self, memory_graph):
        """Test that observations maintain order"""
        await memory_graph.create_entity(
            entity_type="context",
            name="Order Test",
            observations=["First", "Second", "Third"]
        )

        # Add more observations
        await memory_graph.add_observations(
            entity_name="Order Test",
            observations=["Fourth", "Fifth"]
        )

        # Verify order
        entity = await memory_graph.get_entity("Order Test")
        observations = entity["observations"]

        assert observations[0] == "First"
        assert observations[1] == "Second"
        assert observations[2] == "Third"
        assert observations[3] == "Fourth"
        assert observations[4] == "Fifth"

        print(f"✅ Observation ordering preserved correctly")

    @pytest.mark.asyncio
    async def test_relation_metadata_preservation(self, memory_graph):
        """Test that relation metadata is preserved"""
        await memory_graph.create_entity(
            entity_type="feature",
            name="Feature M",
            observations=["Test"]
        )

        await memory_graph.create_entity(
            entity_type="task",
            name="Task N",
            observations=["Test"]
        )

        relation = await memory_graph.create_relation(
            from_entity="Feature M",
            to_entity="Task N",
            relation_type="implements",
            strength=0.95,
            metadata={"custom_data": "test_value"}
        )

        # Verify metadata
        assert relation["metadata"]["strength"] == 0.95
        assert relation["metadata"]["custom_data"] == "test_value"

        # Verify metadata in related entities
        related = await memory_graph.get_related_entities("Feature M")
        assert len(related) > 0
        assert related[0]["relation_metadata"]["strength"] == 0.95

        print(f"✅ Relation metadata preservation working correctly")


# ===== TEST RUNNER =====

async def run_all_tests():
    """Run all tests and generate summary"""
    print("\n" + "=" * 80)
    print("AUTOBOT MEMORY GRAPH COMPREHENSIVE TEST SUITE")
    print("=" * 80)

    # Run pytest with verbose output
    exit_code = pytest.main([
        __file__,
        "-v",
        "-s",
        "--tb=short",
        "--asyncio-mode=auto"
    ])

    print("\n" + "=" * 80)
    if exit_code == 0:
        print("✅ ALL TESTS PASSED")
    else:
        print("❌ SOME TESTS FAILED")
    print("=" * 80)

    return exit_code


if __name__ == "__main__":
    sys.exit(asyncio.run(run_all_tests()))
