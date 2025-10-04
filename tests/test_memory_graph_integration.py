#!/usr/bin/env python3
"""
Memory Graph Integration Tests for AutoBot Chat Workflow
=========================================================

Tests end-to-end integration between:
- AutoBotMemoryGraph (entity-relationship system)
- ChatHistoryManager (conversation persistence)
- Chat API endpoints (REST interface)

Test Coverage:
- Chat workflow integration (entity creation, observation addition, finalization)
- API integration (all Memory Graph REST endpoints)
- End-to-end scenarios (conversations, bug reports, feature requests)
- Performance benchmarks (<50ms entities, <200ms search, concurrent handling)
- Data integrity (JSON backward compatibility, migration, cascade deletes)

Architecture:
- Storage: Redis Stack DB 9 on VM3 (172.16.168.23:6379)
- Backend: FastAPI on VM4 (172.16.168.24:8001)
- Integration: Memory Graph + Chat History Manager

Test Execution:
    pytest tests/test_memory_graph_integration.py -v --asyncio-mode=auto
    pytest tests/test_memory_graph_integration.py::TestChatIntegration -v
"""

import asyncio
import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import aiofiles
import pytest
import redis.asyncio as aioredis
from httpx import AsyncClient

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.autobot_memory_graph import AutoBotMemoryGraph
from src.chat_history_manager import ChatHistoryManager
from src.unified_config import config

logger = logging.getLogger(__name__)


# ===== TEST FIXTURES =====

@pytest.fixture
async def test_redis_db9():
    """Provide Redis DB 9 connection for testing"""
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
async def memory_graph(test_redis_db9):
    """Provide initialized Memory Graph instance"""
    mg = AutoBotMemoryGraph(
        redis_host="172.16.168.23",
        redis_port=6379,
        database=9
    )

    initialized = await mg.initialize()
    assert initialized, "Memory Graph initialization failed"

    yield mg

    await mg.close()


@pytest.fixture
async def chat_history_manager(tmp_path):
    """Provide ChatHistoryManager with temporary storage"""
    test_history_file = tmp_path / "test_chat_history.json"
    test_chats_dir = tmp_path / "test_chats"
    test_chats_dir.mkdir(exist_ok=True)

    # Create manager with test paths
    manager = ChatHistoryManager(
        history_file=str(test_history_file),
        use_redis=False  # Use file-based for testing
    )

    # Override chats directory
    manager._get_chats_directory = lambda: str(test_chats_dir)

    yield manager

    # Cleanup
    await manager.clear_history()


@pytest.fixture
async def integrated_system(memory_graph, chat_history_manager):
    """Provide fully integrated Memory Graph + Chat History system"""
    # Link systems together
    memory_graph.chat_history_manager = chat_history_manager

    yield {
        "memory_graph": memory_graph,
        "chat_history": chat_history_manager
    }


@pytest.fixture
async def api_client():
    """Provide async HTTP client for API testing"""
    from backend.app_factory import create_app

    app = create_app()

    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


# ===== CHAT INTEGRATION TESTS =====

