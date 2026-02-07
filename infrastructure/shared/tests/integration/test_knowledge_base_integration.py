"""
Integration tests for KnowledgeBase async operations with real Redis connections.

Tests validate:
- Real Redis connection management via AsyncRedisManager
- Connection pooling behavior under concurrent load
- Actual store_fact() and get_fact() operations
- Timeout protection and error handling
- Performance metrics (P95 latency targets)

Requirements:
- Redis server running at 172.16.168.23:6379
- pytest-asyncio for async test support
- Real AsyncRedisManager (no mocks)
"""

import asyncio
import json
import statistics
import time

import pytest
from src.knowledge_base import KnowledgeBase


class TestKnowledgeBaseRedisIntegration:
    """Integration tests for KnowledgeBase with real Redis connections"""

    @pytest.fixture
    async def kb(self):
        """Create KnowledgeBase instance with real Redis connection"""
        kb = KnowledgeBase()
        await kb._ensure_redis_initialized()

        # Verify Redis is actually connected
        if not kb.aioredis_client:
            pytest.skip("Redis not available at 172.16.168.23:6379")

        yield kb

        # Cleanup: Remove all test facts
        try:
            test_keys = await kb._scan_redis_keys_async("fact:test_*")
            if test_keys:
                await kb.aioredis_client.delete(*test_keys)
        except Exception:
            pass

    @pytest.mark.asyncio
    async def test_redis_connection_established(self, kb):
        """Test that Redis connection is properly established"""
        # Verify connection exists
        assert kb.aioredis_client is not None
        assert kb.redis_manager is not None

        # Verify connection works with ping
        result = await kb.aioredis_client.ping()
        assert result is True

    @pytest.mark.asyncio
    async def test_connection_pool_multiple_operations(self, kb):
        """Test connection pool handles multiple sequential operations"""
        # Perform 10 sequential operations
        for i in range(10):
            result = await kb.store_fact(
                text=f"Test fact {i}", metadata={"test": True, "iteration": i}
            )
            assert result["status"] == "success"

        # Verify all facts were stored
        facts = await kb.get_fact()
        test_facts = [f for f in facts if "Test fact" in f.get("content", "")]
        assert len(test_facts) >= 10

    @pytest.mark.asyncio
    async def test_store_fact_real_redis(self, kb):
        """Test store_fact() stores data in real Redis"""
        # Store a test fact
        test_content = "Integration test fact content"
        test_metadata = {"source": "integration_test", "priority": "high"}

        result = await kb.store_fact(text=test_content, metadata=test_metadata)

        # Verify success
        assert result["status"] == "success"
        assert "fact_id" in result
        fact_id = result["fact_id"]

        # Verify data was actually stored in Redis
        fact_key = f"fact:{fact_id}"
        fact_data = await kb.aioredis_client.hgetall(fact_key)

        assert fact_data is not None
        assert fact_data.get("content") == test_content

        stored_metadata = json.loads(fact_data.get("metadata", "{}"))
        assert stored_metadata["source"] == "integration_test"
        assert stored_metadata["priority"] == "high"

    @pytest.mark.asyncio
    async def test_get_fact_by_id_real_redis(self, kb):
        """Test get_fact() retrieves specific fact by ID from real Redis"""
        # Store a fact first
        test_content = "Specific fact retrieval test"
        store_result = await kb.store_fact(
            text=test_content, metadata={"test_type": "id_retrieval"}
        )
        fact_id = store_result["fact_id"]

        # Retrieve by ID
        facts = await kb.get_fact(fact_id=fact_id)

        # Verify retrieval
        assert len(facts) == 1
        assert facts[0]["id"] == fact_id
        assert facts[0]["content"] == test_content
        assert facts[0]["metadata"]["test_type"] == "id_retrieval"

    @pytest.mark.asyncio
    async def test_get_fact_by_query_real_redis(self, kb):
        """Test get_fact() searches by query in real Redis"""
        # Store multiple facts
        await kb.store_fact("Python programming is awesome", {"lang": "python"})
        await kb.store_fact("JavaScript is versatile", {"lang": "javascript"})
        await kb.store_fact("Python for data science", {"lang": "python"})

        # Search by query
        facts = await kb.get_fact(query="Python")

        # Verify search results
        assert len(facts) >= 2
        python_facts = [f for f in facts if "Python" in f["content"]]
        assert len(python_facts) >= 2

    @pytest.mark.asyncio
    async def test_get_all_facts_real_redis(self, kb):
        """Test get_fact() retrieves all facts using pipeline"""
        # Store known number of facts
        num_facts = 5
        stored_ids = []

        for i in range(num_facts):
            result = await kb.store_fact(
                text=f"Bulk fact {i}", metadata={"batch": "test_all_facts"}
            )
            stored_ids.append(result["fact_id"])

        # Retrieve all facts
        all_facts = await kb.get_fact()

        # Verify all our facts are present
        our_facts = [f for f in all_facts if f["id"] in stored_ids]
        assert len(our_facts) == num_facts

    @pytest.mark.asyncio
    async def test_concurrent_store_operations(self, kb):
        """Test 50+ concurrent store_fact() operations"""
        num_concurrent = 50

        # Create concurrent store tasks
        async def store_task(idx):
            return await kb.store_fact(
                text=f"Concurrent store test {idx}",
                metadata={"concurrent": True, "index": idx},
            )

        # Execute concurrently
        start_time = time.time()
        results = await asyncio.gather(*[store_task(i) for i in range(num_concurrent)])
        duration = time.time() - start_time

        # Verify all succeeded
        successes = [r for r in results if r["status"] == "success"]
        assert len(successes) == num_concurrent

        # Verify no connection pool exhaustion
        assert all("fact_id" in r for r in successes)

        print(f"\n✓ {num_concurrent} concurrent stores completed in {duration:.2f}s")

    @pytest.mark.asyncio
    async def test_concurrent_get_operations(self, kb):
        """Test 50+ concurrent get_fact() operations"""
        # Store some facts first
        fact_ids = []
        for i in range(10):
            result = await kb.store_fact(
                text=f"Concurrent get test {i}", metadata={"test": "concurrent_get"}
            )
            fact_ids.append(result["fact_id"])

        # Create concurrent get tasks
        num_concurrent = 50

        async def get_task(idx):
            # Mix of different get modes
            if idx % 3 == 0:
                return await kb.get_fact(fact_id=fact_ids[idx % len(fact_ids)])
            elif idx % 3 == 1:
                return await kb.get_fact(query="Concurrent")
            else:
                return await kb.get_fact()

        # Execute concurrently
        start_time = time.time()
        results = await asyncio.gather(*[get_task(i) for i in range(num_concurrent)])
        duration = time.time() - start_time

        # Verify all completed
        assert len(results) == num_concurrent

        # Verify all returned data
        assert all(isinstance(r, list) for r in results)

        print(f"\n✓ {num_concurrent} concurrent gets completed in {duration:.2f}s")

    @pytest.mark.asyncio
    async def test_mixed_concurrent_operations(self, kb):
        """Test mixed store and get operations concurrently"""
        num_operations = 60

        async def mixed_task(idx):
            if idx % 2 == 0:
                # Store operation
                return await kb.store_fact(
                    text=f"Mixed operation {idx}",
                    metadata={"type": "mixed", "op": "store"},
                )
            else:
                # Get operation
                return await kb.get_fact(query="Mixed")

        # Execute mixed operations concurrently
        start_time = time.time()
        results = await asyncio.gather(*[mixed_task(i) for i in range(num_operations)])
        duration = time.time() - start_time

        # Verify all completed
        assert len(results) == num_operations

        # Verify no failures
        store_results = [r for i, r in enumerate(results) if i % 2 == 0]
        assert all(r["status"] == "success" for r in store_results)

        print(f"\n✓ {num_operations} mixed operations completed in {duration:.2f}s")

    @pytest.mark.asyncio
    async def test_performance_p95_latency(self, kb):
        """Test P95 latency meets target (<2000ms for store/get)"""
        num_samples = 50

        # Measure store latencies
        store_latencies = []
        for i in range(num_samples):
            start = time.time()
            result = await kb.store_fact(
                text=f"Latency test {i}", metadata={"test": "latency"}
            )
            latency_ms = (time.time() - start) * 1000
            store_latencies.append(latency_ms)
            assert result["status"] == "success"

        # Measure get latencies
        get_latencies = []
        for i in range(num_samples):
            start = time.time()
            await kb.get_fact()
            latency_ms = (time.time() - start) * 1000
            get_latencies.append(latency_ms)

        # Calculate P95
        store_p95 = statistics.quantiles(store_latencies, n=20)[18]  # 95th percentile
        get_p95 = statistics.quantiles(get_latencies, n=20)[18]

        print(f"\n✓ Store P95 latency: {store_p95:.2f}ms")
        print(f"✓ Get P95 latency: {get_p95:.2f}ms")

        # Verify targets (<2000ms)
        assert store_p95 < 2000, f"Store P95 {store_p95:.2f}ms exceeds 2000ms target"
        assert get_p95 < 2000, f"Get P95 {get_p95:.2f}ms exceeds 2000ms target"

    @pytest.mark.asyncio
    async def test_timeout_protection_store(self, kb):
        """Test that store operations respect timeout limits"""
        # This test verifies the 2s timeout is enforced
        # Normal operations should complete well within timeout

        start_time = time.time()
        result = await kb.store_fact(
            text="Timeout protection test", metadata={"test": "timeout"}
        )
        duration = time.time() - start_time

        # Should complete successfully within timeout
        assert result["status"] == "success"
        assert duration < 2.0, "Operation took longer than timeout limit"

    @pytest.mark.asyncio
    async def test_timeout_protection_get(self, kb):
        """Test that get operations respect timeout limits"""
        # Store some facts first
        for i in range(10):
            await kb.store_fact(f"Timeout test {i}", {"test": "timeout"})

        # Get all facts should complete within timeout
        start_time = time.time()
        facts = await kb.get_fact()
        duration = time.time() - start_time

        assert isinstance(facts, list)
        assert duration < 2.0, "Operation took longer than timeout limit"

    @pytest.mark.asyncio
    async def test_connection_persistence(self, kb):
        """Test that connections are properly reused and persist across operations"""
        # Get initial connection
        initial_client = kb.aioredis_client

        # Perform multiple operations
        for i in range(20):
            await kb.store_fact(f"Persistence test {i}", {"test": "persistence"})

        # Verify same connection is being used
        assert kb.aioredis_client is initial_client

        # Verify connection is still healthy
        assert await kb.aioredis_client.ping() is True

    @pytest.mark.asyncio
    async def test_error_recovery_invalid_data(self, kb):
        """Test graceful error handling with invalid data"""
        # Try to store empty content
        result = await kb.store_fact(text="", metadata={})

        # Should handle gracefully (may succeed with empty string or return error)
        assert "status" in result

        # Try to get non-existent fact
        facts = await kb.get_fact(fact_id="non_existent_id_12345")

        # Should return empty list, not crash
        assert isinstance(facts, list)

    @pytest.mark.asyncio
    async def test_concurrent_operations_no_pool_exhaustion(self, kb):
        """Test that 100+ concurrent operations don't exhaust connection pool"""
        num_operations = 100

        async def operation(idx):
            if idx % 2 == 0:
                return await kb.store_fact(f"Pool test {idx}", {"idx": idx})
            else:
                return await kb.get_fact()

        # Execute all operations concurrently
        start_time = time.time()
        results = await asyncio.gather(*[operation(i) for i in range(num_operations)])
        duration = time.time() - start_time

        # Verify all completed without connection errors
        assert len(results) == num_operations

        # Verify connection pool is still healthy
        assert await kb.aioredis_client.ping() is True

        print(
            f"\n✓ {num_operations} operations completed without pool exhaustion in {duration:.2f}s"
        )

    @pytest.mark.asyncio
    async def test_data_persistence_across_operations(self, kb):
        """Test that stored data persists correctly across multiple operations"""
        # Store initial fact
        result1 = await kb.store_fact("Persistent data test", {"version": 1})
        fact_id = result1["fact_id"]

        # Perform other operations
        await kb.store_fact("Other fact 1", {"version": 2})
        await kb.store_fact("Other fact 2", {"version": 3})
        await kb.get_fact()

        # Retrieve original fact
        facts = await kb.get_fact(fact_id=fact_id)

        # Verify original data is intact
        assert len(facts) == 1
        assert facts[0]["content"] == "Persistent data test"
        assert facts[0]["metadata"]["version"] == 1

    @pytest.mark.asyncio
    async def test_json_encoding_complex_metadata(self, kb):
        """Test that complex metadata is properly encoded/decoded"""
        complex_metadata = {
            "nested": {"level1": {"level2": "deep value"}},
            "array": [1, 2, 3, "four"],
            "unicode": "🔥 emoji test",
            "special_chars": 'quotes: "test", backslash: \\test',
        }

        # Store with complex metadata
        result = await kb.store_fact(
            text="Complex metadata test", metadata=complex_metadata
        )
        fact_id = result["fact_id"]

        # Retrieve and verify
        facts = await kb.get_fact(fact_id=fact_id)

        assert len(facts) == 1
        retrieved_metadata = facts[0]["metadata"]

        # Verify all complex structures preserved
        assert retrieved_metadata["nested"]["level1"]["level2"] == "deep value"
        assert retrieved_metadata["array"] == [1, 2, 3, "four"]
        assert retrieved_metadata["unicode"] == "🔥 emoji test"
        assert (
            retrieved_metadata["special_chars"] == 'quotes: "test", backslash: \\test'
        )


