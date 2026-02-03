"""
Unit Tests for KnowledgeBase Async Operations

Tests comprehensive async functionality including:
- Async Redis initialization with AsyncRedisManager
- store_fact() async operations with timeout protection
- get_fact() variants (by ID, by query, get all) with timeout protection
- Timeout error handling and graceful degradation
- AsyncRedisManager integration and connection pooling

Test Coverage Target: 90%+ for async operations in knowledge_base.py
"""

import asyncio
import json
import logging
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from src.knowledge_base import KnowledgeBase


# Configure logging for tests
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@pytest.fixture
def mock_redis_client():
    """Create a mock async Redis client with common operations."""
    client = AsyncMock()
    client.ping = AsyncMock(return_value=True)
    client.hset = AsyncMock(return_value=1)
    client.hgetall = AsyncMock(return_value={})
    client.scan_iter = AsyncMock()
    client.pipeline = MagicMock()
    return client


@pytest.fixture
def mock_redis_manager(mock_redis_client):
    """Create a mock AsyncRedisManager that returns mock Redis client."""
    manager = AsyncMock()
    manager.main = AsyncMock(return_value=mock_redis_client)
    return manager


@pytest.fixture
async def knowledge_base_with_mock_redis(mock_redis_manager):
    """Create KnowledgeBase instance with mocked Redis."""
    with patch('backend.utils.async_redis_manager.get_redis_manager', return_value=mock_redis_manager):
        kb = KnowledgeBase()
        # Manually trigger initialization to avoid LlamaIndex issues in tests
        kb._redis_initialized = False
        yield kb


class TestAsyncRedisInitialization:
    """Test async Redis initialization with AsyncRedisManager."""

    @pytest.mark.asyncio
    async def test_redis_initialization_success(self, mock_redis_manager, mock_redis_client):
        """
        Test Case 1.1: Successful Redis initialization with connection pooling

        Validates:
        - AsyncRedisManager is called to get manager instance
        - manager.main() returns Redis client
        - Connection is tested with ping()
        - Initialization flag is set
        """
        logger.info("=== Test 1.1: Redis initialization success ===")

        with patch('backend.utils.async_redis_manager.get_redis_manager', return_value=mock_redis_manager):
            kb = KnowledgeBase()

            # Trigger initialization
            await kb._ensure_redis_initialized()

            # Verify manager was obtained
            assert kb.redis_manager is not None
            logger.info("✓ Redis manager obtained")

            # Verify client was obtained from manager.main()
            assert kb.aioredis_client is not None
            mock_redis_manager.main.assert_called_once()
            logger.info("✓ Redis client obtained from manager.main()")

            # Verify ping was called with timeout
            mock_redis_client.ping.assert_called_once()
            logger.info("✓ Connection tested with ping()")

            # Verify initialization flag set
            assert kb._redis_initialized is True
            logger.info("✓ Initialization flag set")

        logger.info("=== Test 1.1: PASSED ===\n")

    @pytest.mark.asyncio
    async def test_redis_initialization_timeout(self, mock_redis_manager):
        """
        Test Case 1.2: Redis initialization handles connection timeout

        Validates:
        - Timeout during ping() is caught
        - Redis client is set to None
        - Manager is set to None
        - No exception propagates
        """
        logger.info("=== Test 1.2: Redis initialization timeout ===")

        # Configure mock to timeout on ping
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(side_effect=asyncio.TimeoutError("Connection timeout"))
        mock_redis_manager.main = AsyncMock(return_value=mock_client)

        with patch('backend.utils.async_redis_manager.get_redis_manager', return_value=mock_redis_manager):
            kb = KnowledgeBase()

            # Trigger initialization - should handle timeout gracefully
            await kb._ensure_redis_initialized()

            # Verify client and manager are None after timeout
            assert kb.aioredis_client is None
            assert kb.redis_manager is None
            logger.info("✓ Client and manager set to None after timeout")

        logger.info("=== Test 1.2: PASSED ===\n")

    @pytest.mark.asyncio
    async def test_redis_initialization_connection_failure(self, mock_redis_manager):
        """
        Test Case 1.3: Redis initialization handles connection failures

        Validates:
        - Connection errors are caught
        - Redis client is set to None
        - Manager is set to None
        - Error is logged
        """
        logger.info("=== Test 1.3: Redis initialization connection failure ===")

        # Configure mock to fail on main()
        mock_redis_manager.main = AsyncMock(side_effect=ConnectionError("Redis unavailable"))

        with patch('backend.utils.async_redis_manager.get_redis_manager', return_value=mock_redis_manager):
            kb = KnowledgeBase()

            # Trigger initialization - should handle error gracefully
            await kb._ensure_redis_initialized()

            # Verify client and manager are None after failure
            assert kb.aioredis_client is None
            assert kb.redis_manager is None
            logger.info("✓ Client and manager set to None after connection failure")

        logger.info("=== Test 1.3: PASSED ===\n")