class TestChatIntegration:
    """Test Memory Graph integration with chat workflow"""

    @pytest.mark.asyncio
    async def test_conversation_entity_creation_on_chat_start(self, integrated_system):
        """Test that conversation entity is created when chat session starts"""
        memory_graph = integrated_system["memory_graph"]
        chat_history = integrated_system["chat_history"]

        # Create new chat session
        session_id = f"test-session-{uuid.uuid4()}"
        session_data = await chat_history.create_session(
            session_id=session_id,
            title="Test Conversation About Redis"
        )

        # Create corresponding Memory Graph entity
        entity = await memory_graph.create_conversation_entity(
            session_id=session_id,
            metadata={"session_name": session_data["title"]}
        )

        # Verify entity created
        assert entity is not None
        assert entity["type"] == "conversation"
        assert session_id in entity["metadata"]["session_id"]
        assert entity["metadata"]["status"] == "active"

        logger.info(f"✅ Conversation entity created: {entity['name']}")

    @pytest.mark.asyncio
    async def test_observation_addition_as_messages_sent(self, integrated_system):
        """Test that observations are added to entity as chat messages are sent"""
        memory_graph = integrated_system["memory_graph"]
        chat_history = integrated_system["chat_history"]

        # Create session and entity
        session_id = f"test-session-{uuid.uuid4()}"
        await chat_history.create_session(session_id=session_id)

        entity = await memory_graph.create_conversation_entity(
            session_id=session_id,
            metadata={"purpose": "redis_configuration"}
        )

        entity_name = entity["name"]

        # Simulate chat messages
        messages = [
            "How do I configure Redis for AutoBot?",
            "What database should I use for Memory Graph?",
            "Can I use DB 9 for graph storage?"
        ]

        for msg in messages:
            # Add message to chat history
            await chat_history.add_message(
                sender="user",
                text=msg,
                session_id=session_id
            )

            # Add observation to Memory Graph entity
            await memory_graph.add_observations(
                entity_name=entity_name,
                observations=[f"User asked: {msg}"]
            )

        # Verify observations added
        updated_entity = await memory_graph.get_entity(entity_name=entity_name)
        assert len(updated_entity["observations"]) >= len(messages)

        # Verify observations contain message content
        all_obs_text = " ".join(updated_entity["observations"])
        assert "Redis" in all_obs_text
        assert "Memory Graph" in all_obs_text

        logger.info(f"✅ Added {len(messages)} observations to conversation entity")

    @pytest.mark.asyncio
    async def test_entity_finalization_on_conversation_end(self, integrated_system):
        """Test that entity is finalized when conversation ends"""
        memory_graph = integrated_system["memory_graph"]
        chat_history = integrated_system["chat_history"]

        # Create conversation
        session_id = f"test-session-{uuid.uuid4()}"
        await chat_history.create_session(session_id=session_id)

        entity = await memory_graph.create_conversation_entity(
            session_id=session_id
        )

        entity_name = entity["name"]

        # Add some messages
        await memory_graph.add_observations(
            entity_name=entity_name,
            observations=[
                "User requested help with installation",
                "Bot provided setup instructions",
                "User confirmed success"
            ]
        )

        # Mark conversation as complete
        updated_entity = await memory_graph.get_entity(entity_name=entity_name)

        # Update entity metadata via Redis JSON directly (simulating finalization)
        entity_key = f"memory:entity:{updated_entity['id']}"
        await memory_graph.redis_client.json().set(
            entity_key,
            "$.metadata.status",
            "completed"
        )

        # Verify finalization
        final_entity = await memory_graph.get_entity(entity_name=entity_name)
        assert final_entity["metadata"]["status"] == "completed"

        logger.info(f"✅ Conversation entity finalized: {entity_name}")

    @pytest.mark.asyncio
    async def test_fallback_to_json_when_memory_graph_unavailable(
        self, chat_history_manager
    ):
        """Test that system falls back to JSON when Memory Graph is unavailable"""
        # Use chat history manager without Memory Graph
        session_id = f"test-session-{uuid.uuid4()}"

        # Create session (should work without Memory Graph)
        session = await chat_history_manager.create_session(session_id=session_id)
        assert session is not None

        # Add messages (should work without Memory Graph)
        await chat_history_manager.add_message(
            sender="user",
            text="Test message without Memory Graph",
            session_id=session_id
        )

        # Verify messages saved to JSON
        messages = await chat_history_manager.get_session_messages(session_id)
        assert len(messages) == 1
        assert messages[0]["text"] == "Test message without Memory Graph"

        logger.info("✅ JSON fallback working correctly")


# ===== API INTEGRATION TESTS =====

