# Knowledge Base Integration Tests

## Overview

Integration tests for `KnowledgeBase` async operations with **real Redis connections**. These tests validate the async refactoring work (KB-ASYNC-009) by testing against actual Redis infrastructure.

## Test Coverage

### Test Categories

1. **Redis Connection Tests**
   - Connection establishment via AsyncRedisManager
   - Connection pooling behavior
   - Connection persistence across operations
   - Ping verification

2. **Real Operation Tests**
   - `store_fact()` with actual Redis storage
   - `get_fact()` with all 3 modes:
     - Specific fact_id retrieval
     - Query-based search
     - All facts retrieval (pipeline)
   - Data persistence verification
   - JSON encoding/decoding with complex metadata

3. **Concurrent Operation Tests**
   - 50+ concurrent `store_fact()` operations
   - 50+ concurrent `get_fact()` operations
   - 60+ mixed concurrent operations
   - 100+ operations testing connection pool limits
   - No connection pool exhaustion

4. **Performance Tests**
   - P95 latency measurement (target: <2000ms)
   - Bulk store performance (100 facts)
   - Bulk retrieve performance (50 retrievals)
   - Throughput metrics

5. **Timeout and Error Tests**
   - Timeout protection enforcement (2s limits)
   - Invalid data handling
   - Non-existent fact retrieval
   - Graceful degradation

## Prerequisites

### Required Services

1. **Redis Server Running**
   ```bash
   # Redis must be available at 172.16.168.23:6379
   redis-cli -h 172.16.168.23 -p 6379 ping
   ```

2. **Python Dependencies**
   ```bash
   pip install pytest pytest-asyncio aioredis
   ```

3. **AutoBot Backend**
   - AsyncRedisManager must be available
   - Configuration properly set up

## Running Tests

### Run All Integration Tests

```bash
# From AutoBot root directory
python -m pytest tests/integration/test_knowledge_base_integration.py -v
```

### Run Specific Test Categories

```bash
# Connection tests only
python -m pytest tests/integration/test_knowledge_base_integration.py -v -k "connection"

# Concurrent operation tests
python -m pytest tests/integration/test_knowledge_base_integration.py -v -k "concurrent"

# Performance tests
python -m pytest tests/integration/test_knowledge_base_integration.py -v -k "performance"

# Timeout tests
python -m pytest tests/integration/test_knowledge_base_integration.py -v -k "timeout"
```

### Run Individual Tests

```bash
# Test Redis connection
python -m pytest tests/integration/test_knowledge_base_integration.py::TestKnowledgeBaseRedisIntegration::test_redis_connection_established -v

# Test concurrent stores
python -m pytest tests/integration/test_knowledge_base_integration.py::TestKnowledgeBaseRedisIntegration::test_concurrent_store_operations -v

# Test P95 latency
python -m pytest tests/integration/test_knowledge_base_integration.py::TestKnowledgeBaseRedisIntegration::test_performance_p95_latency -v
```

### Generate Coverage Report

```bash
python -m pytest tests/integration/test_knowledge_base_integration.py --cov=src.knowledge_base --cov-report=html
```

## Test Behavior

### Automatic Skip When Redis Unavailable

Tests automatically skip if Redis is not available:

```python
@pytest.fixture
async def kb(self):
    kb = KnowledgeBase()
    await kb._ensure_redis_initialized()

    if not kb.aioredis_client:
        pytest.skip("Redis not available at 172.16.168.23:6379")
```

This prevents false failures when running in environments without Redis.

### Test Data Cleanup

All tests clean up after themselves:

```python
# Cleanup: Remove all test facts
try:
    test_keys = await kb._scan_redis_keys_async("fact:test_*")
    if test_keys:
        await kb.aioredis_client.delete(*test_keys)
except Exception:
    pass
```

## Expected Results

### All Tests Passing (Redis Available)

```
tests/integration/test_knowledge_base_integration.py::TestKnowledgeBaseRedisIntegration::test_redis_connection_established PASSED
tests/integration/test_knowledge_base_integration.py::TestKnowledgeBaseRedisIntegration::test_connection_pool_multiple_operations PASSED
tests/integration/test_knowledge_base_integration.py::TestKnowledgeBaseRedisIntegration::test_store_fact_real_redis PASSED
tests/integration/test_knowledge_base_integration.py::TestKnowledgeBaseRedisIntegration::test_get_fact_by_id_real_redis PASSED
tests/integration/test_knowledge_base_integration.py::TestKnowledgeBaseRedisIntegration::test_get_fact_by_query_real_redis PASSED
tests/integration/test_knowledge_base_integration.py::TestKnowledgeBaseRedisIntegration::test_get_all_facts_real_redis PASSED
tests/integration/test_knowledge_base_integration.py::TestKnowledgeBaseRedisIntegration::test_concurrent_store_operations PASSED
tests/integration/test_knowledge_base_integration.py::TestKnowledgeBaseRedisIntegration::test_concurrent_get_operations PASSED
tests/integration/test_knowledge_base_integration.py::TestKnowledgeBaseRedisIntegration::test_mixed_concurrent_operations PASSED
tests/integration/test_knowledge_base_integration.py::TestKnowledgeBaseRedisIntegration::test_performance_p95_latency PASSED
tests/integration/test_knowledge_base_integration.py::TestKnowledgeBaseRedisIntegration::test_timeout_protection_store PASSED
tests/integration/test_knowledge_base_integration.py::TestKnowledgeBaseRedisIntegration::test_timeout_protection_get PASSED
tests/integration/test_knowledge_base_integration.py::TestKnowledgeBaseRedisIntegration::test_connection_persistence PASSED
tests/integration/test_knowledge_base_integration.py::TestKnowledgeBaseRedisIntegration::test_error_recovery_invalid_data PASSED
tests/integration/test_knowledge_base_integration.py::TestKnowledgeBaseRedisIntegration::test_concurrent_operations_no_pool_exhaustion PASSED
tests/integration/test_knowledge_base_integration.py::TestKnowledgeBaseRedisIntegration::test_data_persistence_across_operations PASSED
tests/integration/test_knowledge_base_integration.py::TestKnowledgeBaseRedisIntegration::test_json_encoding_complex_metadata PASSED

=========================== 22 passed in X.XXs ===========================
```