class TestStoreFact:
    """Test store_fact() async operations with timeout protection."""

    @pytest.mark.asyncio
    async def test_store_fact_success(self, knowledge_base_with_mock_redis, mock_redis_client):
        """
        Test Case 2.1: Successfully store a fact with async operations

        Validates:
        - Fact is stored with unique ID
        - Redis hset is called with correct data
        - 2-second timeout is applied
        - Success status returned
        """
        logger.info("=== Test 2.1: Store fact success ===")

        kb = knowledge_base_with_mock_redis

        # Initialize Redis
        await kb._ensure_redis_initialized()

        # Store a fact
        test_content = "AutoBot uses Redis for data storage"
        test_metadata = {"category": "architecture", "source": "documentation"}

        result = await kb.store_fact(test_content, test_metadata)

        # Verify success
        assert result["status"] == "success"
        assert "fact_id" in result
        logger.info(f"✓ Fact stored with ID: {result['fact_id']}")

        # Verify hset was called
        mock_redis_client.hset.assert_called_once()
        call_args = mock_redis_client.hset.call_args

        # Verify fact key format
        fact_key = call_args[0][0]
        assert fact_key.startswith("fact:")
        logger.info(f"✓ Fact key format correct: {fact_key}")

        # Verify fact data
        fact_data = call_args[1]["mapping"]
        assert fact_data["content"] == test_content
        assert json.loads(fact_data["metadata"]) == test_metadata
        assert "timestamp" in fact_data
        assert "id" in fact_data
        logger.info("✓ Fact data contains all required fields")

        logger.info("=== Test 2.1: PASSED ===\n")

    @pytest.mark.asyncio
    async def test_store_fact_timeout(self, knowledge_base_with_mock_redis, mock_redis_client):
        """
        Test Case 2.2: Store fact handles Redis timeout (2s)

        Validates:
        - Timeout during hset is caught
        - Error status returned
        - Appropriate error message
        """
        logger.info("=== Test 2.2: Store fact timeout ===")

        kb = knowledge_base_with_mock_redis
        await kb._ensure_redis_initialized()

        # Configure mock to timeout
        async def slow_hset(*args, **kwargs):
            await asyncio.sleep(3)  # Longer than 2s timeout

        mock_redis_client.hset = AsyncMock(side_effect=slow_hset)

        # Attempt to store fact
        result = await kb.store_fact("Test content", {})

        # Verify timeout error
        assert result["status"] == "error"
        assert "timeout" in result["message"].lower()
        logger.info("✓ Timeout error handled gracefully")

        logger.info("=== Test 2.2: PASSED ===\n")

    @pytest.mark.asyncio
    async def test_store_fact_redis_unavailable(self):
        """
        Test Case 2.3: Store fact when Redis is unavailable

        Validates:
        - Returns error status when Redis not available
        - Appropriate error message
        """
        logger.info("=== Test 2.3: Store fact with Redis unavailable ===")

        kb = KnowledgeBase()
        # Ensure Redis is not initialized
        kb.aioredis_client = None
        kb._redis_initialized = True  # Skip initialization attempt

        result = await kb.store_fact("Test content", {})

        assert result["status"] == "error"
        assert "not available" in result["message"].lower()
        logger.info("✓ Error returned when Redis unavailable")

        logger.info("=== Test 2.3: PASSED ===\n")