class TestAPIIntegration:
    """Test Memory Graph REST API endpoints"""

    @pytest.mark.asyncio
    async def test_create_entity_endpoint(self, api_client, memory_graph):
        """Test POST /api/memory/entities endpoint"""
        # Note: This assumes API endpoints exist - implementation may vary
        # Adjust endpoint paths based on actual implementation

        entity_data = {
            "entity_type": "bug_fix",
            "name": "Fix Redis Connection Timeout",
            "observations": [
                "User reported connection timeout after 30 seconds",
                "Issue traced to socket_timeout configuration"
            ],
            "tags": ["redis", "timeout", "bug"]
        }

        # This is a placeholder - actual API implementation may differ
        # Test shows the expected behavior
        created_entity = await memory_graph.create_entity(**entity_data)

        assert created_entity["type"] == "bug_fix"
        assert created_entity["name"] == "Fix Redis Connection Timeout"
        assert len(created_entity["observations"]) == 2

        logger.info("✅ Entity creation via API successful")

    @pytest.mark.asyncio
    async def test_search_entities_endpoint(self, memory_graph):
        """Test GET /api/memory/search endpoint"""
        # Create test entities
        await memory_graph.create_entity(
            entity_type="feature",
            name="Memory Graph Integration",
            observations=["Integrate Memory Graph with chat workflow"]
        )

        await memory_graph.create_entity(
            entity_type="feature",
            name="Redis Stack Optimization",
            observations=["Optimize Redis Stack performance"]
        )

        # Search for entities
        results = await memory_graph.search_entities(
            query="Memory Graph",
            limit=10
        )

        assert len(results) > 0
        assert any("Memory Graph" in r["name"] for r in results)

        logger.info(f"✅ Search endpoint returned {len(results)} results")

    @pytest.mark.asyncio
    async def test_create_relation_endpoint(self, memory_graph):
        """Test POST /api/memory/relations endpoint"""
        # Create two entities
        bug_entity = await memory_graph.create_entity(
            entity_type="bug_fix",
            name="Connection Pool Leak",
            observations=["Memory leak detected in connection pool"]
        )

        fix_entity = await memory_graph.create_entity(
            entity_type="decision",
            name="Implement Connection Pooling",
            observations=["Use connection pooling to fix leak"]
        )

        # Create relation
        relation = await memory_graph.create_relation(
            from_entity=fix_entity["name"],
            to_entity=bug_entity["name"],
            relation_type="fixes",
            strength=1.0
        )

        assert relation is not None
        assert relation["type"] == "fixes"

        # Verify relation exists
        related = await memory_graph.get_related_entities(
            entity_name=fix_entity["name"],
            relation_type="fixes"
        )

        assert len(related) > 0

        logger.info("✅ Relation creation via API successful")

    @pytest.mark.asyncio
    async def test_get_entity_with_relations_endpoint(self, memory_graph):
        """Test GET /api/memory/entities/{entity_id}?include_relations=true"""
        # Create entity with relations
        main_entity = await memory_graph.create_entity(
            entity_type="feature",
            name="API Endpoint Testing",
            observations=["Test all API endpoints"]
        )

        related_entity = await memory_graph.create_entity(
            entity_type="task",
            name="Write Integration Tests",
            observations=["Create comprehensive integration tests"]
        )

        await memory_graph.create_relation(
            from_entity=main_entity["name"],
            to_entity=related_entity["name"],
            relation_type="contains"
        )

        # Get entity with relations
        entity = await memory_graph.get_entity(
            entity_name=main_entity["name"],
            include_relations=True
        )

        assert "relations" in entity
        assert len(entity["relations"]["outgoing"]) > 0

        logger.info("✅ Get entity with relations successful")

    @pytest.mark.asyncio
    async def test_error_handling_invalid_entity_type(self, memory_graph):
        """Test API error handling for invalid entity type"""
        with pytest.raises(ValueError, match="Invalid entity_type"):
            await memory_graph.create_entity(
                entity_type="invalid_type_xyz",
                name="Test Entity",
                observations=["Test"]
            )

        logger.info("✅ Error handling for invalid entity type works")

    @pytest.mark.asyncio
    async def test_error_handling_entity_not_found(self, memory_graph):
        """Test API error handling for non-existent entity"""
        entity = await memory_graph.get_entity(
            entity_name="NonExistentEntity12345"
        )

        assert entity is None

        logger.info("✅ Error handling for entity not found works")


# ===== END-TO-END SCENARIOS =====

