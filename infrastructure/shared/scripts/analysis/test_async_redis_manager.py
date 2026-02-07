#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Test Script for Async Redis Manager
Comprehensive testing of the new async Redis connection manager
"""

import asyncio
import logging
import sys
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from backend.utils.async_redis_manager import (
    AsyncRedisDatabase,
    get_async_redis,
    get_main_redis,
    get_redis_manager,
    redis_connection,
)
from backend.utils.redis_compatibility import (
    get_redis_client_compat,
    test_async_migration,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def test_async_redis_database():
    """Test individual AsyncRedisDatabase functionality"""
    logger.info("=== Testing AsyncRedisDatabase ===")

    # Test database creation and initialization
    database = AsyncRedisDatabase(
        name="test_db",
        db_number=15,  # Use testing database
        connection_timeout=5.0,
        socket_timeout=5.0,
    )

    # Test initialization
    init_success = await database.initialize()
    assert init_success, "Database initialization failed"
    logger.info("✅ Database initialization successful")

    # Test basic operations
    test_key = f"test_key_{int(time.time())}"
    test_value = "test_value_12345"

    # Test SET operation
    set_result = await database.set(test_key, test_value, ex=60)
    assert set_result, "SET operation failed"
    logger.info("✅ SET operation successful")

    # Test GET operation
    get_result = await database.get(test_key)
    assert (
        get_result == test_value
    ), f"GET operation failed: expected {test_value}, got {get_result}"
    logger.info("✅ GET operation successful")

    # Test EXISTS operation
    exists_result = await database.exists(test_key)
    assert exists_result == 1, "EXISTS operation failed"
    logger.info("✅ EXISTS operation successful")

    # Test TTL operation
    ttl_result = await database.ttl(test_key)
    assert 50 <= ttl_result <= 60, f"TTL operation failed: got {ttl_result}"
    logger.info("✅ TTL operation successful")

    # Test hash operations
    hash_name = f"test_hash_{int(time.time())}"
    hash_field = "field1"
    hash_value = "hash_value_123"

    hset_result = await database.hset(hash_name, hash_field, hash_value)
    assert hset_result >= 0, "HSET operation failed"
    logger.info("✅ HSET operation successful")

    hget_result = await database.hget(hash_name, hash_field)
    assert (
        hget_result == hash_value
    ), f"HGET operation failed: expected {hash_value}, got {hget_result}"
    logger.info("✅ HGET operation successful")

    hgetall_result = await database.hgetall(hash_name)
    assert hash_field in hgetall_result, "HGETALL operation failed"
    assert hgetall_result[hash_field] == hash_value, "HGETALL value mismatch"
    logger.info("✅ HGETALL operation successful")

    # Test list operations
    list_name = f"test_list_{int(time.time())}"
    list_value1 = "list_item_1"
    list_value2 = "list_item_2"

    lpush_result = await database.lpush(list_name, list_value1, list_value2)
    assert lpush_result >= 2, "LPUSH operation failed"
    logger.info("✅ LPUSH operation successful")

    llen_result = await database.llen(list_name)
    assert llen_result == 2, f"LLEN operation failed: expected 2, got {llen_result}"
    logger.info("✅ LLEN operation successful")

    lpop_result = await database.lpop(list_name)
    assert lpop_result is not None, "LPOP operation failed"
    logger.info("✅ LPOP operation successful")

    # Test set operations
    set_name = f"test_set_{int(time.time())}"
    set_value1 = "set_member_1"
    set_value2 = "set_member_2"

    sadd_result = await database.sadd(set_name, set_value1, set_value2)
    assert sadd_result == 2, f"SADD operation failed: expected 2, got {sadd_result}"
    logger.info("✅ SADD operation successful")

    scard_result = await database.scard(set_name)
    assert scard_result == 2, f"SCARD operation failed: expected 2, got {scard_result}"
    logger.info("✅ SCARD operation successful")

    smembers_result = await database.smembers(set_name)
    assert set_value1 in smembers_result, "SMEMBERS operation failed"
    assert set_value2 in smembers_result, "SMEMBERS operation failed"
    logger.info("✅ SMEMBERS operation successful")

    # Test pipeline operations
    async with database.pipeline() as pipe:
        pipe.set(f"pipe_key_1_{int(time.time())}", "pipe_value_1")
        pipe.set(f"pipe_key_2_{int(time.time())}", "pipe_value_2")
        pipe_results = await pipe.execute()
        assert len(pipe_results) == 2, "Pipeline operation failed"
        logger.info("✅ Pipeline operation successful")

    # Test PING
    ping_result = await database.ping()
    assert ping_result, "PING operation failed"
    logger.info("✅ PING operation successful")

    # Cleanup
    await database.delete(test_key, hash_name, list_name, set_name)

    # Test statistics
    stats = database.get_stats()
    assert stats["name"] == "test_db", "Stats retrieval failed"
    assert stats["db_number"] == 15, "Stats retrieval failed"
    logger.info("✅ Statistics retrieval successful")

    # Close database connection
    await database.close()
    logger.info("✅ Database closed successfully")

    logger.info("=== AsyncRedisDatabase tests completed successfully ===")


async def test_async_redis_manager():
    """Test AsyncRedisManager functionality"""
    logger.info("=== Testing AsyncRedisManager ===")

    # Get manager instance
    manager = await get_redis_manager()
    assert manager is not None, "Failed to get Redis manager"
    logger.info("✅ Redis manager instance obtained")

    # Test database access
    main_db = await manager.main()
    assert main_db is not None, "Failed to get main database"
    logger.info("✅ Main database accessed")

    knowledge_db = await manager.knowledge()
    assert knowledge_db is not None, "Failed to get knowledge database"
    logger.info("✅ Knowledge database accessed")

    cache_db = await manager.cache()
    assert cache_db is not None, "Failed to get cache database"
    logger.info("✅ Cache database accessed")

    # Test database operations through manager
    test_key = f"manager_test_{int(time.time())}"
    test_value = "manager_test_value"

    await main_db.set(test_key, test_value, ex=60)
    retrieved_value = await main_db.get(test_key)
    assert retrieved_value == test_value, "Manager database operation failed"
    logger.info("✅ Manager database operations successful")

    # Test health check
    health = await manager.health_check()
    assert health["overall_healthy"], f"Health check failed: {health}"
    assert "databases" in health, "Health check missing databases info"
    logger.info("✅ Health check successful")

    # Test statistics
    stats = await manager.get_statistics()
    assert "manager" in stats, "Statistics missing manager info"
    assert "databases" in stats, "Statistics missing databases info"
    logger.info("✅ Statistics retrieval successful")

    # Test dynamic database creation
    custom_db = await manager.get_or_create_database("custom_test", 14)
    assert custom_db is not None, "Failed to create custom database"

    # Test custom database operations
    custom_key = f"custom_test_{int(time.time())}"
    await custom_db.set(custom_key, "custom_value", ex=60)
    custom_value = await custom_db.get(custom_key)
    assert custom_value == "custom_value", "Custom database operation failed"
    logger.info("✅ Dynamic database creation successful")

    # Cleanup
    await main_db.delete(test_key)
    await custom_db.delete(custom_key)

    logger.info("=== AsyncRedisManager tests completed successfully ===")


async def test_convenience_functions():
    """Test convenience functions"""
    logger.info("=== Testing Convenience Functions ===")

    # Test get_async_redis
    main_db = await get_async_redis("main")
    assert main_db is not None, "get_async_redis failed"
    logger.info("✅ get_async_redis successful")

    # Test get_main_redis
    main_db2 = await get_main_redis()
    assert main_db2 is not None, "get_main_redis failed"
    logger.info("✅ get_main_redis successful")

    # Test redis_connection context manager
    async with redis_connection("cache") as cache_db:
        test_key = f"context_test_{int(time.time())}"
        await cache_db.set(test_key, "context_value", ex=60)
        value = await cache_db.get(test_key)
        assert value == "context_value", "Context manager operation failed"
        await cache_db.delete(test_key)

    logger.info("✅ Context manager successful")

    logger.info("=== Convenience function tests completed successfully ===")


async def test_circuit_breaker():
    """Test circuit breaker functionality"""
    logger.info("=== Testing Circuit Breaker ===")

    # Create a database with aggressive circuit breaker settings
    from backend.utils.async_redis_manager import CircuitBreakerConfig

    circuit_config = CircuitBreakerConfig(
        failure_threshold=2, recovery_timeout=5, success_threshold=1
    )

    # Test with invalid host to trigger failures
    test_db = AsyncRedisDatabase(
        name="circuit_test",
        db_number=15,
        host="nonexistent_host_12345",
        port=6379,
        connection_timeout=1.0,
        circuit_breaker_config=circuit_config,
    )

    # This should fail and trigger circuit breaker
    init_result = await test_db.initialize()
    assert not init_result, "Expected initialization to fail"
    logger.info("✅ Circuit breaker initialization failure handled")

    # Test circuit breaker statistics
    stats = test_db.get_stats()
    assert (
        stats["circuit_state"] == "open" or stats["stats"]["failed_operations"] > 0
    ), "Circuit breaker not triggered"
    logger.info("✅ Circuit breaker statistics working")

    await test_db.close()

    logger.info("=== Circuit breaker tests completed successfully ===")


async def test_performance():
    """Test performance characteristics"""
    logger.info("=== Testing Performance ===")

    manager = await get_redis_manager()
    main_db = await manager.main()

    # Test bulk operations performance
    num_operations = 100

    # Sequential operations
    start_time = time.time()
    for i in range(num_operations):
        await main_db.set(f"perf_test_{i}", f"value_{i}", ex=60)
    sequential_time = time.time() - start_time

    # Pipeline operations
    start_time = time.time()
    async with main_db.pipeline() as pipe:
        for i in range(num_operations):
            pipe.set(f"perf_test_pipe_{i}", f"value_{i}", ex=60)
        await pipe.execute()
    pipeline_time = time.time() - start_time

    logger.info(f"Sequential operations ({num_operations}): {sequential_time:.3f}s")
    logger.info(f"Pipeline operations ({num_operations}): {pipeline_time:.3f}s")
    logger.info(f"Pipeline speedup: {sequential_time/pipeline_time:.1f}x")

    # Cleanup
    keys_to_delete = [f"perf_test_{i}" for i in range(num_operations)]
    keys_to_delete.extend([f"perf_test_pipe_{i}" for i in range(num_operations)])
    await main_db.delete(*keys_to_delete)

    logger.info("✅ Performance tests completed")


async def test_compatibility_layer():
    """Test Redis compatibility layer"""
    logger.info("=== Testing Compatibility Layer ===")

    # Test compatibility wrapper
    compat = get_redis_client_compat("main")

    # Test async operations (preferred)
    test_key = f"compat_test_{int(time.time())}"
    await compat.aset(test_key, "compat_value", ex=60)
    value = await compat.aget(test_key)
    assert value == "compat_value", "Compatibility async operation failed"
    logger.info("✅ Compatibility async operations successful")

    # Test migration test function
    migration_results = await test_async_migration("main")
    assert migration_results[
        "overall_success"
    ], f"Migration test failed: {migration_results}"
    assert migration_results["migration_ready"], "System not ready for migration"
    logger.info("✅ Migration test successful")

    # Cleanup
    await compat.adelete(test_key)

    logger.info("=== Compatibility layer tests completed successfully ===")


async def test_error_handling():
    """Test error handling and recovery"""
    logger.info("=== Testing Error Handling ===")

    manager = await get_redis_manager()
    main_db = await manager.main()

    # Test timeout handling (this should succeed quickly)
    try:
        await main_db.ping()
        logger.info("✅ Normal ping successful")
    except Exception as e:
        logger.warning(f"Ping failed (may be expected in test environment): {e}")

    # Test non-existent key handling
    non_existent_value = await main_db.get("definitely_does_not_exist_key_12345")
    assert non_existent_value is None, "Non-existent key should return None"
    logger.info("✅ Non-existent key handling successful")

    # Test invalid operation handling
    try:
        # Try to set a key with invalid expiration
        await main_db.expire("non_existent_key_12345", -1)
        logger.info("✅ Invalid operation handled gracefully")
    except Exception as e:
        logger.info(f"✅ Invalid operation correctly rejected: {e}")

    logger.info("=== Error handling tests completed successfully ===")


async def run_comprehensive_tests():
    """Run all comprehensive tests"""
    logger.info("🚀 Starting Comprehensive AsyncRedisManager Tests")

    tests = [
        ("AsyncRedisDatabase", test_async_redis_database),
        ("AsyncRedisManager", test_async_redis_manager),
        ("Convenience Functions", test_convenience_functions),
        ("Circuit Breaker", test_circuit_breaker),
        ("Performance", test_performance),
        ("Compatibility Layer", test_compatibility_layer),
        ("Error Handling", test_error_handling),
    ]

    results = {}

    for test_name, test_func in tests:
        try:
            logger.info(f"\n📋 Running {test_name} tests...")
            start_time = time.time()
            await test_func()
            test_time = time.time() - start_time
            results[test_name] = {
                "success": True,
                "time": round(test_time, 3),
                "error": None,
            }
            logger.info(f"✅ {test_name} tests PASSED in {test_time:.3f}s")
        except Exception as e:
            test_time = time.time() - start_time
            results[test_name] = {
                "success": False,
                "time": round(test_time, 3),
                "error": str(e),
            }
            logger.error(f"❌ {test_name} tests FAILED in {test_time:.3f}s: {e}")
            import traceback

            traceback.print_exc()

    # Print summary
    logger.info("\n" + "=" * 60)
    logger.info("📊 TEST SUMMARY")
    logger.info("=" * 60)

    total_tests = len(tests)
    passed_tests = sum(1 for r in results.values() if r["success"])
    total_time = sum(r["time"] for r in results.values())

    for test_name, result in results.items():
        status = "✅ PASS" if result["success"] else "❌ FAIL"
        logger.info(f"{status:8} {test_name:20} ({result['time']:6.3f}s)")
        if not result["success"]:
            logger.error(f"         Error: {result['error']}")

    logger.info("-" * 60)
    logger.info(
        f"Total: {passed_tests}/{total_tests} tests passed in {total_time:.3f}s"
    )

    if passed_tests == total_tests:
        logger.info("🎉 ALL TESTS PASSED! AsyncRedisManager is ready for production.")
        return True
    else:
        logger.error(
            f"💥 {total_tests - passed_tests} tests failed. Please fix issues before deployment."
        )
        return False


async def main():
    """Main test runner"""
    print("AsyncRedisManager Comprehensive Test Suite")
    print("=" * 50)

    # Check if Redis is available
    try:
        # Test basic connection first
        manager = await get_redis_manager()
        main_db = await manager.main()
        await main_db.ping()
        print("✅ Redis connection verified - proceeding with tests")
    except Exception as e:
        print(f"❌ Redis connection failed: {e}")
        print("Please ensure Redis is running and accessible")
        print("Default connection: localhost:6379")
        return False

    # Run comprehensive tests
    success = await run_comprehensive_tests()

    # Cleanup
    try:
        manager = await get_redis_manager()
        await manager.close_all()
        print("\n🧹 Cleanup completed")
    except Exception as e:
        print(f"⚠️ Cleanup warning: {e}")

    return success


if __name__ == "__main__":
    # Run the test suite
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
