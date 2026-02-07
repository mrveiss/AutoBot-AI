# AutoBot Async Operations Performance Baseline & Validation

**Week 2-3: Task 2.5 - Performance Load Testing**

## Mission

Establish comprehensive performance baseline BEFORE async conversions (Tasks 2.1-2.4), then validate 10-50x improvements AFTER senior-backend-engineer completes async implementation.

## Test Framework

### Phase 1: Baseline Measurement (BEFORE Async - Current State)

**Run Now:**
```bash
cd /home/kali/Desktop/AutoBot
python tests/performance/test_async_baseline.py
```

**Measures:**
- ✅ Chat response time with 50 concurrent users
- ✅ Redis operations throughput (100 concurrent ops)
- ✅ Mixed file I/O + Redis workloads
- ✅ Cross-VM latency (6-VM distributed architecture)
- ✅ Event loop blocking detection
- ✅ P50, P95, P99 latency percentiles

**Baseline Expectations (Current Synchronous Code):**
- Chat response: 10-50s with event loop blocking
- Redis ops: Limited by synchronous client (~100 ops/sec)
- Cross-VM: Network latency dominant
- File I/O: Blocking on large transcript files

###Phase 2: Post-Async Validation (AFTER Tasks 2.1-2.4 Complete)

**Run After Async Conversions:**
```bash
# Same script, run after backend-engineer completes async work
python tests/performance/test_async_baseline.py

# Compare with baseline
python tests/performance/compare_async_results.py \
    --baseline results/async_baseline_YYYYMMDD_HHMMSS.json \
    --current results/async_baseline_YYYYMMDD_HHMMSS.json
```

**Success Metrics (Post-Async Targets):**
- ✅ Chat response: <2s (p95) - **10-50x improvement**
- ✅ 50+ concurrent users without degradation
- ✅ Event loop blocking eliminated
- ✅ Redis ops: >1000 ops/sec with async client
- ✅ Cross-VM latency: <100ms (p95)

## Test Scenarios

### 1. Concurrent Chat Requests (50 Users)

**What It Tests:**
- Backend API async handling under concurrent load
- LLM request parallelization
- Redis conversation history async access
- File I/O async transcript operations

**Synchronous Bottlenecks:**
- Blocking Redis client calls (Task 2.1)
- Synchronous file transcript writes (Task 2.2)
- Event loop blocked by synchronous I/O

**Expected Improvement:**
- **BEFORE**: 10-50s response time with blocking
- **AFTER**: <2s (p95) with full async pipeline

### 2. Concurrent Redis Operations (100 Ops)

**What It Tests:**
- Redis connection pooling efficiency
- Async Redis client performance
- Database operation parallelization

**Synchronous Bottlenecks:**
- `redis.Redis()` synchronous client (115 files identified)
- Sequential database operations
- No connection pooling

**Expected Improvement:**
- **BEFORE**: ~100-200 ops/sec sequential
- **AFTER**: >1000 ops/sec with async client and pooling

### 3. Mixed File I/O + Redis Operations (50 Ops)

**What It Tests:**
- Realistic workload combining database + filesystem
- Async coordination between different I/O types
- Chat transcript append + Redis cache performance

**Synchronous Bottlenecks:**
- `open()` blocking file operations (8 backend API files identified)
- Mixed sync/async code paths
- File lock contention

**Expected Improvement:**
- **BEFORE**: Sequential I/O operations
- **AFTER**: Parallel I/O with `aiofiles` and async Redis

### 4. Cross-VM Latency (6-VM Architecture)

**What It Tests:**
- Inter-VM communication performance
- Network latency across distributed services
- Service health check responsiveness

**Measured VMs:**
- Frontend (172.16.168.21)
- NPU Worker (172.16.168.22)
- Redis (172.16.168.23)
- AI Stack (172.16.168.24)
- Browser (172.16.168.25)

**Target:**
- <100ms P95 latency across all VMs

## Performance Metrics Captured

### Latency Metrics
- **Mean**: Average response time
- **Median (P50)**: Middle value, better than mean for skewed distributions
- **P95**: 95th percentile - most requests faster than this
- **P99**: 99th percentile - worst-case for most users
- **Min/Max**: Best and worst case latencies
- **Std Dev**: Latency consistency

### Throughput Metrics
- **Requests per second**: Overall throughput
- **Success rate**: Percentage of successful requests
- **Concurrent capacity**: Maximum users without degradation

### Event Loop Metrics
- **Blocking detection**: Measures synchronous operations blocking event loop
- **Async operation time**: Time spent in async operations
- **I/O wait time**: Time waiting for I/O completion

## Results Storage

**Location:** `/home/kali/Desktop/AutoBot/tests/performance/results/`

**Baseline Files:**
```
async_baseline_YYYYMMDD_HHMMSS.json  # Before async conversions
async_post_YYYYMMDD_HHMMSS.json      # After async conversions
comparison_report_YYYYMMDD.json      # Before/after analysis
```