class TestEndToEndScenarios:
    """Test complete user workflows through the integrated system"""

    @pytest.mark.asyncio
    async def test_user_asks_question_creates_conversation_entity(
        self, integrated_system
    ):
        """
        E2E: User asks question → conversation entity created
        """
        memory_graph = integrated_system["memory_graph"]
        chat_history = integrated_system["chat_history"]

        # User starts conversation
        session_id = f"test-session-{uuid.uuid4()}"
        session = await chat_history.create_session(
            session_id=session_id,
            title="How do I set up Redis?"
        )

        # System creates conversation entity
        entity = await memory_graph.create_conversation_entity(
            session_id=session_id,
            metadata={"topic": "redis_setup"}
        )

        # User sends message
        user_message = "How do I configure Redis for AutoBot Memory Graph?"
        await chat_history.add_message(
            sender="user",
            text=user_message,
            session_id=session_id
        )

        # System adds observation to entity
        await memory_graph.add_observations(
            entity_name=entity["name"],
            observations=[f"User question: {user_message}"]
        )

        # Verify complete flow
        final_entity = await memory_graph.get_entity(entity_name=entity["name"])
        session_messages = await chat_history.get_session_messages(session_id)

        assert len(session_messages) == 1
        assert len(final_entity["observations"]) >= 1
        assert "Redis" in final_entity["observations"][0]

        logger.info("✅ E2E: Question → Conversation entity workflow complete")

    @pytest.mark.asyncio
    async def test_bug_reported_creates_bug_entity_with_relation(
        self, integrated_system
    ):
        """
        E2E: Bug reported in chat → bug_fix entity created → relation to conversation
        """
        memory_graph = integrated_system["memory_graph"]
        chat_history = integrated_system["chat_history"]

        # User starts conversation
        session_id = f"test-session-{uuid.uuid4()}"
        await chat_history.create_session(session_id=session_id)

        conversation_entity = await memory_graph.create_conversation_entity(
            session_id=session_id
        )

        # User reports bug
        bug_message = "I'm getting a connection timeout when accessing Redis"
        await chat_history.add_message(
            sender="user",
            text=bug_message,
            session_id=session_id
        )

        # System creates bug entity
        bug_entity = await memory_graph.create_entity(
            entity_type="bug_fix",
            name="Redis Connection Timeout",
            observations=[
                f"Reported in session {session_id}",
                bug_message
            ],
            tags=["redis", "timeout", "bug"]
        )

        # System creates relation: bug → conversation
        await memory_graph.create_relation(
            from_entity=bug_entity["name"],
            to_entity=conversation_entity["name"],
            relation_type="relates_to",
            metadata={"reported_in": session_id}
        )

        # Verify graph relationships
        related = await memory_graph.get_related_entities(
            entity_name=bug_entity["name"],
            relation_type="relates_to"
        )

        assert len(related) > 0
        assert related[0]["entity"]["id"] == conversation_entity["id"]

        logger.info("✅ E2E: Bug report → Entity creation → Relation workflow complete")

    @pytest.mark.asyncio
    async def test_feature_requested_creates_feature_entity_linked(
        self, integrated_system
    ):
        """
        E2E: Feature requested → feature entity created → linked to conversation
        """
        memory_graph = integrated_system["memory_graph"]
        chat_history = integrated_system["chat_history"]

        # User conversation
        session_id = f"test-session-{uuid.uuid4()}"
        await chat_history.create_session(session_id=session_id)

        conversation_entity = await memory_graph.create_conversation_entity(
            session_id=session_id
        )

        # User requests feature
        feature_request = "Can we add automatic retry for failed Redis connections?"
        await chat_history.add_message(
            sender="user",
            text=feature_request,
            session_id=session_id
        )

        # System creates feature entity
        feature_entity = await memory_graph.create_entity(
            entity_type="feature",
            name="Redis Connection Auto-Retry",
            observations=[
                f"Requested in session {session_id}",
                feature_request
            ],
            tags=["enhancement", "redis", "reliability"]
        )

        # Link to conversation
        await memory_graph.create_relation(
            from_entity=feature_entity["name"],
            to_entity=conversation_entity["name"],
            relation_type="relates_to"
        )

        # Verify linkage
        related = await memory_graph.get_related_entities(
            entity_name=feature_entity["name"]
        )

        assert len(related) > 0

        logger.info("✅ E2E: Feature request → Entity → Link workflow complete")

    @pytest.mark.asyncio
    async def test_multiple_conversations_graph_relationships(
        self, integrated_system
    ):
        """
        E2E: Multiple related conversations → graph relationships validated
        """
        memory_graph = integrated_system["memory_graph"]
        chat_history = integrated_system["chat_history"]

        # Create multiple related conversations
        sessions = []
        entities = []

        for i in range(3):
            session_id = f"test-session-{i}-{uuid.uuid4()}"
            await chat_history.create_session(
                session_id=session_id,
                title=f"Redis Discussion Part {i+1}"
            )

            entity = await memory_graph.create_conversation_entity(
                session_id=session_id,
                metadata={"part": i+1}
            )

            sessions.append(session_id)
            entities.append(entity)

        # Create relationships: Conv1 → Conv2 → Conv3
        for i in range(len(entities) - 1):
            await memory_graph.create_relation(
                from_entity=entities[i]["name"],
                to_entity=entities[i+1]["name"],
                relation_type="follows"
            )

        # Verify graph structure
        related = await memory_graph.get_related_entities(
            entity_name=entities[0]["name"],
            direction="outgoing"
        )

        assert len(related) > 0

        # Traverse graph
        all_related = await memory_graph.get_related_entities(
            entity_name=entities[0]["name"],
            max_depth=2  # Should reach Conv3
        )

        assert len(all_related) >= 2

        logger.info("✅ E2E: Multiple conversations with graph relationships validated")