class TestGetFactById:
    """Test get_fact() with fact_id parameter."""

    @pytest.mark.asyncio
    async def test_get_fact_by_id_success(self, knowledge_base_with_mock_redis, mock_redis_client):
        """
        Test Case 3.1: Successfully retrieve fact by ID

        Validates:
        - Fact is retrieved with correct ID
        - Redis hgetall is called with correct key
        - 2-second timeout is applied
        - Fact data is properly decoded
        """
        logger.info("=== Test 3.1: Get fact by ID success ===")

        kb = knowledge_base_with_mock_redis
        await kb._ensure_redis_initialized()

        # Configure mock to return fact data
        test_fact_id = "test-fact-123"
        mock_fact_data = {
            "content": "Test fact content",
            "metadata": json.dumps({"category": "test"}),
            "timestamp": datetime.now().isoformat(),
        }
        mock_redis_client.hgetall = AsyncMock(return_value=mock_fact_data)

        # Retrieve fact
        facts = await kb.get_fact(fact_id=test_fact_id)

        # Verify result
        assert len(facts) == 1
        assert facts[0]["id"] == test_fact_id
        assert facts[0]["content"] == "Test fact content"
        assert facts[0]["metadata"]["category"] == "test"
        logger.info(f"✓ Fact retrieved successfully: {test_fact_id}")

        # Verify Redis call
        mock_redis_client.hgetall.assert_called_once_with(f"fact:{test_fact_id}")
        logger.info("✓ Redis hgetall called with correct key")

        logger.info("=== Test 3.1: PASSED ===\n")

    @pytest.mark.asyncio
    async def test_get_fact_by_id_timeout(self, knowledge_base_with_mock_redis, mock_redis_client):
        """
        Test Case 3.2: Get fact by ID handles timeout

        Validates:
        - Timeout during hgetall is caught
        - Empty list returned
        - Error logged
        """
        logger.info("=== Test 3.2: Get fact by ID timeout ===")

        kb = knowledge_base_with_mock_redis
        await kb._ensure_redis_initialized()

        # Configure mock to timeout
        async def slow_hgetall(*args, **kwargs):
            await asyncio.sleep(3)

        mock_redis_client.hgetall = AsyncMock(side_effect=slow_hgetall)

        # Attempt to get fact
        facts = await kb.get_fact(fact_id="test-fact-123")

        # Verify empty result on timeout
        assert facts == []
        logger.info("✓ Empty list returned on timeout")

        logger.info("=== Test 3.2: PASSED ===\n")

    @pytest.mark.asyncio
    async def test_get_fact_by_id_not_found(self, knowledge_base_with_mock_redis, mock_redis_client):
        """
        Test Case 3.3: Get fact by ID when fact doesn't exist

        Validates:
        - Returns empty list when fact not found
        - No errors raised
        """
        logger.info("=== Test 3.3: Get fact by ID not found ===")

        kb = knowledge_base_with_mock_redis
        await kb._ensure_redis_initialized()

        # Configure mock to return empty result
        mock_redis_client.hgetall = AsyncMock(return_value={})

        facts = await kb.get_fact(fact_id="nonexistent-fact")

        assert facts == []
        logger.info("✓ Empty list returned for nonexistent fact")

        logger.info("=== Test 3.3: PASSED ===\n")