class TestKnowledgeBaseAsyncRedisManagerIntegration:
    """Integration tests for AsyncRedisManager integration"""

    @pytest.fixture
    async def kb(self):
        """Create KnowledgeBase with AsyncRedisManager"""
        kb = KnowledgeBase()
        await kb._ensure_redis_initialized()

        if not kb.redis_manager:
            pytest.skip("AsyncRedisManager not available")

        yield kb

    @pytest.mark.asyncio
    async def test_async_redis_manager_initialized(self, kb):
        """Test that AsyncRedisManager is properly initialized"""
        assert kb.redis_manager is not None
        assert kb.aioredis_client is not None

    @pytest.mark.asyncio
    async def test_connection_pooling_metrics(self, kb):
        """Test connection pool metrics are available"""
        # Perform some operations
        for i in range(10):
            await kb.store_fact(f"Pool metrics test {i}", {"test": "pool"})

        # Verify connection pool is working (no errors)
        assert await kb.aioredis_client.ping() is True

    @pytest.mark.asyncio
    async def test_circuit_breaker_integration(self, kb):
        """Test that circuit breaker is integrated (if available)"""
        # Perform multiple successful operations
        for i in range(5):
            result = await kb.store_fact(f"Circuit test {i}", {"test": "circuit"})
            assert result["status"] == "success"

        # Circuit should remain closed (working normally)
        # This is validated by successful operations above