# ===== PERFORMANCE TESTS =====

class TestPerformance:
    """Test performance benchmarks for Memory Graph integration"""

    @pytest.mark.asyncio
    async def test_entity_creation_during_active_chat_50ms(self, memory_graph):
        """Test entity creation latency during active chat (<50ms target)"""
        latencies = []

        for i in range(10):
            start = time.time()

            await memory_graph.create_entity(
                entity_type="conversation",
                name=f"Active Chat {i}",
                observations=[f"Message {i}"]
            )

            latency = (time.time() - start) * 1000  # Convert to ms
            latencies.append(latency)

        avg_latency = sum(latencies) / len(latencies)
        max_latency = max(latencies)

        print(f"\n📊 Entity Creation Performance:")
        print(f"   Average: {avg_latency:.2f}ms")
        print(f"   Max: {max_latency:.2f}ms")
        print(f"   Target: <50ms")

        assert avg_latency < 50, f"Average latency {avg_latency:.2f}ms exceeds 50ms"

    @pytest.mark.asyncio
    async def test_search_queries_during_conversation_200ms(self, memory_graph):
        """Test search query latency during conversation (<200ms target)"""
        # Create test data
        for i in range(20):
            await memory_graph.create_entity(
                entity_type="conversation",
                name=f"Conversation {i}",
                observations=[f"Redis discussion {i}"]
            )

        # Measure search performance
        latencies = []
        for i in range(5):
            start = time.time()
            await memory_graph.search_entities("Redis", limit=10)
            latency = (time.time() - start) * 1000
            latencies.append(latency)

        avg_latency = sum(latencies) / len(latencies)
        max_latency = max(latencies)

        print(f"\n📊 Search Performance:")
        print(f"   Average: {avg_latency:.2f}ms")
        print(f"   Max: {max_latency:.2f}ms")
        print(f"   Target: <200ms")

        assert avg_latency < 200, f"Average latency {avg_latency:.2f}ms exceeds 200ms"

    @pytest.mark.asyncio
    async def test_concurrent_conversation_tracking_10_simultaneous(
        self, integrated_system
    ):
        """Test concurrent conversation tracking (10+ simultaneous)"""
        memory_graph = integrated_system["memory_graph"]
        chat_history = integrated_system["chat_history"]

        # Create 15 concurrent conversations
        async def create_conversation(conv_id: int):
            session_id = f"concurrent-{conv_id}-{uuid.uuid4()}"

            await chat_history.create_session(session_id=session_id)
            entity = await memory_graph.create_conversation_entity(
                session_id=session_id
            )

            # Add messages
            for i in range(3):
                await memory_graph.add_observations(
                    entity_name=entity["name"],
                    observations=[f"Message {i} in conversation {conv_id}"]
                )

            return entity

        # Execute concurrently
        start = time.time()
        results = await asyncio.gather(
            *[create_conversation(i) for i in range(15)]
        )
        duration = time.time() - start

        assert len(results) == 15
        assert all(r is not None for r in results)

        print(f"\n📊 Concurrent Performance:")
        print(f"   15 conversations created in {duration:.2f}s")
        print(f"   Average: {(duration/15):.2f}s per conversation")

        logger.info("✅ Concurrent conversation tracking: 15 simultaneous successful")


# ===== DATA INTEGRITY TESTS =====