### Performance Output Examples

```
✓ 50 concurrent stores completed in 1.23s
✓ 50 concurrent gets completed in 0.87s
✓ 60 mixed operations completed in 1.45s
✓ 100 operations completed without pool exhaustion in 2.34s
✓ Store P95 latency: 156.32ms
✓ Get P95 latency: 98.45ms
✓ Stored 100 facts in 4.56s (21.9 facts/sec)
✓ Performed 50 retrievals in 3.21s (15.6 ops/sec)
```

## Integration Test Structure

### Test Classes

1. **TestKnowledgeBaseRedisIntegration**
   - Main integration tests (17 tests)
   - Tests all async operations
   - Validates concurrent behavior
   - Measures performance

2. **TestKnowledgeBaseAsyncRedisManagerIntegration**
   - AsyncRedisManager integration (3 tests)
   - Connection pooling verification
   - Circuit breaker integration

3. **TestKnowledgeBasePerformanceIntegration**
   - Performance-focused tests (2 tests)
   - Bulk operations
   - Throughput measurements

### Total Tests: 22

## Key Validations

1. **Connection Pooling Works**
   - Multiple operations reuse connections
   - No connection exhaustion under 100+ concurrent ops
   - Connections properly released

2. **All get_fact() Modes Work**
   - Mode 1: Specific fact_id retrieval
   - Mode 2: Query-based search
   - Mode 3: All facts retrieval with pipeline

3. **Timeout Protection Active**
   - 2s timeout enforced on all Redis operations
   - Operations complete well within limits
   - No indefinite blocking

4. **Performance Targets Met**
   - P95 latency < 2000ms
   - Store throughput > 10 facts/sec
   - Retrieve throughput > 5 ops/sec

5. **Data Integrity**
   - Complex metadata preserved
   - Unicode and special characters handled
   - Nested structures maintained

## Troubleshooting

### Redis Connection Refused

```bash
# Check Redis is running
sudo systemctl status redis

# Start Redis if needed
sudo systemctl start redis

# Check Redis is listening on correct port
netstat -ln | grep 6379
```

### Tests Skipped

If all tests show `SKIPPED`, Redis is not available at the configured address. Check:

1. Redis server is running
2. Network connectivity to 172.16.168.23:6379
3. Firewall rules allow connection
4. Redis configured to accept remote connections

### Timeout Failures

If timeout tests fail, check:

1. Redis server performance
2. Network latency to Redis
3. System load during test execution

## Development Notes

### Adding New Integration Tests

1. **Add to appropriate test class**
2. **Use the `kb` fixture** for KnowledgeBase instance
3. **Clean up test data** in fixture teardown
4. **Skip if Redis unavailable** (handled by fixture)

Example:
```python
@pytest.mark.asyncio
async def test_my_new_integration(self, kb):
    """Test description"""
    # Test implementation
    result = await kb.some_operation()
    assert result["status"] == "success"
```

### Performance Benchmarks

Update performance targets if infrastructure changes:

```python
# Current targets
P95_LATENCY_TARGET = 2000  # milliseconds
MIN_STORE_RATE = 10        # facts/sec
MIN_RETRIEVE_RATE = 5      # ops/sec
```

## Related Documentation

- **Unit Tests**: `/home/kali/Desktop/AutoBot/tests/unit/test_knowledge_base_async.py`
- **KB-ASYNC Implementation**: `/home/kali/Desktop/AutoBot/src/knowledge_base.py`
- **AsyncRedisManager**: `/home/kali/Desktop/AutoBot/backend/utils/async_redis_manager.py`
- **Architecture**: `/home/kali/Desktop/AutoBot/docs/architecture/`

## Success Criteria

✅ All 22 integration tests pass with real Redis
✅ No connection pool exhaustion under 100+ concurrent ops
✅ P95 latency < 2000ms for store and get operations
✅ All 3 get_fact() modes work correctly
✅ Timeout protection enforced (2s limits)
✅ Data persistence validated across operations
✅ Complex metadata encoding/decoding works
✅ Graceful error handling verified

**Status**: Ready for execution once Redis is available ✓
