# Async Operations Load Testing - Task 2.5

## Overview

Comprehensive performance load testing suite that validates async operations deliver 10-50x performance improvement under concurrent load.

## Test Scenarios

### Test 1: 50 Concurrent Chat Requests (HTTP Load)
- **Method**: Locust-based HTTP load testing
- **Target**: Real FastAPI `/api/chat` endpoint
- **Success Criteria**:
  - Total time < 5 seconds
  - P95 latency < 2 seconds
  - No event loop blocking
  - Error rate < 1%

### Test 2: 100 Concurrent Redis Operations
- **Method**: Direct async Redis operations
- **Target**: AsyncRedisManager with connection pooling
- **Success Criteria**:
  - All operations complete in < 2 seconds
  - No event loop blocking
  - Error rate < 1%

### Test 3: Mixed File I/O + Redis Operations
- **Method**: 25 file operations + 25 Redis operations concurrently
- **Target**: Async file I/O (`asyncio.to_thread`) + async Redis
- **Success Criteria**:
  - Operations don't block each other
  - Total time < 5 seconds
  - No event loop blocking

### Test 4: Cross-VM Concurrent Requests
- **Method**: Health checks to all 6 VMs simultaneously
- **Target**: Main(20), Frontend(21), NPU(22), Redis(23), AI-Stack(24), Browser(25)
- **Success Criteria**:
  - At least 50% VMs reachable
  - No event loop blocking
  - Distributed coordination works

## Installation

### Install Dependencies

```bash
# From AutoBot root directory
pip install locust pytest-benchmark numpy matplotlib httpx
```

### Dependencies Added:
- `locust` - HTTP load testing framework
- `pytest-benchmark` - Performance benchmarking for pytest
- `numpy` - Percentile calculations
- `matplotlib` - Performance visualization (future use)
- `httpx` - Async HTTP client

## Running Tests

### Run All Tests (Pytest)

```bash
# From AutoBot root directory
pytest tests/performance/test_async_operations.py -v -s
```

### Run Individual Tests

```bash
# Test 1: 50 Concurrent Chat Requests
pytest tests/performance/test_async_operations.py::test_50_concurrent_chat_requests -v -s

# Test 2: 100 Concurrent Redis Operations
pytest tests/performance/test_async_operations.py::test_100_concurrent_redis_operations -v -s

# Test 3: Mixed File I/O + Redis
pytest tests/performance/test_async_operations.py::test_mixed_file_redis_operations -v -s

# Test 4: Cross-VM Requests
pytest tests/performance/test_async_operations.py::test_cross_vm_concurrent_requests -v -s
```

### Run Complete Load Testing Suite

```bash
# Run all tests and generate comprehensive report
python tests/performance/test_async_operations.py
```

This will:
1. Execute all 4 test scenarios
2. Collect performance metrics
3. Generate JSON report in `reports/performance/async_load_test_results_<timestamp>.json`
4. Generate Markdown report in `reports/performance/async_load_test_report_<timestamp>.md`

## Performance Metrics Collected

### Latency Distribution
- **Min Response Time**: Fastest operation
- **Average Response Time**: Mean latency
- **P50 (Median)**: 50th percentile latency
- **P95**: 95th percentile latency (primary success metric)
- **P99**: 99th percentile latency
- **Max Response Time**: Slowest operation

### Throughput
- **Requests per Second**: Throughput rate
- **Total Time**: Complete test duration
- **Concurrency Level**: Simultaneous operations

### Reliability
- **Success Rate**: Percentage of successful operations
- **Error Rate**: Percentage of failed operations
- **Event Loop Health**: Blocking detection

## Success Criteria

All tests must meet these criteria to pass:

✅ **10-50x improvement** in response time (compared to blocking operations)
✅ **P95 latency < 2 seconds** for all scenarios
✅ **No event loop blocking** detected
✅ **50+ concurrent users** supported without degradation
✅ **Zero timeouts or errors** under load (< 1% error rate)

## Report Output

### JSON Report (`reports/performance/async_load_test_results_<timestamp>.json`)

