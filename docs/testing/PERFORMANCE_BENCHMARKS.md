# Performance Benchmarking Suite

**Status:** ✅ Production Ready
**Version:** 1.0.0
**Date:** 2025-11-16
**Issue:** #58 - Performance Benchmarking Suite
**Author:** mrveiss

## Overview

AutoBot's Performance Benchmarking Suite provides automated performance testing, regression detection, and comprehensive metrics collection for API endpoints, RAG operations, and system components.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│              Benchmark Runner Script                 │
│            scripts/run_benchmarks.sh                 │
└─────────────────┬───────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────┐
│           Benchmark Framework Core                   │
│        tests/benchmarks/benchmark_base.py            │
├─────────────────────────────────────────────────────┤
│  ┌─────────┐  ┌─────────┐  ┌──────────────────┐   │
│  │ Runner  │  │ Results │  │   Regression     │   │
│  │ Engine  │  │ Metrics │  │    Detection     │   │
│  └─────────┘  └─────────┘  └──────────────────┘   │
└─────────────────┬───────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────┐
│              Benchmark Categories                    │
├──────────────┬───────────────┬──────────────────────┤
│     API      │     RAG       │      Database        │
│  Benchmarks  │  Benchmarks   │    Benchmarks        │
└──────────────┴───────────────┴──────────────────────┘
```

## Features

### Core Capabilities

- **Automated Benchmarking** - Run benchmarks with configurable parameters
- **Statistical Analysis** - Average, median, P95, P99, standard deviation
- **Regression Detection** - Automatic detection of performance degradation
- **Result Persistence** - Save results for historical tracking
- **Baseline Comparison** - Compare current results against baselines
- **Performance Assertions** - Enforce performance requirements

### Metrics Collected

For each benchmark:
- Total execution time
- Average time (mean)
- Minimum time
- Maximum time
- Median time
- Standard deviation
- P95 (95th percentile)
- P99 (99th percentile)
- Operations per second

## Quick Start

### Run All Benchmarks

```bash
bash scripts/run_benchmarks.sh --all
```

### Run Specific Category

```bash
# API endpoint benchmarks
bash scripts/run_benchmarks.sh --api

# RAG query benchmarks
bash scripts/run_benchmarks.sh --rag
```

### Verbose Output

```bash
bash scripts/run_benchmarks.sh --all -v
```

## Benchmark Categories

### 1. API Endpoint Benchmarks

**File:** `tests/benchmarks/api_benchmarks.py`

Tests include:
- Health endpoint response time
- Chat message processing
- MCP tools listing
- Knowledge search queries
- Concurrent request handling
- JSON serialization/deserialization
- Pydantic model validation
- UUID generation

**Performance Targets:**
| Benchmark | Max Avg (ms) | Min Ops/sec |
|-----------|--------------|-------------|
| Health Check | 100 | - |
| JSON Serialization | 1.0 | 1000 |
| Pydantic Validation | 0.5 | 2000 |
| UUID Generation | 0.1 | 10000 |

### 2. RAG Query Benchmarks

**File:** `tests/benchmarks/rag_benchmarks.py`

Tests include:
- Vector similarity computation
- Top-K document retrieval
- Context window assembly
- Document chunking
- Metadata filtering
- Text preprocessing
- Batch embedding simulation
- Full RAG pipeline simulation
- Query expansion

**Performance Targets:**
| Benchmark | Max Avg (ms) | Min Ops/sec |
|-----------|--------------|-------------|
| Vector Similarity (50 docs) | 5.0 | 200 |
| Context Assembly | 1.0 | 1000 |
| Full RAG Pipeline | 50.0 | - |

## Usage

### Python API

```python
from tests.benchmarks.benchmark_base import BenchmarkRunner, assert_performance

# Create runner
runner = BenchmarkRunner(
    warmup_iterations=3,
    default_iterations=10,
    regression_threshold_percent=20.0
)

# Run sync benchmark
result = runner.run_benchmark(
    name="my_benchmark",
    func=lambda: expensive_operation(),
    iterations=20,
    metadata={"test": "data"}
)

# Run async benchmark
result = await runner.run_async_benchmark(
    name="async_benchmark",
    func=async_operation,
    iterations=15
)

# Assert performance requirements
assert_performance(
    result,
    max_avg_ms=100,
    max_p95_ms=200,
    min_ops_per_second=50
)

# Save results
runner.save_results(Path("results.json"))

# Generate report
print(runner.generate_report())
```

### Custom Benchmarks

```python
import pytest
from tests.benchmarks.benchmark_base import BenchmarkRunner

class TestMyBenchmarks:
    @pytest.fixture
    def runner(self):
        return BenchmarkRunner()

    def test_custom_operation(self, runner):
        """Benchmark custom operation"""

        def my_operation():
            # Your code here
            result = complex_calculation()
            return result

        result = runner.run_benchmark(
            name="custom_operation",
            func=my_operation,
            iterations=50,
            metadata={"description": "Custom operation"}
        )

        print(f"Avg: {result.avg_time_ms:.2f}ms")
        print(f"Ops/sec: {result.ops_per_second:.2f}")

        assert result.passed
        assert result.avg_time_ms < 100  # Custom threshold
```

### Regression Detection

```python
from pathlib import Path
from tests.benchmarks.benchmark_base import BenchmarkRunner

runner = BenchmarkRunner(regression_threshold_percent=20.0)

# Load baseline
runner.load_baselines(Path("baseline_results.json"))

# Run current benchmarks
result = runner.run_benchmark("api_health", ...)