**Report Format:**
```json
{
  "timestamp": "2025-10-09T...",
  "test_phase": "BASELINE_BEFORE_ASYNC_CONVERSIONS",
  "total_duration_seconds": 120.5,
  "test_results": [
    {
      "test_name": "concurrent_chat_50_users",
      "p95_latency_ms": 15000,  // 15s baseline (SLOW!)
      "requests_per_second": 3.2,
      "success_rate": 98.0
    }
  ],
  "performance_analysis": {
    "chat_performance": {
      "baseline_p95_ms": 15000,
      "target_after_async_ms": 2000,
      "improvement_needed": "10-50x faster"
    }
  }
}
```

## Running the Tests

### Prerequisites
```bash
# Ensure AutoBot backend is running
bash run_autobot.sh --dev

# Install test dependencies (should already be installed)
pip install aiohttp redis[asyncio] aiofiles
```

### Baseline Testing (Do This NOW)
```bash
# Run baseline performance tests
cd /home/kali/Desktop/AutoBot
python tests/performance/test_async_baseline.py

# Results saved to: tests/performance/results/async_baseline_YYYYMMDD_HHMMSS.json
```

### Post-Async Validation (After Tasks 2.1-2.4)
```bash
# After senior-backend-engineer completes async conversions:
python tests/performance/test_async_baseline.py

# Compare results
python tests/performance/compare_async_results.py \
    --baseline results/async_baseline_20251009_143000.json \
    --current results/async_baseline_20251009_150000.json
```

## Event Loop Profiling

**Detect Synchronous Blocking:**
```python
import asyncio

# Enable debug mode to detect blocking operations
asyncio.run(main(), debug=True)

# AsyncIO will warn about:
# - Synchronous I/O operations blocking event loop
# - Long-running synchronous functions
# - Missing await statements
```

**Expected Warnings (BEFORE Async):**
```
Executing <function_name> took 2.5 seconds (event loop blocked)
```

**Expected Behavior (AFTER Async):**
```
No warnings - all I/O operations properly async
```

## Validation Criteria

### ✅ PASS Criteria (Post-Async)
- Chat P95 latency <2s (down from 10-50s)
- Redis ops >1000/sec (up from ~100/sec)
- Cross-VM latency <100ms P95
- 50+ concurrent users supported
- Zero event loop blocking warnings
- >95% success rate maintained

### ❌ FAIL Criteria
- Chat P95 >5s (insufficient improvement)
- Event loop still blocking
- Cross-VM latency >200ms
- <90% success rate

## Integration with CI/CD

**Automated Performance Testing:**
```yaml
# .github/workflows/performance-tests.yml
name: Async Performance Validation

on:
  pull_request:
    paths:
      - 'backend/**'
      - 'src/**'

jobs:
  performance-test:
    runs-on: ubuntu-latest
    steps:
      - name: Run baseline tests
        run: python tests/performance/test_async_baseline.py

      - name: Check performance regression
        run: |
          if [ $P95_LATENCY -gt 2000 ]; then
            echo "Performance regression detected"
            exit 1
          fi
```

## Troubleshooting

### High Latency Issues
```bash
# Check for synchronous bottlenecks
grep -r "redis.Redis(" backend/ src/  # Should find zero after async
grep -r "open(" backend/api/  # Should use aiofiles after async

# Profile event loop
python -m asyncio --debug tests/performance/test_async_baseline.py
```

### Low Throughput Issues
```bash
# Check Redis connection pooling
redis-cli -h 172.16.168.23 INFO clients

# Check file descriptor limits
ulimit -n  # Should be >1024 for high concurrency
```

## Next Steps

1. **Run Baseline Tests NOW** (before async conversions)
2. **Store baseline results** for comparison
3. **Wait for Tasks 2.1-2.4 completion** (senior-backend-engineer)
4. **Re-run tests** after async conversions
5. **Validate 10-50x improvements**
6. **Document findings** in Memory MCP

## Related Documentation

- Implementation Plan: `/planning/tasks/backend-vulnerabilities-implementation-plan.md` (Lines 281-296)
- Existing Performance Tools: `/monitoring/performance_benchmark.py`
- System Monitoring: `/monitoring/performance_monitor.py`
- Baseline Assessment: `/reports/performance/baseline_performance_assessment.py`

## Performance Engineer Notes

**Current Status (2025-10-09):**
- ✅ Baseline test framework created
- ✅ Test scenarios implemented (4/4)
- ✅ Metrics calculation complete
- ✅ Results storage configured
- ⏳ **AWAITING**: Baseline test execution
- ⏳ **AWAITING**: Tasks 2.1-2.4 completion (async conversions)
- ⏳ **AWAITING**: Post-async validation

**Critical Findings:**
- 115 files with potentially synchronous Redis clients
- 8 backend API files with synchronous file operations
- chat_workflow_manager.py already uses async (good baseline!)
- Existing performance infrastructure reusable

**Recommendations:**
1. Run baseline tests immediately
2. Monitor event loop blocking during baseline
3. Document current performance characteristics
4. Prepare for 10-50x improvement validation
