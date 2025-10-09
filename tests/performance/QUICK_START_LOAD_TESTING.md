# Quick Start: Async Load Testing

## Prerequisites

1. **Backend running**: AutoBot backend must be running on `http://172.16.168.20:8001`
2. **Redis available**: Redis server running on `172.16.168.23:6379`
3. **Async conversion complete**: Tasks 2.1-2.4 must be completed

## Install Dependencies

```bash
pip install locust pytest-benchmark numpy matplotlib httpx
```

## Run Tests

### Option 1: Run All Tests with Report Generation

```bash
python tests/performance/test_async_operations.py
```

**Output:**
- Console output with live progress
- JSON report: `reports/performance/async_load_test_results_<timestamp>.json`
- Markdown report: `reports/performance/async_load_test_report_<timestamp>.md`

### Option 2: Run via Pytest

```bash
pytest tests/performance/test_async_operations.py -v -s
```

**Benefits:**
- Integrates with existing test suite
- Fails fast on assertion errors
- Standard pytest output format

### Option 3: Run Individual Test

```bash
# Test 1: HTTP load testing
pytest tests/performance/test_async_operations.py::test_50_concurrent_chat_requests -v -s

# Test 2: Redis operations
pytest tests/performance/test_async_operations.py::test_100_concurrent_redis_operations -v -s

# Test 3: Mixed I/O
pytest tests/performance/test_async_operations.py::test_mixed_file_redis_operations -v -s

# Test 4: Cross-VM
pytest tests/performance/test_async_operations.py::test_cross_vm_concurrent_requests -v -s
```

## Expected Output

```
================================================================================
Starting Async Operations Load Testing Suite
================================================================================

🚀 Test 1: Running 50 concurrent chat requests...
✅ Test 1 Complete: 48/50 successful, P95: 450.23ms

🚀 Test 2: Running 100 concurrent Redis operations...
✅ Test 2 Complete: 100/100 successful, P95: 125.67ms

🚀 Test 3: Running 50 mixed file/Redis operations...
✅ Test 3 Complete: 50/50 successful, P95: 234.89ms

🚀 Test 4: Running cross-VM concurrent requests...
✅ Test 4 Complete: 4/6 VMs reachable, P95: 89.12ms

================================================================================
Load Testing Suite Complete
================================================================================

📊 PERFORMANCE TEST SUMMARY
================================================================================

50 Concurrent Chat Requests (HTTP):
  ✅ Successful: 48/50
  ⏱️  P95 Latency: 450.23ms
  🔄 Throughput: 12.34 req/s
  🚨 Error Rate: 4.00%
  ⚡ Event Loop: OK ✅

100 Concurrent Redis Operations:
  ✅ Successful: 100/100
  ⏱️  P95 Latency: 125.67ms
  🔄 Throughput: 82.45 req/s
  🚨 Error Rate: 0.00%
  ⚡ Event Loop: OK ✅

...
================================================================================

Performance Report Generated:
  JSON: reports/performance/async_load_test_results_20251006_143022.json
  Markdown: reports/performance/async_load_test_report_20251006_143022.md
```

## Success Criteria

All tests must meet:

- ✅ **P95 latency < 2 seconds**
- ✅ **No event loop blocking**
- ✅ **Error rate < 1%**
- ✅ **10-50x improvement** over blocking operations

## View Reports

### JSON Report

```bash
cat reports/performance/async_load_test_results_*.json | jq '.'
```

### Markdown Report

```bash
cat reports/performance/async_load_test_report_*.md
```

Or open in your favorite markdown viewer.

## Troubleshooting

**Backend not running:**
```bash
bash run_autobot.sh --dev
```

**Redis not accessible:**
```bash
redis-cli -h 172.16.168.23 ping
```

**Import errors:**
```bash
pip install locust pytest-benchmark numpy matplotlib httpx
```

**VMs unreachable (Test 4):**
- This is expected if VMs are not running
- Test will pass if at least 50% VMs respond
- Check VM status: `ping 172.16.168.21`, etc.

## Next Steps

1. Review generated reports in `reports/performance/`
2. Compare before/after metrics
3. Validate 10-50x improvement achieved
4. Document performance improvements in WEEK_1_FINAL_STATUS.md

---

**For detailed documentation**: See `README_ASYNC_LOAD_TESTING.md`