# Check for regression
regression = runner.check_regression(result)
if regression and regression.is_regression:
    print(f"REGRESSION DETECTED: {regression.regression_percent:.1f}%")
    print(f"Baseline: {regression.baseline_avg_ms:.2f}ms")
    print(f"Current: {regression.current_avg_ms:.2f}ms")
```

## Result Storage

### Directory Structure

```
reports/benchmarks/
├── benchmark_results_20251116_143000.json
├── benchmark_results_20251116_160000.json
├── baseline.json  (optional baseline)
└── ...
```

### Result Format

```json
{
  "timestamp": "2025-11-16T14:30:00",
  "total_benchmarks": 15,
  "passed": 14,
  "failed": 1,
  "results": [
    {
      "name": "api_health_endpoint",
      "iterations": 20,
      "total_time_ms": 180.5,
      "avg_time_ms": 9.025,
      "min_time_ms": 8.2,
      "max_time_ms": 12.1,
      "median_time_ms": 9.0,
      "std_dev_ms": 0.85,
      "p95_time_ms": 10.5,
      "p99_time_ms": 11.8,
      "ops_per_second": 110.8,
      "timestamp": "2025-11-16T14:30:05",
      "metadata": {"endpoint": "/api/health"},
      "passed": true,
      "error": null
    }
  ]
}
```

## Pytest Integration

### Running with Pytest

```bash
# All benchmarks
python -m pytest tests/benchmarks/ -v

# Specific test
python -m pytest tests/benchmarks/api_benchmarks.py::TestAPIEndpointBenchmarks::test_health_endpoint_benchmark -v

# With output capture disabled (see print statements)
python -m pytest tests/benchmarks/ -s
```

### Markers

```python
import pytest
from tests.benchmarks.benchmark_base import benchmark_test

@benchmark_test
def test_performance():
    # Benchmark test
    pass
```

## Performance Assertions

### Built-in Assertions

```python
from tests.benchmarks.benchmark_base import assert_performance

# Assert multiple thresholds
assert_performance(
    result,
    max_avg_ms=100,       # Average must be < 100ms
    max_p95_ms=200,       # P95 must be < 200ms
    max_p99_ms=300,       # P99 must be < 300ms
    min_ops_per_second=10 # At least 10 ops/sec
)
```

### Custom Assertions

```python
def assert_latency_budget(result, budget_ms):
    """Ensure total latency is within budget"""
    if result.total_time_ms > budget_ms:
        raise AssertionError(f"Total time {result.total_time_ms}ms exceeds budget {budget_ms}ms")

def assert_consistency(result, max_std_dev_percent):
    """Ensure consistent performance"""
    std_percent = (result.std_dev_ms / result.avg_time_ms) * 100
    if std_percent > max_std_dev_percent:
        raise AssertionError(f"Standard deviation {std_percent:.1f}% exceeds max {max_std_dev_percent}%")
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Performance Benchmarks

on:
  push:
    branches: [main]
  pull_request:

jobs:
  benchmark:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run benchmarks
        run: bash scripts/run_benchmarks.sh --all

      - name: Upload results
        uses: actions/upload-artifact@v3
        with:
          name: benchmark-results
          path: reports/benchmarks/
```

## Best Practices

### Writing Benchmarks

1. **Isolate the Operation** - Benchmark only the target operation
2. **Warmup Runs** - Always include warmup iterations
3. **Sufficient Iterations** - Use enough iterations for statistical significance
4. **Control Environment** - Minimize system noise during benchmarks
5. **Document Expectations** - Clearly state performance requirements

### Avoiding Common Pitfalls

```python
# BAD: Setup included in timing
def test_bad():
    def benchmark():
        data = load_large_file()  # Don't include setup
        process(data)

# GOOD: Separate setup
def test_good():
    data = load_large_file()  # Setup before

    def benchmark():
        process(data)  # Only time the operation
```

### Performance Monitoring

1. Run benchmarks regularly (daily/weekly)
2. Compare against baselines
3. Track trends over time
4. Investigate regressions immediately
5. Document performance improvements

## Troubleshooting

### Issue: High Variance in Results

**Symptoms:** Large standard deviation, inconsistent times

**Solutions:**
- Increase warmup iterations
- Close other applications
- Run on dedicated hardware
- Use more iterations
- Check for GC pauses (Python)

### Issue: Benchmark Failures

**Symptoms:** Tests fail but code works

**Solutions:**
- Check threshold values (may be too strict)
- Verify test environment
- Check for resource constraints
- Review mock implementations

### Issue: Missing Dependencies

**Error:** `ModuleNotFoundError: No module named 'numpy'`

**Solution:**
```bash
pip install numpy pytest httpx
```

## Future Enhancements

1. **Database Benchmarks** - SQLite, Redis query performance
2. **LLM Inference Benchmarks** - Actual model inference timing
3. **Load Testing** - Concurrent user simulation
4. **Memory Profiling** - Track memory usage over time
5. **Visualization Dashboard** - Grafana/Prometheus integration
6. **Historical Trending** - Track performance over releases

## Related Documentation

- [Code Quality Enforcement](../developer/CODE_QUALITY_ENFORCEMENT.md)
- [Testing Guide](TESTING_GUIDE.md)
- [OpenVINO Performance](../developer/OPENVINO_SETUP.md)
- [API Documentation](../api/COMPREHENSIVE_API_DOCUMENTATION.md)

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2025-11-16 | Initial benchmarking suite (Issue #58) |

## References

- **GitHub Issue:** #58 - Performance Benchmarking Suite
- **Framework:** `tests/benchmarks/benchmark_base.py`
- **API Benchmarks:** `tests/benchmarks/api_benchmarks.py`
- **RAG Benchmarks:** `tests/benchmarks/rag_benchmarks.py`
- **Runner Script:** `scripts/run_benchmarks.sh`