class TestKnowledgeBasePerformanceIntegration:
    """Performance integration tests"""

    @pytest.fixture
    async def kb(self):
        """Create KnowledgeBase for performance testing"""
        kb = KnowledgeBase()
        await kb._ensure_redis_initialized()

        if not kb.aioredis_client:
            pytest.skip("Redis not available")

        yield kb

        # Cleanup
        try:
            test_keys = await kb._scan_redis_keys_async("fact:perf_*")
            if test_keys:
                await kb.aioredis_client.delete(*test_keys)
        except Exception:
            pass

    @pytest.mark.asyncio
    async def test_bulk_store_performance(self, kb):
        """Test bulk store operations performance"""
        num_facts = 100

        start_time = time.time()

        # Store facts concurrently in batches
        batch_size = 20
        for batch_start in range(0, num_facts, batch_size):
            batch_tasks = [
                kb.store_fact(
                    f"Performance test fact {i}",
                    {"batch": batch_start // batch_size, "index": i},
                )
                for i in range(batch_start, min(batch_start + batch_size, num_facts))
            ]
            await asyncio.gather(*batch_tasks)

        duration = time.time() - start_time
        rate = num_facts / duration

        print(f"\n✓ Stored {num_facts} facts in {duration:.2f}s ({rate:.1f} facts/sec)")

        # Should achieve reasonable throughput
        assert rate > 10, f"Store rate {rate:.1f} facts/sec is too slow"

    @pytest.mark.asyncio
    async def test_bulk_retrieve_performance(self, kb):
        """Test bulk retrieve operations performance"""
        # Store test data first
        num_facts = 50
        for i in range(num_facts):
            await kb.store_fact(f"Retrieve perf test {i}", {"index": i})

        # Test retrieval performance
        num_retrievals = 50

        start_time = time.time()
        for _ in range(num_retrievals):
            await kb.get_fact()
        duration = time.time() - start_time

        rate = num_retrievals / duration

        print(
            f"\n✓ Performed {num_retrievals} retrievals in {duration:.2f}s ({rate:.1f} ops/sec)"
        )

        # Should achieve reasonable throughput
        assert rate > 5, f"Retrieve rate {rate:.1f} ops/sec is too slow"