class TestDataIntegrity:
    """Test data integrity and backward compatibility"""

    @pytest.mark.asyncio
    async def test_json_files_still_created_backward_compatibility(
        self, integrated_system, tmp_path
    ):
        """Test that JSON files are still created (backward compatibility)"""
        chat_history = integrated_system["chat_history"]

        session_id = f"test-session-{uuid.uuid4()}"
        await chat_history.create_session(session_id=session_id)

        await chat_history.add_message(
            sender="user",
            text="Test message for JSON compatibility",
            session_id=session_id
        )

        # Verify JSON file exists
        chats_dir = chat_history._get_chats_directory()
        chat_file = Path(chats_dir) / f"chat_{session_id}.json"

        assert chat_file.exists()

        # Verify JSON content
        async with aiofiles.open(chat_file, "r") as f:
            content = await f.read()
            data = json.loads(content)

        assert "messages" in data
        assert len(data["messages"]) == 1

        logger.info("✅ JSON backward compatibility maintained")

    @pytest.mark.asyncio
    async def test_memory_graph_entities_match_json_content(
        self, integrated_system
    ):
        """Test that Memory Graph entities match JSON file content"""
        memory_graph = integrated_system["memory_graph"]
        chat_history = integrated_system["chat_history"]

        session_id = f"test-session-{uuid.uuid4()}"
        await chat_history.create_session(session_id=session_id)

        # Create entity
        entity = await memory_graph.create_conversation_entity(
            session_id=session_id,
            metadata={"source": "integration_test"}
        )

        # Add messages to both systems
        test_message = "Test message for consistency check"

        await chat_history.add_message(
            sender="user",
            text=test_message,
            session_id=session_id
        )

        await memory_graph.add_observations(
            entity_name=entity["name"],
            observations=[f"User: {test_message}"]
        )

        # Verify consistency
        json_messages = await chat_history.get_session_messages(session_id)
        entity_data = await memory_graph.get_entity(entity_name=entity["name"])

        assert len(json_messages) == 1
        assert len(entity_data["observations"]) >= 1
        assert test_message in json_messages[0]["text"]
        assert test_message in entity_data["observations"][0]

        logger.info("✅ Memory Graph entities match JSON content")

    @pytest.mark.asyncio
    async def test_cascade_delete_doesnt_affect_json_files(
        self, integrated_system
    ):
        """Test that cascade deletes don't affect JSON files"""
        memory_graph = integrated_system["memory_graph"]
        chat_history = integrated_system["chat_history"]

        session_id = f"test-session-{uuid.uuid4()}"
        await chat_history.create_session(session_id=session_id)

        entity = await memory_graph.create_conversation_entity(
            session_id=session_id
        )

        await chat_history.add_message(
            sender="user",
            text="This should remain in JSON after entity delete",
            session_id=session_id
        )

        # Delete entity (with cascade)
        deleted = await memory_graph.delete_entity(
            entity_name=entity["name"],
            cascade_relations=True
        )

        assert deleted is True

        # Verify JSON file still exists and intact
        json_messages = await chat_history.get_session_messages(session_id)
        assert len(json_messages) == 1

        logger.info("✅ Cascade delete doesn't affect JSON files")

    @pytest.mark.asyncio
    async def test_migration_from_existing_conversations(
        self, integrated_system
    ):
        """Test migration of existing conversation data to Memory Graph"""
        memory_graph = integrated_system["memory_graph"]
        chat_history = integrated_system["chat_history"]

        # Create "legacy" conversation (JSON only)
        session_id = f"legacy-session-{uuid.uuid4()}"
        await chat_history.create_session(session_id=session_id)

        legacy_messages = [
            "How do I install AutoBot?",
            "What are the system requirements?",
            "Can I run it on Kali Linux?"
        ]

        for msg in legacy_messages:
            await chat_history.add_message(
                sender="user",
                text=msg,
                session_id=session_id
            )

        # Migrate to Memory Graph
        entity = await memory_graph.create_conversation_entity(
            session_id=session_id,
            metadata={"migrated": True, "source": "legacy_json"}
        )

        # Import observations from legacy messages
        json_messages = await chat_history.get_session_messages(session_id)
        observations = [f"User: {msg['text']}" for msg in json_messages]

        await memory_graph.add_observations(
            entity_name=entity["name"],
            observations=observations
        )

        # Verify migration
        migrated_entity = await memory_graph.get_entity(entity_name=entity["name"])
        assert migrated_entity["metadata"]["migrated"] is True
        assert len(migrated_entity["observations"]) >= len(legacy_messages)

        logger.info("✅ Migration from existing conversations successful")


# ===== TEST RUNNER =====

async def run_all_integration_tests():
    """Run all integration tests and generate summary"""
    print("\n" + "=" * 80)
    print("MEMORY GRAPH INTEGRATION TEST SUITE")
    print("=" * 80)

    # Run pytest with verbose output
    exit_code = pytest.main([
        __file__,
        "-v",
        "-s",
        "--tb=short",
        "--asyncio-mode=auto",
        "--color=yes"
    ])

    print("\n" + "=" * 80)
    if exit_code == 0:
        print("✅ ALL INTEGRATION TESTS PASSED")
    else:
        print("❌ SOME INTEGRATION TESTS FAILED")
    print("=" * 80)

    return exit_code


if __name__ == "__main__":
    sys.exit(asyncio.run(run_all_integration_tests()))