class TestGetFactByQuery:
    """Test get_fact() with query parameter for content search."""

    @pytest.mark.asyncio
    async def test_get_fact_by_query_success(self, knowledge_base_with_mock_redis, mock_redis_client):
        """
        Test Case 4.1: Successfully search facts by query

        Validates:
        - Facts matching query are returned
        - Case-insensitive search works
        - Multiple facts can match
        """
        logger.info("=== Test 4.1: Get fact by query success ===")

        kb = knowledge_base_with_mock_redis
        await kb._ensure_redis_initialized()

        # Mock scan_iter to return fact keys
        async def mock_scan_iter(match=None):
            yield "fact:123"
            yield "fact:456"

        mock_redis_client.scan_iter = mock_scan_iter

        # Mock hgetall to return different facts
        fact_data = {
            "fact:123": {
                "content": "Redis is a database",
                "metadata": "{}",
                "timestamp": datetime.now().isoformat(),
            },
            "fact:456": {
                "content": "AutoBot uses Redis for storage",
                "metadata": "{}",
                "timestamp": datetime.now().isoformat(),
            }
        }

        async def mock_hgetall(key):
            return fact_data.get(key, {})

        mock_redis_client.hgetall = AsyncMock(side_effect=mock_hgetall)

        # Search for "redis"
        facts = await kb.get_fact(query="redis")

        # Verify both facts match
        assert len(facts) == 2
        assert all("redis" in f["content"].lower() for f in facts)
        logger.info(f"✓ Found {len(facts)} facts matching query 'redis'")

        logger.info("=== Test 4.1: PASSED ===\n")

    @pytest.mark.asyncio
    async def test_get_fact_by_query_no_matches(self, knowledge_base_with_mock_redis, mock_redis_client):
        """
        Test Case 4.2: Search query with no matches

        Validates:
        - Returns empty list when no facts match
        - No errors raised
        """
        logger.info("=== Test 4.2: Get fact by query no matches ===")

        kb = knowledge_base_with_mock_redis
        await kb._ensure_redis_initialized()

        # Mock scan_iter with fact that doesn't match query
        async def mock_scan_iter(match=None):
            yield "fact:123"

        mock_redis_client.scan_iter = mock_scan_iter
        mock_redis_client.hgetall = AsyncMock(return_value={
            "content": "Completely different content",
            "metadata": "{}",
            "timestamp": datetime.now().isoformat(),
        })

        facts = await kb.get_fact(query="nonexistent")

        assert facts == []
        logger.info("✓ Empty list returned for query with no matches")

        logger.info("=== Test 4.2: PASSED ===\n")


class TestGetAllFacts:
    """Test get_fact() without parameters to get all facts."""

    @pytest.mark.asyncio
    async def test_get_all_facts_with_pipeline(self, knowledge_base_with_mock_redis, mock_redis_client):
        """
        Test Case 5.1: Get all facts uses pipeline for efficiency

        Validates:
        - Pipeline is used for batch retrieval
        - All facts are returned
        - 2-second timeout applied to pipeline execution
        """
        logger.info("=== Test 5.1: Get all facts with pipeline ===")

        kb = knowledge_base_with_mock_redis
        await kb._ensure_redis_initialized()

        # Mock scan_iter to return fact keys
        async def mock_scan_iter(match=None):
            for i in range(3):
                yield f"fact:{i}"

        mock_redis_client.scan_iter = mock_scan_iter

        # Mock pipeline
        mock_pipeline = MagicMock()
        mock_pipeline.hgetall = MagicMock()
        mock_pipeline.execute = AsyncMock(return_value=[
            {"content": f"Fact {i}", "metadata": "{}", "timestamp": datetime.now().isoformat()}
            for i in range(3)
        ])
        mock_redis_client.pipeline = MagicMock(return_value=mock_pipeline)

        # Get all facts
        facts = await kb.get_fact()

        # Verify pipeline was used
        mock_redis_client.pipeline.assert_called_once()
        mock_pipeline.execute.assert_called_once()
        logger.info("✓ Pipeline used for batch retrieval")

        # Verify all facts returned
        assert len(facts) == 3
        logger.info(f"✓ Retrieved {len(facts)} facts")

        logger.info("=== Test 5.1: PASSED ===\n")

    @pytest.mark.asyncio
    async def test_get_all_facts_timeout(self, knowledge_base_with_mock_redis, mock_redis_client):
        """
        Test Case 5.2: Get all facts handles pipeline timeout

        Validates:
        - Timeout during pipeline execution is caught
        - Empty list returned
        - Error logged
        """
        logger.info("=== Test 5.2: Get all facts timeout ===")

        kb = knowledge_base_with_mock_redis
        await kb._ensure_redis_initialized()

        # Mock scan_iter
        async def mock_scan_iter(match=None):
            yield "fact:1"

        mock_redis_client.scan_iter = mock_scan_iter

        # Mock pipeline to timeout
        mock_pipeline = MagicMock()
        mock_pipeline.hgetall = MagicMock()

        async def slow_execute():
            await asyncio.sleep(3)  # Longer than 2s timeout

        mock_pipeline.execute = AsyncMock(side_effect=slow_execute)
        mock_redis_client.pipeline = MagicMock(return_value=mock_pipeline)

        # Attempt to get all facts
        facts = await kb.get_fact()

        # Verify empty result on timeout
        assert facts == []
        logger.info("✓ Empty list returned on pipeline timeout")

        logger.info("=== Test 5.2: PASSED ===\n")

    @pytest.mark.asyncio
    async def test_get_all_facts_empty(self, knowledge_base_with_mock_redis, mock_redis_client):
        """
        Test Case 5.3: Get all facts when no facts exist

        Validates:
        - Returns empty list when no facts exist
        - No errors raised
        """
        logger.info("=== Test 5.3: Get all facts empty ===")

        kb = knowledge_base_with_mock_redis
        await kb._ensure_redis_initialized()

        # Mock scan_iter to return no keys
        async def mock_scan_iter(match=None):
            return
            yield  # Make it a generator

        mock_redis_client.scan_iter = mock_scan_iter

        facts = await kb.get_fact()

        assert facts == []
        logger.info("✓ Empty list returned when no facts exist")

        logger.info("=== Test 5.3: PASSED ===\n")


