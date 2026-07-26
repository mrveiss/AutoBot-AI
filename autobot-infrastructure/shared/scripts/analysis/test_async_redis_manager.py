#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Test Script for the Canonical Async Redis Client
Comprehensive testing of autobot_shared.redis_client's async operations.

Issue #12649: migrated off `backend.utils.async_redis_manager` and
`backend.utils.redis_compatibility` — both were archived during the Nov 2025
Redis consolidation (see docs/developer/REDIS_CONSOLIDATION_MIGRATION_GUIDE.md)
and this script had been silently dead (ImportError) ever since. It now
exercises the canonical `autobot_shared.redis_client` API directly.
"""

import asyncio
import logging
import sys
import time
from pathlib import Path

# Add the repo root to path so `autobot_shared` is importable when this
# script is run standalone (python3 test_async_redis_manager.py).
repo_root = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(repo_root))

from autobot_shared.redis_client import (
    close_all_redis_connections,
    get_async_redis_client,
    get_redis_health,
    get_redis_metrics,
    redis_context,
    redis_delete,
    redis_get,
    redis_set,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def test_basic_operations():
    """Test basic string/key operations on the canonical async client."""
    logger.info("=== Testing Basic Operations ===")

    client = await get_async_redis_client(database="main")
    assert client is not None, "Failed to get async Redis client for 'main'"

    test_key = f"test_key_{int(time.time())}"
    test_value = "test_value_12345"

    set_result = await client.set(test_key, test_value, ex=60)
    assert set_result, "SET operation failed"
    logger.info("SET operation successful")

    get_result = await client.get(test_key)
    assert get_result == test_value, f"GET operation failed: expected {test_value}, got {get_result}"
    logger.info("GET operation successful")

    exists_result = await client.exists(test_key)
    assert exists_result == 1, "EXISTS operation failed"
    logger.info("EXISTS operation successful")

    ttl_result = await client.ttl(test_key)
    assert 50 <= ttl_result <= 60, f"TTL operation failed: got {ttl_result}"
    logger.info("TTL operation successful")

    await client.delete(test_key)
    logger.info("=== Basic operations tests completed successfully ===")


async def test_hash_operations():
    """Test hash operations on the canonical async client."""
    logger.info("=== Testing Hash Operations ===")

    client = await get_async_redis_client(database="main")
    hash_name = f"test_hash_{int(time.time())}"
    hash_field = "field1"
    hash_value = "hash_value_123"

    hset_result = await client.hset(hash_name, hash_field, hash_value)
    assert hset_result >= 0, "HSET operation failed"
    logger.info("HSET operation successful")

    hget_result = await client.hget(hash_name, hash_field)
    assert hget_result == hash_value, f"HGET operation failed: expected {hash_value}, got {hget_result}"
    logger.info("HGET operation successful")

    hgetall_result = await client.hgetall(hash_name)
    assert hash_field in hgetall_result, "HGETALL operation failed"
    assert hgetall_result[hash_field] == hash_value, "HGETALL value mismatch"
    logger.info("HGETALL operation successful")

    await client.delete(hash_name)
    logger.info("=== Hash operations tests completed successfully ===")


async def test_list_and_set_operations():
    """Test list and set operations on the canonical async client."""
    logger.info("=== Testing List and Set Operations ===")

    client = await get_async_redis_client(database="main")

    list_name = f"test_list_{int(time.time())}"
    lpush_result = await client.lpush(list_name, "list_item_1", "list_item_2")
    assert lpush_result >= 2, "LPUSH operation failed"
    logger.info("LPUSH operation successful")

    llen_result = await client.llen(list_name)
    assert llen_result == 2, f"LLEN operation failed: expected 2, got {llen_result}"
    logger.info("LLEN operation successful")

    lpop_result = await client.lpop(list_name)
    assert lpop_result is not None, "LPOP operation failed"
    logger.info("LPOP operation successful")

    set_name = f"test_set_{int(time.time())}"
    set_value1, set_value2 = "set_member_1", "set_member_2"
    sadd_result = await client.sadd(set_name, set_value1, set_value2)
    assert sadd_result == 2, f"SADD operation failed: expected 2, got {sadd_result}"
    logger.info("SADD operation successful")

    scard_result = await client.scard(set_name)
    assert scard_result == 2, f"SCARD operation failed: expected 2, got {scard_result}"
    logger.info("SCARD operation successful")

    smembers_result = await client.smembers(set_name)
    assert set_value1 in smembers_result, "SMEMBERS operation failed"
    assert set_value2 in smembers_result, "SMEMBERS operation failed"
    logger.info("SMEMBERS operation successful")

    await client.delete(list_name, set_name)
    logger.info("=== List and set operations tests completed successfully ===")


async def test_pipeline_operations():
    """Test pipeline operations on the canonical async client."""
    logger.info("=== Testing Pipeline Operations ===")

    client = await get_async_redis_client(database="main")
    key1, key2 = f"pipe_key_1_{int(time.time())}", f"pipe_key_2_{int(time.time())}"

    async with client.pipeline() as pipe:
        pipe.set(key1, "pipe_value_1")
        pipe.set(key2, "pipe_value_2")
        pipe_results = await pipe.execute()
        assert len(pipe_results) == 2, "Pipeline operation failed"
    logger.info("Pipeline operation successful")

    await client.delete(key1, key2)
    logger.info("=== Pipeline operations tests completed successfully ===")


async def test_named_databases():
    """Test database separation (main/knowledge/cache) via the canonical client."""
    logger.info("=== Testing Named Database Access ===")

    for database in ("main", "knowledge", "cache"):
        db_client = await get_async_redis_client(database=database)
        assert db_client is not None, f"Failed to get async client for '{database}'"
        assert await db_client.ping(), f"PING failed for '{database}'"
        logger.info("Named database '%s' accessed and pinged successfully", database)

    logger.info("=== Named database tests completed successfully ===")


async def test_health_and_metrics():
    """Test health/metrics reporting exposed by the canonical connection manager."""
    logger.info("=== Testing Health and Metrics ===")

    # Touch 'main' first so it has metrics/health entries to report.
    client = await get_async_redis_client(database="main")
    await client.ping()

    health = get_redis_health()
    assert "databases" in health, "Health check missing databases info"
    assert "total_databases" in health, "Health check missing total_databases"
    logger.info("Health check successful: %s", health.get("overall_healthy"))

    metrics = get_redis_metrics("main")
    assert "main" in metrics, "Metrics missing 'main' database entry"
    assert "circuit_breaker_state" in metrics["main"], "Metrics missing circuit_breaker_state"
    logger.info("Circuit breaker state for 'main': %s", metrics["main"]["circuit_breaker_state"])
    logger.info("Metrics retrieval successful")

    logger.info("=== Health and metrics tests completed successfully ===")


async def test_performance():
    """Test performance characteristics: sequential vs pipelined writes."""
    logger.info("=== Testing Performance ===")

    client = await get_async_redis_client(database="main")
    num_operations = 100

    start_time = time.time()
    for i in range(num_operations):
        await client.set(f"perf_test_{i}", f"value_{i}", ex=60)
    sequential_time = time.time() - start_time

    start_time = time.time()
    async with client.pipeline() as pipe:
        for i in range(num_operations):
            pipe.set(f"perf_test_pipe_{i}", f"value_{i}", ex=60)
        await pipe.execute()
    pipeline_time = time.time() - start_time

    logger.info("Sequential operations (%d): %.3fs", num_operations, sequential_time)
    logger.info("Pipeline operations (%d): %.3fs", num_operations, pipeline_time)
    if pipeline_time > 0:
        logger.info("Pipeline speedup: %.1fx", sequential_time / pipeline_time)

    keys_to_delete = [f"perf_test_{i}" for i in range(num_operations)]
    keys_to_delete.extend([f"perf_test_pipe_{i}" for i in range(num_operations)])
    await client.delete(*keys_to_delete)

    logger.info("=== Performance tests completed successfully ===")


async def test_convenience_functions():
    """Test the module-level convenience functions and context manager."""
    logger.info("=== Testing Convenience Functions ===")

    test_key = f"convenience_test_{int(time.time())}"
    set_ok = await redis_set(test_key, "convenience_value", expire=60, database="cache")
    assert set_ok, "redis_set failed"
    logger.info("redis_set successful")

    value = await redis_get(test_key, database="cache")
    assert value == "convenience_value", "redis_get failed"
    logger.info("redis_get successful")

    deleted = await redis_delete(test_key, database="cache")
    assert deleted == 1, "redis_delete failed"
    logger.info("redis_delete successful")

    async with redis_context("cache") as ctx_client:
        ctx_key = f"context_test_{int(time.time())}"
        await ctx_client.set(ctx_key, "context_value", ex=60)
        ctx_value = await ctx_client.get(ctx_key)
        assert ctx_value == "context_value", "Context manager operation failed"
        await ctx_client.delete(ctx_key)
    logger.info("redis_context successful")

    logger.info("=== Convenience function tests completed successfully ===")


async def test_error_handling():
    """Test error handling and recovery on the canonical async client."""
    logger.info("=== Testing Error Handling ===")

    client = await get_async_redis_client(database="main")

    try:
        await client.ping()
        logger.info("Normal ping successful")
    except Exception as e:
        logger.warning("Ping failed (may be expected in test environment): %s", e)

    non_existent_value = await client.get("definitely_does_not_exist_key_12345")
    assert non_existent_value is None, "Non-existent key should return None"
    logger.info("Non-existent key handling successful")

    try:
        await client.expire("non_existent_key_12345", -1)
        logger.info("Invalid operation handled gracefully")
    except Exception as e:
        logger.info("Invalid operation correctly rejected: %s", e)

    logger.info("=== Error handling tests completed successfully ===")


async def run_comprehensive_tests():
    """Run all comprehensive tests"""
    logger.info("Starting Comprehensive Canonical Redis Client Tests")

    tests = [
        ("Basic Operations", test_basic_operations),
        ("Hash Operations", test_hash_operations),
        ("List and Set Operations", test_list_and_set_operations),
        ("Pipeline Operations", test_pipeline_operations),
        ("Named Databases", test_named_databases),
        ("Health and Metrics", test_health_and_metrics),
        ("Performance", test_performance),
        ("Convenience Functions", test_convenience_functions),
        ("Error Handling", test_error_handling),
    ]

    results = {}

    for test_name, test_func in tests:
        start_time = time.time()
        try:
            logger.info("Running %s tests...", test_name)
            await test_func()
            test_time = time.time() - start_time
            results[test_name] = {"success": True, "time": round(test_time, 3), "error": None}
            logger.info("%s tests PASSED in %.3fs", test_name, test_time)
        except Exception as e:
            test_time = time.time() - start_time
            results[test_name] = {"success": False, "time": round(test_time, 3), "error": str(e)}
            logger.error("%s tests FAILED in %.3fs: %s", test_name, test_time, e)

    logger.info("=" * 60)
    logger.info("TEST SUMMARY")
    logger.info("=" * 60)

    total_tests = len(tests)
    passed_tests = sum(1 for r in results.values() if r["success"])
    total_time = sum(r["time"] for r in results.values())

    for test_name, result in results.items():
        status = "PASS" if result["success"] else "FAIL"
        logger.info("%-4s %-24s (%6.3fs)", status, test_name, result["time"])
        if not result["success"]:
            logger.error("     Error: %s", result["error"])

    logger.info("-" * 60)
    logger.info("Total: %d/%d tests passed in %.3fs", passed_tests, total_tests, total_time)

    if passed_tests == total_tests:
        logger.info("ALL TESTS PASSED! Canonical async Redis client is healthy.")
        return True
    else:
        logger.error("%d tests failed. Please investigate before deployment.", total_tests - passed_tests)
        return False


async def main():
    """Main test runner"""
    print("Canonical Async Redis Client Test Suite")
    print("=" * 50)

    try:
        client = await get_async_redis_client(database="main")
        assert client is not None
        await client.ping()
        print("Redis connection verified - proceeding with tests")
    except Exception as e:
        print(f"Redis connection failed: {e}")
        print("Please ensure Redis is running and accessible")
        return False

    success = await run_comprehensive_tests()

    try:
        await close_all_redis_connections()
        print("Cleanup completed")
    except Exception as e:
        print(f"Cleanup warning: {e}")

    return success


if __name__ == "__main__":
    # Run the test suite
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