```json
{
  "timestamp": "2025-10-06T...",
  "test_suite": "Async Operations Load Testing",
  "metrics": [
    {
      "test_name": "50 Concurrent Chat Requests (HTTP)",
      "total_requests": 50,
      "p95_latency": 0.45,
      "event_loop_blocked": false,
      ...
    }
  ],
  "summary": {
    "total_tests": 4,
    "all_passed": true,
    "avg_p95_latency": 0.52
  }
}
```

### Markdown Report (`reports/performance/async_load_test_report_<timestamp>.md`)

Comprehensive report with:
- Executive summary table
- Detailed metrics per test
- Success criteria evaluation
- Before/after comparison (if baseline provided)

## Event Loop Monitoring

The test suite includes sophisticated event loop monitoring:

```python
async def _monitor_event_loop():
    """Detect event loop blocking"""
    for _ in range(10):
        start = time.time()
        await asyncio.sleep(0.001)  # 1ms sleep
        duration = time.time() - start

        # If sleep takes >10ms, event loop is blocked
        if duration > 0.01:
            return True  # BLOCKED
    return False  # OK
```

This runs concurrently with all operations to detect blocking behavior in real-time.

## Troubleshooting

### Test Failures

**P95 Latency Exceeds 2s:**
- Check if async conversion is complete (Tasks 2.1-2.4)
- Verify Redis connection pooling is enabled
- Check for blocking I/O operations

**Event Loop Blocked:**
- Identify blocking operations (file I/O, database calls)
- Ensure all I/O uses `asyncio.to_thread` or async libraries
- Review CPU-intensive operations

**High Error Rate:**
- Check service health: `docker ps`, `systemctl status`
- Verify Redis connectivity: `redis-cli -h 172.16.168.23 ping`
- Check backend logs: `tail -f logs/backend.log`

### VM Connectivity Issues (Test 4)

If VMs are unreachable:

```bash
# Check VM status
ping 172.16.168.21  # Frontend
ping 172.16.168.22  # NPU Worker
ping 172.16.168.23  # Redis
ping 172.16.168.24  # AI Stack
ping 172.16.168.25  # Browser

# Verify services running
curl http://172.16.168.20:8001/api/health  # Main backend
curl http://172.16.168.21:5173  # Frontend
```

### Locust Load Testing Issues

If Locust tests fail to start:

```bash
# Verify backend is running
curl http://172.16.168.20:8001/api/health

# Check if port is accessible
nc -zv 172.16.168.20 8001

# Run Locust standalone for debugging
locust -f tests/performance/test_async_operations.py --host=http://172.16.168.20:8001
```

## Integration with CI/CD

Add to pytest run:

```yaml
# .github/workflows/performance-tests.yml
- name: Run Performance Load Tests
  run: |
    pytest tests/performance/test_async_operations.py -v --tb=short

- name: Upload Performance Reports
  uses: actions/upload-artifact@v3
  with:
    name: performance-reports
    path: reports/performance/
```

## Architecture

```
AsyncOperationsLoadTester
├── setup() - Initialize Redis and Chat managers
├── test_concurrent_chat_requests() - Locust HTTP load
├── test_concurrent_redis_operations() - Async Redis ops
├── test_mixed_file_redis_operations() - Combined I/O
├── test_cross_vm_concurrent_requests() - Distributed test
├── teardown() - Cleanup resources
└── run_all_tests() - Orchestrate complete suite

PerformanceReportGenerator
├── generate_report() - Create JSON + Markdown
├── _generate_json_report() - Metrics export
└── _generate_markdown_report() - Human-readable report
```

## Performance Baseline

**Before Async Conversion (Blocking):**
- Chat requests: ~10-50 seconds for 50 users
- Redis operations: Sequential, event loop blocked
- File I/O: Blocking operations

**After Async Conversion (Target):**
- Chat requests: < 5 seconds total, P95 < 2s
- Redis operations: 100 ops in < 2 seconds
- File I/O: Non-blocking, concurrent execution
- **Expected Improvement: 10-50x faster**

## References

- **Task Documentation**: WEEK 2-3: PERFORMANCE LOAD TESTING - Task 2.5
- **Async Redis Manager**: `backend/utils/async_redis_manager.py`
- **Chat Workflow Manager**: `src/chat_workflow_manager.py`
- **Existing Tests**: `tests/performance/test_async_chat_performance.py`

---

**Generated by**: AutoBot Performance Testing Suite
**Last Updated**: 2025-10-06