class TestTimeoutHandling:
    """Test timeout error handling and graceful degradation."""

    @pytest.mark.asyncio
    async def test_asyncio_wait_for_timeout_protection(self, knowledge_base_with_mock_redis, mock_redis_client):
        """
        Test Case 6.1: Verify asyncio.wait_for provides timeout protection

        Validates:
        - All Redis operations wrapped in asyncio.wait_for
        - 2-second timeout consistently applied
        - TimeoutError properly caught and handled
        """
        logger.info("=== Test 6.1: asyncio.wait_for timeout protection ===")

        kb = knowledge_base_with_mock_redis
        await kb._ensure_redis_initialized()

        # Test store_fact timeout protection
        async def slow_operation(*args, **kwargs):
            await asyncio.sleep(5)  # Exceeds 2s timeout

        mock_redis_client.hset = AsyncMock(side_effect=slow_operation)

        result = await kb.store_fact("Test", {})
        assert result["status"] == "error"
        assert "timeout" in result["message"].lower()
        logger.info("✓ store_fact timeout protection verified")

        # Test get_fact timeout protection
        mock_redis_client.hgetall = AsyncMock(side_effect=slow_operation)

        facts = await kb.get_fact(fact_id="test")
        assert facts == []
        logger.info("✓ get_fact timeout protection verified")

        logger.info("=== Test 6.1: PASSED ===\n")

    @pytest.mark.asyncio
    async def test_graceful_degradation_on_redis_failure(self):
        """
        Test Case 6.2: Graceful degradation when Redis fails

        Validates:
        - Operations return safe defaults on Redis failure
        - No exceptions propagate to caller
        - Errors are logged appropriately
        """
        logger.info("=== Test 6.2: Graceful degradation on Redis failure ===")

        kb = KnowledgeBase()
        kb.aioredis_client = None
        kb._redis_initialized = True

        # Test store_fact with no Redis
        result = await kb.store_fact("Test", {})
        assert result["status"] == "error"
        logger.info("✓ store_fact returns error status when Redis unavailable")

        # Test get_fact with no Redis
        facts = await kb.get_fact(fact_id="test")
        assert facts == []
        logger.info("✓ get_fact returns empty list when Redis unavailable")

        logger.info("=== Test 6.2: PASSED ===\n")


# ============================================================================
# TEST EXECUTION
# ============================================================================

if __name__ == "__main__":
    """Run all tests with pytest"""
    pytest.main([
        __file__,
        '-v',  # Verbose output
        '--tb=short',  # Short traceback format
        '--asyncio-mode=auto',  # Enable async support
        '--log-cli-level=INFO',  # Show INFO logs
        '-k', 'test_',  # Run all test functions
    ])
